# -*- coding: utf-8 -*-
"""灵灵本体：窗口、交互、漫游、聊天、设置、托盘全在这里接线。"""
from __future__ import annotations

import io
import os
import queue
import random
import subprocess
import threading
import time
import tkinter as tk

from PIL import Image

from . import config, dnd, fileops, frames, intent, llm, mood, outfits, paths, vision, wardrobe
from . import memory as memory_mod
from . import persona as persona_mod
from .anim import Animator
from .behavior import Roamer
from .bubble import Bubble
from .settings_ui import SettingsWindow
from .tray import Tray

BG_KEY = '#FF00FF'
LINK_COLOR = '#6A2FC4'      # 可点击的文件路径（主色系，不用下划线）
LINK_HOVER = '#4A1E8F'
LINK_BG = '#F1EAFB'
LINK_BG_HOVER = '#E4D6F8'

# 子窗口摆位（物理像素）：贴在灵灵左侧、底边略高于她的脚
CHAT_SIZE = (414, 710)      # 聊天窗尺寸
CHAT_GAP = 12               # 聊天窗离她身体的横向距离（比设置窗更贴近）
WIN_GAP = 26                # 和她身体之间的横向间距（含窗口边框）
WIN_BOTTOM_ANCHOR = 0.35    # 窗口底边落在她身高的哪个比例（0.35 = 胸口偏上）

# 没配模型时，至少能答上「关于她自己」的几句，别的仍走随机台词。
# 这里只有人设类问答，不包含任何业务知识。
OFFLINE_RULES = (
    (('你是谁', '你叫什么', '你的名字'), ['我是灵灵呀，住在你桌面角落的小桌宠～',
                                          '叫我灵灵就好，是只会在你电脑上待着的小家伙']),
    (('在干嘛', '在干什么', '做什么呢', '忙什么'), ['在看你干活呀，顺便发会儿呆',
                                                    '没干嘛，就在这儿陪着你～']),
    (('几岁', '多大', '年龄'), ['桌宠没有年龄的啦，反正比你小一点']),
    (('喜欢什么', '爱好', '喜欢'), ['喜欢被摸头、喜欢投喂，还喜欢看你摸鱼']),
    (('会什么', '能做什么', '功能', '会干什么'),
     ['会陪你聊天、换衣服、看屏幕……不过要真聊起来，得先在设置里给我配个模型']),
    (('你好', 'hi', 'hello', '嗨', '在吗'), ['我在呢～', '嗨，今天也辛苦啦']),
    (('再见', '拜拜', '晚安', '走了'), ['去吧去吧，我在这儿等你', '晚安～记得早点睡']),
    (('谢谢', '感谢'), ['不客气呀', '嘿嘿，小事']),
)


def offline_reply(lines, q):
    text = (q or '').strip().lower()
    for keys, answers in OFFLINE_RULES:
        if any(k.lower() in text for k in keys):
            return random.choice(answers)
    # 像问题但没配模型：老实说答不上来，别用「嗯嗯，然后呢」敷衍
    looks_like_question = any(k in text for k in ('?', '？', '吗', '什么', '怎么', '为什么', '多少', '哪'))
    if looks_like_question:
        return pick(lines, 'fallback', '这个我答不上来，得先给我接个模型～')
    return pick(lines, 'chat', pick(lines, 'fallback', '在呢在呢～'))
BUBBLE_H = 96
HISTORY_KEEP = 200
EXTRACT_EVERY = 8          # 每聊这么多轮，提炼一次记忆


def pick(lines, key, fallback='你好呀～'):
    arr = lines.get(key) or []
    arr = [x for x in arr if isinstance(x, str) and x.strip()]
    return random.choice(arr) if arr else fallback


def _dpi_scale(root):
    """当前显示器的缩放比例（125% → 1.25）。"""
    try:
        return max(1.0, min(2.0, root.winfo_fpixels('1i') / 96.0))
    except Exception:
        return 1.0


def _enable_dpi_awareness():
    """让 Tk 直接按物理像素渲染，避免 Windows 把整窗拉伸导致发虚。"""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


