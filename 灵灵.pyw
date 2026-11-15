# -*- coding: utf-8 -*-
"""灵灵 · 独立桌宠（启动入口）

只做桌宠的事：动画、气泡、拖动、投喂、漫游、陪聊、换装、看屏幕。
联网是可选的——没配模型时她只说自己的台词。

  pythonw 灵灵.pyw              正常启动
  python  灵灵.pyw --selftest   自检：打印帧数后退出
  python  灵灵.pyw --settings   启动并直接打开设置窗口
"""
from __future__ import annotations

import os
import sys

from ling import frames

__all__ = ['Pet']

_MUTEX = {'handle': None}


def already_running():
    """同一时间只允许一只灵灵（用命名互斥量，进程退出自动释放）。"""
    if os.environ.get('LING_ALLOW_MULTI') == '1':
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, 'Local\\ling_pet_single_instance')
        _MUTEX['handle'] = handle          # 保持引用，别被回收
        return kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def selftest():
    rows = frames.load_frames(1.0)
    total = sum(len(v) for v in rows.values())
    print('SELFTEST_OK rows=%d frames=%d' % (len(rows), total))
    return 0


def main():
    if '--selftest' in sys.argv:
        return selftest()
    if already_running():
        if '--settings' in sys.argv:
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo('灵灵', '灵灵已经在桌面上啦～\n要改设置就在她身上点右键。')
                root.destroy()
            except Exception:
                pass
        return 0

    from ling.pet import Pet
    app = Pet()
    if '--settings' in sys.argv:
        app.root.after(1200, app.open_settings)
    app.root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
