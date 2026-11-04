"""Real history edits, cross-directory duplicates, retries and protocol binding."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from record_store import RecordStore
import test_records as fixtures
from test_records import SyntheticRecognizer, voice_result, ROOT


def undo_result():
    return dict(text='撤销上一条数据', simulated=False, reason=None,
                command={'intent': 'annotate', 'status': 'void'})


# Fixture helpers are copied explicitly so discover does not run old tests twice.
class EditStoreTests(unittest.TestCase):
    setUp = fixtures.StoreTests.setUp
    tearDown = fixtures.StoreTests.tearDown
    write_record = fixtures.StoreTests.write_record

    def test_undo_binds_preview_target_and_never_creates_a_command_record(self):
        first = self.store.save_result(voice_result(), 'first')
        value = self.store.prepare_annotation(undo_result())
        self.assertEqual(value['annotation_target'], first['record_id'])
        newer = self.store.save_result(voice_result(), 'newer')
        updated = self.store.apply_annotation(value, 'undo-once')
        self.assertEqual(updated['status'], '已撤销')
        self.assertEqual(self.store.apply_annotation(value, 'undo-once')['record_id'], first['record_id'])
        restarted = RecordStore(ROOT/'asr_runtime', self.directory)
        rows = {r['record_id']: r for r in restarted.list_page()['rows']}
        self.assertEqual(rows[first['record_id']]['status'], '已撤销')
        self.assertEqual(rows[newer['record_id']]['status'], '正常')
        self.assertEqual(len(list(self.directory.glob('record_*.json'))), 2)
        self.assertEqual(len(json.loads((self.directory/'history_edits.json').read_text(encoding='utf-8'))['annotations'][first['record_id']]), 1)

    def test_undo_skips_instruction_rows_and_updates_old_read_only_source(self):
        path, data = self.write_record(self.old, saved_at='2026-11-01T10:00:00+08:00')
        original = path.read_bytes()
        instruction = voice_result()
        instruction.update(command={'intent': 'help'}, text='帮助')
        self.store.save_result(instruction, 'command')
        value = self.store.prepare_annotation(undo_result())
        self.assertEqual(value['annotation_target'], data['record_id'])
        self.store.apply_annotation(value, 'undo-legacy')
        self.assertEqual(path.read_bytes(), original)
        row = next(r for r in self.store.list_page()['rows'] if r['record_id'] == data['record_id'])
        self.assertEqual(row['status'], '已撤销')

    def test_empty_undo_and_missing_target_never_modify_other_records(self):
        with self.assertRaisesRegex(ValueError, '没有可以'):
            self.store.prepare_annotation(undo_result())
        saved = self.store.save_result(voice_result(), 'target')
        value = self.store.prepare_annotation(undo_result())
        self.store.clear_records(record_id=saved['record_id'])
        self.store.save_result(voice_result(), 'other')
        with self.assertRaisesRegex(ValueError, '已经清除'):
            self.store.apply_annotation(value, 'late-undo')
        self.assertEqual(self.store.list_page()['rows'][0]['status'], '正常')

    def test_single_clear_covers_duplicate_directories_and_survives_restart(self):
        _, data = self.write_record()
        self.write_record(self.old, **data)
        _, keep = self.write_record()
        self.assertEqual(self.store.clear_records(record_id=data['record_id'])['cleared'], 1)
        self.assertEqual(self.store.clear_records(record_id=data['record_id'])['cleared'], 0)
        restarted = RecordStore(ROOT/'asr_runtime', self.directory, [self.old])
        self.assertEqual([r['record_id'] for r in restarted.list_page()['rows']], [keep['record_id']])

    def test_clear_all_rejects_stale_list_then_clears_current_and_allows_new_records(self):
        self.write_record()
        revision = self.store.list_page()['revision']
        self.write_record(self.old)
        with self.assertRaisesRegex(ValueError, '已变化'):
            self.store.clear_records(revision=revision)
        page = self.store.list_page()
        self.assertEqual(page['total'], 2)
        self.assertEqual(self.store.clear_records(revision=page['revision'])['cleared'], 2)
        restarted = RecordStore(ROOT/'asr_runtime', self.directory, [self.old])
        self.assertEqual(restarted.list_page()['total'], 0)
        restarted.save_result(voice_result(), 'after-clear')
        self.assertEqual(restarted.list_page()['total'], 1)

    def test_failed_clear_preserves_previous_deletions_and_does_not_report_success(self):
        _, old = self.write_record()
        _, keep = self.write_record()
        self.store.clear_records(record_id=old['record_id'])
        before = (self.directory/'history_edits.json').read_bytes()
        with patch('record_store.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.store.clear_records(record_id=keep['record_id'])
        self.assertEqual((self.directory/'history_edits.json').read_bytes(), before)
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_invalid_edit_index_fails_closed_and_annotation_cannot_be_saved_as_text(self):
        with self.assertRaises(ValueError):
            self.store.save_result(undo_result(), 'wrong-path')
        self.write_record()
        (self.directory/'history_edits.json').write_text('{broken')
        with self.assertRaisesRegex(ValueError, '损坏'):
            self.store.list_page()
        with self.assertRaisesRegex(ValueError, '损坏'):
            self.store.clear_records(revision='0'*64)


class UndoRecognizer(SyntheticRecognizer):
    def recognize(self, cancelled, progress):
        super().recognize(cancelled, progress)
        return undo_result()


class EditProtocolTests(unittest.TestCase):
    setUp = fixtures.BackendRecordTests.setUp
    tearDown = fixtures.BackendRecordTests.tearDown
    launch = fixtures.BackendRecordTests.launch
    take = fixtures.BackendRecordTests.take
    send = fixtures.BackendRecordTests.send

    def test_undo_requires_confirmation_then_updates_existing_record(self):
        saved = self.store.save_result(voice_result(), 'saved')
        self.launch(UndoRecognizer())
        self.send('start', 'undo')
        self.take('state')
        self.take('progress')
        preview = self.take('result')
        self.assertEqual(preview['annotation_target'], saved['record_id'])
        self.assertEqual(self.store.list_page()['rows'][0]['status'], '正常')
        self.send('confirm', 'confirm-undo', 'undo')
        self.take('state')
        result = self.take('confirmed')
        self.assertEqual(result['effect'], 'record_updated')
        self.assertEqual(result['record']['status'], '已撤销')
        self.assertEqual(self.store.list_page()['total'], 1)

    def test_cancelled_undo_does_not_annotate_and_clear_is_blocked_while_pending(self):
        saved = self.store.save_result(voice_result(), 'saved')
        self.launch(UndoRecognizer())
        self.send('start', 'undo')
        self.take('state'); self.take('progress'); self.take('result')
        self.input.queue.put(json.dumps(dict(protocol=1, id='clear-pending', action='delete_record',
                                             record_id=saved['record_id']))+'\n')
        self.assertEqual(self.take('error')['code'], 'history_edit_busy')
        self.send('cancel', 'cancel-undo', 'undo')
        self.take('cancelled')
        self.assertEqual(self.store.list_page()['rows'][0]['status'], '正常')

    def test_clear_protocol_reports_actual_count_and_keeps_future_records(self):
        saved = self.store.save_result(voice_result(), 'saved')
        self.launch()
        self.input.queue.put(json.dumps(dict(protocol=1, id='delete-one', action='delete_record',
                                             record_id=saved['record_id']))+'\n')
        self.assertEqual(self.take('history_cleared')['cleared'], 1)
        self.store.save_result(voice_result(), 'new')
        revision = self.store.list_page()['revision']
        self.input.queue.put(json.dumps(dict(protocol=1, id='clear-all', action='clear_history',
                                             revision=revision))+'\n')
        self.assertEqual(self.take('history_cleared')['cleared'], 1)
        self.assertEqual(self.store.list_page()['total'], 0)


if __name__ == '__main__':
    unittest.main()
