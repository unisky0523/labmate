"""Version 1 file contract for the future PL/DMA executable (Python 3.7+)."""
import array
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

PROTOCOL = 'labmate.fft.v1'
MAX_N = 65536


def read_json(path, maximum=262144):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise ValueError('FFT JSON exceeds size limit')
    def reject(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=reject)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def valid_n(n):
    return type(n) is int and 256 <= n <= MAX_N and n & (n-1) == 0


def hann_q15(n):
    return [min(32767, int((.5-.5*math.cos(2*math.pi*i/n))*32768+.5)) for i in range(n)]


def pack_i16(values):
    values = array.array('h', values)
    if sys.byteorder != 'little':
        values.byteswap()
    return values.tobytes()


def make_request(directory, request_id, capture, n=4096):
    """Crop a contiguous central segment; preserve physical gain and interval."""
    if not valid_n(n):
        raise ValueError('FFT length must be a power of two, 256..65536')
    directory = Path(directory)
    raw = Path(capture['raw_path']).read_bytes()
    if digest(raw) != capture['raw_sha256'] or len(raw) != capture['sample_count']:
        raise ValueError('Captured waveform checksum or length mismatch')
    if len(raw) < n:
        raise ValueError('采样点不足：收到 %d 点，FFT 需要 %d 点。' % (len(raw), n))
    start = (len(raw)-n)//2
    # 8-bit ADC codes are widened by 7 bits, leaving headroom for DC removal.
    values = [(v if v < 128 else v-256)*128 for v in raw[start:start+n]]
    data, window = pack_i16(values), pack_i16(hann_q15(n))
    (directory/'input.i16le').write_bytes(data)
    (directory/'window.q15le').write_bytes(window)
    request = dict(protocol=PROTOCOL, request_id=request_id, fft_size=n,
                   input_file='input.i16le', input_dtype='int16_le', input_sha256=digest(data),
                   window_file='window.q15le', window_sha256=digest(window),
                   window='hann_periodic_q15', remove_dc=True,
                   dc_rounding='truncate_toward_zero', window_rounding='arithmetic_shift_right_15',
                   output_kind='power_u64_le', output_order='natural', bin_count=n//2+1,
                   sample_interval_s=capture['sample_interval_s'],
                   volts_per_input_lsb=capture['volts_per_code']/128,
                   volts_offset=capture['volts_offset'],
                   capture=capture, segment_start=start, segment_count=n,
                   window_sum=sum(hann_q15(n))/32768.,
                   response_file='response.json', power_file='power.u64le')
    write_json(directory/'request.json', request)
    return request


def validate_request(request, directory):
    if (not isinstance(request, dict) or request.get('protocol') != PROTOCOL
            or not isinstance(request.get('request_id'), str) or not 1 <= len(request['request_id']) <= 64
            or not valid_n(request.get('fft_size'))):
        raise ValueError('Invalid FFT request header')
    n = request['fft_size']
    expected = dict(input_file='input.i16le', input_dtype='int16_le', window_file='window.q15le',
                    window='hann_periodic_q15', remove_dc=True, dc_rounding='truncate_toward_zero',
                    window_rounding='arithmetic_shift_right_15', output_kind='power_u64_le',
                    output_order='natural', bin_count=n//2+1, response_file='response.json', power_file='power.u64le')
    if any(request.get(k) != v for k, v in expected.items()):
        raise ValueError('Unsupported FFT request format or numeric convention')
    for file_key, hash_key in (('input_file', 'input_sha256'), ('window_file', 'window_sha256')):
        data = (Path(directory)/request[file_key]).read_bytes()
        if len(data) != 2*n or digest(data) != request.get(hash_key):
            raise ValueError('FFT input/window file mismatch')
    if (not math.isclose(request.get('window_sum', 0), sum(hann_q15(n))/32768., rel_tol=1e-12)
            or (Path(directory)/'window.q15le').read_bytes() != pack_i16(hann_q15(n))):
        raise ValueError('Window coefficients differ from the version 1 convention')
    for field in ('sample_interval_s', 'volts_per_input_lsb'):
        value = request.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid FFT physical calibration: ' + field)
    return request


def decode_response(request, response, directory, allow_reference=False):
    validate_request(request, directory)
    expected = dict(protocol=PROTOCOL, request_id=request['request_id'], input_sha256=request['input_sha256'],
                    fft_size=request['fft_size'], bin_count=request['bin_count'],
                    output_kind='power_u64_le', output_order='natural', power_file='power.u64le',
                    status='complete', overflow=False, backend='fpga')
    if allow_reference and response.get('backend') == 'software_reference':
        expected['backend'] = 'software_reference'
    if any(type(response.get(k)) is not type(v) or response.get(k) != v for k, v in expected.items()):
        raise ValueError('FPGA FFT response does not match the submitted frame or reports an error')
    for key in ('fft_right_shift', 'power_right_shift'):
        if type(response.get(key)) is not int or not 0 <= response[key] <= 64:
            raise ValueError('Missing or invalid FFT numeric scale: ' + key)
    data = (Path(directory)/'power.u64le').read_bytes()
    if len(data) != request['bin_count']*8 or digest(data) != response.get('power_sha256'):
        raise ValueError('FFT power output length/checksum mismatch')
    powers = [p[0] for p in struct.iter_unpack('<Q', data)]
    scale = 2.**response['fft_right_shift'] * 2.**(response['power_right_shift']/2.)
    gain = request['volts_per_input_lsb']*scale/request['window_sum']
    n = request['fft_size']
    amplitudes = [math.sqrt(p)*gain*(1 if k in (0, n//2) else 2) for k, p in enumerate(powers)]
    if any(not math.isfinite(a) for a in amplitudes):
        raise ValueError('Non-finite calibrated spectrum')
    df = 1./(request['sample_interval_s']*n)
    peak = max(range(1, len(amplitudes)), key=lambda k: amplitudes[k])
    return dict(protocol=PROTOCOL, request_id=request['request_id'], backend=response['backend'],
                fft_size=n, bin_spacing_hz=df, nyquist_hz=df*n/2,
                amplitudes_vpeak=amplitudes, peak_bin=peak, peak_frequency_hz=peak*df,
                peak_amplitude_vpeak=amplitudes[peak], channel=request['capture']['channel'],
                sample_rate_hz=1/request['sample_interval_s'], window=request['window'],
                remove_dc=True, captured_at=request['capture']['captured_at'],
                analysis_duration_s=n*request['sample_interval_s'],
                segment_start=request['segment_start'], source='SDS1202X / HOST4')
