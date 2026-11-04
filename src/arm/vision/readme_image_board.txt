LabMate ARM image-reader test kit

This kit uses the same PP-OCRv5 mobile model weights as the PC reference,
converted to Paddle-Lite. It accepts a complete image, automatically finds
the Keysight screen/sidebar, detects text, reads measurement or cursor rows,
and writes JSON. Cursor rows currently cover Delta X, 1/Delta X, and Delta Y;
the bottom X1/X2/Y1/Y2 menu is not parsed.
Its Python geometry and validation code is shared with the PC pipeline.
The board runtime and accuracy still require testing on the physical board.
IMPORTANT: the bundled smoke_infer is too new for the reviewed factory rootfs
(glibc 2.30). Rebuild it with the board SDK/sysroot before use; see
BUILD_BOARD.txt. The board may also need pyclipper and libgomp.so.1.

On board Linux, unpack into a directory. Python needs numpy, cv2, pyclipper.
From that directory:
  python3 -c 'import numpy, cv2, pyclipper'
  ldd ./smoke_infer
  chmod +x smoke_infer
  export LD_LIBRARY_PATH="$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  python3 -m c_vision_lite.board_reader --image sample.jpg --bundle . --out runs
  python3 -m c_vision_lite.board_reader --image sample_cursor.jpg --bundle . --out runs

Then replace the sample path with a board-captured JPEG or PNG:
  python3 -m c_vision_lite.board_reader --image /path/to/photo.jpg --bundle . --out runs

For a camera frame, use --camera 0 (or --camera /dev/video0):
  python3 -m c_vision_lite.board_reader --camera 0 --bundle . --out runs

The caller may pass --request-id UUID to correlate a B-side voice command.
Any invalid reading returns valid=false in JSON and exit code 2.

The printed JSON and runs/<timestamp>_<request-id-prefix>/reading.json contain
all rows. --camera saves and processes one frame; alternatively, another
capture process can save a JPEG or PNG and pass its path via --image.
No manual ROI coordinates are required.

If the process fails, return the command output, free -m, and the run folder.
For a memory probe, add --detector-size 512; this changes input resolution
and needs a separate accuracy comparison. The default is 960.
