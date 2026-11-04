"""Both observed packings, quiet calibration, and complete stereo segments."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_frontend import AudioProfileError, StereoFrontEnd, identify_profile
from asr_adapter import gui_splitter


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class AudioFrontEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime = ROOT/'asr_runtime'
        cls.audio = module('frontend_test_audio', runtime/'board_audio.py')
        with patch.dict(sys.modules, board_audio=cls.audio):
            cls.mic = module('frontend_test_mic', runtime/'board_mic.py')
        with patch.dict(sys.modules, board_audio=cls.audio, board_mic=cls.mic):
            cls.listen = module('frontend_test_listen', runtime/'board_listen.py')

    def setUp(self):
        self.random = np.random.RandomState(13)

    def encode(self, pair, layout):
        words = np.rint(np.clip(pair, -.99, .99)*8388608).astype(np.int32).astype(np.uint32)&0xffffff
        octets = np.frombuffer(words.astype('<u4').tobytes(), np.uint8).reshape(-1, 2, 4)
        if layout == 'msb-first':
            octets = octets[:, :, [2, 1, 0, 3]]
        return octets.copy().tobytes()

    def quiet(self, layout='little', scale=(.0015, .002)):
        return [self.encode(self.random.normal(size=(882, 2))*scale, layout) for _ in range(50)]

    def frontend(self, layout='little', scale=(.0015, .002)):
        args = SimpleNamespace(speech_threshold=.01, end_silence=.8, max_utterance=12.)
        result = StereoFrontEnd(self.mic._decode_s24le,
                               gui_splitter(self.listen.UtteranceSplitter, args))
        for frame in self.quiet(layout, scale):
            self.assertIsNone(result.feed(frame))
        self.assertTrue(result.profile_ready.is_set())
        return result

    def test_both_observed_layouts_are_identified_from_bytes(self):
        for layout in ('little', 'msb-first'):
            with self.subTest(layout=layout):
                front = self.frontend(layout)
                self.assertEqual(front.profile['byte_order'], layout)
                self.assertEqual(front.frames_seen, 0)  # Quiet self-test is not a command.

    def test_zero_input_stays_ambiguous_and_fails_without_ready(self):
        args = SimpleNamespace(speech_threshold=.01, end_silence=.8, max_utterance=12.)
        front = StereoFrontEnd(self.mic._decode_s24le, gui_splitter(self.listen.UtteranceSplitter, args))
        for _ in range(249):
            self.assertIsNone(front.feed(bytes(7056)))
        with self.assertRaises(AudioProfileError):
            front.feed(bytes(7056))
        self.assertFalse(front.profile_ready.is_set())

    def test_left_justified_or_random_data_is_not_chosen_for_small_rms(self):
        normal = np.frombuffer(b''.join(self.quiet()), np.uint8).reshape(-1, 2, 4).copy()
        normal[:, :, 0] = 0  # Both ends now look like sign extension.
        for raw in (normal.tobytes(), self.random.randint(0, 256, size=7056*50).astype(np.uint8).tobytes()):
            with self.assertRaises(AudioProfileError):
                identify_profile(raw, self.mic._decode_s24le)

    def test_malformed_and_short_windows_are_rejected(self):
        for raw in (b'', b'123', bytes(7056*2)):
            with self.assertRaises(AudioProfileError):
                identify_profile(raw, self.mic._decode_s24le)

    def test_better_channel_is_selected_once_and_samples_are_preserved(self):
        wave = np.sin(np.arange(882)*2*np.pi*440/44100)
        for layout in ('little', 'msb-first'):
            for channel in (0, 1):
                with self.subTest(layout=layout, channel=channel):
                    front = self.frontend(layout)
                    raw_frames = self.quiet(layout)[:20]
                    pair = np.column_stack((wave*.004, wave*.004))
                    pair[:, channel] = wave*.04
                    raw_frames += [self.encode(pair, layout)]*35+self.quiet(layout)
                    segments = []
                    for raw in raw_frames:
                        value = front.feed(raw)
                        if value is not None:
                            segments.append(value)
                    self.assertEqual(len(segments), 1)
                    audio, metadata = segments[0]
                    self.assertEqual(metadata['selected_channel'], channel)
                    start, end = metadata['stream_start_sample'], metadata['stream_end_sample']
                    original = self.mic._decode_s24le(b''.join(raw_frames), 2, channel=channel, byte_order=layout)
                    np.testing.assert_array_equal(audio, original[start:end])

    def test_higher_background_channel_uses_its_measured_floor(self):
        front = self.frontend(scale=(.012, .0015))
        self.assertGreater(front.profile['thresholds'][0], .02)
        self.assertEqual(front.profile['thresholds'][1], .01)
        for raw in self.quiet(scale=(.012, .0015))*3:
            self.assertIsNone(front.feed(raw))
        self.assertEqual(front.splitter.rejected, 0)

    def test_mid_stream_packing_change_stops_instead_of_decoding_noise(self):
        front = self.frontend('little')
        with self.assertRaisesRegex(AudioProfileError, '采样排列改变'):
            for raw in self.quiet('msb-first'):
                front.feed(raw)

    def test_same_layout_continues_across_health_windows(self):
        front = self.frontend()
        for raw in self.quiet()*3:
            self.assertIsNone(front.feed(raw))
        self.assertEqual(front.splitter.rejected, 0)

    def test_incomplete_live_frame_is_rejected(self):
        front = self.frontend()
        with self.assertRaises(AudioProfileError):
            front.feed(bytes(7055))


if __name__ == '__main__':
    unittest.main()
