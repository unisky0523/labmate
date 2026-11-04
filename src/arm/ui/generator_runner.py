"""Isolated CLI bridge to C's unchanged DG driver; one lock spans config + on.

Never imported in the ASR process. USB operations use the driver's per-query
timeouts; no kill/retry loop or desktop VISA dependency is introduced.
"""
import argparse
import json
from pathlib import Path
import sys

STATE_KEYS = ('output', 'load', 'waveform', 'frequency_hz', 'amplitude_unit',
              'amplitude', 'offset_v', 'sweep', 'start_hz', 'stop_hz', 'time_s', 'spacing', 'trigger')


def execute_job(job, board, driver):
    from asr_runtime.generator_commands import validate_request
    if not isinstance(job, dict) or set(job) - {'request', 'enable', 'expected_state', 'response_capture'}:
        raise ValueError('Invalid generator job')
    request = dict(validate_request(job['request']))
    enable = job.get('enable', False)
    if type(enable) is not bool or (enable and request['action'] != 'sweep'):
        raise ValueError('Only an explicit sweep start may configure and enable')
    steps = []
    observer = None
    def call(value):
        raw = driver.execute(value)
        steps.append(raw)
        if not (raw.get('status') == 'complete' and raw.get('valid') is True
                and raw.get('simulated') is False and raw.get('identity_verified') is True):
            raise RuntimeError(raw.get('error_code', 'DG_FAILED') + ': ' + raw.get('detail', 'DG request failed'))
        identity = raw.get('identity', '').split(',')
        if len(identity) < 4 or identity[2].strip() != board.EXPECTED_SERIAL:
            raise RuntimeError('DEVICE_IDENTITY_MISMATCH: serial does not match HOST2 binding')
        return raw
    try:
        with board.device_lock(driver.config_path):
            binding = board.load_binding(driver.config_path)
            row = board.select_device(board.devices(), binding['serial'], binding['usb_route'])
            driver.resource = board.visa_resource(row, driver.usb_resources('@py'))
            action, channel = request['action'], request['channel']
            if ('expected_state' in job or action in ('pause', 'resume')
                    or (action == 'output' and request['state'] == 'on')):
                state = call(dict(action='status', channel=channel))['state']
                if action in ('pause', 'resume') and state['sweep'] != 'ON':
                    raise RuntimeError('SWEEP_NOT_CONFIGURED: stop clears sweep; use start sweep to configure again')
                if 'expected_state' in job or action == 'resume' or request.get('state') == 'on':
                    expected = job.get('expected_state')
                    if not isinstance(expected, dict) or any(state.get(k) != expected.get(k) for k in STATE_KEYS):
                        raise RuntimeError('STATE_CHANGED: generator settings changed after review; query and confirm again')
                request = dict(action='output', channel=channel,
                               state='off' if action == 'pause' else 'on') if action in ('pause', 'resume') else request
            raw = call(request)
            if enable:
                # The configure step must be a real complete OFF readback first.
                if raw['state']['output'] != 'OFF' or raw['state']['sweep'] != 'ON':
                    raise RuntimeError('READBACK_MISMATCH: configured sweep not verified OFF')
                if job.get('response_capture'):
                    from sweep_response import start_observer, mark_start
                    observer = start_observer(job['response_capture'])
                    mark_start(observer)
                raw = call(dict(action='output', channel=channel, state='on'))
                if observer:
                    from fft_protocol import write_json
                    write_json(Path(observer['directory'])/'control.json', dict(valid=True))
            return dict(device_id='rigol_dg4102', source='scpi', status='complete', valid=True,
                        simulated=False, identity_verified=True, electrical_output_verified=False,
                        request=job['request'], enable=enable, state=raw['state'], steps=steps,
                        completed_at=raw.get('completed_at'), host2_binding=binding,
                        response_capture=observer)
    except Exception as error:
        return dict(device_id='rigol_dg4102', source='scpi', status='failed', valid=False,
                    simulated=False, electrical_output_verified=False, request=job['request'],
                    enable=enable, steps=steps, error_code=getattr(error, 'code', 'DG_CONTROL_FAILED'),
                    detail=str(error), state_unknown=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--job', required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    sys.path[:0] = [str(root/'c_instrument/vendor'), str(root)]
    sys.path.append(str(root/'c_instrument/compat_py37'))
    from c_instrument import dg4102, dg4102_board
    class Driver:
        config_path = root/'c_instrument/board_config/dg4102_host2.json'
        resource = None
        usb_resources = staticmethod(dg4102.usb_resources)
        def execute(self, request):
            return dg4102.execute(request, resource=self.resource, backend='@py', timeout_ms=3000)
    result = execute_job(json.loads(args.job), dg4102_board, Driver())
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0 if result['valid'] else 2


if __name__ == '__main__':
    sys.exit(main())
