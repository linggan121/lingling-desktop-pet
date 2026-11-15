# -*- coding: utf-8 -*-
"""看屏幕：截一张图 → 过滤隐私窗口 → 交给视觉模型随口点评一句。

隐私规则（照 luna 的做法）：前台窗口标题命中敏感词就直接不看，
连截图都不截，免得把密码/银行页面发出去。
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import io

from PIL import Image, ImageGrab

from . import llm

PRIVATE_WORDS = (
    '密码', '口令', '银行', '支付', '收款', '转账', '验证码', '身份证', '工资',
    '私钥', '密钥', '支付宝', '微信支付', '1password', 'keepass', 'bitwarden',
    'lastpass', '密码本', '简历',
)

PROMPT = (
    '你是桌面宠物「{name}」。请看你主人屏幕上现在是什么，用一句中文随口点评：'
    '不超过 35 字，口语、轻松，不要罗列界面元素，不要念窗口标题，不要提任何隐私信息。'
    '可以带上一个情绪标记，例如 <mood:好奇>，只能从这些里选：平静、微笑、开心、得意、害羞、'
    '生气、惊讶、失落、思考、无语、温柔、难过。'
)


def foreground_title():
    """当前前台窗口的标题（拿不到就返回空串）。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ''
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 2)
        user32.GetWindowTextW(hwnd, buf, length + 2)
        return buf.value or ''
    except Exception:
        return ''


def is_private(title):
    t = (title or '').lower()
    return any(word.lower() in t for word in PRIVATE_WORDS)


def grab_b64(max_width=1024, quality=72):
    """截屏并压成 JPEG（更小、上传更快），返回 base64。"""
    img = ImageGrab.grab()
    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize((max_width, max(1, int(img.height * ratio))), Image.LANCZOS)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def look(cfg, persona, model='', timeout=40.0):
    """返回模型的一句话点评；隐私窗口返回 None。"""
    llm_cfg = cfg.get('llm') or {}
    if not llm.ready(llm_cfg):
        raise llm.LLMError('还没配置模型')

    title = foreground_title()
    if is_private(title):
        return None

    name = (persona or {}).get('name', '灵灵')
    prompt = PROMPT.format(name=name)
    b64 = grab_b64()
    return llm.complete_vision(llm_cfg, model, prompt, b64, timeout=timeout)
