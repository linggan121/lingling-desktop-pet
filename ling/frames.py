# -*- coding: utf-8 -*-
"""切帧：读 assets/frames.json 从精灵图里裁出每一动作的帧序列。

两级来源：
1. 有 `assets/outfits/<id>/frames.json` → 直接用那套素材（真·新衣服）
2. 没有 → 用主精灵图，在内存里给裙子上色（配色变体）

缓存只存「原色」和每个素材包各一份；上色是内存计算，不落盘。
"""
from __future__ import annotations

import os
import pickle
import sys

from PIL import Image

from . import outfits, paths

FRAME_CACHE_VERSION = 3


def asset_stamp(sheet):
    """素材的「版本」时间戳。

    打包版每次运行都会把素材解压到新的临时目录，文件时间戳都是新的，
    直接用素材时间去比缓存会导致每次都重切帧；所以打包版改看 exe 本身的时间。
    """
    if paths.FROZEN:
        try:
            return os.path.getmtime(sys.executable)
        except Exception:
            pass
    try:
        return os.path.getmtime(sheet)
    except Exception:
        return 0


def _read_rows(src_dir, key, scale):
    """从 src_dir 的 frames.json 切帧，缓存到 data/_frames_<key>.pkl。"""
    meta = paths.read_json(os.path.join(src_dir, 'frames.json'), {})
    sheet = os.path.join(src_dir, meta.get('sheet') or 'spritesheet.webp')
    cache = os.path.join(paths.DATA, '_frames_%s.pkl' % key)
    stamp = asset_stamp(sheet)

    try:
        if os.path.exists(cache) and os.path.getmtime(cache) > stamp:
            with open(cache, 'rb') as f:
                d = pickle.load(f)
            if d.get('v') == FRAME_CACHE_VERSION:
                return d['rows']
    except Exception:
        pass

    img = Image.open(sheet).convert('RGBA')
    rows = {}
    for idx, row in enumerate(meta.get('rows') or []):
        frames = []
        for fr in row.get('frames') or []:
            box = (fr['x'], fr['y'], fr['x'] + fr['w'], fr['y'] + fr['h'])
            im = img.crop(box)
            nw = max(1, int(fr['w'] * scale))
            nh = max(1, int(fr['h'] * scale))
            im = im.resize((nw, nh), Image.LANCZOS)
            r, g, b, a = im.split()
            a = a.point(lambda v: 255 if v >= 128 else 0)   # 硬边，避免紫边
            frames.append(Image.merge('RGBA', (r, g, b, a)))
        rows[idx] = frames

    try:
        with open(cache, 'wb') as f:
            pickle.dump({'v': FRAME_CACHE_VERSION, 'rows': rows}, f)
    except Exception:
        pass
    return rows


def load_base(scale=1.0):
    """主精灵图的原色帧（带缓存）。"""
    return _read_rows(paths.ASSETS, 'default', scale)


def load_frames(scale=1.0, outfit='classic'):
    """返回 {行号: [PIL.Image, ...]}，已按 outfit 准备好。"""
    pack = outfits.pack_dir(outfit)
    if pack:
        return _read_rows(pack, 'outfit_' + outfit, scale)

    rows = load_base(scale)
    if not outfits.exists(outfit) or outfit == outfits.DEFAULT:
        return rows
    return {idx: [outfits.recolor(im, outfit) for im in frames]
            for idx, frames in rows.items()}
