"""Restricted DG4102 language; quantities must include explicit units."""
import re
from decimal import Decimal

INTENT = 'generator_control'
FREQ_UNIT = r'(?:兆赫兹|千赫兹|赫兹|兆赫茨|千赫茨|赫茨|M[hH][zZ]|[kK][hH][zZ]|[hH][zZ])'
AMP_UNIT = r'(?:毫伏峰峰值|豪伏峰峰值|伏峰峰值|mVpp|Vpp)'


def scaled(number, unit, decimal_text):
    value = Decimal(generator_number(number, decimal_text))
    scale = Decimal('1')
    if unit.startswith(('兆', 'M')):
        scale = Decimal('1000000')
    elif unit.startswith(('千', 'k', 'K')):
        scale = Decimal('1000')
    elif unit.startswith(('毫', '豪', 'm')):
        scale = Decimal('0.001')
    return float(value * scale)


def generator_number(token, decimal_text):
    """Also accept common sweep endpoints 一万/一百万 without changing old records."""
    if not any(c in token for c in '万亿'):
        return decimal_text(token)
    sign = '-' if token.startswith(('负', '-')) else ''
    token = token.lstrip('+-负正')
    for char, multiplier in (('亿', 100000000), ('万', 10000)):
        if char not in token:
            continue
        if token.count(char) != 1:
            raise ValueError('频率数字中的万、亿顺序无效。')
        head, tail = token.split(char)
        head_value = Decimal(decimal_text(head))
        if not head_value.is_finite() or head_value <= 0 or head_value != int(head_value):
            raise ValueError('万、亿前须为完整正整数。')
        if tail and not tail.startswith(('零', '〇', '0')) and not any(c in tail for c in '十百千万'):
            raise ValueError('一万二等数字有歧义，请说一万两千或一万零二。')
        tail_value = Decimal(generator_number(tail, decimal_text)) if tail else Decimal(0)
        if not 0 <= tail_value < multiplier:
            raise ValueError('频率数字单位顺序无效。')
        return sign + format(head_value*multiplier+tail_value, 'f')
    raise ValueError('频率数字无效。')


