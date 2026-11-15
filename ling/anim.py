# -*- coding: utf-8 -*-
"""帧动画播放器：只管「把一串 PIL 图按 fps 贴到 canvas 上」。"""
from __future__ import annotations

from PIL import Image, ImageTk


class Animator(object):
    def __init__(self, root, canvas, img_id, rows):
        self.root = root
        self.canvas = canvas
        self.img_id = img_id
        self.rows = rows
        self.cur = ''
        self.last_frame = None      # 最近一帧的 PIL 图（挤压效果要用）
        self._photo = None          # 必须留引用，否则图会被回收变成空白
        self._timer = None

    # ---------------- 基础 ----------------
    def _frames_for(self, row, reverse=False, mirror=False):
        frames = self.rows.get(row) or []
        out = list(reversed(frames)) if reverse else list(frames)
        if mirror:
            out = [im.transpose(Image.FLIP_LEFT_RIGHT) for im in out]
        return out

    def _cancel(self):
        if self._timer:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None

    def stop(self):
        self._cancel()
        self.cur = ''

    def _show(self, image):
        self._photo = ImageTk.PhotoImage(image)
        self.canvas.itemconfig(self.img_id, image=self._photo)
        self.last_frame = image

    # ---------------- 播放 ----------------
    def play(self, name, row=None, fps=6, loop=True, reverse=False, mirror=False,
             seq=None, on_end=None):
        if row is None and not seq:
            return
        self._cancel()
        self.cur = name
        plan = seq if seq else [(row, None, mirror)]
        frames = []
        for (r, limit, mir) in plan:
            frs = self._frames_for(r, reverse=reverse, mirror=mir)
            if limit:
                frs = frs[:limit]
            frames.extend(frs)
        if not frames:
            return
        state = {'i': 0}

        def tick():
            try:
                if not self.root.winfo_exists():
                    return
                self._show(frames[state['i'] % len(frames)])
            except Exception:
                return
            state['i'] += 1
            if not loop and state['i'] >= len(frames):
                if on_end:
                    self.root.after(60, on_end)
                return
            try:
                self._timer = self.root.after(max(40, int(1000 / fps)), tick)
            except Exception:
                pass

        tick()

    def idle(self, on_done=None):
        self.play('站立待机', row=0, fps=3, loop=True, on_end=on_done)

    # ---------------- 摸头：压扁再弹回 ----------------
    def squish(self, on_end=None):
        base = self.last_frame
        if base is None:
            if on_end:
                on_end()
            return
        self._cancel()
        self.cur = '摸头'
        steps = [0.98, 0.93, 0.88, 0.92, 0.97, 1.0]
        state = {'i': 0}

        def tick():
            try:
                if not self.root.winfo_exists():
                    return
                k = steps[state['i']]
                w = max(1, int(base.width * k))
                h = max(1, int(base.height * k))
                self._show(base.resize((w, h), Image.LANCZOS))
            except Exception:
                return
            state['i'] += 1
            if state['i'] >= len(steps):
                if on_end:
                    self.root.after(40, on_end)
                return
            self._timer = self.root.after(38, tick)

        tick()
