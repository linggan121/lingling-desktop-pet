# -*- coding: utf-8 -*-
"""设置读写：默认值合并 + 原子写。字段只增不减，旧配置读进来不会丢东西。"""
from __future__ import annotations

from . import llm, paths

DEFAULTS = {
    'x': None,
    'y': None,
    'feed': 0,
    'roam': False,       # 是否允许自己散步（默认关：先不动，想看她走再开）
    'roam_explicit': False,   # 用户是否亲手开/关过（没设过就按默认关处理）
    'tray': True,        # 显示托盘图标
    'tts': False,        # 预留：语音播报
    'outfit': 'auto',            # 当前服装（auto = 跟着时段/季节走）
    'outfit_manual': '',         # 手动选的服装
    'outfit_manual_at': 0,       # 手动换装的时间戳（2 小时内不被自动覆盖）
    'outfit_auto': True,         # 是否按时段/季节自动换
    'llm': dict(llm.DEFAULT_LLM),
}

SETTINGS_PATH = paths.data_path('settings.json')


def _merge(base, extra):
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    data = paths.read_json(SETTINGS_PATH, {})
    if not isinstance(data, dict):
        data = {}
    cfg = _merge(DEFAULTS, data)
    cfg['llm'] = _merge(llm.DEFAULT_LLM, data.get('llm') if isinstance(data.get('llm'), dict) else {})
    return cfg


def save(cfg):
    return paths.write_json(SETTINGS_PATH, cfg)
