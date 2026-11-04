"""Temporary host-only VM build exchange; serves only this task's source."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse
import json
from pathlib import Path
import uuid
import zipfile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--task', choices=['fft_integration_20261103', 'history_image_preview_20261102', 'voice_confirm_20261102', 'desktop_entry_20261102', 'record_management_20261102', 'voice_calibration_20261102'],
                    default='history_image_preview_20261102')
args = parser.parse_args()
marker = (b'LABMATE_UI_FFT_V1' if args.task == 'fft_integration_20261103' else
          b'LABMATE_UI_VOICE_CALIBRATION_V1' if args.task == 'voice_calibration_20261102' else
          b'LABMATE_UI_RECORD_EDIT_V1' if args.task == 'record_management_20261102' else
          b'LABMATE_DESKTOP_ENTRY_V1' if args.task == 'desktop_entry_20261102' else
          b'LABMATE_UI_VOICE_CONFIRM_V1' if args.task == 'voice_confirm_20261102'
          else b'LABMATE_UI_IMAGE_PREVIEW_V1')
folder = root/'work'/args.task
folder.mkdir(exist_ok=True)
token = uuid.uuid4().hex
base = 'http://192.168.80.1:8765/' + token
source = root/('work/vendor_desktop_labmate' if args.task == 'desktop_entry_20261102' else 'work/labmate_ui')
project = 'QMainUI.pro' if args.task == 'desktop_entry_20261102' else 'labassistant.pro'
binary_name = 'QMainApp' if args.task == 'desktop_entry_20261102' else 'labassistant'
archive_path = folder/'preview_source.zip'
with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in source.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            archive.write(path, path.relative_to(source).as_posix())
guest = '''import io, pathlib, subprocess, urllib.request, zipfile
base = BASE_URL
root = pathlib.Path.home() / GUEST_FOLDER
source = root / 'source'
build = root / 'arm'
source.mkdir(parents=True, exist_ok=True)
build.mkdir(parents=True, exist_ok=True)
print('Downloading current source...', flush=True)
with zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(base+'/source.zip', timeout=15).read())) as archive:
    archive.extractall(str(source))
command = 'source /home/labmat/petalinux_sdk_2020_2/environment-setup-cortexa9t2hf-neon-xilinx-linux-gnueabi && qmake '+str(source/PROJECT_NAME)+' && make -j2'
print('Building updated ARM Qt interface...', flush=True)
log = root / 'build.log'
with log.open('wb') as stream:
    result = subprocess.call(['bash', '-c', command], cwd=str(build), stdout=stream, stderr=subprocess.STDOUT)
data = log.read_bytes()
urllib.request.urlopen(base+'/log', data, timeout=15).read()
if result:
    print(data.decode('utf-8', 'replace')[-5000:])
    raise SystemExit(result)
binary = (build/BINARY_NAME).read_bytes()
print(urllib.request.urlopen(base+'/binary', binary, timeout=30).read().decode())
print('Build completed and returned to Windows.', flush=True)
'''.replace('BASE_URL', repr(base)).replace('GUEST_FOLDER', repr('labmate_ui_' + args.task)).replace('PROJECT_NAME', repr(project)).replace('BINARY_NAME', repr(binary_name)).encode('utf-8')
(folder/'build_command.txt').write_text('python3 -c "import urllib.request;exec(urllib.request.urlopen(\''+base+'/build.py\').read())"', encoding='utf-8')

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/'+token+'/build.py':
            content = guest
        elif self.path == '/'+token+'/source.zip':
            content = archive_path.read_bytes()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path not in ('/'+token+'/binary', '/'+token+'/log'):
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 8000000:
            self.send_error(413)
            return
        content = self.rfile.read(length)
        if self.path.endswith('/binary'):
            if (content[:5] != b'\x7fELF\x01' or int.from_bytes(content[18:20], 'little') != 40
                    or marker not in content):
                self.send_error(400, 'Expected matching ARM executable')
                return
            (folder/binary_name).write_bytes(content)
            print('ARM_PREVIEW_RECEIVED', len(content), flush=True)
        else:
            (folder/'build.log').write_bytes(content)
            print('BUILD_LOG_RECEIVED', len(content), flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

print('BUILD_EXCHANGE_READY', flush=True)
HTTPServer(('192.168.80.1', 8765), Handler).serve_forever()
