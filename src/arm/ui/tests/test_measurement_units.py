"""Manual unit parsing, quantity-aware ASR review and actual history schema."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'asr_runtime'))
import text_cli as parser
import asr_cli as asr
import asr_grammar as grammar
from record_store import RecordStore


def measurement(phrase):
    result = parser.parse_command(phrase)
    assert result['intent'] == 'record_manual'
    return result['measurements']


class UnitParserTests(unittest.TestCase):
    def test_each_quantity_and_prefix_in_spoken_and_symbolic_units(self):
        for name, key, base, symbol in [('电压', 'voltage', '伏', 'V'),
                                       ('电流', 'current', '安', 'A'),
                                       ('频率', 'frequency', '赫兹', 'Hz')]:
            for chinese, prefix in [('', ''), ('毫', 'm'), ('微', 'u'), ('纳', 'n'),
                                    ('皮', 'p'), ('千', 'k'), ('兆', 'M')]:
                for phrase in ['记录%s一点二%s%s' % (name, chinese, base),
                               '记录%s1.20%s%s' % (name, prefix, symbol)]:
                    with self.subTest(phrase=phrase):
                        item, = measurement(phrase)
                        self.assertEqual((item['quantity'], Decimal(item['value']), item['unit']),
                                         (key, Decimal('1.2'), prefix+symbol))
                        self.assertFalse(item['unit_inferred'])

    def test_milli_mega_and_micro_symbols_remain_distinct(self):
        for unit, expected in [('mA', 'mA'), ('ma', 'mA'), ('MA', 'MA'),
                               ('μA', 'uA'), ('µA', 'uA'), ('uA', 'uA')]:
            self.assertEqual(measurement('记录电流1'+unit)[0]['unit'], expected)
        self.assertEqual(measurement('记录频率1mHz')[0]['unit'], 'mHz')
        self.assertEqual(measurement('记录频率1MHz')[0]['unit'], 'MHz')
        self.assertEqual(measurement('记录频率1kHz')[0]['unit'], 'kHz')
        self.assertEqual(measurement('记录电压0.000mV')[0]['value'], '0.000')

    def test_standalone_and_all_three_quantities(self):
        for phrase in ['电压三点三伏', '电流一毫安', '频率一兆赫兹', '记录一下频率一千赫兹']:
            self.assertEqual(len(measurement(phrase)), 1)
        items = measurement('记录电压三点三伏，电流一毫安，频率一千赫兹')
        self.assertEqual([m['quantity'] for m in items], ['voltage','current','frequency'])
        self.assertEqual([m['unit'] for m in items], ['V','mA','kHz'])

    def test_kilo_suffix_and_integer_thousands_are_both_preserved(self):
        self.assertEqual(measurement('记录频率三千赫兹')[0]['value'], '3')
        self.assertEqual(measurement('记录频率三千赫兹')[0]['unit'], 'kHz')
        self.assertEqual(measurement('记录频率三千零一赫兹')[0]['value'], '3001')
        self.assertEqual(measurement('记录频率三千零一赫兹')[0]['unit'], 'Hz')

    def test_missing_unit_wrong_dimension_and_duplicate_quantity_are_rejected(self):
        for phrase in ['记录电流一', '记录电流一毫', '记录频率一千', '记录电压一安',
                       '记录频率一毫安', '记录电流一兆赫兹', '记录电压三伏电压四伏',
                       '记录电流一毫安然后拍照', '记录电流1MAA']:
            with self.subTest(phrase=phrase), self.assertRaises(ValueError):
                parser.parse_command(phrase)

    def test_english_command_aliases_are_still_case_insensitive(self):
        for text, intent in [('READ','read'),('HELP','help'),('OK','confirm'),('NO','cancel')]:
            self.assertEqual(parser.parse_command(text)['intent'],intent)

    def test_model_homophone_is_restored_only_in_measurement_units(self):
        self.assertEqual(measurement('记录 电流 一 豪 安')[0]['unit'],'mA')
        self.assertEqual(measurement('频率 一 豪 赫 兹')[0]['unit'],'mHz')
        self.assertEqual(parser.normalize_asr_text('豪华实验室'),'豪华实验室')
        self.assertEqual(parser.normalize_asr_text('记录电流一豪安'),'记录电流一毫安')


class UnitHistoryTests(unittest.TestCase):
    def test_single_quantities_and_three_together_survive_saving_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecordStore(ROOT/'asr_runtime', directory)
            for index, phrase in enumerate(['记录电压三微伏','记录电流一毫安','记录频率一兆赫兹',
                                           '记录电压三伏电流二纳安频率一千赫兹']):
                row = store.save_result(dict(text=phrase, command=parser.parse_command(phrase),
                                             simulated=False, reason=None), 'unit-record-'+str(index))
                self.assertEqual(row['source'],'语音报数')
            reopened = RecordStore(ROOT/'asr_runtime', directory)
            rows = reopened.list_page(size=6)['rows']
            self.assertEqual(len(rows),4)
            self.assertTrue(any('电流 1 mA' in r['content'] for r in rows))
            self.assertTrue(any('频率 1 MHz' in r['content'] for r in rows))
            self.assertTrue(any('电流 2 nA' in r['content'] and '频率 1 kHz' in r['content'] for r in rows))

    def test_schema_rejects_wrong_unit_dimension_for_saved_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RecordStore(ROOT/'asr_runtime',directory)
            with self.assertRaises(ValueError):
                store.save_result(dict(text='bad',simulated=False,reason=None,
                    command=dict(intent='record_manual',measurements=[
                        dict(quantity='current',value='1',unit='kHz')])), 'bad')
            self.assertEqual(store.list_page()['total'],0)


def transcript(text, confidence=.95):
    return dict(text=text, words=[dict(word=text,conf=confidence)], segments=[], timings_ms=dict(total_ms=1))


class UnitContextTests(unittest.TestCase):
    def analyze(self, *transcripts):
        with patch.object(asr,'transcribe',side_effect=transcripts) as decode, \
             patch.object(asr,'audio_problem',return_value=None):
            result = asr.analyze(np.ones(3200,dtype=np.float32)*.03, object(), {}, .45,
                                 grammar=grammar.GRAMMAR_JSON,command_grammar=True,unit_context=True)
        return result, decode

    def test_current_unit_is_reviewed_with_current_only_grammar_on_same_audio(self):
        result, decode = self.analyze(transcript('记录电流一毫安'),transcript('电流一毫安'))
        self.assertIsNone(result['reason'])
        self.assertEqual(result['command']['measurements'][0]['unit'],'mA')
        self.assertEqual(result['unit_context'],'电流')
        self.assertEqual(decode.call_count,2)
        self.assertIs(decode.call_args_list[0].args[0],decode.call_args_list[1].args[0])
        focused = decode.call_args_list[1].kwargs['grammar']
        self.assertIn('豪',focused)
        self.assertNotIn('电压',focused)
        self.assertNotIn('频率',focused)

    def test_agreeing_context_can_rescore_a_low_confidence_unit(self):
        result, _ = self.analyze(transcript('记录电流一微安',.2),transcript('电流一微安',.95))
        self.assertIsNone(result['reason'])
        self.assertEqual(result['command']['measurements'][0]['unit'],'uA')

    def test_unit_or_number_disagreement_never_saves_a_guessed_result(self):
        for focused in ['记录电流一安','记录电流二毫安']:
            result, _ = self.analyze(transcript('记录电流一毫安'),transcript(focused))
            self.assertIsNone(result['command'])
            self.assertIn('不一致',result['reason'])

    def test_missing_unit_cannot_be_invented_by_a_constrained_second_pass(self):
        result, decode = self.analyze(transcript('记录电流一'))
        self.assertIsNone(result['command'])
        self.assertIsNotNone(result['reason'])
        self.assertEqual(decode.call_count,1)

    def test_acoustic_homophone_is_displayed_and_parsed_as_milli(self):
        result, _ = self.analyze(transcript('记录 电流 一 豪 安'),transcript('电流 一 豪 安'))
        self.assertIsNone(result['reason'])
        self.assertEqual(result['text'],'电流一毫安')
        self.assertEqual(result['command']['measurements'][0]['unit'],'mA')
        self.assertIn('豪',result['text_acoustic'])

    def test_all_generated_manual_phrases_parse_with_model_compatible_words(self):
        for label, data in grammar.UNIT_CONTEXT_GRAMMARS.items():
            for phrase in json.loads(data):
                if phrase=='[unk]':
                    continue
                with self.subTest(phrase=phrase):
                    command=parser.parse_command(phrase)
                    self.assertEqual(len(command['measurements']),1)
                    self.assertNotIn('毫',phrase)

    def test_unit_review_must_also_pass_confidence(self):
        result, _ = self.analyze(transcript('记录频率一兆赫兹'),transcript('频率一兆赫兹',.2))
        self.assertIsNone(result['command'])
        self.assertIsNotNone(result['reason'])

    def test_multiple_quantities_and_other_commands_are_not_truncated_to_one(self):
        for phrase in ['记录电压三伏电流一毫安频率一千赫兹','读取数据','确认','连续记录三次数据']:
            with self.subTest(phrase=phrase):
                result, decode = self.analyze(transcript(phrase))
                self.assertIsNone(result['reason'])
                self.assertEqual(decode.call_count,1)
        self.assertEqual(len(self.analyze(transcript('记录电压三伏电流一毫安频率一千赫兹'))[0]['command']['measurements']),3)


if __name__ == '__main__':
    unittest.main()
