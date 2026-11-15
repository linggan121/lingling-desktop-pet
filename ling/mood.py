# -*- coding: utf-8 -*-
"""情绪解析：从模型的回复里抠出情绪标记，并兜底猜一个。

思路来自 luna-desktop-pet 的 app/mood.py（MIT License, © 2026 Elysia20230），
按灵灵的 9 行动作做了简化：不换表情图，只用来挑动作。

三件事：
  1. 认 <mood:害羞> / [[mood:害羞]] / 【情绪：害羞】 等多种写法，并把它从正文里删掉；
  2. 模型忘了写标记时，用关键词猜一个；
  3. 把各种情绪词归一化到 12 档。
"""
from __future__ import annotations

import re

EMOTIONS = ["平静", "微笑", "开心", "得意", "害羞", "生气", "惊讶", "失落", "思考", "无语", "温柔", "难过"]

SYNONYMS = {
    "平静": ["平静", "平淡", "neutral", "default", "usual", "冷静"],
    "微笑": ["微笑", "轻笑", "浅笑", "smile", "含笑", "愉悦"],
    "开心": ["开心", "高兴", "快乐", "happy", "大笑", "欢喜", "兴奋"],
    "得意": ["得意", "自豪", "欣慰", "proud", "自信", "傲然", "神气"],
    "害羞": ["害羞", "脸红", "羞", "臊", "shy", "blush", "难为情", "娇羞"],
    "生气": ["生气", "恼", "怒", "angry", "愠", "不满", "发脾气", "凶"],
    "惊讶": ["惊讶", "吃惊", "意外", "surprise", "震惊", "诧异"],
    "失落": ["失落", "沮丧", "低落", "sad", "郁闷", "消沉"],
    "思考": ["思考", "沉吟", "think", "沉思", "琢磨"],
    "无语": ["无语", "无奈", "speechless", "汗", "扶额", "吐槽"],
    "温柔": ["温柔", "柔和", "怜爱", "gentle", "轻柔", "宠溺"],
    "难过": ["难过", "悲伤", "委屈", "哭泣", "cry", "伤心", "哽咽"],
}

# 情绪 -> 动作（灵灵只有 9 行动作，只能用动作表达情绪）
# 行号含义见 assets/frames.json：0 待机 1 右跑 2 左跑 3 坐 4 招手 5 跳舞 6 抱胸 7 加油 8 笑
EMOTION_ACTS = {
    "平静": dict(row=0, fps=3, loop=True),
    "微笑": dict(row=8, fps=4, loop=False),
    "开心": dict(row=8, fps=5, loop=False),
    "得意": dict(row=7, fps=3, loop=True),
    "害羞": dict(row=3, fps=4, loop=True),
    "生气": dict(row=6, fps=3, loop=True),
    "惊讶": dict(row=4, fps=8, loop=False),
    "失落": dict(row=3, fps=3, loop=True),
    "思考": dict(row=6, fps=2, loop=True),
    "无语": dict(row=6, fps=3, loop=True),
    "温柔": dict(row=8, fps=3, loop=False),
    "难过": dict(row=3, fps=3, loop=True),
}

_MOOD_KEYS = '情绪|心情|表情|mood|emotion'
_PATTERNS = [
    re.compile(r'<\s*(' + _MOOD_KEYS + r')\s*[:：]\s*([^>\n]{1,12})\s*>', re.IGNORECASE),
    re.compile(r'\[\[\s*(' + _MOOD_KEYS + r')\s*[:：]\s*([^\]\n]{1,12})\s*\]\]', re.IGNORECASE),
    re.compile(r'[【\[]\s*(' + _MOOD_KEYS + r')\s*[:：]\s*([^】\]\n]{1,12})\s*[】\]]', re.IGNORECASE),
]
_DEFAULT = '平静'


def normalize(emotion):
    """把任意情绪词归一化成 12 档之一；认不出来返回 None。"""
    text = (emotion or '').strip().strip('。.!！~～、 ')
    if not text:
        return None
    if text in EMOTIONS:
        return text
    lowered = text.lower()
    for canonical, words in SYNONYMS.items():
        for word in words:
            if word.lower() in lowered:
                return canonical
    return None


def parse(raw_text):
    """返回 (干净的正文, 情绪或 None)。"""
    if not raw_text:
        return '', None
    text = raw_text
    found = None
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            candidate = normalize(match.group(2))
            if candidate and not found:
                found = candidate
        text = pattern.sub('', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text, found


def guess(text):
    """没有标记时按词儿猜一个，保证一定有情绪。"""
    if not text:
        return _DEFAULT
    t = text
    if any(k in t for k in ('对不起', '抱歉', '呜', '原谅')):
        return '难过'
    if any(k in t for k in ('哼', '笨蛋', '讨厌', '不许', '闭嘴')):
        return '生气'
    if any(k in t for k in ('……', '...', '不必', '随你', '无所谓')):
        return '无语'
    if any(k in t for k in ('是嘛', '哦？', '有趣', '当然', '自然', '区区', '本灵灵')):
        return '得意'
    if any(k in t for k in ('诶', '欸', '真的吗', '怎么会', '骗人')):
        return '惊讶'
    if any(k in t for k in ('让我想想', '怎么办', '大约', '琢磨')):
        return '思考'
    if any(k in t for k in ('呢', '吧', '嘛')) and t.endswith(('。', '～', '~', '呀')):
        return '温柔'
    return '微笑'


def to_emotion(cleaned_emotion, text):
    return normalize(cleaned_emotion or '') or guess(text)


def act_for(emotion):
    """情绪 -> play() 参数。"""
    return dict(EMOTION_ACTS.get(emotion) or EMOTION_ACTS['平静'])
