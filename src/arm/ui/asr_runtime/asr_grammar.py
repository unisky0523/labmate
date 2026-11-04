"""Small domain corpus for Vosk's runtime bigram language model."""

import json
from main import METRIC_PREFIXES


LEGACY_WORDS = [
    "读取", "数据", "记录", "保存", "连续", "每", "隔", "秒",
    "一次", "两次", "三次", "五次", "共", "当前", "电压", "电流",
    "伏", "安", "点", "零", "一", "二", "三", "四", "五", "六",
    "七", "八", "九", "十", "百", "千", "负", "上", "一条",
    "有", "问题", "撤销", "确认", "取消", "帮助", "退出",
    "拍", "拍摄", "拍照", "照片", "波形", "屏幕", "摄像头", "看",
    "状态", "存", "留下", "[unk]",
]
LEGACY_JSON = json.dumps(LEGACY_WORDS, ensure_ascii=False)

PHRASES = [
    "读取 数据", "读取 当前 数据", "读 一下 数据", "记录 数据",
    "记录 一下 当前 数据", "保存 数据", "查看 记录", "查看 上 一条 记录",
    "查看 最近 记录", "上 一条 数据 有 问题", "撤销 上 一条 记录",
    "撤销 上 一条 数据", "作废 上 一条 数据",
    "拍 一下 波形", "拍摄 波形", "调用 摄像头 拍摄 一下 波形",
    "保存 波形", "保存 当前 波形", "当前 状态",
    "停止 记录", "帮助", "退出 程序", "确认", "确认 保存", "取消", "[unk]",
    "记录 电压 负 一 点 二 伏", "记录 电流 负 一 点 二 安",
    "记录 电压 十二 伏", "记录 电压 十 二 伏",
    "记录 电压 一 百 零 二 伏", "记录 电流 一 千 零 二 安",
    "请 帮 我 读取 数据", "帮 我 记录 数据", "请 帮 我 连续 记录 五 次 数据",
]
DIGITS = "零 一 二 三 四 五 六 七 八 九".split()
for digit in DIGITS + ["两", "十"]:
    PHRASES.extend([
        "连续 记录 %s 次 数据" % digit,
        "每 隔 %s 秒 记录 一 次 共 三 次" % digit,
    ])

# Vosk builds a bigram grammar: vary both numeric positions, rather than
# constraining a batch to three readings or to a one-second interval.
def spoken_integer(value):
    if value < 10:
        return DIGITS[value]
    if value == 100:
        return "一 百"
    tens, units = divmod(value, 10)
    return ("" if tens == 1 else DIGITS[tens] + " ") + "十" + (" " + DIGITS[units] if units else "")


for count in range(1, 101):
    number = spoken_integer(count)
    PHRASES.extend([
        "连续 记录 %s 次 数据" % number,
        "连续 记录 %s 次 数据 时间 间隔 一 秒" % number,
        "每 隔 一 秒 记录 一 次 共 %s 次" % number,
    ])
for seconds in [spoken_integer(n) for n in range(61)] + ["两", "零 点 五", "一 点 五", "二 点 五"]:
    PHRASES.extend([
        "连续 记录 三 次 数据 时间 间隔 %s 秒" % seconds,
        "连续 记录 三 次 数据 间隔 %s 秒" % seconds,
        "每 隔 %s 秒 记录 一 次 共 三 次" % seconds,
    ])
for first in DIGITS:
    for second in DIGITS:
        PHRASES.append(
            "记录 电压 %s 点 %s %s 伏 电流 %s 点 %s 安"
            % (first, first, second, second, first))

# Checked against the installed model's actual word IDs: 毫 and the joined
# units are absent. 豪 is an exact homophone; text_cli restores it only in a
# measurement unit. Every unit below uses known individual model words.
UNIT_CONTEXT_GRAMMARS = {}
manual_phrases = []
for quantity, bases in [('电压', ('伏', '伏 特')), ('电流', ('安', '安 培')), ('频率', ('赫 兹',))]:
    phrases = ['[unk]']
    for chinese, _ in METRIC_PREFIXES:
        for base in bases:
            spoken_prefix = '豪' if chinese == '毫' else chinese
            unit = (spoken_prefix + ' ' if chinese else '') + base
            for value in DIGITS + ['两', '十', '十 二', '一 百', '一 千', '零 点 一', '一 点 五', '负 一 点 二']:
                phrases.extend([
                    '记录 %s %s %s' % (quantity, value, unit),
                    '%s %s %s' % (quantity, value, unit),
                ])
            # A decimal can have any number of spoken digits, and quantities
            # can be combined; the full parser still checks the whole sentence.
            for digit in DIGITS:
                phrases.append('记录 %s 一 点 %s %s' % (quantity, digit, unit))
                phrases.append('记录 %s 零 点 %s 一 %s' % (quantity, digit, unit))
    manual_phrases.extend(phrases[1:])
    UNIT_CONTEXT_GRAMMARS[quantity] = json.dumps(phrases, ensure_ascii=False)