def validate_request(request):
    """Mirror the driver envelope before any USB call, including direct JSON."""
    import math
    if not isinstance(request, dict) or type(request.get('channel')) is not int or request['channel'] not in (1, 2):
        raise ValueError('信号发生器通道须为 1 或 2。')
    action = request.get('action')
    fields = {'status': set(), 'output': {'state'}, 'stop': set(), 'trigger': set(),
              'pause': set(), 'resume': set(), 'start_sweep': set(),
              'adjust_frequency': {'frequency_hz'}, 'adjust_amplitude': {'amplitude_vpp'},
              'sine': {'frequency_hz', 'amplitude_vpp', 'offset_v', 'load'},
              'sweep': {'start_hz', 'stop_hz', 'time_s', 'amplitude_vpp', 'offset_v', 'load', 'spacing', 'trigger'}}
    if action not in fields or set(request) - {'action', 'channel'} - fields[action]:
        raise ValueError('信号发生器动作或参数无效。')
    if action == 'output' and request.get('state') not in ('on', 'off'):
        raise ValueError('输出状态须为 on 或 off。')
    if action in ('adjust_frequency', 'adjust_amplitude'):
        name, low, high = ('frequency_hz',1e-6,100e6) if action == 'adjust_frequency' else ('amplitude_vpp',.02,10)
        value=request.get(name)
        if type(value) not in (int,float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('频率或峰峰值超出驱动允许的范围。')
        return request
    if action not in ('sine', 'sweep'):
        return request
    bounds = {'amplitude_vpp': (0.02, 10)}
    bounds.update({'frequency_hz': (1e-6, 100e6)} if action == 'sine' else
                  {'start_hz': (1e-6, 100e6), 'stop_hz': (1e-6, 100e6), 'time_s': (0.001, 300)})
    for name, (low, high) in bounds.items():
        value = request.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('%s 超出驱动范围或缺少数值。' % name)
    offset = request.get('offset_v', 0)
    load = request.get('load', 'highz')
    if type(offset) not in (int, float) or not math.isfinite(offset) or load not in ('highz', '50'):
        raise ValueError('偏置或负载设置无效。')
    if abs(offset) + request['amplitude_vpp']/2 > (5 if load == 'highz' else 2.5):
        raise ValueError('幅度加偏置超出驱动允许的电压范围。')
    maximum = request.get('frequency_hz', max(request.get('start_hz', 0), request.get('stop_hz', 0)))
    if maximum > 10e6 and (request['amplitude_vpp'] > 1 or offset != 0):
        raise ValueError('超过 10 MHz 时只允许不超过 1 Vpp，且偏置为零。')
    if action == 'sweep' and (request['start_hz'] == request['stop_hz'] or
                            request.get('spacing', 'lin') not in ('lin', 'log') or
                            request.get('trigger', 'int') not in ('int', 'man', 'ext')):
        raise ValueError('扫频端点须不同，间距或触发模式须有效。')
    return request


def parse_generator(text, num, decimal_text):
    """Return None for unrelated legacy commands; reject incomplete DG commands."""
    num = num.replace('百千', '百千万亿')
    channel = 2  # User-selected default HOST2 device output channel, not USB port number.
    match = re.match(r'(?:信号发生器)?(?:通道|CH)(一|二|1|2)', text, flags=re.I)
    if match:
        channel = 1 if match[1] in ('一', '1') else 2
        text = text[match.end():]
    aliases = {'查询信号发生器状态': 'status', '查看信号发生器状态': 'status', '信号发生器状态': 'status',
               '查询扫频状态': 'status', '查看扫频状态': 'status',
               '开始扫频': 'start_sweep', '暂停扫频': 'pause', '继续扫频': 'resume', '恢复扫频': 'resume',
               '停止扫频': 'stop', '停止信号发生器': 'stop', '触发扫频': 'trigger'}
    if text in aliases:
        return dict(intent=INTENT, request=dict(action=aliases[text], channel=channel), enable=False)
    outputs = {'开启信号输出': 'on', '打开信号输出': 'on', '关闭信号输出': 'off',
               '信号发生器开启输出': 'on', '信号发生器关闭输出': 'off'}
    if text in outputs:
        return dict(intent=INTENT, request=dict(action='output', channel=channel, state=outputs[text]), enable=False)
    change = re.fullmatch(rf'(?:设置|修改)(?:信号发生器)(频率|峰峰值)(?:为|是|等于)?({num})'
                          rf'({FREQ_UNIT}|毫伏|豪伏|伏|mVpp|Vpp|mV|V)', text)
    if change:
        quantity, number, unit = change.groups()
        frequency = quantity == '频率'
        if not re.fullmatch(FREQ_UNIT if frequency else r'(?:毫伏|豪伏|伏|mVpp|Vpp|mV|V)', unit):
            raise ValueError('信号发生器频率需要 Hz 单位，峰峰值需要电压单位。')
        request = dict(action='adjust_frequency' if frequency else 'adjust_amplitude', channel=channel)
        request['frequency_hz' if frequency else 'amplitude_vpp'] = scaled(number,unit,decimal_text)
        validate_request(request)
        return dict(intent=INTENT, request=request, enable=False)
    # Explicit labels make missing, duplicate, and dimensionally wrong fields reject.
    sep = r'[,，、;；]*'
    sweep = re.fullmatch(rf'(配置|设置|开始)(线性|对数)?扫频{sep}(?:起始频率|从)({num})({FREQ_UNIT}){sep}'
                         rf'(?:终止频率|结束频率|到)({num})({FREQ_UNIT}){sep}'
                         rf'(?:扫频时间|时间)({num})秒{sep}(?:幅度|幅值)({num})({AMP_UNIT})', text)
    if sweep:
        verb, spacing, start, su, stop, eu, seconds, amp, au = sweep.groups()
        request = dict(action='sweep', channel=channel, start_hz=scaled(start, su, decimal_text),
                       stop_hz=scaled(stop, eu, decimal_text), time_s=float(generator_number(seconds, decimal_text)),
                       amplitude_vpp=scaled(amp, au, decimal_text), offset_v=0, load='highz',
                       spacing='log' if spacing == '对数' else 'lin', trigger='int')
        validate_request(request)
        return dict(intent=INTENT, request=request, enable=verb == '开始')
    sine = re.fullmatch(rf'(?:设置|配置)(?:信号发生器)?正弦波{sep}(?:频率)?({num})({FREQ_UNIT}){sep}'
                        rf'(?:幅度|幅值)({num})({AMP_UNIT})', text)
    if sine:
        frequency, fu, amp, au = sine.groups()
        request = dict(action='sine', channel=channel, frequency_hz=scaled(frequency, fu, decimal_text),
                       amplitude_vpp=scaled(amp, au, decimal_text), offset_v=0, load='highz')
        validate_request(request)
        return dict(intent=INTENT, request=request, enable=False)
    if any(word in text for word in ('扫频', '信号发生器', '信号输出', '正弦波')):
        raise ValueError('信号发生器指令不完整。例：配置扫频起始频率一百赫兹终止频率十千赫兹时间五秒幅度一伏峰峰值。幅度须明确为峰峰值。')
    return None


def describe_request(request, enable=False):
    validate_request(request)
    head = 'DG4102 HOST2，CH%d：' % request['channel']
    action = request['action']
    if action == 'adjust_frequency':
        return head + '将固定正弦波频率改为 %g Hz；先回读其余参数供核对，配置后输出关闭。' % request['frequency_hz']
    if action == 'adjust_amplitude':
        return head + '将峰峰值改为 %g Vpp；先回读并保留当前模式及已回读参数，配置后输出关闭。' % request['amplitude_vpp']
    if action == 'sweep':
        text = '%g → %g Hz，%g 秒，%s扫频，%g Vpp，偏置 %g V，负载设置 %s，内部触发。' % (
            request['start_hz'], request['stop_hz'], request['time_s'],
            '对数' if request.get('spacing', 'lin') == 'log' else '线性', request['amplitude_vpp'],
            request.get('offset_v', 0), request.get('load', 'highz'))
        return head + text + ('确认后配置并开启输出。' if enable else '确认后配置，保持输出关闭。')
    if action == 'sine':
        return head + '正弦波 %g Hz，%g Vpp，偏置 %g V，负载设置 %s；确认后配置，保持输出关闭。' % (
            request['frequency_hz'], request['amplitude_vpp'], request.get('offset_v', 0), request.get('load', 'highz'))
    return head + {'status': '查询状态，不改变设置。', 'pause': '暂停扫频：关闭输出，保留配置；扫频内部时序可能继续。',
                   'resume': '按当前扫频进度恢复输出，不保证从暂停位置继续。', 'start_sweep': '使用上次成功配置重新开始扫频。',
                   'stop': '停止扫频：关闭输出并关闭扫频模式。', 'trigger': '发送一次手动扫频触发；返回不代表扫频完成。',
                   'output': '开启当前配置的输出。' if request.get('state') == 'on' else '关闭输出，保留当前模式。'}[action]
