"""Isolated SDS1202X HOST4 binary-waveform acquisition; no FFT on the ARM."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import sys
import time

from fft_protocol import digest, write_json


def quantity(reply, unit):
    matches = list(re.finditer(r'(?<![A-Za-z0-9])([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)\s*([numkKMGTµμ]?)([A-Za-z/]+)', reply))
    for match in reversed(matches):
        if match[3].lower() == unit.lower():
            factor = {'':1, 'n':1e-9, 'u':1e-6, 'µ':1e-6, 'μ':1e-6, 'm':1e-3,
                      'k':1e3, 'K':1e3, 'M':1e6, 'G':1e9, 'T':1e12}[match[2]]
            value = float(match[1])*factor
            if math.isfinite(value):
                return value
    raise ValueError('Unrecognized %s reply: %s' % (unit, reply))


def binary_block(raw, channel, maximum=16000000, allow_legacy_all=False):
    if not isinstance(raw, bytes):
        raise ValueError('Waveform response is not binary')
    index = raw.find(b'#', 0, 80)
    prefix = raw[:index].strip() if index >= 0 else b'!'
    allowed = [b'', ('C%d:WF DAT2,' % channel).encode(), ('C%d:WF DAT2' % channel).encode(),
               ('C%d:WAVEFORM DAT2,' % channel).encode(), ('C%d:WAVEFORM DAT2' % channel).encode()]
    if allow_legacy_all:
        allowed.append(('C%d:WF ALL,' % channel).encode())
    if prefix not in allowed:
        raise ValueError('Unexpected waveform channel/header: ' + repr(prefix))
    if index < 0 or raw[index+1:index+2] not in [bytes([n]) for n in range(49,58)]:
        raise ValueError('Missing definite-length waveform block')
    width = int(raw[index+1:index+2])
    field = raw[index+2:index+2+width]
    if len(field) != width or not field.isdigit():
        raise ValueError('Invalid waveform length field')
    length, start = int(field), index+2+width
    if not 256 <= length <= maximum or len(raw) < start+length:
        raise ValueError('Waveform block incomplete or too large')
    if raw[start+length:] not in (b'', b'\n', b'\r\n', b'\n\n', b'\r\n\r\n'):
        raise ValueError('Unexpected bytes after waveform payload')
    payload = raw[start:start+length]
    if prefix.endswith(b'ALL,') and b'WAVEDESC' in payload[:64]:
        raise ValueError('Descriptor-bearing ALL blocks are not analog sample arrays')
    return payload


def capture(io, resource, directory, channel=1, cancelled=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    evidence, original_mode, original_setup, stopped = [], None, None, False
    started = time.monotonic()
    def check():
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('FFT capture cancelled')
    def query(command):
        check()
        reply = io.query(command)
        evidence.append(dict(command=command, reply=reply))
        return reply
    def write(command):
        io.device.write(command)
        evidence.append(dict(command=command))
    failure, restoration = None, []
    try:
        identity = query('*IDN?')
        if not re.search(r'(?i)SIGLENT\s*,\s*SDS1202X\s*,\s*SDS1XDC4163410\s*,', identity):
            raise ValueError('HOST4 scope identity does not match the verified SDS1202X')
        mode = query('TRMD?')
        match = re.fullmatch(r'(?:TRMD\s+)?(AUTO|NORM|SINGLE|STOP)', mode.strip(), re.I)
        if not match or match[1].upper() == 'SINGLE':
            raise ValueError('请将示波器设为自动/普通运行或停止状态；单次布防状态不自动重置。')
        original_mode = match[1].upper()
        original_setup = query('WFSU?')
        setup = re.search(r'SP,\s*(\d+)\s*,NP,\s*(\d+)\s*,FP,\s*(\d+)(?:\s*,SN,\s*(\d+))?', original_setup, re.I)
        if not setup:
            raise ValueError('Unrecognized WFSU transfer settings')
        sp, np, fp, sn = setup.groups()
        if sn is not None and int(sn) != 0:
            raise ValueError('FFT currently requires a non-segmented scope record (SN=0).')
        original_setup = 'WFSU SP,%s,NP,%s,FP,%s' % (sp, np, fp)
        if sn is not None:
            original_setup += ',SN,'+sn
        # Set this before the write: even an uncertain STOP needs restoration.
        stopped = True
        write('STOP')
        if not re.search(r'\bSTOP\b', query('TRMD?'), re.I):
            raise ValueError('Scope did not confirm a stopped record')
        rate = quantity(query('SARA?'), 'Sa/s')
        tdiv = quantity(query('TDIV?'), 'S')
        vdiv = quantity(query('C%d:VDIV?' % channel), 'V')
        offset = quantity(query('C%d:OFST?' % channel), 'V')
        if rate <= 0 or tdiv <= 0 or vdiv <= 0 or rate*tdiv*14 < 256:
            raise ValueError('采样配置无效或时窗过短，请扩大示波器时基后重试。')
        # Full contiguous analog record: no sparse-point aliasing or NP header ambiguity.
        write('WFSU SP,1,NP,0,FP,0')
        check()
        raw_reply = io.query_raw('C%d:WF? DAT2' % channel)
        (directory/'scope_reply.bin').write_bytes(raw_reply)
        # Verified 1.1.2.13 R5 replies ALL to DAT2 but sends only analog bytes.
        legacy = '1.1.2.13 R5' in identity
        data = binary_block(raw_reply, channel, allow_legacy_all=legacy)
        if b':WF ALL,' in raw_reply[:40] and len(data) != int(round(rate*tdiv*14)):
            raise ValueError('Legacy ALL record length differs from the verified sample/timebase span')
        path = directory/'scope_codes.i8'
        path.write_bytes(data)
        capture_info = dict(device_id='siglent_sds1202x', physical_port='HOST4', usb_route='1-1.4',
                            resource=resource, identity=identity, channel=channel,
                            captured_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
                            sample_count=len(data), sample_interval_s=1/rate, sample_rate_hz=rate,
                            volts_per_code=vdiv/25., volts_offset=-offset,
                            time_div_s=tdiv, raw_dtype='int8', raw_path=str(path.resolve()),
                            raw_sha256=digest(data), original_trigger_mode=original_mode,
                            selection='contiguous_segment_of_frozen_record',
                            calibration='SDS1000X analog byte: V=code*(VDIV/25)-OFST',
                            acquisition_seconds=time.monotonic()-started)
    except Exception as error:
        failure = error
    finally:
        if stopped:
            for command in (original_setup, 'TRMD '+original_mode if original_mode else None):
                if command:
                    try:
                        write(command)
                    except Exception as error:
                        restoration.append(str(error))
            if not restoration:
                try:
                    reply = io.query('TRMD?')
                    if not re.search(r'\b'+original_mode+r'\b', reply, re.I):
                        restoration.append('Trigger mode readback differs after restoration')
                except Exception as error:
                    restoration.append(str(error))
        write_json(directory/'scope_evidence.json', dict(commands=evidence,
                   failure=str(failure) if failure else None, restoration_errors=restoration))
    if restoration:
        raise RuntimeError('示波器原设置恢复未确认：'+'; '.join(restoration)) from failure
    if failure:
        raise failure
    check()
    write_json(directory/'capture.json', capture_info)
    return capture_info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--resource', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--channel', type=int, choices=(1,2), default=1)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path[:0] = [str(root/'c_instrument/vendor'), str(root)]
    sys.path.append(str(root/'c_instrument/compat_py37'))
    from c_instrument.transport import VisaTransport
    import usb.core
    device = usb.core.find(idVendor=0xf4ec, idProduct=0xee3a)
    if (device is None or device.serial_number != 'SDS1XDC4163410'
            or device.bus != 1 or device.port_numbers != (1,4)):
        raise RuntimeError('HOST4 上未找到已绑定的 SDS1202X（USB 路径 1-1.4）。')
    io = VisaTransport(args.resource, '@py', 15000)
    try:
        from sweep_response import scope_guard
        with scope_guard():
            value = capture(io, args.resource, args.out, args.channel)
    finally:
        io.close()
    print(json.dumps(value, ensure_ascii=True, allow_nan=False))


if __name__ == '__main__':
    main()
