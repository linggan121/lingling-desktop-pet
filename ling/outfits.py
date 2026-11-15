# -*- coding: utf-8 -*-
"""换装：在现有精灵图上给裙子重新上色，得到不同颜色的「服装」。

为什么这么做：灵灵只有一套立绘，没有第二套美术。裙子是低饱和的深灰格子，
把「暗且灰」的像素换成目标色相、保留原来的明暗纹理，就能得到酒红/藏蓝/墨绿…
等配色，成本为零、不增加素材体积。

以后有真·新衣服时：新建 `assets/outfits/<id>/`，里面放 `frames.json` 和
`spritesheet.webp`（帧布局与现在一致），再把 `<id>` 加到 `OUTFITS` 里即可，
代码会自动优先用这个素材包，而不是重新上色。
"""
from __future__ import annotations

import os

from PIL import Image, ImageChops

from . import paths

# 暗部选色范围：明度 <= 0.62、饱和度 <= 0.32 的像素（裙子、袜口阴影）
V_MAX = 0.62
S_MAX = 0.32
TARGET_SAT = 0.42

# sat / v_gain 可单独调：奶油要浅一点，夜间紫要暗一点
OUTFITS = {
    'classic': {'name': '原色·灰格', 'hue': None},
    'wine': {'name': '酒红格', 'hue': 355},
    'navy': {'name': '藏蓝格', 'hue': 215},
    'forest': {'name': '墨绿格', 'hue': 135},
    'cream': {'name': '奶油格', 'hue': 42, 'sat': 0.22, 'v_gain': 1.35},
    'mist': {'name': '雾紫格', 'hue': 272, 'sat': 0.34, 'v_gain': 0.86},
}

DEFAULT = 'classic'


def exists(outfit_id):
    return outfit_id in OUTFITS or pack_dir(outfit_id) is not None


def pack_dir(outfit_id):
    """如果有独立的素材包 assets/outfits/<id>/{frames.json, 贴图}，就用它。"""
    d = os.path.join(paths.ASSETS, 'outfits', outfit_id)
    if os.path.isfile(os.path.join(d, 'frames.json')):
        return d
    return None


def available():
    """菜单里要列的服装：内置配色 + assets/outfits 下的素材包。"""
    ids = list(OUTFITS.keys())
    base = os.path.join(paths.ASSETS, 'outfits')
    try:
        for name in sorted(os.listdir(base)):
            if name not in ids and os.path.isfile(os.path.join(base, name, 'frames.json')):
                ids.append(name)
    except Exception:
        pass
    return ids


def name_of(outfit_id):
    if outfit_id in OUTFITS:
        return OUTFITS[outfit_id]['name']
    return outfit_id


def _cloth_mask(hsv):
    """暗 + 灰 = 衣服；用两个通道各做一次阈值再相乘。"""
    s = hsv.getchannel('S').point(lambda v: 255 if v <= int(S_MAX * 255) else 0)
    v = hsv.getchannel('V').point(lambda x: 255 if x <= int(V_MAX * 255) else 0)
    return ImageChops.multiply(s, v)


def recolor(im, outfit_id):
    """返回换装后的新图；原色或素材包直接返回原图。"""
    spec = OUTFITS.get(outfit_id) or OUTFITS[DEFAULT]
    hue = spec.get('hue')
    if hue is None:
        return im

    hsv = im.convert('HSV')
    mask = _cloth_mask(hsv)
    h, s, v = hsv.split()
    h = h.point(lambda _: int(round(hue / 360.0 * 255)))
    sat = spec.get('sat', TARGET_SAT)
    s = s.point(lambda _: int(round(sat * 255)))
    gain = spec.get('v_gain', 1.0)
    if gain != 1.0:
        v = v.point(lambda x: min(255, int(round(x * gain))))
    tinted = Image.merge('HSV', (h, s, v)).convert('RGB')

    rgb = im.convert('RGB')
    rgb.paste(tinted, mask=mask)
    out = rgb.convert('RGBA')
    out.putalpha(im.getchannel('A'))
    return out
