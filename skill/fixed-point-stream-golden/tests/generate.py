"""Regenerate fixed FIR coefficients, independent integer oracle and response metrics."""
from pathlib import Path
import json
import numpy as np
from scipy.signal import firwin, freqz

ROOT = Path(__file__).resolve().parents[1]
h = firwin(127, 7200, fs=44100, window=('kaiser', 7.5))
q = np.rint(h * 131072).astype(np.int64)
q[63] += 131072 - int(q.sum())
lines = ['function signed [17:0] coefficient;', 'input [6:0] index;', 'begin case(index)']
lines += ["7'd%d: coefficient = 18'h%05x;" % (i, int(v) & 0x3ffff) for i, v in enumerate(q)]
lines += ["default: coefficient = 0;", 'endcase end', 'endfunction']
(ROOT/'rtl/fir_coeff.vh').write_text('\n'.join(lines)+'\n', encoding='ascii')
(ROOT/'tests/coefficients.json').write_text(json.dumps(q.tolist()), encoding='ascii')
w, z = freqz(q/131072, worN=65536, fs=44100)
db = 20*np.log10(np.maximum(abs(z), 1e-15))
metrics = {'sample_rate':44100, 'taps':127, 'coefficient_bits':18, 'fractional_bits':17,
           'passband_100_to_6400_min_db':float(db[(w>=100)&(w<=6400)].min()),
           'passband_100_to_6400_max_db':float(db[(w>=100)&(w<=6400)].max()),
           'stopband_8000_up_max_db':float(db[w>=8000].max()),
           'fir_group_delay_ms':63/44100*1000, 'coefficient_l1':float(abs(q).sum()/131072)}
(ROOT/'tests/filter_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='ascii')

def clip(x):
    return max(-8388608, min(8388607, x))

rng = np.random.default_rng(20261102)
hist = [[0]*127 for _ in range(8)]
px, py = [0]*8, [0]*8
inputs, expected = [], []
for n in range(6000):
    ch = n % 2 if n < 4000 else n % 8
    # Channel separation, impulse, DC settling, clipping, random words and metadata.
    if n < 400: x = 4000000 if n == 0 else 0
    elif n < 2000: x = 2000000 if ch == 0 else -1000000
    elif n < 3000: x = 8388607 if (n//2)%2 else -8388608
    elif n < 4000: x = 0
    else: x = int(rng.integers(-8388608, 8388608))
    invalid = int(n >= 4000 and n % 31 == 0)
    flags = int(rng.integers(0, 8)) << 29 | invalid << 28
    word = flags | (x & 0xffffff) << 4 | (n % 16)
    if invalid: result = word
    else:
        dc = clip(x - px[ch] + py[ch] - (py[ch] >> 7))
        px[ch], py[ch] = x, dc
        hist[ch] = [dc] + hist[ch][:-1]
        acc = sum(int(a)*int(b) for a,b in zip(hist[ch],q))
        y = clip((acc + 65536) >> 17)
        result = (word & 0x7000000f) | ((y & 0xffffff) << 4)
        parity = bin(result >> 4).count('1') & 1
        result |= parity << 31
    inputs.append('%09x' % (ch << 32 | word))
    expected.append('%09x' % (ch << 32 | result))
(ROOT/'tests/input.hex').write_text('\n'.join(inputs)+'\n', encoding='ascii')
(ROOT/'tests/expected.hex').write_text('\n'.join(expected)+'\n', encoding='ascii')
print(json.dumps(metrics, indent=2))
