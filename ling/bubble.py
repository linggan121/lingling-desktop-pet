# -*- coding: utf-8 -*-
"""重写气泡：文字先量再画框，保证字符永远在框里；尺寸跟着 DPI 缩放。"""
from __future__ import annotations


class Bubble(object):
    FILL = '#FFFFFF'
    OUTLINE = '#E8DFF7'
    TEXT = '#2C2738'

    def __init__(self, canvas, width, bubble_h, scale=1.0):
        self.canvas = canvas
        self.W = width
        self.h = bubble_h
        self.s = max(0.6, float(scale or 1.0))
        self.pad = int(round(12 * self.s))
        self._job = None

    # ---------------- 绘制 ----------------
    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def clear(self):
        self.canvas.delete('bubble')

    def say(self, text, ms=3800):
        if not text:
            return
        self.clear()
        s = self.s
        maxw = min(self.W - int(round(8 * s)), int(round(288 * s)))
        inner = max(60, maxw - self.pad * 2)
        tail = int(round(10 * s))
        bottom = self.h - int(round(4 * s))
        limit = self.h - int(round(10 * s))

        tid = self.canvas.create_text(self.W // 2, 0, text=text, width=inner,
                                      font=('Microsoft YaHei', 9),
                                      fill=self.TEXT, tags='bubble')
        bh = 0
        tw = 0
        for fs in (9, 8, 7):
            try:
                self.canvas.itemconfig(tid, font=('Microsoft YaHei', fs))
            except Exception:
                pass
            x1, y1, x2, y2 = self.canvas.bbox(tid)
            tw, th = x2 - x1, y2 - y1
            bh = max(int(round(46 * s)), th + self.pad * 2)
            if bh <= limit or fs == 7:
                break

        bw = max(int(round(120 * s)), min(maxw, tw + self.pad * 2))
        top = bottom - bh
        if top < int(round(2 * s)):
            top = int(round(2 * s))
            bh = bottom - top
        left = max(int(round(2 * s)), (self.W - bw) // 2)

        self._round_rect(left, top, left + bw, top + bh, int(round(12 * s)),
                         fill=self.FILL, outline=self.OUTLINE, width=1, tags='bubble')
        tail_x = self.W // 2
        self.canvas.create_polygon(
            [tail_x - int(round(8 * s)), top + bh - 1,
             tail_x + int(round(8 * s)), top + bh - 1,
             tail_x, top + bh + tail],
            fill=self.FILL, outline=self.OUTLINE, tags='bubble')
        self.canvas.coords(tid, self.W // 2, top + bh // 2)
        self.canvas.tag_raise(tid)

        if self._job:
            try:
                self.canvas.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.canvas.after(ms, self.clear)
