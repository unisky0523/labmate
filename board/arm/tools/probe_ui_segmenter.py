"""Manual board probe: original continuous microphone, no model or GUI.

Run only after closing the assistant and other audio tests. The observer wraps
the splitter only in this Python process and preserves its original decisions.
No source, capture parameters, audio files or experiment records are written.
"""
import queue
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path('/home/root/labmate_ui_test/asr_runtime')))
import board_listen


def main():
    levels = []
    original = board_listen.UtteranceSplitter.accept

    def observe(self, frame):
        centered = frame - np.mean(frame)
        levels.append(float(np.sqrt(np.mean(centered * centered))))
        return original(self, frame)

    args = SimpleNamespace(speech_threshold=0.01, end_silence=0.8,
                           max_utterance=12.0, playback_device='default',
                           audio_device='hw:0,1', mic_channel=0,
                           no_es8388_init=False)
    board_listen.UtteranceSplitter.accept = observe
    try:
        print('INITIALIZING original microphone...', flush=True)
        with board_listen.ContinuousMicrophone(args) as mic:
            for label, seconds in [('QUIET_1', 4), ('SPEAK', 4), ('QUIET_2', 3)]:
                start = len(levels)
                print(label, seconds, 'seconds', flush=True)
                time.sleep(seconds)
                if mic.error is not None:
                    raise RuntimeError(str(mic.error))
                values = np.asarray(levels[start:])
                if not len(values):
                    print(label, 'NO_FRAMES', flush=True)
                    continue
                print('%s frames=%d above_0.01=%d median=%.6f max=%.6f' % (
                    label, len(values), np.count_nonzero(values >= 0.01),
                    np.median(values), np.max(values)), flush=True)
            complete = 0
            while True:
                try:
                    audio, metadata, ended = mic.utterances.get_nowait()
                except queue.Empty:
                    break
                complete += 1
                print('UTTERANCE seconds=%.2f' % metadata['duration_seconds'], flush=True)
            print('SUMMARY utterances=%d rejected=%d dropped=%d' % (
                complete, mic.splitter.rejected, mic.dropped), flush=True)
    finally:
        board_listen.UtteranceSplitter.accept = original
    print('AUDIO_CLOSED', flush=True)


if __name__ == '__main__':
    main()
