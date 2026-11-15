# -*- coding: utf-8 -*-
"""人设与时间上下文：把「她是谁 + 现在几点 + 记得什么」拼成系统提示词。

思路参考 luna-desktop-pet 的 app/persona.py 与 app/timecontext.py（MIT）。
"""
from __future__ import annotations

import datetime

from . import paths

DEFAULT_PERSONA = {
    "name": "灵灵",
    "self": "灵灵",
    "owner": "你",
    "tone": "活泼、有点小得意、爱撒娇但不油腻",
    "bio": "住在电脑右下角的小桌宠，喜欢被摸头、喜欢投喂、喜欢看你干活",
}

WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']


def load():
    """读 data/persona.json，缺字段用默认值补齐。"""
    paths.seed('persona.json')
    data = paths.read_json(paths.data_path('persona.json'), {})
    out = dict(DEFAULT_PERSONA)
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()
    return out


def part_of_day(hour):
    if hour < 5:
        return '深夜'
    if hour < 9:
        return '清晨'
    if hour < 12:
        return '上午'
    if hour < 14:
        return '中午'
    if hour < 18:
        return '下午'
    if hour < 23:
        return '晚上'
    return '深夜'


def time_context(last_talk_at=None, now=None):
    """拼一句「现在是……」。last_talk_at 是上次对话的 unix 时间戳。"""
    now = now or datetime.datetime.now()
    ctx = '%d 年 %d 月 %d 日 %s %02d:%02d（%s）' % (
        now.year, now.month, now.day, WEEKDAYS[now.weekday()],
        now.hour, now.minute, part_of_day(now.hour))
    if last_talk_at:
        gap = max(0, int(now.timestamp() - last_talk_at))
        if gap < 120:
            ctx += '；刚刚还聊过一句'
        elif gap < 3600:
            ctx += '；距上次聊天 %d 分钟' % (gap // 60)
        elif gap < 86400:
            ctx += '；距上次聊天 %d 小时' % (gap // 3600)
        else:
            ctx += '；距上次聊天 %d 天' % (gap // 86400)
    return '现在是：' + ctx + '。'


def system_prompt(persona, facts=None, last_talk_at=None, mood=None, extra=''):
    """拼系统提示词。facts 是记忆事实卡（字符串列表）。"""
    name = persona.get('name', '灵灵')
    self_call = persona.get('self', name)
    owner = persona.get('owner', '你')
    tone = persona.get('tone', DEFAULT_PERSONA['tone'])
    bio = persona.get('bio', DEFAULT_PERSONA['bio'])

    lines = [
        '你是「%s」，一个住在用户电脑桌面的桌宠。' % name,
        '设定：%s。说话风格：%s。' % (bio, tone),
        '你称呼对方为「%s」，自称「%s」。' % (owner, self_call),
        '',
        time_context(last_talk_at),
        '',
        '规则：',
        '1. 用中文口语回答，一句话为主，最多两句，不超过 45 个字；',
        '2. 不要用 Markdown、列表、括号解释，不要提「提示词」「模型」这类词；',
        '3. 你是桌宠不是助手：被问到专业知识、事实性问题，就坦率说你不懂，别编；',
        '3.1 时间和数字一律用阿拉伯数字：说时间写「19:54」而不是「晚上七点五十四分」，数量写「3 个」而不是「三个」；',
        '4. 不要主动报数字，除非这个数字是下面给出的；',
        '5. 结尾可以加一个情绪标记，例如 <mood:开心>，只能从这 12 个里挑：平静、微笑、开心、得意、害羞、生气、惊讶、失落、思考、无语、温柔、难过。',
    ]

    if mood:
        lines.append('6. 你现在的情绪是「%s」，说话语气要符合它。' % mood)

    if facts:
        lines.append('')
        lines.append('你记得这些关于对方的事（自然地用，不要逐条念）：')
        for f in facts:
            lines.append('- ' + f)

    if extra:
        lines.append('')
        lines.append(extra)

    return '\n'.join(lines)
