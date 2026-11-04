"""Numeric, binary acquisition, cancellation and durable spectrum-history contracts."""
import copy
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1]/'tools'))
from fft_protocol import make_request, read_json, write_json, digest, decode_response, hann_q15
from fft_control import FFTControl
from fft_reference import reference
from record_store import RecordStore
from scope_waveform import binary_block, quantity, capture


class BinaryTests(unittest.TestCase):
    def test_units_are_case_sensitive_for_metric_prefixes(self):
        for text, unit, expected in [('SARA 1.00GSa/s','Sa/s',1e9), ('TDIV 2.00mS','S',.002),
                                     ('C1:VDIV 3.00E-01V','V',.3), ('C1:OFST -500mV','V',-.5)]:
            self.assertAlmostEqual(quantity(text, unit), expected)
        with self.assertRaises(ValueError):
            quantity('garbage', 'V')

    def test_binary_newlines_and_zero_bytes_are_samples(self):
        payload = bytes(range(256))*2
        for prefix in (b'', b'C1:WF DAT2,', b'C1:WF DAT2'):
            reply = prefix+b'#9000000512'+payload+b'\n\n'
            self.assertEqual(binary_block(reply, 1), payload)

    def test_channel_short_block_and_extra_bytes_rejected(self):
        for data in (b'C2:WF DAT2,#9000000256'+bytes(256), b'#9000000512'+bytes(256),
                     b'#9000000256'+bytes(256)+b'junk', b'#0'+bytes(256)):
            with self.assertRaises(ValueError):
                binary_block(data, 1)

    def test_legacy_all_requires_opt_in_and_rejects_descriptors(self):
        raw = b'C1:WF ALL,#9000000512'+bytes(range(256))*2+b'\n\n'
        with self.assertRaises(ValueError):
            binary_block(raw, 1)
        self.assertEqual(len(binary_block(raw, 1, allow_legacy_all=True)), 512)
        with self.assertRaises(ValueError):
            binary_block(raw.replace(bytes(range(8)), b'WAVEDESC', 1), 1, allow_legacy_all=True)

    def test_fft_phrase_aliases(self):
        sys.path.insert(0, str(ROOT/'asr_runtime'))
        from text_cli import parse_command
        for phrase in ('FFT分析', '频谱分析', '分析波形', '请帮我频谱分析'):
            self.assertEqual(parse_command(phrase)['intent'], 'fft_analyze')


class FFTTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.jobs = self.base/'jobs'
        self.store = RecordStore(ROOT/'asr_runtime', self.base/'records')
        self.control = FFTControl(dict(fft_size=4096), dict(root='/scope', resource='USB::scope'), self.store, self.jobs)
        self.directory = self.control.job_path('frame-1')
        self.directory.mkdir(parents=True)
        n = 4096
        raw = bytes((int(round(20*math.sin(2*math.pi*40*k/n)))+8)%256 for k in range(n))
        (self.directory/'scope_codes.i8').write_bytes(raw)
        self.capture = dict(raw_path=str(self.directory/'scope_codes.i8'), raw_sha256=digest(raw),
                            sample_count=n, sample_interval_s=1e-5, volts_per_code=.04,
                            volts_offset=-.5, channel=1, captured_at='2026-11-03T12:00:00+08:00')
        write_json(self.directory/'capture.json', self.capture)
        write_json(self.directory/'scope_evidence.json', dict(commands=[]))
        self.request = make_request(self.directory, 'frame-1', self.capture, n)
        self.value = dict(text='频谱分析', command=dict(intent='fft_analyze'), simulated=False)

    def tearDown(self):
        self.temp.cleanup()

    def make_result(self):
        folder = self.base/'reference'
        s = reference(self.directory/'request.json', folder)
        response = read_json(folder/'response.json')
        # Deliberately injected hardware fixture, never sent to the real UI.
        response['backend'] = 'fpga'
        shutil.copyfile(str(folder/'power.u64le'), str(self.directory/'power.u64le'))
        write_json(self.directory/'response.json', response)
        return response, s

    def test_coherent_sine_frequency_amplitude_and_window(self):
        response, _ = self.make_result()
        result = decode_response(self.request, response, self.directory)
        self.assertEqual(result['peak_bin'], 40)
        self.assertAlmostEqual(result['peak_frequency_hz'], 976.5625)
        self.assertAlmostEqual(result['peak_amplitude_vpeak'], .8, delta=.006)
        self.assertEqual(hann_q15(4096)[2048], 32767)

    def test_mismatched_frame_scale_overflow_and_reference_rejected(self):
        response, _ = self.make_result()
        for key, value in [('request_id','old'), ('input_sha256','bad'), ('fft_size',1024),
                            ('overflow',True), ('backend','software_reference'),
                            ('fft_right_shift',-1), ('power_right_shift',True), ('power_file','../power.u64le')]:
            raw = dict(response, **{key:value})
            with self.assertRaises(ValueError, msg=key):
                decode_response(self.request, raw, self.directory)

    def test_input_corruption_detected(self):
        response, _ = self.make_result()
        (self.directory/'input.i16le').write_bytes(bytes(8192))
        with self.assertRaises(ValueError):
            decode_response(self.request, response, self.directory)

    def test_power_checksum_and_length_detected(self):
        response, _ = self.make_result()
        (self.directory/'power.u64le').write_bytes(bytes(8))
        with self.assertRaises(ValueError):
            decode_response(self.request, response, self.directory)

    def test_single_sided_dc_and_nyquist_not_doubled(self):
        response, _ = self.make_result()
        powers = [0]*2049
        powers[0] = powers[1] = powers[-1] = 10000
        blob = struct.pack('<2049Q', *powers)
        (self.directory/'power.u64le').write_bytes(blob)
        response['power_sha256'] = digest(blob)
        result = decode_response(self.request, response, self.directory)
        a = result['amplitudes_vpeak']
        self.assertEqual(a[1], 2*a[0])
        self.assertEqual(a[-1], a[0])

    def test_numeric_scale_restoration(self):
        response, _ = self.make_result()
        original = decode_response(self.request, response, self.directory)['peak_amplitude_vpeak']
        response.update(fft_right_shift=2, power_right_shift=2)
        self.assertAlmostEqual(decode_response(self.request, response, self.directory)['peak_amplitude_vpeak'], original*8)

    def test_unconnected_fpga_is_pending_and_saved_without_fake_spectrum(self):
        value = self.control.preview(self.value, 'frame-1', threading.Event())
        self.assertFalse(value['fft_result']['valid'])
        self.assertEqual(value['spectrum_image_path'], '')
        row = self.control.save(value, 'frame-1')
        self.assertEqual(row['status'], '待 FPGA')
        self.assertEqual(row['image_path'], '')
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_spectrum_is_copied_and_survives_job_deletion_restart_and_save_retry(self):
        self.make_result()
        def renderer(executable, source, target):
            Path(target).write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        self.control.renderer = renderer
        value = self.control.preview(self.value, 'frame-1', threading.Event())
        row = self.control.save(value, 'frame-1')
        self.assertEqual(row['image_kind'], 'spectrum')
        self.assertEqual(self.control.save(value, 'frame-1')['record_id'], row['record_id'])
        self.assertEqual(self.store.list_page()['total'], 1)
        image = Path(row['image_path'])
        self.assertTrue(image.is_file())
        shutil.rmtree(str(self.jobs))
        store = RecordStore(ROOT/'asr_runtime', self.base/'records')
        self.assertEqual(store.list_page()['rows'][0]['image_path'], str(image))
        self.assertTrue(image.is_file())

    def test_cancellation_does_not_submit_worker_or_save(self):
        token = threading.Event()
        token.set()
        self.assertIsNone(self.control.preview(self.value, 'frame-1', token))
        self.assertEqual(self.store.list_page()['total'], 0)

    def test_damaged_cached_request_cannot_be_submitted(self):
        request = dict(self.request, request_id='old-frame')
        write_json(self.directory/'request.json', request)
        with self.assertRaises(ValueError):
            self.control.preview(self.value, 'frame-1', threading.Event())


class RestoreTests(unittest.TestCase):
    def test_transfer_failure_still_restores_original_trigger_and_setup(self):
        commands = []
        class IO:
            @property
            def device(self): return self
            def write(self, text): commands.append(text)
            def query(self, text):
                if text == '*IDN?': return 'SIGLENT,SDS1202X,SDS1XDC4163410,1.1'
                if text == 'TRMD?': return 'TRMD STOP' if commands and 'TRMD AUTO' not in commands else 'TRMD AUTO'
                return {'WFSU?':'WFSU SP,0,NP,0,FP,0', 'SARA?':'SARA 1GSa/s', 'TDIV?':'TDIV 1mS',
                        'C1:VDIV?':'C1:VDIV 1V', 'C1:OFST?':'C1:OFST 0V'}[text]
            def query_raw(self, text): raise RuntimeError('USB disconnected')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError):
                capture(IO(), 'USB::scope', folder)
        self.assertEqual(commands[-2:], ['WFSU SP,0,NP,0,FP,0', 'TRMD AUTO'])


if __name__ == '__main__':
    unittest.main()
