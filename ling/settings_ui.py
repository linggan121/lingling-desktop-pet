# -*- coding: utf-8 -*-
"""设置窗口：改模型、填 Key、测试连接。

布局用 grid（label 一列、控件一列），避免 pack 混用父容器导致控件被挤成 1px。
"""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from . import llm, ollama

ACCENT = '#7C3DDB'
BG = '#FFFFFF'
TEXT = '#2C2738'
HINT = '#8A8496'


class SettingsWindow(object):
    def __init__(self, root, cfg, on_save, scale=1.0, anchor=None):
        self.root = root
        self.s = max(0.8, float(scale or 1.0))
        self.on_save = on_save
        self.cfg = dict(cfg or {})

        self._ui_queue = queue.Queue()
        self.provider_labels = [p['label'] for p in llm.PROVIDERS.values()]
        self.provider_keys = list(llm.PROVIDERS.keys())

        self.win = tk.Toplevel(root)
        self.win.title('灵灵设置')
        self.win.configure(bg=BG)
        w, h = int(round(470 * self.s)), int(round(430 * self.s))
        self._size = (w, h)
        self._anchor = anchor
        if anchor is None:
            self.win.geometry('%dx%d' % (w, h))
        self.win.attributes('-topmost', True)
        self.win.resizable(False, False)

        # 按钮条先占住底部：内容再长也不会把它挤出去
        bar = tk.Frame(self.win, bg=BG)
        bar.pack(side='bottom', fill='x', padx=16, pady=(6, 14))

        head = tk.Frame(self.win, bg=ACCENT, height=44)
        head.pack(fill='x')
        tk.Label(head, text='灵灵设置', bg=ACCENT, fg='#fff',
                 font=('Microsoft YaHei', 11, 'bold')).pack(side='left', padx=14, pady=10)

        body = tk.Frame(self.win, bg=BG)
        body.pack(fill='both', expand=True, padx=16, pady=(12, 0))

        tk.Label(body, text='对话模型', bg=BG, fg=TEXT,
                 font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        tk.Label(body, text='不填 Key 也能用，灵灵会说自己内置的台词；Ollama 不需要 Key。',
                 bg=BG, fg=HINT, font=('Microsoft YaHei', 8),
                 wraplength=430, justify='left').pack(anchor='w', pady=(2, 10))

        form = tk.Frame(body, bg=BG)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)

        self.provider_var = tk.StringVar()
        self.base_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.key_var = tk.StringVar()

        self.provider_box = ttk.Combobox(form, textvariable=self.provider_var,
                                         values=self.provider_labels, state='readonly',
                                         font=('Microsoft YaHei', 9))
        self.provider_box.bind('<<ComboboxSelected>>', self._on_provider)

        self.base_entry = tk.Entry(form, textvariable=self.base_var,
                                   font=('Consolas', 9), relief='solid', bd=1)
        self.model_entry = tk.Entry(form, textvariable=self.model_var,
                                    font=('Consolas', 9), relief='solid', bd=1)
        self.key_entry = tk.Entry(form, textvariable=self.key_var, show='*',
                                  font=('Consolas', 9), relief='solid', bd=1)
        self.vision_var = tk.StringVar()
        self.vision_entry = tk.Entry(form, textvariable=self.vision_var,
                                     font=('Consolas', 9), relief='solid', bd=1)

        rows = [
            ('服务商', self.provider_box),
            ('接口地址', self.base_entry),
            ('模型名', self.model_entry),
            ('API Key', self.key_entry),
            ('视觉模型', self.vision_entry),
        ]
        for i, (label, widget) in enumerate(rows):
            tk.Label(form, text=label, bg=BG, fg=TEXT, width=7, anchor='w',
                     font=('Microsoft YaHei', 9)).grid(row=i, column=0, sticky='w', pady=5)
            widget.grid(row=i, column=1, sticky='ew', padx=(6, 0), pady=5, ipady=3)

        self.target_label = tk.Label(body, text='', bg=BG, fg=HINT,
                                     font=('Microsoft YaHei', 8),
                                     wraplength=int(420 * self.s), justify='left')
        self.target_label.pack(anchor='w', pady=(10, 0))
        tk.Label(body, text='Key 只保存在本机 settings.json，不会上传到别处。',
                 bg=BG, fg=HINT, font=('Microsoft YaHei', 8)).pack(anchor='w', pady=(2, 0))
        tk.Label(body, text='视觉模型 = 看屏幕用的多模态模型；留空就用上面的对话模型'
                            '（需支持图片，例如 gpt-4o / glm-4v / qwen-vl-plus / llava）。',
                 bg=BG, fg=HINT, font=('Microsoft YaHei', 8), wraplength=int(430 * self.s),
                 justify='left').pack(anchor='w', pady=(2, 0))

        self.local_tuned_var = tk.BooleanVar(value=True)
        tune_row = tk.Frame(body, bg=BG)
        tune_row.pack(anchor='w', pady=(6, 0))
        tk.Checkbutton(tune_row, text='本地模型优化（回复更短、温度更低，适合小模型）',
                       variable=self.local_tuned_var, bg=BG, fg=TEXT,
                       activebackground=BG, selectcolor=BG,
                       font=('Microsoft YaHei', 9)).pack(side='left')
        tk.Button(tune_row, text='生成上下文配置', command=self._write_modelfile,
                  relief='flat', bg='#EAF1FB', fg='#1F5FAF',
                  font=('Microsoft YaHei', 8), padx=8, pady=2).pack(side='left', padx=(8, 0))

        self.status = tk.Label(body, text='', bg=BG, fg=HINT,
                               font=('Microsoft YaHei', 8), wraplength=430, justify='left')
        self.status.pack(anchor='w', pady=(6, 0))

        self.install_row = tk.Frame(body, bg=BG)
        self.install_btn = tk.Button(self.install_row, text='一键安装本地模型（约 3 GB）',
                                     command=self._install_local, relief='flat',
                                     bg='#FFF3E0', fg='#B25B00',
                                     font=('Microsoft YaHei', 9, 'bold'),
                                     padx=12, pady=4)
        self.install_btn.pack(side='left')

        self.local_btn = tk.Button(bar, text='本地模型', command=self._pick_local,
                                   relief='flat', bg='#EAF1FB', fg='#1F5FAF',
                                   font=('Microsoft YaHei', 9), padx=8, pady=4)
        self.local_btn.pack(side='left', padx=(8, 0))
        tk.Button(bar, text='测试连接', command=self._test, relief='flat',
                  bg='#F0EBFA', fg=ACCENT, font=('Microsoft YaHei', 9),
                  padx=10, pady=4).pack(side='left')
        self.auto_btn = tk.Button(bar, text='自动匹配', command=self._auto_match,
                                  relief='flat', bg='#EAF4EA', fg='#2E7D32',
                                  font=('Microsoft YaHei', 9), padx=8, pady=4)
        self.auto_btn.pack(side='left', padx=(8, 0))
        tk.Button(bar, text='保存', command=self._save, relief='flat',
                  bg=ACCENT, fg='#fff', font=('Microsoft YaHei', 9, 'bold'),
                  padx=18, pady=4).pack(side='right')
        tk.Button(bar, text='取消', command=self.win.destroy, relief='flat',
                  bg='#EFEFEF', fg=TEXT, font=('Microsoft YaHei', 9),
                  padx=14, pady=4).pack(side='right', padx=(0, 8))

        # 粘贴 Key 时直接可用，不用先点输入框
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        for entry in (self.base_entry, self.model_entry, self.key_entry):
            entry.bind('<Control-a>', lambda e, w=entry: (w.select_range(0, 'end'), 'break')[1])

        try:
            self.win.update_idletasks()
            need_w = max(self._size[0], self.win.winfo_reqwidth())
            need_h = max(self._size[1], self.win.winfo_reqheight())
            limit_h = int(self.win.winfo_screenheight() * 0.9)
            need_h = min(need_h, limit_h)
            self._size = (need_w, need_h)
        except Exception:
            pass
        if self._anchor is not None:
            try:
                self.win.update_idletasks()
                self._anchor(self.win, *self._size)
            except Exception:
                pass
        for var in (self.base_var, self.model_var):
            try:
                var.trace_add('write', lambda *a: self._refresh_target())
            except Exception:
                pass
        self._apply_cfg(self.cfg)
        try:
            self.win.after(80, self._pump_ui)
        except Exception:
            pass
        try:
            self.win.after(120, self._focus_start)
        except Exception:
            pass

    def _focus_start(self):
        """打开就把焦点给她，免得用户以为「点不进去」。"""
        try:
            self.win.lift()
            self.win.focus_force()
            self.key_entry.focus_set()
        except Exception:
            pass

    # ---------------- 数据 ----------------
    def _write_modelfile(self):
        """按当前模型生成 Modelfile（num_ctx 4096），并说明怎么用。"""
        model = (self.model_var.get() or '').strip() or 'qwen2.5:3b'
        try:
            from . import paths
            path = ollama.write_modelfile(paths.data_path(''), model)
        except Exception as exc:
            self._set_status(text='生成失败：%s' % str(exc)[:50], fg='#C62828')
            return
        variant = model.split(':')[0] + '-lingling'
        self._set_status(
            text='已生成配置：%s\n接着在命令行执行：\n'
                 'ollama create %s -f "%s"\n'
                 '然后模型名填 %s，上下文就是 4096 了。' % (path, variant, path, variant),
            fg='#2E7D32')

    def _apply_cfg(self, cfg):
        provider = cfg.get('provider') or 'deepseek'
        preset = llm.PROVIDERS.get(provider, llm.PROVIDERS['deepseek'])
        try:
            idx = self.provider_labels.index(preset['label'])
        except ValueError:
            idx = 0
        self.provider_var.set(self.provider_labels[idx])
        self.base_var.set(cfg.get('base_url') or preset.get('base_url', ''))
        self.model_var.set(cfg.get('model') or preset.get('model', ''))
        self.key_var.set(cfg.get('api_key') or '')
        self.vision_var.set(cfg.get('vision_model') or '')
        tuned = cfg.get('local_tuned')
        try:
            self.local_tuned_var.set(True if tuned is None else bool(tuned))
        except Exception:
            pass
        try:
            self._refresh_target()
        except Exception:
            pass

    def _current_provider_key(self):
        label = self.provider_var.get()
        try:
            return self.provider_keys[self.provider_labels.index(label)]
        except Exception:
            return 'deepseek'

    def _post(self, fn):
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
            self.win.after(80, self._pump_ui)
        except Exception:
            pass

    def _set_status(self, text='', fg=HINT):
        """设置状态文字；不够高就把窗口撑高，别把按钮和文字裁掉。"""
        try:
            self.status.config(text=text, fg=fg)
        except Exception:
            return
        try:
            self.win.update_idletasks()
            need = self.win.winfo_reqheight()
            cur = self.win.winfo_height()
            if need > cur:
                sh = self.win.winfo_screenheight()
                h = min(need + 6, int(sh * 0.9))
                w = self.win.winfo_width()
                x, y = self.win.winfo_x(), self.win.winfo_y()
                if y + h > sh - 8:
                    y = max(8, sh - h - 8)
                self.win.geometry('%dx%d+%d+%d' % (w, h, x, y))
        except Exception:
            pass

    def _refresh_target(self):
        try:
            base = self.base_var.get().strip()
            model = self.model_var.get().strip() or '（模型空）'
            if not base:
                self.target_label.config(text='会请求：（接口地址为空，选个服务商就会自动填）')
                return
            url = llm.endpoint(base)
            self.target_label.config(text='会请求：%s    模型：%s' % (url, model))
        except Exception:
            self.target_label.config(text='会请求：地址看起来不对')

    def _auto_match(self):
        """拿这把 Key 并行试常见服务商；成功就把服务商/地址/模型全填好并保存。"""
        key = llm.clean_key(self.key_var.get())
        if not key:
            self._set_status(text='先把 API Key 粘进来', fg='#C62828')
            return
        order = ['deepseek', 'doubao', 'siliconflow', 'qwen', 'moonshot', 'zhipu',
                 'openrouter', 'openai']
        if key.startswith('ark-'):
            order.remove('doubao')
            order.insert(0, 'doubao')
        self._set_status(text='正在同时试这几家…（各发一条测试消息）', fg=HINT)
        try:
            self.auto_btn.config(state='disabled')
        except Exception:
            pass

        probe_msgs = [{'role': 'user', 'content': '回复两个字：在的'}]

        def probe(name):
            base_cfg = {'provider': name, 'api_key': key}
            try:
                llm.complete(base_cfg, probe_msgs, temperature=0.1, timeout=6)
                return (name, '', '')
            except Exception as exc:
                msg = str(exc)
                # 钥匙不对 / 没配 / 网络不通 → 都不算「这家认这把 Key」
                if ('钥匙' in msg or '还没填' in msg
                        or '连不上' in msg or 'timed out' in msg.lower()
                        or 'timed out' in msg or '超时' in msg):
                    return None
                # 这家认这把 Key，只是默认模型不对：先拉模型列表挑，挑不到就挨个试常见模型
                try:
                    cands = llm.list_models(base_cfg, timeout=6)
                    pick = llm.pick_chat_model(cands, name)
                    if pick:
                        llm.complete(dict(base_cfg, model=pick), probe_msgs,
                                     temperature=0.1, timeout=8)
                        return (name, pick, '')
                except Exception:
                    pass
                for candidate in llm.FALLBACK_MODELS.get(name, []):
                    try:
                        llm.complete(dict(base_cfg, model=candidate), probe_msgs,
                                     temperature=0.1, timeout=8)
                        return (name, candidate, '')
                    except Exception as exc2:
                        msg = str(exc2)
                        if '钥匙' in msg:
                            break
                return (name, '', msg[:60])

        def work():
            results = []
            state = {'done': 0}
            lock = threading.Lock()

            def run(name):
                try:
                    r = probe(name)
                    if r is not None:
                        with lock:
                            results.append(r)
                finally:
                    with lock:
                        state['done'] += 1

            threads = [threading.Thread(target=run, args=(n,), daemon=True) for n in order]
            for t in threads:
                t.start()
            deadline = time.time() + 14
            while time.time() < deadline:
                with lock:
                    if any(r[2] == '' for r in results):
                        break
                    if state['done'] >= len(order):
                        break
                time.sleep(0.1)

            with lock:
                snapshot = list(results)

            best = None
            for r in snapshot:
                if r[2] == '':
                    best = r
                    break
            if best is None and snapshot:
                best = snapshot[0]

            def ui():
                try:
                    self.auto_btn.config(state='normal')
                except Exception:
                    pass
                if best is None:
                    self._set_status(text='这几家都不认这把 Key，检查是不是复制错了，'
                                            '或者问下 Key 是哪家的', fg='#C62828')
                    return
                name, model, note = best
                preset = llm.PROVIDERS[name]
                try:
                    self.provider_var.set(preset['label'])
                    self.base_var.set(preset['base_url'])
                    self.model_var.set(model or preset['model'])
                except Exception:
                    pass
                self._refresh_target()
                if not note:
                    self._save(silent=True)
                if note:
                    extra = ('模型名要填方舟的 Model ID，比如 doubao-seed-2-1-turbo-260628。'
                             if name == 'doubao' else '')
                    self._set_status(text='能连上，但模型名不对。%s' % extra, fg='#EF6C00')
                else:
                    self._set_status(text='匹配到「%s」，模型用 %s，已自动保存'
                                            % (preset['label'], model or preset['model']),
                                       fg='#2E7D32')

            self._post(ui)

        threading.Thread(target=work, daemon=True).start()

    # ---------------- 本地 Ollama ----------------
    def _pick_local(self):
        """探测本机 Ollama，列出已下载模型，选一个切过去。"""
        self._set_status(text='正在看本机有没有 Ollama…', fg=HINT)

        def work():
            info = ollama.probe()
            self._post(lambda: self._show_local(info))

        threading.Thread(target=work, daemon=True).start()

    def _ensure_height(self):
        """内容变高时把窗口撑开，别把按钮挤到看不见。"""
        try:
            self.win.update_idletasks()
            need = self.win.winfo_reqheight()
            cur = self.win.winfo_height()
            if need > cur:
                sh = self.win.winfo_screenheight()
                h = min(need + 6, int(sh * 0.9))
                w = self.win.winfo_width() or self._size[0]
                x, y = self.win.winfo_x(), self.win.winfo_y()
                if y + h > sh - 8:
                    y = max(8, sh - h - 8)
                self.win.geometry('%dx%d+%d+%d' % (w, h, x, y))
        except Exception:
            pass

    def _show_install(self, text, needs_ollama=True):
        self._install_needs_ollama = needs_ollama
        self._set_status(text=text, fg='#EF6C00')
        try:
            self.install_btn.config(
                text='一键安装本地模型（约 3 GB）' if needs_ollama
                else '只下载模型 qwen2.5:3b（约 2 GB）')
            self.install_row.pack(anchor='w', pady=(6, 0))
        except Exception:
            pass
        self._ensure_height()

    def _hide_install(self):
        try:
            self.install_row.pack_forget()
        except Exception:
            pass

    def _show_local(self, info):
        self._local_info = info
        if not info.get('alive'):
            self._show_install(
                text='没检测到本机 Ollama。点下面「一键安装」会自动装好并下载 3B 小模型；'
                     '自己装好也可以直接点「本地模型」。', needs_ollama=True)
            return
        models = info.get('models') or []
        if not models:
            self._show_install(
                text='Ollama 已经装好了（v%s），只是还没下载模型。点下面按钮直接下，'
                     '不会重复安装。' % (info.get('version') or '?'), needs_ollama=False)
            return
        self._hide_install()
        self._set_status(text='检测到 Ollama（v%s），共 %d 个模型'
                             % (info.get('version') or '?', len(models)), fg='#2E7D32')
        self._dialog_models(models, info.get('host') or ollama.DEFAULT_HOST)

    def _ask_dir(self):
        from tkinter import filedialog
        start = getattr(self, '_install_dir', '')
        if not start or not os.path.isdir(start):
            for candidate in ('D:\\', 'E:\\', 'C:\\'):
                if os.path.isdir(candidate):
                    start = candidate
                    break
        return filedialog.askdirectory(
            parent=self.win, mustexist=False,
            title='选择安装位置（Ollama 和模型都会放在这个目录下）',
            initialdir=start)

    def _cancel_install(self):
        try:
            ollama.abort_all()
        except Exception:
            pass
        self._set_status(text='已经取消安装。装了一半的模型会留在磁盘上，'
                             '下次点「一键安装」会接着用。', fg='#EF6C00')
        try:
            self.install_btn.config(state='normal', text='一键安装本地模型（约 3 GB）',
                                    command=self._install_local)
        except Exception:
            pass

    def _install_local(self):
        """先选安装位置，再装 Ollama + 拉 qwen2.5:3b。"""
        from tkinter import filedialog

        needs_ollama = getattr(self, '_install_needs_ollama', True)
        if not needs_ollama:
            base = None
        else:
            base = self._ask_dir()
            if not base:
                return
            self._install_dir = base

        try:
            self.install_btn.config(state='normal', text='取消安装',
                                    command=self._cancel_install)
        except Exception:
            pass
        self._set_status(text='准备安装…（第一次要下载 3 GB 左右，耐心等）', fg=HINT)

        def progress(msg):
            self._post(lambda: self._set_status(text=msg, fg=HINT))

        def work():
            try:
                ok, info = ollama.install_to(base, progress=progress, model='qwen2.5:3b')
            except Exception as exc:
                ok, info = False, str(exc)[:80]

            def done():
                try:
                    self.install_btn.config(state='normal', text='一键安装本地模型（约 3 GB）',
                                            command=self._install_local)
                except Exception:
                    pass
                if ok:
                    try:
                        where = ollama.paths_info()
                        extra = '\n程序在 %s\n模型在 %s' % (where['cli'] or '已安装',
                                                          where['models'])
                    except Exception:
                        extra = ''
                    self._set_status(text='装好了：%s，正在切换…%s' % (info, extra),
                                     fg='#2E7D32')
                    self._hide_install()
                    self._pick_local()
                else:
                    self._set_status(text='没装成：%s' % info, fg='#C62828')
                    try:
                        self.install_row.pack(anchor='w', pady=(6, 0))
                    except Exception:
                        pass
                    self._ensure_height()

            self._post(done)

        threading.Thread(target=work, daemon=True).start()

    def _dialog_models(self, models, host):
        win = tk.Toplevel(self.win)
        win.title('选择本地模型')
        win.configure(bg=BG)
        win.transient(self.win)
        win.attributes('-topmost', True)
        tk.Label(win, text='本机已下载的模型（双击直接用）：', bg=BG, fg=TEXT,
                 font=('Microsoft YaHei', 10)).pack(anchor='w', padx=14, pady=(12, 6))
        box = tk.Listbox(win, height=min(10, max(3, len(models))), width=40,
                         font=('Consolas', 10), relief='solid', bd=1,
                         selectbackground=ACCENT, selectforeground='#FFFFFF')
        for name in models:
            box.insert('end', name)
        box.selection_set(0)
        box.pack(fill='both', expand=True, padx=14, pady=(0, 10))

        def use(event=None):
            sel = box.curselection()
            if not sel:
                return
            model = box.get(sel[0])
            win.destroy()
            self._apply_local(model, host)

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill='x', padx=14, pady=(0, 12))
        tk.Button(bar, text='用这个模型', command=use, relief='flat', bg=ACCENT, fg='#fff',
                  font=('Microsoft YaHei', 9, 'bold'), padx=16, pady=4).pack(side='right')
        tk.Button(bar, text='取消', command=win.destroy, relief='flat', bg='#EFEFEF',
                  fg=TEXT, font=('Microsoft YaHei', 9), padx=12, pady=4
                  ).pack(side='right', padx=(0, 8))
        box.bind('<Double-Button-1>', use)
        win.bind('<Escape>', lambda e: win.destroy())
        win.bind('<Return>', use)

    def _apply_local(self, model, host):
        cfg = ollama.apply_model({'provider': self._current_provider_key()}, model, host)
        provider = cfg['provider']
        preset = llm.PROVIDERS.get(provider, llm.PROVIDERS['deepseek'])
        try:
            idx = self.provider_labels.index(preset['label'])
        except ValueError:
            idx = 0
        self.provider_var.set(self.provider_labels[idx])
        self.base_var.set(cfg['base_url'])
        self.model_var.set(cfg['model'])
        self.key_var.set('')
        self._set_status(text='已切到本地模型 %s，正在测试能不能通…' % model, fg=HINT)
        self._test()

    def _on_provider(self, event=None):
        key = self._current_provider_key()
        preset = llm.PROVIDERS.get(key, {})
        self.base_var.set(preset.get('base_url', ''))
        self.model_var.set(preset.get('model', ''))
        if key == 'ollama':
            self._set_status(text='Ollama 要先在本机跑起来：ollama serve', fg=HINT)
        elif key == 'custom':
            self._set_status(text='自定义：地址填到 /v1 这一层就行', fg=HINT)
        else:
            self._set_status(text='', fg=HINT)
        self._refresh_target()

    def _collect(self):
        return {
            'provider': self._current_provider_key(),
            'base_url': self.base_var.get().strip(),
            'model': self.model_var.get().strip(),
            'api_key': self.key_var.get().strip(),
            'vision_model': self.vision_var.get().strip(),
            'local_tuned': bool(self.local_tuned_var.get()),
        }

    # ---------------- 动作 ----------------
    def _save(self, silent=False):
        cfg = self._collect()
        if self.on_save:
            self.on_save(cfg)
        if not silent:
            self._set_status(text='已保存，下次开口就生效', fg='#2E7D32')

    def _test(self):
        cfg = self._collect()
        if not llm.ready(cfg):
            self._set_status(text='还差点东西：地址/模型为空，或者没填 Key', fg='#C62828')
            return
        self._set_status(text='正在连接…', fg=HINT)

        def work():
            try:
                text = llm.complete(cfg, [{'role': 'user', 'content': '回复两个字：在的'}],
                                    temperature=0.2, timeout=20)
                msg = '连接成功：' + (text.strip()[:40] or '（空回复）') + '　（已自动保存）'
                color = '#2E7D32'
                try:
                    self._save(silent=True)
                except Exception:
                    pass
            except Exception as e:
                msg = '连接失败：' + str(e)[:80]
                color = '#C62828'
            try:
                self._post(lambda: self._set_status(text=msg, fg=color))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()
