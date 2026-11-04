"""Exercise real PCM decoding and endpoint detection without audio devices."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    import numpy as np
except ImportError:
    raise unittest.SkipTest('PCM regression requires NumPy')

RUNTIME = Path(__file__).resolve().parents[1] / 'asr_runtime'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifiedPcmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        audio = load('verified_board_audio', RUNTIME / 'board_audio.py')
        with patch.dict(sys.modules, board_audio=audio):
            cls.mic = load('verified_board_mic', RUNTIME / 'board_mic.py')
        with patch.dict(sys.modules, board_audio=audio, board_mic=cls.mic):
            cls.listen = load('verified_board_listen', RUNTIME / 'board_listen.py')

    def native_frame(self, amplitude):
        signal = np.sin(np.arange(882) * (2 * np.pi * 440 / 44100)) * amplitude
        values = np.rint(signal * 8388608).astype(np.int32).astype(np.uint32) & 0xffffff
        return np.repeat(values, 2).astype('<u4').tobytes()

    def test_quiet_speech_quiet_produces_one_utterance_with_original_gate(self):
        quiet = self.native_frame(0.004)
        speech = self.native_frame(0.12)
        wrong = self.mic._decode_s24le(quiet, 2, byte_order='msb-first')
        self.assertGreater(float(np.std(wrong)), 0.01)
        args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8,
                               max_utterance=12.0, mic_channel=0,
                               audio_device='hw:0,1')
        microphone = self.listen.ContinuousMicrophone(args)
        chunks = iter([quiet] * 150 + [quiet] * 50 + [speech] * 100 + [quiet] * 60)

        def read(size):
            self.assertEqual(size, 7056)
            try:
                return next(chunks)
            except StopIteration:
                microphone.stop.set()
                return b''

        microphone.recording = SimpleNamespace(stdout=SimpleNamespace(read=read))
        microphone.check_devices = lambda: None
        microphone.es8388 = {'available': True, 'errors': []}
        microphone.ready.set()
        microphone._read()
        self.assertIsNone(microphone.error)
        self.assertEqual(microphone.utterances.qsize(), 1)
        converted, metadata, ended = microphone.utterances.get_nowait()
        self.assertEqual(metadata['pcm_layout'], 's24-le-low24-in-4')
        self.assertEqual(metadata['speech_threshold'], 0.01)
        self.assertEqual(metadata['end_silence_seconds'], 0.8)
        self.assertAlmostEqual(metadata['duration_seconds'], 3.1)
        self.assertEqual(len(converted), 49600)
        self.assertGreater(float(np.max(np.abs(converted))), 0.10)
        self.assertEqual(microphone.splitter.rejected, 0)

    def test_gui_endpoint_ignores_weak_bursts_without_changing_clean_audio(self):
        from asr_adapter import gui_splitter
        args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8, max_utterance=12.0)
        def frame(amplitude):
            return np.sin(np.arange(882)*(2*np.pi*440/44100)).astype(np.float32)*amplitude
        quiet, speech, weak = frame(0.004), frame(0.12), frame(0.018)
        original = self.listen.UtteranceSplitter()
        improved = gui_splitter(self.listen.UtteranceSplitter, args)
        old_segments, new_segments = [], []
        frames = [quiet]*50 + [speech]*25 + [weak if i % 10 == 5 else quiet for i in range(110)]
        for value in frames:
            old = original.accept(value)
            new = improved.accept(value)
            if old is not None: old_segments.append(old)
            if new is not None: new_segments.append(new)
        self.assertEqual(old_segments, [])
        self.assertEqual(len(new_segments), 1)
        self.assertLess(len(new_segments[0][0])/44100, 2.0)
        # A clean short "确认" keeps identical samples and capture boundaries.
        original = self.listen.UtteranceSplitter()
        improved = gui_splitter(self.listen.UtteranceSplitter, args)
        for value in [quiet]*50 + [speech]*10 + [quiet]*40:
            old = original.accept(value)
            new = improved.accept(value)
        self.assertIsNotNone(old)
        self.assertIsNotNone(new)
        np.testing.assert_array_equal(old[0], new[0])
        self.assertEqual(old[1:], new[1:])

    def test_gui_endpoint_does_not_split_a_sentence_at_short_pauses(self):
        from asr_adapter import gui_splitter
        args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8, max_utterance=12.0)
        quiet = np.zeros(882, dtype=np.float32)
        speech = np.sin(np.arange(882)*(2*np.pi*440/44100)).astype(np.float32)*0.12
        splitter = gui_splitter(self.listen.UtteranceSplitter, args)
        for value in [quiet]*50 + [speech]*15 + [quiet]*30 + [speech]*15:
            self.assertIsNone(splitter.accept(value))
        results = [splitter.accept(quiet) for _ in range(40)]
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_gui_endpoint_recovers_from_overlong_noise(self):
        from asr_adapter import gui_splitter
        args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8, max_utterance=12.0)
        wave = np.sin(np.arange(882)*(2*np.pi*440/44100)).astype(np.float32)
        splitter = gui_splitter(self.listen.UtteranceSplitter, args)
        for _ in range(610):splitter.accept(wave*0.12)
        self.assertTrue(splitter.discarding)
        for i in range(110):splitter.accept(wave*(0.018 if i % 10 == 5 else 0.004))
        self.assertFalse(splitter.discarding)
        self.assertEqual(splitter.rejected, 1)


if __name__ == '__main__':
    unittest.main()