class Pet(object):
    ACTS = [
        ('招手问好', dict(row=4, fps=8, loop=False)),
        ('跳个舞', dict(row=5, fps=6, loop=True)),
        ('开心一笑', dict(row=8, fps=4, loop=False)),
        ('抱胸思考', dict(row=6, fps=3, loop=True)),
        ('期待加油', dict(row=7, fps=3, loop=True)),
        ('坐下休息', dict(row=3, fps=4, loop=True)),
        ('向右小跑', dict(row=1, fps=8, loop=True)),
        ('向左小跑', dict(row=2, fps=8, loop=True)),
        ('快速招手', dict(row=4, fps=10, loop=False)),
        ('慢动作思考', dict(row=6, fps=2, loop=True)),
        ('倒放跳舞', dict(row=5, fps=6, loop=True, reverse=True)),
        ('原地转身', dict(seq=[(1, None, True), (2, None, True)], fps=8, loop=True)),
        ('手舞足蹈', dict(row=5, fps=8, loop=True)),
        ('东张西望', dict(seq=[(6, 3, False), (7, 3, True)], fps=3, loop=True)),
        ('连招表演', dict(seq=[(4, 4, False), (5, None, False), (8, None, False)], fps=6, loop=False)),
    ]

    def __init__(self):
        self.cfg = config.load()
        paths.seed('lines.json')
        paths.seed('persona.json')
        self.lines = paths.read_json(paths.data_path('lines.json'), {})

        self.root = tk.Tk()
        self.root.withdraw()
        self.dpi = _dpi_scale(self.root)
        self.scale = self.dpi * max(0.6, min(2.0, float(self.cfg.get('scale') or 1.0)))

        self.wardrobe = wardrobe.Wardrobe()
        self._restore_wardrobe()
        self._outfit = self.wardrobe.resolve()
        self.rows = self._frames_for_outfit(self._outfit)
        self.wardrobe.remember(self._outfit)
        self._compute_layout()

        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.bg = '#F7F5FB'
        if not os.environ.get('LING_OPAQUE'):
            try:
                self.root.attributes('-transparentcolor', BG_KEY)
                self.bg = BG_KEY
            except Exception:
                pass
        try:
            self._icon_img = tk.PhotoImage(file=os.path.join(paths.ASSETS, 'app_256.png'))
            self.root.iconphoto(True, self._icon_img)
        except Exception:
            try:
                self.root.iconbitmap(os.path.join(paths.ASSETS, 'app.ico'))
            except Exception:
                pass

        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H, bg=self.bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack()

        x, y = self.cfg.get('x'), self.cfg.get('y')
        if not isinstance(x, int) or not isinstance(y, int):
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x, y = sw - self.W - 24, sh - self.H - 64
        self.root.geometry('%dx%d+%d+%d' % (self.W, self.H, x, y))

        self.img_id = self.canvas.create_image(
            self.W // 2, self.H - int(round(8 * self.scale)), anchor='s')
        self.anim = Animator(self.root, self.canvas, self.img_id, self.rows)
        self.bubble = Bubble(self.canvas, self.W, self.bubble_h, self.scale)

        self.mem = memory_mod.Memory()
        self.persona = persona_mod.load()
        self.roamer = Roamer(self._bounds)

        self._feed = int(self.cfg.get('feed') or 0)
        self._mood = '平静'
        self._drag = None
        self._moved = False
        self._click_at = 0
        self._hover_at = 0
        self._walk = None
        self._walk_job = None
        self._sleeping = False
        self._roam_on = False      # 不再自己走动；这个开关已从菜单移除
        self._chat = None
        self._chat_msgs = []
        self._gen_thread = None
        self._gen_stop = None
        self._turn_count = 0
        self._last_talk = 0
        self._tray = None
        self._looking = False
        self._chat_opening = False
        self._ui_queue = queue.Queue()
        self._child_offsets = []
        self._attached = []          # 拖进来/选进来的文件
        self._file_options = []      # 当前的编号选项
        self._pending_act = None     # 等待确认的动作
        self._watch_proc = None      # filee watch 的进程
        self._filee = fileops.find_cli()
        self._dnd = None

        self._bind()
        self._start_tray()

        self.root.after(60, self._show_window)
        self.root.after(120, self._enable_dnd)
        self.root.after(900, self.greet)
        self.root.after(2200, self._auto_act)
        self.root.after(600, self._roam_tick)
        self.root.after(5000, self._wardrobe_tick)
        self.root.after(60, self._pump_ui)

    def _compute_layout(self):
        s = self.scale
        self.char_w = max((im.width for fr in self.rows.values() for im in fr),
                          default=int(round(160 * s)))
        self.char_h = max((im.height for fr in self.rows.values() for im in fr),
                          default=int(round(200 * s)))
        self.bubble_h = int(round(BUBBLE_H * s))
        self.W = max(self.char_w + int(round(110 * s)), int(round(320 * s)))
        self.H = self.char_h + self.bubble_h + int(round(20 * s))

    # ---------------- 窗口 ----------------
    def _post(self, fn):
        """工作线程把要执行的界面动作丢进队列，由主线程执行。"""
        try:
            self._ui_queue.put(fn)
        except Exception:
            pass

    def _pump_ui(self):
        try:
            for _ in range(20):
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.root.after(60, self._pump_ui)
        except Exception:
            pass

    def _show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)
        except Exception:
            pass

    def _restore_geom(self, key, win):
        """按上次记住的窗口位置放置；没有记录就返回 False。"""
        g = self.cfg.get(key)
        if not (isinstance(g, list) and len(g) == 4 and all(isinstance(v, int) for v in g)):
            return False
        gw, gh, gx, gy = g
        if gw < 200 or gh < 150:
            return False
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        gx = max(0, min(gx, sw - 120))
        gy = max(0, min(gy, sh - 80))
        try:
            px, py = self.root.winfo_x(), self.root.winfo_y()
        except Exception:
            px, py = 0, 0
        if abs(gx - px) > 700 or abs(gy - py) > 620:
            return False        # 离她太远，按默认位置重新贴过去
        if win is None:
            self._pending_geom = (key, gw, gh, gx, gy)
            return True
        try:
            win.geometry('%dx%d+%d+%d' % (gw, gh, gx, gy))
        except Exception:
            return False
        return True

    def _watch_geom(self, key, win):
        """用户拖动/缩放后记住尺寸和位置（防抖 0.6 秒）。"""
        state = {'job': None}

        def on_conf(event):
            if event.widget is not win:
                return
            try:
                if state['job']:
                    win.after_cancel(state['job'])
            except Exception:
                pass
            state['job'] = win.after(600, lambda: self._save_geom(key, win))

        try:
            win.bind('<Configure>', on_conf, add='+')
        except Exception:
            pass

    def _save_geom(self, key, win):
        try:
            self.cfg[key] = [win.winfo_width(), win.winfo_height(),
                             win.winfo_x(), win.winfo_y()]
            config.save(self.cfg)
        except Exception:
            pass

    def _anchor_window(self, win, w, h, shrink=False, gap=None):
        """把子窗口贴在灵灵左侧、底边略高于她的脚；左边放不下就切到右侧。"""
        try:
            px, py = self.root.winfo_x(), self.root.winfo_y()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x = px - w - WIN_GAP
            if x < 8:                        # 左边放不下 → 挪到右边
                x = px + self.W + WIN_GAP
            if x + w > sw - 8:
                x = max(8, sw - w - 8)
            y = py + int(self.H * WIN_BOTTOM_ANCHOR) - h
            if y < 8:
                y = 8
            if y + h > sh - 8:
                y = max(8, sh - h - 8)
            win.geometry('%dx%d+%d+%d' % (w, h, x, y))
        except Exception:
            pass
    def _place(self, x, y):
        try:
            self.root.geometry('+%d+%d' % (int(x), int(y)))
        except Exception:
            pass

    def _follow_children(self, dx, dy):
        """聊天窗 / 设置窗跟着灵灵一起挪。"""
        wins = []
        if self._chat is not None:
            wins.append(self._chat)
        st = getattr(self, '_settings', None)
        if st is not None:
            wins.append(getattr(st, 'win', None))
        try:
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        for w in wins:
            if w is None:
                continue
            try:
                if not w.winfo_exists():
                    continue
                nx = w.winfo_x() + dx
                ny = w.winfo_y() + dy
                nx = max(8, min(nx, sw - w.winfo_width() - 8))
                ny = max(8, min(ny, sh - w.winfo_height() - 8))
                w.geometry('+%d+%d' % (nx, ny))
            except Exception:
                pass

    def _bounds(self):
        return (self.root.winfo_x(), self.root.winfo_y(), self.W, self.H,
                self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    # ---------------- 气泡 ----------------
    def say(self, text, ms=3800):
        self.bubble.say(text, ms)

    def _bubble_visible(self):
        try:
            return bool(self.canvas.find_withtag('bubble'))
        except Exception:
            return False

    # ---------------- 交互 ----------------
    def _bind(self):
        for w in (self.root, self.canvas):
            w.bind('<ButtonPress-1>', self._press)
            w.bind('<B1-Motion>', self._drag_move)
            w.bind('<ButtonRelease-1>', self._release)
            w.bind('<Double-Button-1>', self._on_double)
            w.bind('<Button-3>', self._menu)
            w.bind('<Enter>', self._on_enter)

    def _child_windows(self):
        wins = []
        if self._chat is not None:
            wins.append(self._chat)
        st = getattr(self, '_settings', None)
        if st is not None:
            wins.append(getattr(st, 'win', None))
        return [w for w in wins if w is not None]

    def _press(self, e):
        self._drag = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y())
        self._moved = False
        # 记住每个子窗口相对她的偏移，拖动时按这个偏移一起挪（不受坐标刷新延迟影响）
        self._child_offsets = []
        try:
            px, py = self.root.winfo_x(), self.root.winfo_y()
            for w in self._child_windows():
                if w.winfo_exists():
                    self._child_offsets.append((w, w.winfo_x() - px, w.winfo_y() - py))
        except Exception:
            self._child_offsets = []
        self._wake()
        self.anim.play('开心一笑', row=8, fps=4, loop=False)

    def _drag_move(self, e):
        if not self._drag:
            return
        x0, y0, wx, wy = self._drag
        dx, dy = e.x_root - x0, e.y_root - y0
        if abs(dx) > 3 or abs(dy) > 3:
            self._moved = True
        if self._moved:
            self._stop_walk()
            # 拖动时把她限制在屏幕内，避免窗口跑到屏幕外导致坐标被系统改写
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            nx = max(0, min(wx + dx, sw - self.W))
            ny = max(0, min(wy + dy, sh - self.H))
            self._place(nx, ny)
            # 拖动她的时候，打开着的窗口按固定偏移一起挪（其它情况不动）
            for w, offx, offy in self._child_offsets:
                try:
                    if not w.winfo_exists():
                        continue
                    cx = max(8, min(nx + offx, sw - w.winfo_width() - 8))
                    cy = max(8, min(ny + offy, sh - w.winfo_height() - 8))
                    w.geometry('+%d+%d' % (cx, cy))
                except Exception:
                    pass
            row = 1 if dx >= 0 else 2
            if self.anim.cur != '奔跑':
                self.anim.play('奔跑', row=row, fps=8, loop=True)

    def _release(self, e):
        self._child_offsets = []
        if self._drag and self._moved:
            self._snap_to_edge()
            self.cfg['x'] = self.root.winfo_x()
            self.cfg['y'] = self.root.winfo_y()
            config.save(self.cfg)
            self.anim.idle()
        elif self._drag and time.time() - self._click_at > 1.2:
            # 单击 = 摸头：压扁 + 冒心心 + 说一句
            self._click_at = time.time()
            self.anim.squish(on_end=self._after_pat)
            self._heart()
            self.say(pick(self.lines, 'pat', '嘿嘿～'), 2600)
        self._drag = None

    def _after_pat(self):
        if self.anim.cur != '奔跑':
            self.anim.idle()

    def _heart(self):
        """tkinter 没有 alpha，用「往上飘 + 缩小」近似。"""
        try:
            s = self.scale
            x, y = self.W // 2 + int(round(46 * s)), self.H - self.char_h + int(round(18 * s))
            item = self.canvas.create_text(x, y, text='♥', fill='#FF5C8A',
                                           font=('Arial', int(round(14 * s)), 'bold'),
                                           tags='heart')
        except Exception:
            return
        step = {'i': 0}

        def tick():
            step['i'] += 1
            if step['i'] > 12:
                try:
                    self.canvas.delete(item)
                except Exception:
                    pass
                return
            try:
                self.canvas.move(item, 0, -2)
                base = int(round(14 * self.scale))
                size = max(int(round(7 * self.scale)), base - step['i'] // 2)
                self.canvas.itemconfig(item, font=('Arial', size, 'bold'))
            except Exception:
                return
            self.root.after(40, tick)

        tick()

    def _on_double(self, e):
        self.open_chat()

    def _on_enter(self, e):
        self._wake()
        if time.time() - self._hover_at < 6:
            return
        self._hover_at = time.time()
        self.anim.play('招手问好', row=4, fps=8, loop=False, on_end=self.anim.idle)
        self.say(pick(self.lines, 'hover', '在这儿呢～'), 3200)

    # ---------------- 贴边 ----------------
    def _snap_to_edge(self):
        """松手时离屏幕边缘 30px 以内就吸上去，并弹一下。"""
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            margin = 30
            nx, ny = x, y
            pad = (self.W - self.char_w) // 2
            if x <= margin:
                nx = -pad
            elif x + self.W >= sw - margin:
                nx = sw - self.W + pad
            if y <= margin:
                ny = 0
            elif y + self.H >= sh - margin:
                ny = sh - self.H + 8
            if (nx, ny) != (x, y):
                self._place(nx, ny)
                self._bounce(nx, ny)
        except Exception:
            pass

    def _bounce(self, x, y):
        """吸附时弹一下：往外偏 3px 再回来。"""
        dx = 3 if x >= 0 else -3
        try:
            self.root.after(30, lambda: self._place(x - dx, y))
            self.root.after(90, lambda: self._place(x, y))
        except Exception:
            pass

    # ---------------- 漫游 / 睡觉 ----------------
    def _roam_tick(self):
        try:
            if not self._roam_on:
                self.root.after(1500, self._roam_tick)
                return
            busy = (self._drag is not None or self._walk is not None
                    or self._bubble_visible() or self._chat_visible()
                    or self.anim.cur not in ('', '站立待机', '睡着'))
            action = self.roamer.tick(busy=busy)
            if action:
                kind = action.get('type')
                if kind == 'sleep':
                    self._fall_asleep()
                elif kind == 'walk':
                    self._start_walk(action)
                elif kind == 'rest':
                    self.play_index()
        except Exception:
            pass
        self.root.after(600, self._roam_tick)

    def _fall_asleep(self):
        self._sleeping = True
        self.roamer.state = 'sleep'
        self.anim.play('睡着', row=3, fps=2, loop=True)
        self.say(pick(self.lines, 'sleep', '呼…'), 2200)

    def _wake(self):
        was_asleep = self._sleeping
        self.roamer.touch()
        if was_asleep:
            self._sleeping = False
            self.say(pick(self.lines, 'wake', '嗯？我没睡！'), 2000)
            self.anim.idle()

    def _start_walk(self, plan):
        if not self._roam_on:
            self.roamer.end_walk()
            return
        dx = int(plan.get('dx') or 0)
        if abs(dx) < 8:
            self.roamer.end_walk()
            return
        self._walk = {'left': dx, 'row': plan.get('row', 1)}
        self.anim.play('巡逻', row=self._walk['row'], fps=8, loop=True)
        self._walk_step()

    def _walk_step(self):
        if not self._walk:
            return
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            sw = self.root.winfo_screenwidth()
            left = self._walk['left']
            step = 3 if left > 0 else -3
            if abs(left) < abs(step):
                step = left
            nx = x + step
            nx = max(-((self.W - self.char_w) // 2), min(nx, sw - self.W + (self.W - self.char_w) // 2))
            self._place(nx, y)
            self._walk['left'] = left - step
            if self._walk['left'] == 0:
                self._stop_walk(idle=True)
                return
        except Exception:
            self._stop_walk()
            return
        self._walk_job = self.root.after(50, self._walk_step)

    def _stop_walk(self, idle=False):
        if self._walk_job:
            try:
                self.root.after_cancel(self._walk_job)
            except Exception:
                pass
            self._walk_job = None
        if self._walk:
            self._walk = None
            self.roamer.end_walk()
            self.cfg['x'] = self.root.winfo_x()
            self.cfg['y'] = self.root.winfo_y()
            config.save(self.cfg)
        if idle and self.anim.cur == '巡逻':
            self.anim.idle()

    # ---------------- 动作 ----------------
    def play_index(self, i=None):
        i = random.randrange(len(self.ACTS)) if i is None else i
        name, kw = self.ACTS[i % len(self.ACTS)]
        kw = dict(kw)
        if kw.get('loop', True):
            self.anim.play(name, **kw)
            self.root.after(4200, lambda n=name: self.anim.idle() if self.anim.cur == n else None)
        else:
            self.anim.play(name, on_end=self.anim.idle, **kw)
        return name

    def _auto_act(self):
        try:
            if random.random() < 0.45 and not self._sleeping:
                self.play_index()
            self.root.after(random.randint(9000, 16000), self._auto_act)
        except Exception:
            pass

    # ---------------- 换装 ----------------
    def _restore_wardrobe(self):
        self.wardrobe.auto = bool(self.cfg.get('outfit_auto', True))
        manual = self.cfg.get('outfit_manual') or ''
        if manual and outfits.exists(manual):
            self.wardrobe.manual = manual
            self.wardrobe.manual_at = float(self.cfg.get('outfit_manual_at') or 0)

    def _frames_for_outfit(self, outfit_id):
        rows = frames.load_frames(1.0, outfit_id)
        try:
            right = rows.get(1) or []
            if right:
                rows[2] = [im.transpose(Image.FLIP_LEFT_RIGHT) for im in right]
        except Exception:
            pass
        return rows

    def _set_outfit(self, outfit_id, announce=False):
        if not outfits.exists(outfit_id) or outfit_id == self._outfit:
            return
        self.rows = self._frames_for_outfit(outfit_id)
        self.anim.rows = self.rows
        self._outfit = outfit_id
        self.wardrobe.remember(outfit_id)
        self.anim.idle()
        if announce:
            self.say(pick(self.lines, 'outfit_change', '换件衣服～'), 2600)

    def _outfit_menu(self, parent):
        sm = tk.Menu(parent, tearoff=0)
        self._outfit_var = tk.StringVar(value=self._outfit)
        for oid in outfits.available():
            sm.add_radiobutton(label=outfits.name_of(oid), value=oid,
                               variable=self._outfit_var,
                               command=lambda o=oid: self._choose_outfit(o))
        sm.add_separator()
        self._auto_var = tk.BooleanVar(value=self.wardrobe.auto)
        sm.add_checkbutton(label='按时段 / 季节自动换', variable=self._auto_var,
                           command=self._toggle_auto_outfit)
        return sm

    def _choose_outfit(self, outfit_id):
        self.wardrobe.set_manual(outfit_id)
        self.cfg['outfit_manual'] = outfit_id
        self.cfg['outfit_manual_at'] = self.wardrobe.manual_at
        self.cfg['outfit'] = 'auto'
        config.save(self.cfg)
        self._set_outfit(outfit_id, announce=True)

    def reset_windows(self):
        """忘掉记下的位置，把已打开的窗口重新贴到她旁边。"""
        for key in ('chat_geom', 'settings_geom'):
            self.cfg.pop(key, None)
        config.save(self.cfg)
        try:
            if self._chat is not None and self._chat.winfo_exists():
                self._chat.update_idletasks()
                self._anchor_window(self._chat, self._chat.winfo_width(),
                                    self._chat.winfo_height(), shrink=True, gap=CHAT_GAP)
        except Exception:
            pass
        st = getattr(self, '_settings', None)
        try:
            if st is not None and st.win.winfo_exists():
                st.win.update_idletasks()
                self._anchor_window(st.win, st.win.winfo_width(), st.win.winfo_height())
        except Exception:
            pass
        self.say('窗口搬回来啦～', 2200)

    def _toggle_auto_outfit(self):
        self.wardrobe.auto = bool(self._auto_var.get())
        self.cfg['outfit_auto'] = self.wardrobe.auto
        config.save(self.cfg)
        if self.wardrobe.auto:
            self._set_outfit(self.wardrobe.resolve(), announce=True)

    def _wardrobe_tick(self):
        try:
            if self.wardrobe.auto:
                target, changed = self.wardrobe.tick()
                if changed:
                    self._set_outfit(target, announce=True)
        except Exception:
            pass
        self.root.after(300000, self._wardrobe_tick)

    def play_mood(self, emotion):
        """按情绪换个动作（AI 回复结束后调用）。"""
        self._mood = emotion or '平静'
        spec = mood.act_for(self._mood)
        self.anim.play('情绪·' + self._mood, on_end=None, **spec)
        self.root.after(6000, self.anim.idle)

    # ---------------- 菜单 ----------------
    def _menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label='聊聊天', command=self.open_chat)
        m.add_command(label='看看我在干什么', command=self.look_screen)
        m.add_command(label='逗一下我', command=self.tease)
        m.add_command(label='我今天心情', command=self.mood_check)
        m.add_command(label='投喂一口', command=self.feed)
        m.add_separator()
        m.add_command(label='换个动作', command=lambda: self.play_index())
        m.add_cascade(label='换装', menu=self._outfit_menu(m))
        skill = tk.Menu(m, tearoff=0)
        skill.add_command(label='选文件转换…', command=self.pick_files)
        skill.add_command(label='可用格式…', command=self._list_formats)
        skill.add_command(label='停止监听', command=lambda: self._stop_watch())
        m.add_cascade(label='技能', menu=skill)
        m.add_command(label='窗口搬回来', command=self.reset_windows)
        m.add_command(label='设置…', command=self.open_settings)
        m.add_command(label='回到右下角', command=self.reset_pos)
        m.add_separator()
        m.add_command(label='退出灵灵', command=self.quit)
        try:
            m.tk_popup(e.x_root, e.y_root)
        except Exception:
            pass

    def reset_pos(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x, y = sw - self.W - 24, sh - self.H - 64
        self._place(x, y)
        self.cfg['x'], self.cfg['y'] = x, y
        config.save(self.cfg)
        self.say('回到老地方啦～', 3000)

    # ---------------- 小功能 ----------------
    def greet(self):
        self.play_index(0)
        self.say(pick(self.lines, 'greet', '灵灵在呢～'), 3800)

    def tease(self):
        self.play_index()
        self.say(pick(self.lines, 'tease', '嘿嘿，被你发现了～'), 3800)

    def mood_check(self):
        n = self._feed
        key = 'mood_high' if n >= 5 else ('mood_mid' if n >= 1 else 'mood_low')
        self.anim.play('期待加油', row=7, fps=3, loop=True)
        self.say(pick(self.lines, key, '我今天心情不错～'), 4200)
        self.root.after(4200, self.anim.idle)

    def feed(self):
        self._feed += 1
        self.cfg['feed'] = self._feed
        config.save(self.cfg)
        self.anim.play('跳个舞', row=5, fps=6, loop=True)
        self.say(pick(self.lines, 'feed', '咔嚓咔嚓…') + '（第 %d 口）' % self._feed, 3800)
        self.root.after(3800, self.anim.idle)

    def quit(self):
        self.save()
        self.say('那我先撤啦～', 700)
        self.root.after(700, self._destroy)

    def save(self):
        try:
            self.cfg['x'] = self.root.winfo_x()
            self.cfg['y'] = self.root.winfo_y()
            self.cfg['feed'] = self._feed
            config.save(self.cfg)
        except Exception:
            pass

    def _destroy(self):
        try:
            self._stop_watch(silent=True)
        except Exception:
            pass
        try:
            if self._dnd is not None:
                self._dnd.detach()
        except Exception:
            pass
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------------- 托盘 ----------------
    def _start_tray(self):
        if not self.cfg.get('tray', True):
            return
        try:
            self._tray = Tray(self.root, os.path.join(paths.ASSETS, 'app.ico'),
                              on_toggle=self._toggle_visible,
                              on_reset=self.reset_pos,
                              on_quit=self.quit,
                              on_settings=self.open_settings)
            self._tray.start()
        except Exception:
            self._tray = None

    def _toggle_visible(self):
        try:
            if self.root.state() == 'withdrawn':
                self.root.deiconify()
                self.root.lift()
                self.root.attributes('-topmost', True)
            else:
                self.root.withdraw()
        except Exception:
            pass

    # ---------------- 设置 ----------------
    def open_settings(self):
        win = getattr(self, '_settings', None)
        if win is not None:
            try:
                if win.win.winfo_exists():
                    win.win.deiconify()
                    win.win.lift()
                    win.win.focus_force()
                    return
            except Exception:
                pass
        # 从右键菜单里调用时菜单还占着 grab，直接建窗口会导致控件不布局（空白）。
        # 延后一拍，等菜单彻底收起再建。
        self.root.after(30, self._open_settings_now)

    def _open_settings_now(self):
        win = getattr(self, '_settings', None)
        if win is not None:
            try:
                if win.win.winfo_exists():
                    win.win.deiconify()
                    win.win.lift()
                    return
            except Exception:
                pass
        anchor = None if self._restore_geom('settings_geom', None) else self._anchor_window
        self._settings = SettingsWindow(self.root, self.cfg.get('llm') or {},
                                        self._save_llm, scale=self.scale,
                                        anchor=anchor)
        if anchor is None:
            self._restore_geom('settings_geom', self._settings.win)
        self._watch_geom('settings_geom', self._settings.win)
        try:
            self._settings.win.update_idletasks()
            self._settings.win.lift()
        except Exception:
            pass

    def _save_llm(self, cfg):
        self.cfg['llm'] = cfg
        config.save(self.cfg)

    # ---------------- 文件技能（拖文件 + 聊天指令） ----------------
    def _enable_dnd(self):
        def deliver(paths):
            # 窗口过程里绝不能碰 Tk；丢进队列，让主线程的泵去处理
            self._ui_queue.put(lambda p=list(paths): self._on_files_dropped(p))

        try:
            self._dnd = dnd.enable(self.root, deliver)
        except Exception:
            self._dnd = None

    def _on_files_dropped(self, file_list):
        files = [p for p in file_list if os.path.exists(p)]
        if not files:
            return
        self._attached = files
        try:
            self.open_chat()
        except Exception:
            pass
        links = []
        for f in files[:10]:
            name = os.path.basename(f.rstrip('\\/')) or f
            icon = '▸' if os.path.isdir(f) else '·'
            links.append(('%s %s%s' % (icon, name, '（文件夹）' if os.path.isdir(f) else ''), f))
        if len(files) > 10:
            links.append(('…还有 %d 个' % (len(files) - 10), os.path.dirname(files[0])))

        options = self._build_file_options(files)
        self._file_options = options
        if not self._filee:
            text = '收到 %d个文件（还没装 Filee，暂时只能陪你聊天）' % len(files)
            self._chat_add('灵灵', text, links=links)
            self.say('收到文件啦～', 3000)
            return
        rows = ['收到 %d个文件，你要哪样？' % len(files)]
        for i, (label, _act) in enumerate(options, 1):
            rows.append('%d. %s' % (i, label))
        rows.append('回数字就行，也可以直接说别的。')
        self._chat_add('灵灵', '\n'.join(rows), links=links)
        self.say('收到文件啦～', 3000)

    def _build_file_options(self, files):
        """按拖进来的东西给出可执行的选项。"""
        opts = [
            ('转成 webp', {'action': 'convert', 'to': 'webp', 'preset': '', 'quality': None}),
            ('用 to-pdf 预设', {'action': 'convert', 'to': '', 'preset': 'to-pdf', 'quality': None}),
            ('转成 jpg（质量 80）', {'action': 'convert', 'to': 'jpg', 'preset': '', 'quality': 80}),
        ]
        folder = next((f for f in files if os.path.isdir(f)), '')
        if folder:
            opts.append(('盯着这个文件夹，新文件转成 jpg',
                         {'action': 'watch', 'to': 'jpg', 'preset': '', 'folder': folder}))
        return opts

    def pick_files(self):
        if not self._filee:
            self.say('还没装 Filee，装好我才能转文件哦', 4000)
            return
        from tkinter import filedialog
        files = filedialog.askopenfilenames(title='选要处理的文件')
        if files:
            self._on_files_dropped(list(files))

    UNSUPPORTED_HINTS = ('拆', '合并', '重命名', '改名', '整理', '归类', '归档', '压缩', '解压',
                         '加密', '解密', '翻译', '对比', '去重', '排序', '删除', '移动',
                         '复制', '查找', '搜索', '识别', 'ocr')

    def _handle_file_request(self, text):
        if not self._attached or not self._filee:
            return False

        # 1) 回了数字 → 直接执行对应选项
        picked = (text or '').strip()
        if self._file_options and picked.isdigit():
            idx = int(picked) - 1
            if 0 <= idx < len(self._file_options):
                label, act = self._file_options[idx]
                self._chat_add('灵灵', '好，那我来：%s' % label)
                self._execute(act)
                return True
            self._chat_add('灵灵', '只有 1 到 %d 这几个选项哦。' % len(self._file_options))
            return True

        try:
            fmts = fileops.format_names()
            preset_list = fileops.presets()
        except Exception:
            fmts, preset_list = [], []
        act = intent.parse(text, formats=fmts, presets=preset_list, attached=self._attached)

        if act:
            kind = act.get('action')
            if kind in ('convert', 'watch'):
                # 2) 自己说别的 → 先把要做什么说清楚，再执行
                self._chat_add('灵灵', '收到，我这样做：%s' % self._describe(act))
                self._execute(act)
            elif kind == 'watch_need_format':
                self._chat_add('灵灵', '要转成什么格式？比如「盯着这个文件夹转成 webp」')
            elif kind == 'stop_watch':
                self._stop_watch()
            elif kind == 'list_formats':
                self._list_formats()
            else:
                return False
            return True

        # 3) 听起来是文件任务，但她不会 → 直接说清楚
        low = (text or '').lower()
        if any(hint in low for hint in self.UNSUPPORTED_HINTS):
            self._chat_add('灵灵',
                           '这个我还不会。我目前只会：换格式（270 种）、用预设、调图片质量、'
                           '盯着文件夹自动转。你说的「%s」得等以后。' % (text or '')[:20])
            return True
        return False

    def _describe(self, act):
        kind = act.get('action')
        target = act.get('to') or act.get('preset') or ''
        if act.get('quality'):
            target += '，质量 %d' % act['quality']
        if kind == 'watch':
            folder = act.get('folder') or ''
            return '盯着「%s」，新文件都转成 %s' % (os.path.basename(folder.rstrip('\\/')) or folder, target)
        return '把 %d个文件转成 %s（放在原目录）' % (len(self._attached), target)

    def _execute(self, act):
        kind = act.get('action')
        if kind == 'convert':
            self._run_convert(act)
        elif kind == 'watch':
            self._run_watch(act)

    def _run_convert(self, act):
        files = list(self._attached)
        label = self._chat_add('灵灵', '开始转换 %d 个文件…' % len(files))

        def work():
            try:
                res = fileops.convert(files, to=act.get('to') or None,
                                      preset=act.get('preset') or None,
                                      quality=act.get('quality'))
                text = res['message']
                if res.get('errors'):
                    text += '（%s）' % res['errors'][0]
            except Exception as e:
                text = '转换没成功：%s' % str(e)[:60]
                res = {'outputs': []}

            def ui():
                try:
                    if label is not None and label.winfo_exists():
                        label.master.destroy()      # 去掉“开始转换…”
                except Exception:
                    pass
                links = [('· ' + os.path.basename(p), p)
                         for p in (res.get('outputs') or [])[:10]]
                self._chat_add('灵灵', text, links=links)
                self.say(text[:40], 5200)
                self.play_index()

            self._post(ui)

        threading.Thread(target=work, daemon=True).start()

    def _run_watch(self, act):
        folder = act.get('folder') or (self._attached[0] if self._attached else '')
        if not folder or not os.path.isdir(folder):
            self._chat_add('灵灵', '把要盯着的文件夹拖给我，或者直接说「盯着 D:\\下载」')
            return
        try:
            self._stop_watch(silent=True)
            self._watch_proc = fileops.start_watch(folder, to=act.get('to') or None,
                                                   preset=act.get('preset') or None)
            name = os.path.basename(folder.rstrip('\\/')) or folder
            out_dir = os.path.join(folder.rstrip('\\/'), 'converted')
            self._chat_add('灵灵', '好，我盯着「%s」了，新文件会自动转成 %s。\n'
                                   '说「停止监听」我就停。' % (name, act.get('to') or act.get('preset')),
                           links=[('▸ converted（转好的文件都在这儿）', out_dir)])
            self.say('盯好啦～', 3200)
        except Exception as e:
            self._chat_add('灵灵', '盯不住：%s' % str(e)[:50])

    def _stop_watch(self, silent=False):
        proc = self._watch_proc
        self._watch_proc = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            if not silent:
                self._chat_add('灵灵', '不盯了，监听已经停掉。')

    def _list_formats(self):
        try:
            names = fileops.format_names()
        except Exception:
            names = []
        if not names:
            self.say('还没装 Filee，装好我才能转文件哦', 4000)
            return
        self._chat_add('灵灵', '我会转 %d 种格式，常用的这些：\n%s'
                       % (len(names), '、'.join(names[:28])))
        self.say('我能转 %d 种格式～' % len(names), 4200)

    # ---------------- 看屏幕 ----------------
    def _log(self, text):
        try:
            with io.open(paths.data_path('vision.log'), 'a', encoding='utf-8') as f:
                f.write(time.strftime('[%H:%M:%S] ') + text + '\n')
        except Exception:
            pass

    def look_screen(self):
        if self._looking:
            self.say('我还在看呢，等一下～', 2000)
            return
        if vision.is_private(vision.foreground_title()):
            self.say('这个窗口我不看～', 2600)
            return
        if not llm.ready(self.cfg.get('llm')):
            self.say('得先去设置里给我配个模型呀', 3000)
            return

        self._looking = True
        self.say('让我瞄一眼…', 42000)
        model = (self.cfg.get('llm') or {}).get('vision_model') or ''
        self._log('开始看屏幕 model=%s' % (model or '(默认)'))

        def work():
            text, err = '', ''
            try:
                text = vision.look(self.cfg, self.persona, model)
            except Exception as e:
                err = str(e)[:60]
                self._log('失败: %r' % e)
            else:
                self._log('返回: %r' % (text or ''))

            def ui():
                self._looking = False
                if err:
                    self.say('看不太清：' + err, 4200)
                    return
                if not text:
                    self.say('这个窗口我不看～', 2600)
                    return
                clean, emo = mood.parse(text)
                clean = (clean or text).strip()
                self.say(clean[:80], 6000)
                self.play_mood(mood.to_emotion(emo, clean))

            self._post(ui)

        threading.Thread(target=work, daemon=True).start()

    # ---------------- 聊天 ----------------
    def _chat_visible(self):
        try:
            return bool(self._chat and self._chat.winfo_exists())
        except Exception:
            return False

    def clear_chat(self):
        """清空聊天记录：内存、界面、history.json 一起清。"""
        self._chat_msgs = []
        try:
            paths.write_json(paths.data_path('history.json'), [])
        except Exception:
            pass
        try:
            for w in self._chat_inner.winfo_children():
                w.destroy()
        except Exception:
            pass
        self._chat_add('灵灵', '记录清空啦，我们重新开始～')

    def _close_chat(self):
        try:
            if self._chat is not None:
                self._chat.destroy()
        except Exception:
            pass
        self._chat = None

    def open_chat(self):
        if self._chat_opening:
            return
        if self._chat_visible():
            try:
                self._chat.deiconify()
                self._chat.lift()
                self._chat.focus_force()
            except Exception:
                pass
            return
        self._chat_opening = True
        try:
            self._open_chat_window()
        finally:
            self._chat_opening = False

    def _open_chat_window(self):
        win = tk.Toplevel(self.root)
        self._chat = win
        try:
            win.protocol('WM_DELETE_WINDOW', self._close_chat)
        except Exception:
            pass
        win.title('和灵灵聊聊')
        win.configure(bg='#FFFFFF')
        cw, ch = CHAT_SIZE
        if not self._restore_geom('chat_geom', win):
            self._anchor_window(win, cw, ch, shrink=True, gap=CHAT_GAP)
        self._watch_geom('chat_geom', win)
        win.attributes('-topmost', True)

        head = tk.Frame(win, bg='#7C3DDB', height=44)
        head.pack(fill='x')
        tk.Label(head, text='灵灵', bg='#7C3DDB', fg='#fff',
                 font=('Microsoft YaHei', 11, 'bold')).pack(side='left', padx=14, pady=10)
        state = '在线 · %s' % (self.cfg.get('llm', {}).get('model') or '未配置')
        if not llm.ready(self.cfg.get('llm')):
            state = '离线 · 只会说自己的台词'
        tk.Label(head, text=state, bg='#7C3DDB', fg='#E9DEFF',
                 font=('Microsoft YaHei', 8)).pack(side='right', padx=(12, 0))
        tk.Button(head, text='清空记录', command=self.clear_chat, relief='flat',
                  bg='#8F57E0', fg='#FFFFFF', font=('Microsoft YaHei', 8),
                  padx=8, pady=1).pack(side='right', padx=(0, 6))
        if not llm.ready(self.cfg.get('llm')):
            tk.Button(head, text='配置模型', command=self.open_settings, relief='flat',
                      bg='#FFFFFF', fg='#7C3DDB', font=('Microsoft YaHei', 8, 'bold'),
                      padx=8, pady=1).pack(side='right', padx=(0, 6))

        body = tk.Frame(win, bg='#FFFFFF')
        body.pack(fill='both', expand=True, padx=10, pady=8)

        canvas = tk.Canvas(body, bg='#FFFFFF', highlightthickness=0)
        sb = tk.Scrollbar(body, orient='vertical', command=canvas.yview)
        inner = tk.Frame(canvas, bg='#FFFFFF')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

        self._chat_inner = inner
        self._chat_canvas = canvas

        bottom = tk.Frame(win, bg='#FFFFFF')
        bottom.pack(fill='x', padx=10, pady=(0, 10))
        entry = tk.Entry(bottom, font=('Microsoft YaHei', 10), relief='solid', bd=1)
        entry.pack(side='left', fill='x', expand=True, ipady=5)
        entry.bind('<Return>', lambda e: self._send(entry))
        tk.Button(bottom, text='发送', bg='#7C3DDB', fg='#fff', relief='flat',
                  font=('Microsoft YaHei', 10), command=lambda: self._send(entry)
                  ).pack(side='left', padx=(8, 0), ipadx=10, ipady=3)

        self._chat_add('灵灵', '想说什么都可以，我就在这儿陪你～')
        for m in self._load_history()[-20:]:
            self._chat_add('灵灵' if m.get('role') == 'assistant' else '你', m.get('text', ''))
        entry.focus_set()

    def _chat_add(self, who, text, links=None):
        """加一条聊天消息；links 里的每项 (显示文字, 路径) 会渲染成可点击的链接。"""
        try:
            row = tk.Frame(self._chat_inner, bg='#FFFFFF')
            row.pack(fill='x', pady=4)
            color = '#7C3DDB' if who == '灵灵' else '#2C2738'
            tk.Label(row, text=who, bg='#FFFFFF', fg=color,
                     font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w')
            lab = None
            if text:
                lab = tk.Label(row, text=text, bg='#F7F5FB', fg='#2C2738', justify='left',
                               wraplength=330, font=('Microsoft YaHei', 10),
                               padx=10, pady=8)
                lab.pack(anchor='w', pady=(2, 0))
            for shown, path in (links or []):
                link = tk.Label(row, text='  ' + shown + '  ', bg=LINK_BG, fg=LINK_COLOR,
                                justify='left', wraplength=320, cursor='hand2',
                                font=('Microsoft YaHei', 10),
                                padx=6, pady=4)
                link.pack(anchor='w', pady=(3, 0))
                link.bind('<Button-1>', lambda e, p=path: self._open_location(p))
                link.bind('<Enter>', lambda e, w=link: w.config(bg=LINK_BG_HOVER))
                link.bind('<Leave>', lambda e, w=link: w.config(bg=LINK_BG))
            self._chat_scroll_bottom()
            return lab if lab is not None else row
        except Exception:
            return None

    def _chat_scroll_bottom(self):
        """等布局更新完再滚到底，否则新消息会露出一半。"""
        def go():
            try:
                if self._chat_canvas is None or not self._chat_canvas.winfo_exists():
                    return
                self._chat_inner.update_idletasks()
                self._chat_canvas.configure(scrollregion=self._chat_canvas.bbox('all'))
                self._chat_canvas.yview_moveto(1.0)
            except Exception:
                pass

        try:
            self.root.after(16, go)
        except Exception:
            pass

    def _open_location(self, path):
        """点链接：打开文件所在文件夹并选中它（文件夹就直接打开）。"""
        try:
            path = str(path)
            if os.path.isdir(path):
                subprocess.Popen(['explorer', os.path.normpath(path)])
            elif os.path.exists(path):
                subprocess.Popen(['explorer', '/select,' + os.path.normpath(path)])
            else:
                parent = os.path.dirname(path)
                if parent and os.path.isdir(parent):
                    subprocess.Popen(['explorer', os.path.normpath(parent)])
                else:
                    self.say('这个位置打不开了…', 2200)
        except Exception:
            self.say('这个位置打不开了…', 2200)

    def _send(self, entry):
        q = entry.get().strip()
        if not q:
            return
        entry.delete(0, 'end')
        self._chat_add('你', q)
        self._chat_msgs.append({'role': 'user', 'content': q})
        self._turn_count += 1
        self._last_talk = time.time()
        self._save_history()

        if self._handle_file_request(q):
            return

        if not llm.ready(self.cfg.get('llm')):
            self.root.after(240, lambda: self._say_offline(q))
            return

        label = self._chat_add('灵灵', '…')
        stop_flag = threading.Event()
        self._gen_stop = stop_flag
        buffer = {'text': ''}
        pending = {'dirty': False}
        state = {'done': False}

        def flush():
            if state['done']:
                return
            if pending['dirty']:
                pending['dirty'] = False
                try:
                    if label is not None and label.winfo_exists():
                        label.config(text=buffer['text'][-400:] or '…')
                        self._chat_canvas.yview_moveto(1.0)
                except Exception:
                    pass
            if not state['done']:
                self.root.after(80, flush)

        def on_chunk(piece):
            buffer['text'] += piece
            pending['dirty'] = True

        def on_done(text):
            state['done'] = True
            clean, emo = mood.parse(text)
            if not clean:
                clean = text
            emo = mood.to_emotion(emo, clean)

            def ui():
                try:
                    if label is not None and label.winfo_exists():
                        label.config(text=clean)
                        self._chat_canvas.yview_moveto(1.0)
                except Exception:
                    pass
                self.say(clean[:40], 4200)
                self.play_mood(emo)
                self._chat_msgs.append({'role': 'assistant', 'content': clean})
                self._save_history()
                self._maybe_extract()
            self._post(ui)

        def on_error(err):
            state['done'] = True

            def ui():
                try:
                    if label is not None and label.winfo_exists():
                        label.config(text='（%s）' % err, fg='#C62828')
                except Exception:
                    pass
                self._say_offline(q)
            self._post(ui)

        def work():
            try:
                llm.stream(self.cfg.get('llm'), self._build_messages(),
                           on_chunk=on_chunk, on_done=on_done, on_error=on_error,
                           stop_flag=stop_flag)
            except Exception as e:
                self._post(lambda: on_error(str(e)))

        self.root.after(90, flush)
        self._gen_thread = threading.Thread(target=work, daemon=True)
        self._gen_thread.start()

    def _build_messages(self):
        facts = self.mem.prompt_block(self._last_user_text(), 5)
        sys_prompt = persona_mod.system_prompt(self.persona, facts, self._last_talk, self._mood)
        msgs = [{'role': 'system', 'content': sys_prompt}]
        if self._attached:
            names = '、'.join(os.path.basename(p.rstrip('\\/')) for p in self._attached[:5])
            msgs.append({'role': 'system',
                         'content': '用户刚拖进来这些文件：%s。'
                                    '如果他说的是转换格式，交给本地技能处理；'
                                    '否则当普通聊天回答，别编造文件内容；'
                                    '也不要承诺你做不到的文件操作（拆分、合并、重命名、整理、'
                                    'OCR、翻译等），直接说你只会转换格式。' % names})
        for m in self._chat_msgs[-10:]:
            msgs.append({'role': m['role'], 'content': m['content']})
        return msgs

    def _last_user_text(self):
        for m in reversed(self._chat_msgs):
            if m.get('role') == 'user':
                return m.get('content', '')
        return ''

    def _say_offline(self, q):
        text = self.reply(q)
        clean, emo = mood.parse(text)
        self.say(clean or text, 3800)
        self.play_mood(mood.to_emotion(emo, clean or text))
        lab = self._chat_add('灵灵', clean or text)
        if lab is not None:
            self._chat_msgs.append({'role': 'assistant', 'content': clean or text})
            self._save_history()

    def reply(self, q):
        """没配模型时的陪聊：先认「关于她自己」的几句话，其余随机挑台词。"""
        return offline_reply(self.lines, q)

    # ---------------- 历史与记忆 ----------------
    def _history_path(self):
        return paths.data_path('history.json')

    def _load_history(self):
        data = paths.read_json(self._history_path(), [])
        return data if isinstance(data, list) else []

    def _save_history(self):
        items = [{'role': m['role'], 'text': m['content'], 'ts': time.time()}
                 for m in self._chat_msgs[-HISTORY_KEEP:]]
        paths.write_json(self._history_path(), items)

    def _maybe_extract(self):
        """每 EXTRACT_EVERY 轮，让模型提炼一次记忆（后台线程，失败就算了）。"""
        if self._turn_count % EXTRACT_EVERY != 0:
            return
        if not llm.ready(self.cfg.get('llm')):
            return
        lines = ['%s：%s' % ('你' if m['role'] == 'user' else '灵灵', m['content'])
                 for m in self._chat_msgs[-16:]]

        def work():
            try:
                text = llm.complete(self.cfg.get('llm'),
                                    memory_mod.extract_messages(lines),
                                    temperature=0.2, timeout=25)
                facts = memory_mod.parse_extracted(text)
                if facts:
                    self.mem.add_many(facts)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

