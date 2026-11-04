import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'asr_runtime')]
from sweep_response import measure_pairs, make_plot_data
from fft_protocol import write_json
from record_store import RecordStore
from test_generator_control import success, PHRASE
from text_cli import parse_command


class SweepTests(unittest.TestCase):
    def test_real_query_values_and_time_brackets_not_sweep_interpolation(self):
        ticks = [0.]
        calls = []
        class IO:
            def query(self, q):
                calls.append(q)
                ticks[0] += .02
                return 'C1:PAVA FREQ,1234Hz' if q.endswith('FREQ') else 'C1:PAVA PKPK,0.42V'
        rows = measure_pairs(IO(), .1, 0, clock=lambda:ticks[0], wait=lambda t:ticks.__setitem__(0,ticks[0]+t))
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[0]['frequency_hz'],1234)
        self.assertEqual(rows[0]['vpp_v'],.42)
        self.assertAlmostEqual(rows[0]['pair_span_s'],.04)
        self.assertEqual(calls[:2],['C1:PAVA? FREQ','C1:PAVA? PKPK'])

    def test_timeout_aborts_without_consuming_a_late_reply_as_next_pair(self):
        class IO:
            def query(self,q): raise OSError('USB timeout')
        rows=measure_pairs(IO(),1,0,clock=lambda:0,wait=lambda t:None)
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['valid'])

    def test_out_of_range_and_single_frequency_cannot_make_fake_curve(self):
        config=dict(start_hz=100,stop_hz=10000,started_at='now')
        with self.assertRaises(ValueError):
            make_plot_data([dict(valid=True,frequency_hz=100000,vpp_v=1)],config)
        points=[dict(valid=True,frequency_hz=500,vpp_v=.8),dict(valid=False),
                dict(valid=True,frequency_hz=200,vpp_v=.2)]
        data=make_plot_data(points,config)
        self.assertEqual(data['frequencies_hz'],[200,500])
        self.assertEqual(data['amplitudes_vpeak'],[.2,.8])

    def test_background_result_appears_in_same_history_after_refresh_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            store=RecordStore(ROOT/'asr_runtime',root/'records')
            folder=root/'records/sweep_responses/task'
            folder.mkdir(parents=True)
            command=parse_command(PHRASE.replace('配置扫频','开始扫频'))
            raw=success(command['request'])
            raw['response_capture']=dict(directory=str(folder),status='collecting')
            value=dict(text='开始扫频',simulated=False,command=command)
            row=store.save_generator_result(value,'one',raw)
            self.assertEqual(row['image_path'],'')
            (folder/'response.png').write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            write_json(folder/'result.json',dict(status='complete',point_count=10))
            again=RecordStore(ROOT/'asr_runtime',root/'records').list_page()['rows'][0]
            self.assertEqual(again['record_id'],row['record_id'])
            self.assertEqual(again['image_kind'],'sweep_response')
            self.assertEqual(again['status'],'曲线完成')
            self.assertEqual(again['image_path'],str(folder/'response.png'))
            self.assertEqual(store.save_generator_result(value,'one',raw)['record_id'],row['record_id'])

    def test_generator_starts_observer_before_output_without_changing_sweep(self):
        from generator_runner import execute_job
        from test_generator_control import Driver, BOARD
        with tempfile.TemporaryDirectory() as tmp:
            observer=dict(directory=tmp,status='armed')
            d=Driver()
            with patch('sweep_response.start_observer',return_value=observer) as start, patch('sweep_response.mark_start') as mark:
                raw=execute_job(dict(request=parse_command(PHRASE)['request'],enable=True,response_capture={}),BOARD,d)
                self.assertTrue(raw['valid'])
                self.assertEqual(start.call_count,0)
                raw=execute_job(dict(request=parse_command(PHRASE)['request'],enable=True,response_capture=dict(directory=tmp)),BOARD,d)
                self.assertTrue(raw['valid'])
                self.assertEqual(start.call_count,1)
                mark.assert_called_once_with(observer)
                self.assertEqual([r['action'] for r in d.calls],['sweep','output','sweep','output'])
