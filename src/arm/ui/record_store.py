"""Read legacy records and save GUI-confirmed recognition results.

History reads never rewrite old records. Duplicate copies are merged by ID.
Only confirmation writes recognized text, parsed values and the save time.
This module does not capture audio or dispatch instrument/camera operations.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
import threading
from uuid import uuid4

BEIJING = timezone(timedelta(hours=8))
QUANTITIES = {'voltage': '电压', 'current': '电流', 'frequency': '频率'}
MIN_CLOCK_YEAR = 2026


def bounded(value, limit=512):
    return str('' if value is None else value)[:limit]


def display_time(value):
    if not value:
        return '未记录'
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if moment.tzinfo is None:
            return moment.strftime('%Y-%m-%d %H:%M:%S') + '（原时区未知）'
        return moment.astimezone(BEIJING).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, OverflowError):
        return bounded(value, 96)


def record_row(record):
    measurements = record.get('measurements')
    instrument = record.get('record_kind') == 'instrument_result'
    control = record.get('record_kind') == 'generator_control'
    fft = record.get('record_kind') == 'fft_result'
    if instrument or control or fft:
        content = bounded(record.get('content') or '仪器回执')
    elif isinstance(measurements, list) and measurements:
        content = '；'.join('%s %s %s' % (QUANTITIES.get(item.get('quantity'), '数据'),
                                        bounded(item.get('value'), 64), bounded(item.get('unit'), 16))
                           for item in measurements if isinstance(item, dict))
    elif record.get('record_kind') == 'voice_result':
        content = bounded(record.get('original_text') or '已确认语音指令')
    else:
        unit = record.get('unit')
        quantity = '电压 ' if unit in ('V', 'mV') else '电流 ' if unit in ('A', 'mA') else ''
        value = '未记录' if record.get('value') is None else bounded(record.get('value'), 64)
        content = '%s%s %s' % (quantity, value, bounded(unit, 16))
    source_id = bounded(record.get('source'), 48)
    simulated = record.get('is_simulated') is True or source_id == 'mock'
    source = ('模拟数据' if simulated else
              {'manual_voice': '语音报数', 'manual_voice_result': '语音报数',
               'voice_result': '语音指令', 'manual_text': '手动输入',
               'instrument_usb': '仪器 USB'}.get(
                  source_id, source_id or '未注明'))
    status = {'active': '正常', 'abnormal': '异常', 'void': '已撤销'}.get(bounded(record.get('status'), 16), '未知')
    if record.get('valid') is False and record.get('status') != 'void':
        status = '无效'
    if instrument and record.get('status') not in ('void', 'abnormal'):
        status = {'complete': '完成', 'partial': '部分成功', 'failed': '读取失败'}.get(
            record.get('acquisition_status'), '未知')
    if control and record.get('status') not in ('void', 'abnormal'):
        status = '已回读/执行' if record.get('valid') else '执行失败'
    if fft and record.get('status') not in ('void', 'abnormal'):
        status = '频谱完成' if record.get('valid') else '待 FPGA'
    time_text = display_time(record.get('saved_at'))
    trigger = record.get('trigger') if isinstance(record.get('trigger'), dict) else {}
    detail = ('数据内容：%s\n记录时间：%s\n来源：%s；状态：%s\n'
              '原始话语：%s\n采集/报数时间：%s\n确认时间：%s\n'
              '保存时间原值：%s\n记录编号：%s') % (
                  content, time_text, source, status,
                  bounded(record.get('original_text') or trigger.get('asr_text') or '未记录', 512),
                  display_time(record.get('input_at') or record.get('captured_at') or trigger.get('recorded_at')),
                  display_time(record.get('confirmed_at')),
                  bounded(record.get('saved_at'), 96), bounded(record.get('record_id'), 64))
    detail += '\n显示时区：北京时间 UTC+08:00（无时区的旧时间保持原值）'
    if record.get('clock_warning'):
        detail += '\n时间说明：保存时板卡系统时间尚未校准。'
    if instrument:
        detail += '\n采集状态：' + str(record.get('acquisition_status'))
        for entry in record.get('devices', []):
            raw = entry['result']
            name = '万用表' if entry['action'] == 'meter.read' else '示波器'
            detail += '\n%s：%s；采集时间：%s' % (name, raw['status'], display_time(raw.get('captured_at')))
            for item in raw.get('measurements', []):
                label = ('通道%s ' % item['channel'] if item.get('channel') else '') + str(item.get('label') or '数据')
                detail += '\n  %s：%s %s；有效：%s' % (label,
                    item.get('value') if item.get('valid') else '读取失败', item.get('unit', ''), item.get('valid'))
                if item.get('error_code'):
                    detail += '；错误：' + bounded(item['error_code'], 96)
            if raw.get('detail'):
                detail += '\n  错误：' + bounded(raw['detail'], 256)
        if record.get('image_path'):
            detail += '\n示波器屏幕截图：' + bounded(record['image_path'], 512)
        detail += '\n原始回执：' + bounded(record.get('receipt_path'), 512)
    if record.get('annotations'):
        detail += '\n批注：' + '；'.join('%s %s %s' % (
            display_time(item.get('created_at')), {'void': '作废', 'abnormal': '异常'}.get(item.get('status'), '批注'),
            bounded(item.get('original_request') or item.get('reason'), 120))
            for item in record['annotations'][:6])
    if fft:
        raw = record['fft_result']
        detail += '\nFFT 来源：SDS1202X / HOST4 / CH1；计算：' + raw['backend']
        detail += '\n采样与结果目录：' + bounded(record.get('fft_data_path'), 512)
        if record.get('image_path'):
            detail += '\n频谱图：' + bounded(record['image_path'], 512)
    image_path = record.get('image_path')
    image_kind = 'spectrum' if fft else 'screenshot'
    observer = record.get('control_result', {}).get('response_capture') if control else None
    if isinstance(observer, dict):
        image_kind = 'sweep_response'
        folder = Path(observer['directory'])
        try:
            from fft_protocol import read_json
            observed = read_json(folder/'result.json', maximum=8000000)
            detail += '\n扫频响应：'+observed['status']+'；连续扫频，频率与峰峰值顺序读取，非同步测量。'
            detail += '\n数据目录：'+str(folder)+'\n有效绘图点数：'+str(observed.get('point_count', 0))
            if observed.get('detail'):
                detail += '\n'+bounded(observed['detail'],512)
            if observed['status'] in ('complete', 'partial') and (folder/'response.png').is_file():
                image_path = str(folder/'response.png')
                status = ('曲线完成' if observed['status'] == 'complete' else '部分曲线') if record.get('status') == 'active' else status
        except (OSError, ValueError, KeyError):
            detail += '\n响应曲线采集中，请稍后刷新历史。' if observer['status'] != 'failed' else '\n响应曲线准备失败：'+observer.get('detail','')
    return dict(record_id=bounded(record.get('record_id'), 64), content=bounded(content),
                saved_at=bounded(record.get('saved_at'), 96), time_text=time_text,
                source=source, status=status, simulated=simulated, detail=bounded(detail, 2600),
                image_path=bounded(image_path, 2048), image_kind=image_kind)


class RecordStore:
    def __init__(self, runtime, directory, history_dirs=()):
        self.directory = Path(directory).resolve()
        self.history_dirs = list(dict.fromkeys([self.directory] + [Path(p).resolve() for p in history_dirs if p]))
        self.lock = threading.Lock()
        # Load the selected source's standard-library schema module separately
        # from ASR's `main`; history annotation roots must not mutate ASR globals.
        spec = importlib.util.spec_from_file_location('_labmate_gui_records', str(Path(runtime) / 'main.py'))
        self.core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.core)
        self.core.RECORD_DIR = self.directory

    def _load_edits(self):
        path = self.directory / 'history_edits.json'
        if not path.exists():
            return dict(schema=1, deleted={}, annotations={})
        try:
            edits = json.loads(path.read_text(encoding='utf-8'))
            if (edits.get('schema') != 1 or not isinstance(edits.get('deleted'), dict)
                    or not isinstance(edits.get('annotations'), dict)):
                raise ValueError('invalid history edits')
            for key in set(edits['deleted']) | set(edits['annotations']):
                if not re.fullmatch(r'[0-9a-f]{32}', key):
                    raise ValueError('invalid record id')
            for events in edits['annotations'].values():
                if not isinstance(events, list) or any(not isinstance(e, dict) or
                        e.get('status') not in ('void', 'abnormal') for e in events):
                    raise ValueError('invalid annotations')
            return edits
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError('历史修改信息损坏，已停止读取和清除，请检查备份。') from error

    def _write_edits(self, edits):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / 'history_edits.json'
        temporary = path.with_name('.history_edits_' + uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(edits, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(path))
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _order(record):
        try:
            moment = datetime.fromisoformat(str(record.get('saved_at', '')).replace('Z', '+00:00'))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=BEIJING)
            return moment.timestamp(), record['record_id']
        except (ValueError, OSError, OverflowError):
            return float('-inf'), record['record_id']

    @staticmethod
    def _revision(records):
        return hashlib.sha256('\n'.join(sorted(records)).encode('utf-8')).hexdigest()

    def prepare_annotation(self, result):
        command = result.get('command') or {}
        if command.get('intent') != 'annotate' or command.get('status') not in ('void', 'abnormal'):
            raise ValueError('不是有效的撤销或异常标记指令。')
        with self.lock:
            records, _, _ = self._read_all()
            candidates = [r for r in records.values() if r.get('status') != 'void' and
                          (r.get('record_kind') == 'instrument_result' or r.get('measurements')
                           or r.get('value') is not None)]
            if not candidates:
                raise ValueError('没有可以处理的已保存数据。')
            target = max(candidates, key=self._order)
            row = record_row(target)
            value = dict(result)
            value['annotation_target'] = target['record_id']
            action = '撤销' if command['status'] == 'void' else '标记异常'
            value['summary'] = '将%s：%s\n记录时间：%s\n核对后点击“确认保存”或说“确认”，取消则不修改。' % (
                action, row['content'], row['time_text'])
            return value

    def apply_annotation(self, result, operation_id):
        command = result.get('command') or {}
        target = result.get('annotation_target')
        if (result.get('simulated') is not False or result.get('reason') or
                command.get('intent') != 'annotate' or command.get('status') not in ('void', 'abnormal')
                or not isinstance(target, str) or not re.fullmatch(r'[0-9a-f]{32}', target)):
            raise ValueError('撤销目标无效，请重新开始。')
        with self.lock:
            records, _, _ = self._read_all()
            if target not in records:
                raise ValueError('目标记录已经清除，未修改其他数据。')
            edits = self._load_edits()
            events = edits['annotations'].setdefault(target, [])
            if not any(e.get('request_id') == operation_id for e in events):
                if records[target].get('status') == 'void':
                    raise ValueError('该记录已撤销，未修改其他数据。')
                events.append(dict(event_id=hashlib.sha256(operation_id.encode()).hexdigest()[:32],
                                   request_id=operation_id, record_id=target, status=command['status'],
                                   created_at=datetime.now().astimezone().isoformat(timespec='milliseconds'),
                                   original_request=bounded(result.get('text'), 512)))
                self._write_edits(edits)
            updated, _, _ = self._read_all()
            return record_row(updated[target])

    def clear_records(self, record_id=None, revision=None):
        with self.lock:
            records, _, _ = self._read_all()
            if record_id is not None:
                if not isinstance(record_id, str) or not re.fullmatch(r'[0-9a-f]{32}', record_id):
                    raise ValueError('记录编号无效。')
                selected = [record_id] if record_id in records else []
            else:
                if revision != self._revision(records):
                    raise ValueError('历史记录已变化，请刷新后重新确认清除。')
                selected = list(records)
            edits = self._load_edits()
            stamp = datetime.now().astimezone().isoformat(timespec='milliseconds')
            for key in selected:
                edits['deleted'][key] = stamp
            if selected:
                self._write_edits(edits)
            return dict(cleared=len(selected))

    def _validate_history(self, record):
        """Bad field shapes must not break sorting/formatting of other rows."""
        for key in ('saved_at', 'source', 'status'):
            if key in record and not isinstance(record[key], str):
                raise ValueError('invalid ' + key)
        if record.get('record_kind') == 'fft_result':
            from fft_control import validate_saved_fft
            raw = validate_saved_fft(record['fft_result'])
            if (record.get('source') != 'instrument_usb' or record.get('is_simulated') is not False
                    or record.get('valid') is not raw['valid'] or not isinstance(record.get('content'), str)
                    or raw['request_id'] != record.get('request_id')):
                raise ValueError('Invalid FFT history entry')
            return
        if record.get('record_kind') == 'generator_control':
            from generator_control import validate_control
            raw = validate_control(record['control_result'])
            if (record.get('source') != 'instrument_usb' or record.get('is_simulated') is not False
                    or record.get('valid') is not raw['valid'] or not isinstance(record.get('content'), str)):
                raise ValueError('invalid generator control history')
            return
        if record.get('record_kind') == 'instrument_result':
            from instrument_adapter import validate_result
            if (record.get('source') != 'instrument_usb' or record.get('is_simulated') is not False
                    or record.get('acquisition_status') not in ('complete', 'partial', 'failed')
                    or not isinstance(record.get('content'), str)
                    or not isinstance(record.get('devices'), list) or not 1 <= len(record['devices']) <= 2):
                raise ValueError('invalid instrument record')
            for entry in record['devices']:
                validate_result(entry['result'], entry['action'])
            statuses = [entry['result']['status'] for entry in record['devices']]
            aggregate = ('complete' if all(s == 'complete' for s in statuses)
                         else 'failed' if all(s == 'failed' for s in statuses) else 'partial')
            if record['acquisition_status'] != aggregate or record.get('valid') != (aggregate == 'complete'):
                raise ValueError('inconsistent instrument status')
            return
        measurements = record.get('measurements')
        if measurements is not None:
            if not isinstance(measurements, list) or not 1 <= len(measurements) <= 3:
                raise ValueError('invalid measurements')
            for item in measurements:
                if not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in ('quantity', 'value', 'unit')):
                    raise ValueError('invalid measurement fields')
            # Reuse the source's decimal/unit validation without rejecting an
            # explicitly invalid/void historical record's display status.
            self.core.validate_reading(dict(record_kind='manual', source='manual_text',
                                           is_simulated=False, valid=True, measurements=measurements))
        else:
            value = record.get('value')
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError('invalid legacy value')
            if record.get('unit') is not None and not isinstance(record['unit'], str):
                raise ValueError('invalid legacy unit')

    def _read_all(self):
        records = {}
        skipped = conflicts = 0
        priorities = {'active': 0, 'abnormal': 1, 'void': 2}
        try:
            for directory in self.history_dirs:
                self.core.RECORD_DIR = directory
                try:
                    paths = list(directory.glob('record_*.json'))
                except OSError:
                    skipped += 1
                    continue
                for path in sorted(paths):
                    try:
                        if path.stat().st_size > 1024 * 1024:
                            raise ValueError('oversized record')
                        record = self.core.read_record(path)
                        if not isinstance(record, dict):
                            raise ValueError('invalid record')
                        self._validate_history(record)
                        key = record['record_id']
                        if key not in records:
                            records[key] = record
                        else:
                            existing = records[key]
                            if any(existing.get(name) != record.get(name) for name in
                                   ('measurements', 'devices', 'value', 'unit', 'source', 'is_simulated', 'valid', 'saved_at', 'original_text', 'recognized_command')):
                                conflicts += 1
                            if priorities.get(record.get('status'), 0) > priorities.get(existing.get('status'), 0):
                                existing['status'] = record['status']
                            existing['annotations'] = list({bounded(item.get('event_id') or item, 1024): item
                                for item in existing.get('annotations', []) + record.get('annotations', [])}.values())
                            # Never turn a simulated/invalid duplicate into a
                            # real/valid row just because one copy lacks flags.
                            if record.get('is_simulated') is True or record.get('source') == 'mock':
                                existing['is_simulated'] = True
                            if record.get('valid') is False:
                                existing['valid'] = False
                    except (ValueError, KeyError, TypeError, OSError, AttributeError, RecursionError, OverflowError):
                        skipped += 1
        finally:
            self.core.RECORD_DIR = self.directory
        edits = self._load_edits()
        for key in list(records):
            if key in edits['deleted']:
                del records[key]
                continue
            events = records[key].get('annotations', []) + edits['annotations'].get(key, [])
            records[key]['annotations'] = events
            if records[key].get('status') == 'void' or any(e.get('status') == 'void' for e in events):
                records[key]['status'] = 'void'
            elif any(e.get('status') == 'abnormal' for e in events):
                records[key]['status'] = 'abnormal'
        return records, skipped, conflicts

    def list_page(self, page=0, size=4):
        if type(page) is not int or page < 0 or type(size) is not int or not 1 <= size <= 6:
            raise ValueError('invalid page or size')
        with self.lock:
            records, skipped, conflicts = self._read_all()
            ordered = sorted(records.values(), key=self._order, reverse=True)
            total = len(ordered)
            pages = max(1, (total + size - 1) // size)
            page = min(max(0, page), pages - 1)
            rows = [record_row(item) for item in ordered[page * size:(page + 1) * size]]
            warnings = []
            if skipped:
                warnings.append('已跳过 %d 个损坏或不可读文件' % skipped)
            if conflicts:
                warnings.append('%d 个重复编号内容不一致，优先显示当前记录目录版本' % conflicts)
            if datetime.now().year < MIN_CLOCK_YEAR:
                warnings.append('板卡时间尚未校准，新记录前请先校时')
            return dict(rows=rows, page=page, total_pages=pages, total=total, warnings=warnings,
                        revision=self._revision(records))

    def save_result(self, result, operation_id):
        """Save the existing recognizer's completed result, without audio hooks."""
        command = result.get('command')
        if not isinstance(command, dict) or not isinstance(command.get('intent'), str):
            raise ValueError('没有可保存的识别结果。')
        if result.get('simulated') is not False or result.get('reason'):
            raise ValueError('模拟或未通过检查的识别结果不能保存。')
        if command['intent'] == 'annotate':
            raise ValueError('撤销指令必须处理目标记录，不能作为新数据保存。')
        with self.lock:
            records, _, _ = self._read_all()
            for record in records.values():
                if record.get('request_id') == operation_id:
                    return record_row(record)
            measurements = command.get('measurements') if command['intent'] == 'record_manual' else None
            if command['intent'] == 'record_manual':
                # Reuse decimal/unit checks only. The stored source explicitly
                # says this is a recognized result, with no audio evidence.
                self._validate_history(dict(measurements=measurements))
                self.core.validate_reading(dict(record_kind='manual', source='manual_text',
                                               is_simulated=False, valid=True,
                                               measurements=measurements))
            now = datetime.now().astimezone()
            stamp = now.isoformat(timespec='milliseconds')
            record_id = hashlib.sha256(operation_id.encode('utf-8')).hexdigest()[:32]
            document = dict(schema_version=3, record_kind='voice_result', record_id=record_id,
                            request_id=operation_id, source='manual_voice_result' if measurements else 'voice_result',
                            is_simulated=False, valid=True, status='active',
                            original_text=bounded(result.get('text'), 2048), recognized_command=command,
                            input_at=result.get('recognized_at'), confirmed_at=stamp, saved_at=stamp,
                            audio_path=None, image_path=None, clock_warning=now.year < MIN_CLOCK_YEAR)
            if measurements is not None:
                document['measurements'] = measurements
            self._validate_history(document)
            path = self.directory / ('record_' + now.strftime('%Y%m%d_%H%M%S_%f') + '_' + record_id + '.json')
            self.core.write_json_atomically(path, document)
            with path.open('r+b') as saved:
                os.fsync(saved.fileno())
            return record_row(self.core.read_record(path))

    def save_generator_result(self, result, operation_id, raw):
        from generator_control import validate_control, state_text
        validate_control(raw)
        with self.lock:
            records, _, _ = self._read_all()
            for record in records.values():
                if record.get('request_id') == operation_id:
                    return record_row(record)
            now = datetime.now().astimezone()
            stamp = now.isoformat(timespec='milliseconds')
            record_id = hashlib.sha256(operation_id.encode('utf-8')).hexdigest()[:32]
            document = dict(schema_version=5, record_kind='generator_control', record_id=record_id,
                            request_id=operation_id, source='instrument_usb', is_simulated=False,
                            valid=raw['valid'], status='active', content=state_text(raw), control_result=raw,
                            original_text=bounded(result.get('text'), 2048), recognized_command=result['command'],
                            confirmed_at=stamp, saved_at=stamp, image_path=None,
                            clock_warning=now.year < MIN_CLOCK_YEAR)
            self._validate_history(document)
            path = self.directory/('record_'+now.strftime('%Y%m%d_%H%M%S_%f')+'_'+record_id+'.json')
            self.core.write_json_atomically(path, document)
            with path.open('r+b') as f:
                os.fsync(f.fileno())
            return record_row(self.core.read_record(path))

    def save_fft_result(self, result, operation_id, raw):
        """Keep the PNG and binary/metadata files under permanent history storage."""
        import shutil
        from fft_control import validate_saved_fft, summary
        from fft_protocol import read_json, write_json
        validate_saved_fft(raw)
        if result.get('simulated') is not False or raw['request_id'] != operation_id:
            raise ValueError('FFT 回执与实际任务不匹配。')
        with self.lock:
            records, _, _ = self._read_all()
            for record in records.values():
                if record.get('request_id') == operation_id:
                    if record.get('record_kind') != 'fft_result':
                        raise ValueError('本轮编号已用于其他记录。')
                    return record_row(record)
            record_id = hashlib.sha256(operation_id.encode('utf-8')).hexdigest()[:32]
            destination = self.directory/'fft'/record_id
            destination.mkdir(parents=True, exist_ok=True)
            source = Path(raw['job_directory']).resolve()
            names = ['scope_codes.i8', 'capture.json', 'scope_evidence.json', 'input.i16le',
                     'window.q15le', 'request.json', 'analysis.json']
            if raw['valid']:
                names += ['response.json', 'power.u64le', 'spectrum.json', 'spectrum.png']
            for name in names:
                incoming = source/name
                if not incoming.is_file() or incoming.stat().st_size > 20000000:
                    raise ValueError('FFT 归档文件缺失或过大：' + name)
                temporary = destination/(name+'.tmp')
                with incoming.open('rb') as src, temporary.open('wb') as out:
                    shutil.copyfileobj(src, out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(str(temporary), str(destination/name))
            # Archived metadata must continue to work after the job cache is removed.
            captured = read_json(destination/'capture.json')
            captured['raw_path'] = str((destination/'scope_codes.i8').resolve())
            write_json(destination/'capture.json', captured)
            request = read_json(destination/'request.json')
            request['capture'] = captured
            write_json(destination/'request.json', request)
            now = datetime.now().astimezone()
            stamp = now.isoformat(timespec='milliseconds')
            document = dict(schema_version=6, record_kind='fft_result', record_id=record_id,
                            request_id=operation_id, source='instrument_usb', is_simulated=False,
                            valid=raw['valid'], status='active', fft_result=dict(raw),
                            content=summary(raw).split('\n')[0], original_text=bounded(result.get('text'), 2048),
                            recognized_command=result['command'], captured_at=raw['captured_at'],
                            confirmed_at=stamp, saved_at=stamp, clock_warning=now.year < MIN_CLOCK_YEAR,
                            fft_data_path=str(destination.resolve()),
                            image_path=str((destination/'spectrum.png').resolve()) if raw['valid'] else None)
            document['fft_result']['job_directory'] = str(destination.resolve())
            document['fft_result']['image_path'] = document['image_path']
            write_json(destination/'analysis.json', document['fft_result'])
            self._validate_history(document)
            path = self.directory/('record_'+now.strftime('%Y%m%d_%H%M%S_%f')+'_'+record_id+'.json')
            self.core.write_json_atomically(path, document)
            with path.open('r+b') as saved:
                os.fsync(saved.fileno())
            return record_row(document)

    def save_instrument_result(self, result, operation_id, receipt):
        """Archive real results and screenshot bytes, retaining failed items."""
        from instrument_adapter import result_text
        import shutil
        if result.get('simulated') is not False or receipt.get('request_id') != operation_id:
            raise ValueError('仪器回执与真实语音请求不匹配。')
        with self.lock:
            records, _, _ = self._read_all()
            for record in records.values():
                if record.get('request_id') == operation_id:
                    if record.get('record_kind') != 'instrument_result':
                        raise ValueError('本轮编号已被其他类型记录使用。')
                    return record_row(record)
            now = datetime.now().astimezone()
            stamp = now.isoformat(timespec='milliseconds')
            record_id = hashlib.sha256(operation_id.encode('utf-8')).hexdigest()[:32]
            document = dict(schema_version=4, record_kind='instrument_result', record_id=record_id,
                            request_id=operation_id, source='instrument_usb', is_simulated=False,
                            valid=receipt['acquisition_status'] == 'complete', status='active',
                            acquisition_status=receipt['acquisition_status'], devices=receipt['devices'],
                            content='\n'.join(result_text(entry) for entry in receipt['devices']),
                            original_text=bounded(result.get('text'), 2048), recognized_command=result['command'],
                            captured_at=receipt.get('created_at'), confirmed_at=stamp, saved_at=stamp,
                            receipt_path=receipt['receipt_path'], audio_path=None, image_path=None,
                            clock_warning=now.year < MIN_CLOCK_YEAR)
            if result.get('batch'):
                document['batch'] = dict(result['batch'])
                document['content'] = '连续记录第 %d/%d 次（间隔 %g 秒）\n%s' % (
                    result['batch']['index'], result['batch']['count'],
                    result['batch']['interval_seconds'], document['content'])
            self._validate_history(document)
            for entry in receipt['devices']:
                raw = entry['result']
                if entry['action'] == 'scope.capture_screen' and raw['status'] == 'complete':
                    source = Path(raw['image_path'])
                    suffix = source.suffix.lower()
                    if suffix not in ('.bmp', '.png', '.jpg', '.jpeg') or source.stat().st_size != raw['image_bytes']:
                        raise ValueError('截图文件无效。')
                    destination = self.directory / 'images' / (record_id + suffix)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_suffix(suffix + '.tmp')
                    try:
                        with source.open('rb') as incoming, temporary.open('wb') as outgoing:
                            shutil.copyfileobj(incoming, outgoing)
                            outgoing.flush()
                            os.fsync(outgoing.fileno())
                        os.replace(str(temporary), str(destination))
                    finally:
                        try:
                            temporary.unlink()
                        except FileNotFoundError:
                            pass
                    document['image_path'] = str(destination.resolve())
            path = self.directory / ('record_' + now.strftime('%Y%m%d_%H%M%S_%f') + '_' + record_id + '.json')
            self.core.write_json_atomically(path, document)
            with path.open('r+b') as saved:
                os.fsync(saved.fileno())
            return record_row(self.core.read_record(path))
