# -*- coding: utf-8 -*-
"""灵灵 · 独立桌宠（启动入口）

只做桌宠的事：动画、气泡、拖动、投喂、漫游、陪聊、看屏幕、文件技能。
联网是可选的——没配模型时她只说自己的台词。

  pythonw 灵灵.pyw              正常启动
  python  灵灵.pyw --selftest   自检：打印帧数后退出
  python  灵灵.pyw --engine-test 自检内置转换引擎（写日志后退出）
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


def engine_test():
    """打包后自检：确认转换引擎在冻结环境里能用（结果写日志）。"""
    import io
    import tempfile
    import traceback

    from ling import convert_engine, paths

    log_path = paths.data_path('engine_test.log')
    lines = []

    def log(msg):
        lines.append(str(msg))

    try:
        tmp = tempfile.mkdtemp(prefix='ling_engine_')
        try:
            from PIL import Image
            src = os.path.join(tmp, 'probe.png')
            Image.new('RGB', (240, 160), (80, 120, 200)).save(src)
            for target in ('webp', 'jpg', 'ico', 'pdf'):
                res = convert_engine.convert([src], target)
                log('%s -> ok=%s out=%s err=%s' % (target, res['ok'],
                                                  len(res['outputs']), res['errors'][:1]))
            import fitz  # noqa: F401
            log('pymupdf: OK')
            import pillow_heif  # noqa: F401
            log('pillow_heif: OK')
            import py7zr  # noqa: F401
            log('py7zr: OK')
            log('ENGINE_OK')
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        log(traceback.format_exc())
        log('ENGINE_FAIL')
    try:
        with io.open(log_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    except Exception:
        pass
    return 0


def main():
    if '--selftest' in sys.argv:
        return selftest()
    if '--engine-test' in sys.argv:
        return engine_test()
    if already_running():
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                '灵灵已经在运行',
                '桌面上已经有一只灵灵了。\n\n'
                '如果你刚换了新版本：先右键旧的灵灵 →「退出灵灵」，\n'
                '再双击新版本，否则打开的还是旧的那只。')
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
