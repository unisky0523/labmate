"""Offline golden FFT only. Outputs are labelled software_reference, never FPGA."""
import argparse
from pathlib import Path
import shutil
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'work/labmate_ui'))
from fft_protocol import read_json, write_json, validate_request, digest, decode_response


def reference(request_path, output):
    import numpy as np
    request_path, output = Path(request_path).resolve(), Path(output).resolve()
    if output == request_path.parent:
        raise ValueError('Reference outputs must use a separate directory from the production FPGA job')
    request = validate_request(read_json(request_path), request_path.parent)
    output.mkdir(parents=True, exist_ok=True)
    for name in ('request.json', 'input.i16le', 'window.q15le'):
        shutil.copyfile(str(request_path.parent/name), str(output/name))
    samples = np.frombuffer((output/'input.i16le').read_bytes(), dtype='<i2').astype(np.int64)
    window = np.frombuffer((output/'window.q15le').read_bytes(), dtype='<i2').astype(np.int64)
    total, n = int(samples.sum()), request['fft_size']
    dc = (abs(total)//n)*(1 if total >= 0 else -1)
    values = ((samples-dc)*window) >> 15
    transformed = np.fft.rfft(values)
    powers = np.rint(transformed.real**2+transformed.imag**2).astype('<u8').tobytes()
    (output/'power.u64le').write_bytes(powers)
    response = dict(protocol=request['protocol'], request_id=request['request_id'],
                    input_sha256=request['input_sha256'], fft_size=n, bin_count=n//2+1,
                    output_kind='power_u64_le', output_order='natural', power_file='power.u64le',
                    power_sha256=digest(powers), status='complete', overflow=False,
                    backend='software_reference', fft_right_shift=0, power_right_shift=0)
    write_json(output/'response.json', response)
    spectrum = decode_response(request, response, output, allow_reference=True)
    write_json(output/'spectrum.json', spectrum)
    (output/'windowed.i16le').write_bytes(struct.pack('<%dh' % n, *values.tolist()))
    return spectrum


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = reference(args.request, args.out)
    print('SOFTWARE REFERENCE: N=%d peak_bin=%d frequency=%g Hz amplitude=%g Vpeak' % (
        result['fft_size'], result['peak_bin'], result['peak_frequency_hz'], result['peak_amplitude_vpeak']))
