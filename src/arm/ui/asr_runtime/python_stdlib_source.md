# Project-local Python 3.7.6 standard-library compatibility files

Sources: CPython v3.7.6 official repository.
- https://github.com/python/cpython/blob/v3.7.6/Lib/wave.py
- https://github.com/python/cpython/blob/v3.7.6/Lib/chunk.py
- https://github.com/python/cpython/blob/v3.7.6/LICENSE

chunk.py is unmodified. wave.py only defers the audioop import to big-endian systems: its two audioop.byteswap calls are already inside big-endian branches. This avoids requiring the audioop extension on the little-endian Navigator board. No new ARM binary is included. These modules live in the application directory and do not replace system Python files. See PYTHON_STDLIB_LICENSE.txt.

After copying to the board, enter the application directory and run:

```sh
python3 -c "import wave, chunk; print(wave.__file__); print(chunk.__file__)"
python3 -u board_app.py --source mock --no-vosk
```
