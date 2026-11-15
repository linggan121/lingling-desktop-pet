# -*- coding: utf-8 -*-
"""Filee 命令行封装：查格式、查预设、转换、盯着文件夹。

Filee 是一个 MIT 许可的开源文件转换器（https://github.com/KnifeLemon/Filee），
在 Windows 上通常装在 D:\\Filee，CLI 是 filee.cmd / filee-cli.exe。
我们只调用它的进程，不复制它的代码。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
TIMEOUT = 600


def _startupinfo():
    si = None
    if os.name == 'nt':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def find_cli():
    """找 filee 可执行文件；找不到返回空串。"""
    found = shutil.which('filee')
    if found:
        return found
    candidates = []
    local = os.environ.get('LOCALAPPDATA') or ''
    pf = os.environ.get('ProgramFiles') or ''
    for base in ('D:\\Filee', 'C:\\Filee', os.path.join(local, 'Programs', 'Filee'),
                 os.path.join(pf, 'Filee')):
        if not base:
            continue
        candidates += [os.path.join(base, 'cli', 'filee.cmd'),
                       os.path.join(base, 'filee-cli.exe'),
                       os.path.join(base, 'Filee.exe')]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ''


def available():
    return bool(find_cli())


def run(args, timeout=TIMEOUT):
    """跑一条 filee 命令，返回 (退出码, 标准输出, 标准错误)。"""
    cli = find_cli()
    if not cli:
        raise RuntimeError('还没装 Filee')
    cmd = [cli] + list(args)
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                          startupinfo=_startupinfo(),
                          creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0)
    out = proc.stdout.decode('utf-8', 'ignore')
    err = proc.stderr.decode('utf-8', 'ignore')
    return proc.returncode, out, err


# ------------------------------------------------------------------ 格式 / 预设
def formats():
    """返回 {分组: [(格式名, 说明, [扩展名...]), ...]}。"""
    code, out, err = run(['formats'])
    if code != 0:
        return {}
    groups = {}
    current = None
    for line in out.splitlines():
        if not line.strip():
            continue
        if not line.startswith(' ') and line.rstrip().endswith(':'):
            current = line.strip().rstrip(':')
            groups[current] = []
            continue
        if current is None:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        exts = [p for p in parts[2:] if p.startswith('.')]
        groups[current].append((name, parts[1], exts))
    return groups


def format_names():
    names = []
    for items in formats().values():
        names += [it[0] for it in items]
    return names


def group_of(ext):
    """给定扩展名（不带点），返回它所属的分组名。"""
    ext = (ext or '').lower().lstrip('.')
    for group, items in formats().items():
        for _name, _label, exts in items:
            if any(e.lower().lstrip('.') == ext for e in exts):
                return group
    return ''


def targets_for(ext):
    """某个扩展名在同一分组里能转成哪些格式（不含自身）。"""
    ext = (ext or '').lower().lstrip('.')
    group = group_of(ext)
    if not group:
        return []
    return [name for name, _label, exts in formats().get(group, [])
            if not any(e.lower().lstrip('.') == ext for e in exts)]


def presets():
    """返回 [(id, 名称, 目标格式), ...]。"""
    code, out, err = run(['presets'])
    if code != 0:
        return []
    rows = []
    for line in out.splitlines():
        if not line.strip() or line.lower().startswith('id '):
            continue
        parts = line.split()
        if len(parts) >= 3:
            rows.append((parts[0], ' '.join(parts[1:-1]), parts[-1]))
    return rows


def preset_ids():
    return [p[0] for p in presets()]


# ------------------------------------------------------------------ 转换
def build_convert_args(paths, to=None, preset=None, quality=None, out=None,
                       recursive=False, overwrite=False):
    args = ['convert'] + list(paths)
    if to:
        args += ['--to', to]
    if preset:
        args += ['--preset', preset]
    if quality:
        args += ['--quality', str(int(quality))]
    if out:
        args += ['--output', out]
    if recursive:
        args.append('--recursive')
    if overwrite:
        args.append('--overwrite')
    args += ['--json', '--quiet']
    return args


def convert(paths, to=None, preset=None, quality=None, out=None,
            recursive=False, overwrite=False, timeout=TIMEOUT):
    """执行转换，返回结构化结果。

    {'ok': bool, 'converted': int, 'failed': int, 'skipped': int,
     'outputs': [路径...], 'errors': [文本...], 'message': '给人看的一句话'}
    """
    paths = [p for p in paths if p]
    if not paths:
        return {'ok': False, 'converted': 0, 'failed': 0, 'skipped': 0,
                'outputs': [], 'errors': ['没有文件'], 'message': '没有要转换的文件'}
    args = build_convert_args(paths, to=to, preset=preset, quality=quality,
                              out=out, recursive=recursive, overwrite=overwrite)
    code, stdout, stderr = run(args, timeout=timeout)

    data = None
    start = stdout.find('{')
    if start >= 0:
        try:
            data = json.loads(stdout[start:])
        except Exception:
            data = None

    if data:
        outputs = []
        errors = []
        for item in data.get('files') or []:
            outputs += item.get('outputs') or []
            if item.get('state') not in ('done', 'skipped', None):
                errors.append('%s：%s' % (os.path.basename(item.get('source', '')),
                                          item.get('error') or item.get('state')))
        converted = int(data.get('converted') or 0)
        failed = int(data.get('failed') or 0)
        skipped = int(data.get('skipped') or 0)
    else:
        outputs, errors = [], [l.strip() for l in (stderr or stdout).splitlines() if l.strip()][:3]
        converted, failed, skipped = (1, 0, 0) if code == 0 else (0, 1, 0)

    if code == 0 and converted:
        message = '好了，%d 个文件转完了' % converted
    elif code == 3:
        message = '没有能转的文件（格式可能不支持）'
    elif failed:
        message = '%d 个成功，%d 个失败' % (converted, failed)
    else:
        message = '转换失败' + ('：' + errors[0] if errors else '')
    return {'ok': code == 0 and converted > 0, 'converted': converted, 'failed': failed,
            'skipped': skipped, 'outputs': outputs, 'errors': errors, 'message': message}


# ------------------------------------------------------------------ watch
def start_watch(folder, to=None, preset=None, out=None):
    """后台盯着一个文件夹，返回 Popen。"""
    cli = find_cli()
    if not cli:
        raise RuntimeError('还没装 Filee')
    args = [cli, 'watch', folder]
    if to:
        args += ['--to', to]
    if preset:
        args += ['--preset', preset]
    if out:
        args += ['--output', out]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            startupinfo=_startupinfo(),
                            creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return proc
