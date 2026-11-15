# -*- coding: utf-8 -*-
"""让 Tk 窗口接收「从资源管理器拖进来的文件」。

tkinter 本身不支持文件拖放，这里用 Win32 的方式：
DragAcceptFiles + 子类化窗口过程，处理 WM_DROPFILES。

副作用只在当前窗口上：拖窗移动的逻辑完全不受影响（那是 Tk 自己的鼠标事件）。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
shell32.DragFinish.argtypes = [wintypes.HANDLE]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint,
                             wintypes.WPARAM, wintypes.LPARAM)

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint,
                                   wintypes.WPARAM, wintypes.LPARAM]
shell32.DragQueryFileW.restype = ctypes.c_uint
shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, ctypes.c_uint,
                                   ctypes.c_wchar_p, ctypes.c_uint]

_handlers = []


class _DropHandler(object):
    def __init__(self, hwnd, root, callback):
        self.hwnd = hwnd
        self.root = root
        self.callback = callback
        self.old_proc = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
        self.proc = WNDPROC(self._wndproc)
        user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(self.proc, ctypes.c_void_p).value)
        shell32.DragAcceptFiles(hwnd, True)

    def _read(self, hdrop):
        count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        paths = []
        for i in range(count):
            length = shell32.DragQueryFileW(hdrop, i, None, 0)
            buf = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(hdrop, i, buf, length + 1)
            if buf.value:
                paths.append(buf.value)
        return paths

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                paths = self._read(wparam)
                shell32.DragFinish(wparam)
                if paths:
                    self.root.after(0, lambda p=list(paths): self.callback(p))
                return 0
            except Exception:
                pass
        return user32.CallWindowProcW(self.old_proc, hwnd, msg, wparam, lparam)

    def detach(self):
        try:
            shell32.DragAcceptFiles(self.hwnd, False)
            user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self.old_proc)
        except Exception:
            pass


def enable(root, callback):
    """给 Tk 的根窗口开启文件拖放，回调收到 [路径, ...]。"""
    try:
        root.update_idletasks()
        hwnd = int(root.winfo_id())
        # winfo_id 是子窗口，真正接收拖放的是顶层
        parent = user32.GetParent(hwnd)
        hwnd = parent if parent else hwnd
        handler = _DropHandler(hwnd, root, callback)
        _handlers.append(handler)
        return handler
    except Exception:
        return None


# ------------------------------------------------------------------ 测试用
class DROPFILES(ctypes.Structure):
    _fields_ = [('pFiles', wintypes.DWORD), ('pt', wintypes.POINT),
                ('fNC', wintypes.BOOL), ('fWide', wintypes.BOOL)]


def make_hdrop(paths):
    """构造一个 HDROP，用于测试（模拟系统拖放）。"""
    text = '\0'.join(paths) + '\0\0'
    data = text.encode('utf-16-le')
    header = DROPFILES()
    header.pFiles = ctypes.sizeof(DROPFILES)
    header.pt = wintypes.POINT(0, 0)
    header.fNC = False
    header.fWide = True
    total = ctypes.sizeof(DROPFILES) + len(data)
    hglobal = kernel32.GlobalAlloc(0x0042, total)   # GMEM_MOVEABLE | GMEM_ZEROINIT
    ptr = kernel32.GlobalLock(hglobal)
    ctypes.memmove(ptr, ctypes.byref(header), ctypes.sizeof(DROPFILES))
    ctypes.memmove(ptr + ctypes.sizeof(DROPFILES), data, len(data))
    kernel32.GlobalUnlock(hglobal)
    return hglobal


def simulate_drop(root, paths):
    """测试钩子：直接往窗口丢一个假的拖放事件。"""
    hwnd = int(root.winfo_id())
    parent = user32.GetParent(hwnd)
    hwnd = parent if parent else hwnd
    hdrop = make_hdrop(paths)
    user32.SendMessageW(hwnd, WM_DROPFILES, hdrop, 0)
    return hdrop
