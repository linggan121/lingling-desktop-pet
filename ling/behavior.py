# -*- coding: utf-8 -*-
"""漫游与睡觉：一只「自己会动」的桌宠该有的行为决策。

纯逻辑，不碰 Tk，方便单独测试。数值取自 jarvis 的 usePetRoamer.ts：
每 15–40 秒决策一次、60 px/s、一次走 100–400 px、10 分钟没人理就睡。
优先级（由 Pet 保证）：拖拽 > 说话气泡 > 手动点播的动作 > 漫游。
"""
from __future__ import annotations

import random
import time

MARGIN = 8


class Roamer(object):
    WALK_EVERY = (15.0, 40.0)     # 秒
    SPEED = 60.0                  # px/s
    DISTANCE = (100, 400)         # px
    SLEEP_AFTER = 600.0           # 秒（10 分钟）
    WALK_CHANCE = 0.65            # 到点了，走路的概率（否则只是换个姿势）

    def __init__(self, bounds, now=None, rng=None):
        self.bounds = bounds                 # () -> (x, y, w, h, screen_w, screen_h)
        self._now = now or time.time
        self._rng = rng or random.Random()
        self.state = 'idle'                  # idle / walk / sleep
        self.last_touch = self._now()
        self.next_think = self._now() + self._rng.uniform(*self.WALK_EVERY)

    # ---------------- 外部调用 ----------------
    def touch(self):
        """用户动了它一下。返回 True 表示把它从睡梦里叫醒了。"""
        self.last_touch = self._now()
        self.next_think = self._now() + self._rng.uniform(*self.WALK_EVERY)
        if self.state == 'sleep':
            self.state = 'idle'
            return True
        return False

    def end_walk(self):
        self.state = 'idle'
        self.next_think = self._now() + self._rng.uniform(*self.WALK_EVERY)

    @property
    def sleeping(self):
        return self.state == 'sleep'

    # ---------------- 决策 ----------------
    def tick(self, busy=False):
        """由主循环定时调用。返回动作字典或 None：
        {'type': 'sleep'} / {'type': 'walk', 'dx': int, 'ms': int, 'row': 1|2}
        / {'type': 'rest'}（原地换个动作）
        """
        now = self._now()
        if self.state == 'walk':
            return None
        if self.state == 'sleep':
            return None
        if busy:
            return None
        if now - self.last_touch >= self.SLEEP_AFTER:
            self.state = 'sleep'
            return {'type': 'sleep'}
        if now < self.next_think:
            return None

        self.next_think = now + self._rng.uniform(*self.WALK_EVERY)
        if self._rng.random() > self.WALK_CHANCE:
            return {'type': 'rest'}
        plan = self._plan_walk()
        if plan is None:
            return {'type': 'rest'}
        return plan

    def _plan_walk(self):
        try:
            x, y, w, h, sw, sh = self.bounds()
        except Exception:
            return None
        left_room = x - MARGIN
        right_room = (sw - w - MARGIN) - x
        go_right = right_room >= left_room
        room = max(0, right_room if go_right else left_room)
        if room < 40:
            go_right = not go_right
            room = max(0, right_room if go_right else left_room)
        if room < 40:
            return None
        dist = min(self._rng.randint(*self.DISTANCE), room)
        dx = dist if go_right else -dist
        self.state = 'walk'
        return {
            'type': 'walk',
            'dx': int(dx),
            'ms': int(abs(dx) / self.SPEED * 1000),
            'row': 1 if go_right else 2,     # 1=向右跑 2=向左跑
        }
