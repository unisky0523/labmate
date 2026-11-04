"""Exercise full command phrases and the actual shipped ASR vocabulary."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'asr_runtime'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(RUNTIME/filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


saved_path = sys.path[:]
try:
    sys.path.insert(0, str(RUNTIME))
    parser = module('_batch_text_cli', 'text_cli.py')
finally:
    sys.path[:] = saved_path
grammar = module('_batch_grammar', 'asr_grammar.py')


class BatchCommandTests(unittest.TestCase):
    def test_variable_counts_default_one_second(self):
        for phrase, count in [('连续记录三次数据', 3), ('连续记录五次数据', 5),
                              ('连续记录十二次数据', 12), ('连续记录一百次数据', 100),
                              ('连续记录数据两次', 2), ('连续 记录 四 次 数据', 4)]:
            with self.subTest(phrase=phrase):
                self.assertEqual(parser.parse_command(phrase),
                                 dict(intent='record_device', count=count, interval=1.0))

    def test_requested_suffix_and_existing_interval_first_forms(self):
        for phrase, count, interval in [
            ('连续记录三次数据，时间间隔一秒', 3, 1),
            ('连续记录五次数据时间间隔两秒', 5, 2),
            ('连续记录12次数据,时间间隔1.5秒', 12, 1.5),
            ('连续记录两次数据，间隔零点五秒', 2, .5),
            ('请帮我连续记录三次数据，时间间隔为一秒', 3, 1),
            ('每隔两秒记录一次，共五次', 5, 2),
            ('连续记录三次数据，时间间隔零秒', 3, 0),
        ]:
            with self.subTest(phrase=phrase):
                self.assertEqual(parser.parse_command(phrase),
                                 dict(intent='record_device', count=count, interval=float(interval)))

    def test_invalid_counts_intervals_and_trailing_words_are_rejected(self):
        for phrase in ['连续记录零次数据', '连续记录一百零一次数据', '连续记录一点五次数据',
                       '连续记录三次数据时间间隔负一秒', '连续记录三次数据时间间隔六十一秒',
                       '连续记录三次数据时间间隔一', '连续记录三次数据时间间隔一秒然后拍照']:
            with self.subTest(phrase=phrase), self.assertRaises(ValueError):
                parser.parse_command(phrase)

    def test_all_batch_vocabulary_entries_parse_and_cover_bounds(self):
        commands = []
        for phrase in json.loads(grammar.GRAMMAR_JSON):
            if phrase.startswith(('连续 记录 ', '每 隔 ')):
                compact = phrase.replace(' ', '')
                # Legacy grammar includes zero counts; those must remain rejected.
                if compact == '连续记录零次数据':
                    continue
                commands.append(parser.parse_command(phrase))
        self.assertIn(dict(intent='record_device', count=100, interval=1.0), commands)
        self.assertIn(dict(intent='record_device', count=3, interval=60.0), commands)
        self.assertIn(dict(intent='record_device', count=3, interval=.5), commands)


if __name__ == '__main__':
    unittest.main()