PHRASES.extend(manual_phrases)
PHRASES.extend([
    '记录 电压 三 点 三 伏 电流 一 豪 安 频率 一 千 赫 兹',
    '记录 电流 一 豪 安 电压 三 点 三 伏',
    '记录 频率 一 千 赫 兹 电压 三 点 三 伏',
])

# DG4102 control vocabulary is separate from spoken measurement records.
# Use individual model words; unknown tokens are checked on the target model.
GENERATOR_PHRASES = [
    '查询 信号 发生器 状态', '查看 信号 发生器 状态', '信号 发生器 状态',
    '查询 扫 频 状态', '开始 扫 频', '暂停 扫 频', '继续 扫 频', '恢复 扫 频',
    '停止 扫 频', '停止 信号 发生器', '触发 扫 频',
    '开启 信号 输出', '打开 信号 输出', '关闭 信号 输出',
    '通道 二 开始 扫 频', '通道 二 停止 扫 频',
    '设置 信号 发生器 频率 为 五 千 赫 兹',
    '设置 信号 发生器 峰 峰 值 一 伏',
    '配置 扫 频 起始 频率 一 百 赫 兹 终止 频率 一 万 赫 兹 时间 五 秒 幅度 一 伏 峰 峰 值',
    '配置 扫 频 起始 频率 一 万 赫 兹 终止 频率 一 百 万 赫 兹 时间 五 秒 幅度 一 伏 峰 峰 值',
]
for mode in ('', '线性 ', '对数 '):
    for verb in ('配置', '设置', '开始'):
        GENERATOR_PHRASES.append(
            '%s %s扫 频 起始 频率 一 百 赫 兹 终止 频率 十 千 赫 兹 时间 五 秒 幅度 一 伏 峰 峰 值' % (verb, mode))
for digit in DIGITS + ['两', '十', '一 百', '十 二', '一 点 五', '零 点 一']:
    GENERATOR_PHRASES.extend([
        '设置 信号 发生器 频率 为 %s 千 赫 兹' % digit,
        '设置 信号 发生器 频率 %s 赫 兹' % digit,
        '修改 信号 发生器 峰 峰 值 为 %s 伏' % digit,
        '设置 信号 发生器 峰 峰 值 %s 豪 伏' % digit,
    ])
    for prefix in ('', '千 ', '兆 '):
        GENERATOR_PHRASES.extend([
            '配置 扫 频 从 %s %s赫 兹 到 十 千 赫 兹 扫 频 时间 五 秒 幅度 一 伏 峰 峰 值' % (digit, prefix),
            '配置 扫 频 起始 频率 一 百 赫 兹 终止 频率 %s %s赫 兹 时间 五 秒 幅度 一 伏 峰 峰 值' % (digit, prefix),
            '设置 正弦 波 频率 %s %s赫 兹 幅度 一 伏 峰 峰 值' % (digit, prefix),
        ])
    for prefix in ('', '豪 '):
        GENERATOR_PHRASES.append(
            '配置 扫 频 起始 频率 一 百 赫 兹 终止 频率 十 千 赫 兹 时间 五 秒 幅度 %s %s伏 峰 峰 值' % (digit, prefix))
    GENERATOR_PHRASES.append(
        '配置 扫 频 起始 频率 一 百 赫 兹 终止 频率 十 千 赫 兹 时间 %s 秒 幅度 一 伏 峰 峰 值' % digit)
PHRASES.extend(GENERATOR_PHRASES)
PHRASES.extend(['频 谱 分析', '分析 频 谱', '波形 频 谱 分析', '分析 波形',
                '开始 频 谱 分析', '进行 频 谱 分析'])
GRAMMAR_JSON = json.dumps(PHRASES, ensure_ascii=False)
# The GUI listens with this smaller vocabulary only while a result is pending.
SAVE_CONFIRM_GRAMMAR_JSON = json.dumps([
    "确认", "确认 保存", "取消", "[unk]",
], ensure_ascii=False)
CONFIRM_GRAMMAR_JSON = json.dumps([
    "可以", "好的", "是 的", "确认", "确认 保存", "行", "没 问题",
    "不 行", "不 可以", "不 是", "不 对", "取消", "重说", "再 说 一遍",
    "[unk]",
], ensure_ascii=False)


def load_grammar(path):
    """A supplied file is a UTF-8 JSON array of space-tokenized phrases."""
    return json.dumps(json.loads(path.read_text(encoding="utf-8-sig")), ensure_ascii=False)
