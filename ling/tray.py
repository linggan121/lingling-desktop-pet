# -*- coding: utf-8 -*-
"""托盘图标：立绘被拖出屏幕、或者想看设置的时候，靠它把灵灵找回来。"""
from __future__ import annotations

import os
import threading

try:
    import pystray
    from pystray import Menu, MenuItem
    HAS_TRAY = True
except Exception:      # 没装 pystray 就静默降级，不影响桌宠本体
    HAS_TRAY = False


def _icon_image(icon_path):
    from PIL import Image, ImageDraw
    try:
        img = Image.open(icon_path).convert('RGBA')
        return img.resize((64, 64), Image.LANCZOS)
    except Exception:
        # 兜底：画一个紫底白点
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=(124, 61, 219, 255))
        d.ellipse((22, 24, 30, 34), fill=(255, 255, 255, 255))
        d.ellipse((40, 24, 48, 34), fill=(255, 255, 255, 255))
        return img


class Tray(object):
    """托盘菜单动作都切回 Tk 主线程执行。"""

    def __init__(self, root, icon_path, on_toggle, on_reset, on_quit, on_settings=None, title='灵灵'):
        self.root = root
        self.icon_path = icon_path
        self._on_toggle = on_toggle
        self._on_reset = on_reset
        self._on_quit = on_quit
        self._on_settings = on_settings
        self.title = title
        self.icon = None
        self._thread = None

    def _call(self, fn):
        if fn is None:
            return None
        return lambda *a: self.root.after(0, fn)

    def start(self):
        if not HAS_TRAY:
            return False
        items = [
            MenuItem('显示 / 隐藏', self._call(self._on_toggle), default=True),
        ]
        if self._on_settings:
            items.append(MenuItem('设置…', self._call(self._on_settings)))
        items.append(MenuItem('回到右下角', self._call(self._on_reset)))
        items.append(Menu.SEPARATOR)
        items.append(MenuItem('退出灵灵', self._call(self._on_quit)))
        try:
            self.icon = pystray.Icon('ling', _icon_image(self.icon_path), self.title,
                                     Menu(*items))
            def _run():
                try:
                    self.icon.run()
                except Exception:
                    pass      # 托盘起不来不影响桌宠本体

            self._thread = threading.Thread(target=_run, daemon=True)
            self._thread.start()
            return True
        except Exception:
            self.icon = None
            return False

    def stop(self):
        try:
            if self.icon is not None:
                self.icon.stop()
        except Exception:
            pass
        self.icon = None

