# -*- coding: utf-8 -*-
"""换装规则：按时段、按季节自动挑衣服，手动换的衣服两小时内不被覆盖。

规则直接从 luna-desktop-pet 的思路来（深夜换睡衣、冬天不穿夏装、
手动换过的衣服 2 小时内不自动改），按灵灵现有的 6 套配色落地。
"""
from __future__ import annotations

import datetime
import time

from . import outfits

MANUAL_LOCK_HOURS = 2.0

# 季节 -> 默认配色
SEASON_OUTFIT = {
    'spring': 'forest',
    'summer': 'cream',
    'autumn': 'wine',
    'winter': 'navy',
}

# 夜间配色（22:00 - 06:00）
NIGHT_OUTFIT = 'mist'
NIGHT_START = 22
NIGHT_END = 6


def season_of(month):
    if month in (12, 1, 2):
        return 'winter'
    if month in (3, 4, 5):
        return 'spring'
    if month in (6, 7, 8):
        return 'summer'
    return 'autumn'


def auto_outfit(now=None):
    """按时段 + 季节挑一套。深夜优先于季节。"""
    now = now or datetime.datetime.now()
    if now.hour >= NIGHT_START or now.hour < NIGHT_END:
        return NIGHT_OUTFIT
    return SEASON_OUTFIT[season_of(now.month)]


class Wardrobe(object):
    """只管「现在该穿哪套」，不碰界面。"""

    def __init__(self, now=None):
        self._now = now or time.time
        self.manual = None          # 手动选的配色 id
        self.manual_at = 0.0        # 手动选的时间戳
        self.auto = True            # 是否允许自动换

    # ---------------- 外部调用 ----------------
    def set_manual(self, outfit_id):
        if not outfits.exists(outfit_id):
            return False
        self.manual = outfit_id
        self.manual_at = self._now()
        return True

    def manual_locked(self):
        return (self.manual is not None
                and (self._now() - self.manual_at) < MANUAL_LOCK_HOURS * 3600)

    def resolve(self, now=None):
        """当前应该穿哪套。"""
        if not self.auto:
            return self.manual or outfits.DEFAULT
        if self.manual_locked():
            return self.manual
        return auto_outfit(now)

    def tick(self, now=None):
        """定时调用：返回 (该穿的配色, 是否和上一套不同)。"""
        target = self.resolve(now)
        return target, target != getattr(self, 'current', None)

    def remember(self, outfit_id):
        self.current = outfit_id
