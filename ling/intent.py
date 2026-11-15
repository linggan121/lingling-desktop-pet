# -*- coding: utf-8 -*-
"""把『自然语言指令』翻译成文件操作。

只做本地规则解析（不联网、可单测）：
  「转成 webp」「换成 png」「导出 pdf」「用 to-pdf 预设」「质量 80」
  「盯着这个文件夹」「停止监听」「有哪些格式」
"""
from __future__ import annotations

import re

STOP_WORDS = ('停止监听', '别盯了', '不要盯了', '取消监听', '停止watch', 'stop watch', 'stop watching')
WATCH_WORDS = ('盯着', '监听', '监视', 'watch')
LIST_WORDS = ('哪些格式', '什么格式', '支持什么', '格式列表', '能转成什么', '有哪些')

_VERB = r'(?:转成|转换成|转换|转|换成|变成|导出为|导出|输出为|输出|保存为|另存为|存为|变成|to|into|as)'
_EXTRA = r'(?:\s*(?:格式|文件|一下|吧|呢|呗|哈))?'


def _clean(text):
    return (text or '').strip().strip('。！!？?~～')


def _find_target(text, names):
    """在句子里找目标格式：先看动作词后面，再全局找已知格式名。"""
    low = text.lower()
    name_set = {n.lower(): n for n in names}
    pattern = _VERB + r'\s*(?:成|为|to)?\s*([a-zA-Z0-9][a-zA-Z0-9_\-]{1,9})' + _EXTRA
    for m in re.finditer(pattern, low):
        token = m.group(1).lower().strip('.,')
        if token in name_set:
            return name_set[token]
    return ''


def _find_preset(text, presets):
    """预设 id 直接命中；预设名称要带「预设」字样，或多个单词的名字。"""
    low = text.lower()
    for pid, pname, _target in presets:
        if pid.lower() in low:
            return pid
    has_kw = ('预设' in low) or ('preset' in low)
    for pid, pname, _target in presets:
        if not pname or len(pname) < 3:
            continue
        if pname.lower() in low and (has_kw or ' ' in pname):
            return pid
    return ''


def _find_quality(text):
    m = re.search(r'(?:质量|品质|quality|压缩率)\s*[:：]?\s*(\d{1,3})', text, re.IGNORECASE)
    if not m:
        m = re.search(r'(\d{1,3})\s*%', text)
    if m:
        try:
            q = int(m.group(1))
            if 1 <= q <= 100:
                return q
        except Exception:
            pass
    return None


def _find_folder(text, attached):
    """『盯着 D:\\xxx』或『盯着这个文件夹（拖进来的文件夹）』。"""
    m = re.search(r'["“]([^"”]{2,200})["”]', text)
    if m:
        return m.group(1)
    m = re.search(r'([A-Za-z]:\\[^\s，,。]+)', text)
    if m:
        return m.group(1)
    # 没有明确路径就用拖进来的第一个（后面执行时再校验是不是文件夹）
    for p in attached or []:
        if p:
            return p
    return ''


def parse(text, formats=(), presets=(), attached=()):
    """返回意图 dict 或 None。

    {'action': 'convert', 'to': 'webp'|'', 'preset': 'to-pdf'|'', 'quality': 80|None}
    {'action': 'watch', 'to': ..., 'preset': ..., 'folder': '...'}
    {'action': 'stop_watch'}
    {'action': 'list_formats'}
    """
    raw = _clean(text)
    if not raw:
        return None
    low = raw.lower()

    if any(w in low for w in STOP_WORDS):
        return {'action': 'stop_watch'}

    if any(w in low for w in LIST_WORDS):
        return {'action': 'list_formats'}

    is_watch = any(w in low for w in WATCH_WORDS)
    to = _find_target(raw, formats)
    preset = _find_preset(raw, presets)
    quality = _find_quality(raw)

    if is_watch:
        folder = _find_folder(raw, attached)
        if not (to or preset):
            return {'action': 'watch_need_format', 'folder': folder}
        return {'action': 'watch', 'to': to, 'preset': preset, 'folder': folder}

    # 只回一个格式名（比如「webp」「转 webp」已处理），也算指令
    if not to and not preset:
        bare = raw.strip().lower().strip('。！!？?~～')
        for name in formats:
            if bare == name.lower():
                to = name
                break

    if to or preset:
        return {'action': 'convert', 'to': to, 'preset': preset, 'quality': quality}

    if quality:
        # 只说了质量：如果拖进来的是图片，常见动作是压一下
        return {'action': 'convert', 'to': '', 'preset': '', 'quality': quality}
    return None
