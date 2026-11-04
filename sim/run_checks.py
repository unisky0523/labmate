#!/usr/bin/env python3
"""Run the existing offline ARM tests on restored sources; no board is accessed."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(ROOT/'sim/results'))
    parser.add_argument('--workspace', help='Optional external workspace to retain prepared files')
    args = parser.parse_args()
    results = Path(args.out).resolve()
    results.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('labmate_prepare', str(ROOT/'build/prepare.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    temporary = None
    if args.workspace:
        workspace = Path(args.workspace).resolve()
    else:
        temporary = tempfile.TemporaryDirectory(prefix='labmate_checks_')
        workspace = Path(temporary.name)
    module.prepare(workspace, ['arm'])
    arm = workspace/'arm'
    suites = [
        ('arm_ui', arm, ['-m', 'unittest', 'discover', '-s', 'work/labmate_ui/tests', '-v']),
        ('dg4102', arm/'work/labmate_ui/dg4102_driver', ['-m', 'unittest', 'c_instrument.test_dg4102', 'c_instrument.test_dg4102_board', '-v']),
        ('voice_cli', arm/'reference/voice_cli', ['-m', 'unittest', 'discover', '-s', 'tests', '-v']),
    ]
    record = {'date': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
              'python': sys.version, 'board_accessed': False, 'suites': []}
    task_temp = workspace/'test_tmp'
    task_temp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               TEMP=str(task_temp), TMP=str(task_temp), TMPDIR=str(task_temp))
    try:
        for name, cwd, arguments in suites:
            command = [sys.executable, '-B'] + arguments
            process = subprocess.run(command, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, encoding='utf-8', errors='replace')
            log = results/(name+'.log')
            log.write_text(process.stdout, encoding='utf-8')
            match = re.search(r'Ran (\d+) tests? in ', process.stdout)
            summaries = re.findall(r'(?m)^(?:OK[^\n]*|FAILED[^\n]*)$', process.stdout)
            status = {'name': name, 'exit_code': process.returncode,
                      'tests': int(match.group(1)) if match else None, 'log': log.name,
                      'summary': summaries[-1].strip() if summaries else 'No unittest summary'}
            record['suites'].append(status)
            print(json.dumps(status), flush=True)
        record['passed'] = all(s['exit_code']==0 for s in record['suites'])
        (results/'local_checks.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return 0 if record['passed'] else 1
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == '__main__':
    sys.exit(main())
