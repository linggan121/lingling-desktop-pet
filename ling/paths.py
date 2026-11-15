# -*- coding: utf-8 -*-
"""路径与文件读写。

源码运行和打包运行走同一套逻辑：
- 素材：源码在 ./assets，打包后在 PyInstaller 解压目录
- 数据：源码在 ./data，打包后优先用 exe 旁的 data（便携），否则 %LOCALAPPDATA%\\灵灵
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

FROZEN = bool(getattr(sys, 'frozen', False))

if FROZEN:
    BASE = os.path.dirname(os.path.abspath(sys.executable))
    RES = getattr(sys, '_MEIPASS', BASE)
    ASSETS = os.path.join(RES, 'assets')
    _portable = os.path.join(BASE, 'data')
    if os.path.isdir(_portable):
        DATA = _portable
    else:
        DATA = os.path.join(os.environ.get('LOCALAPPDATA') or BASE, '灵灵')
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES = BASE
    ASSETS = os.path.join(BASE, 'assets')
    DATA = os.path.join(BASE, 'data')

os.makedirs(DATA, exist_ok=True)


def data_path(name):
    return os.path.join(DATA, name)


def bundled(name):
    """打包时随程序带的数据文件（用于首次运行复制到 DATA）。"""
    return os.path.join(RES, 'data', name)


def read_json(path, default=None):
    try:
        with io.open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_json(path, obj):
    """原子写：先写临时文件再替换，写到一半崩了也不会把配置写坏。"""
    folder = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.flush()
        # 不做 fsync：某些虚拟磁盘/网络盘上 fsync 会长时间阻塞，
        # 配置文件了不起丢最后一次改动，不值得为此卡住界面。
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)  # noqa: F821  (tmp 只在成功创建后存在)
        except Exception:
            pass
        # 退路：直接覆盖，至少尽量保存
        try:
            with io.open(path, 'w', encoding='utf-8') as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False


def seed(name):
    """把内置的 data 文件复制出来（已存在则不动），方便用户改。"""
    target = data_path(name)
    if os.path.exists(target):
        return target
    try:
        shutil.copyfile(bundled(name), target)
    except Exception:
        pass
    return target
