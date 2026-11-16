# -*- coding: utf-8 -*-
"""本机 Ollama 探测：是否在跑、装了哪些模型。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import time
import urllib.request

CREATE_NO_WINDOW = 0x08000000
KILL_ON_CLOSE = 0x2000

_ACTIVE = []          # 正在跑的子进程（winget / ollama pull）
_JOB = {'handle': None}


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [('ReadOperationCount', ctypes.c_ulonglong),
                ('WriteOperationCount', ctypes.c_ulonglong),
                ('OtherOperationCount', ctypes.c_ulonglong),
                ('ReadTransferCount', ctypes.c_ulonglong),
                ('WriteTransferCount', ctypes.c_ulonglong),
                ('OtherTransferCount', ctypes.c_ulonglong)]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', ctypes.c_uint32),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', ctypes.c_uint32),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', ctypes.c_uint32),
                ('SchedulingClass', ctypes.c_uint32)]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _BASIC_LIMIT),
                ('IoInfo', _IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t)]


def _job_handle():
    """建一个 kill-on-close 的 Job：灵灵退出时，安装子进程一起结束。"""
    if os.name != 'nt':
        return None
    if _JOB['handle']:
        return _JOB['handle']
    try:
        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        handle = k32.CreateJobObjectW(None, None)
        info = _EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = KILL_ON_CLOSE
        k32.SetInformationJobObject(ctypes.c_void_p(handle), 9, ctypes.byref(info),
                                    ctypes.sizeof(info))
        _JOB['handle'] = handle
        return handle
    except Exception:
        return None


def _spawn(cmd, **kwargs):
    kwargs.setdefault('creationflags', CREATE_NO_WINDOW if os.name == 'nt' else 0)
    proc = subprocess.Popen(cmd, **kwargs)
    job = _job_handle()
    if job:
        try:
            ctypes.windll.kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(job), ctypes.c_void_p(int(proc._handle)))
        except Exception:
            pass
    _ACTIVE.append(proc)
    return proc


def abort_all():
    """取消安装：把还在跑的 winget / ollama pull 全部结束。"""
    while _ACTIVE:
        proc = _ACTIVE.pop()
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass


def active():
    return [p for p in _ACTIVE if p.poll() is None]


def paths_info():
    """安装/模型的实际位置，给界面显示用。"""
    exe = cli_path()
    models = os.path.join(os.path.expanduser('~'), '.ollama', 'models')
    return {'cli': exe, 'models': models}

DEFAULT_HOST = 'http://127.0.0.1:11434'


def _get(url, timeout=2.5):
    req = urllib.request.Request(url, headers={'User-Agent': 'lingling'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', 'ignore')


def parse_tags(payload):
    """把 /api/tags 的返回解析成模型名列表。"""
    try:
        data = json.loads(payload)
    except Exception:
        return []
    items = data.get('models') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        if isinstance(item, dict):
            name = item.get('name') or item.get('model') or ''
            if name:
                names.append(name)
    return names


def parse_version(payload):
    try:
        data = json.loads(payload)
        return str(data.get('version') or '')
    except Exception:
        return ''


def probe(host=DEFAULT_HOST, timeout=2.5):
    """返回 {'alive': bool, 'version': str, 'models': [...], 'error': str}"""
    base = (host or DEFAULT_HOST).rstrip('/')
    if base.endswith('/v1'):
        base = base[:-3]
    info = {'alive': False, 'version': '', 'models': [], 'error': '', 'host': base}
    try:
        info['version'] = parse_version(_get(base + '/api/version', timeout))
        info['models'] = parse_tags(_get(base + '/api/tags', timeout))
        info['alive'] = True
    except Exception as exc:
        info['error'] = str(exc)[:80]
    return info


def apply_model(cfg_llm, model, host=DEFAULT_HOST):
    """返回改成 Ollama 后的 llm 配置。"""
    cfg = dict(cfg_llm or {})
    base = (host or DEFAULT_HOST).rstrip('/')
    if base.endswith('/v1'):
        base = base[:-3]
    cfg.update({
        'provider': 'ollama',
        'base_url': base + '/v1',
        'model': model or 'qwen2.5:7b',
        'api_key': 'ollama',
    })
    return cfg



RECOMMENDED_NUM_CTX = 4096


def modelfile_text(model, num_ctx=RECOMMENDED_NUM_CTX):
    """生成 Ollama Modelfile：把上下文调到 4096（默认 2048 容易截断人设）。"""
    return (
        '# 灵灵推荐的本地配置：把上下文放大到 %d\n'
        'FROM %s\n'
        'PARAMETER num_ctx %d\n'
        'PARAMETER temperature 0.75\n'
        'PARAMETER top_p 0.9\n'
        'PARAMETER repeat_penalty 1.1\n'
    ) % (num_ctx, model, num_ctx)


def write_modelfile(data_dir, model, num_ctx=RECOMMENDED_NUM_CTX):
    """写出 Modelfile，返回路径。"""
    import os
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, 'Modelfile.lingling')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(modelfile_text(model, num_ctx))
    return path



# ------------------------------------------------------------------ 安装 / 拉模型
def cli_path():
    """找 ollama 命令行。"""
    found = shutil.which('ollama')
    if found:
        return found
    local = os.environ.get('LOCALAPPDATA') or ''
    candidates = [
        os.path.join(local, 'Programs', 'Ollama', 'ollama.exe'),
        r'C:\Program Files\Ollama\ollama.exe',
        r'C:\Program Files (x86)\Ollama\ollama.exe',
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ''


def _run(cmd, timeout=1800):
    proc = _spawn(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return 1, '', 'timeout'
    finally:
        if proc in _ACTIVE:
            _ACTIVE.remove(proc)
    return proc.returncode, (out or b'').decode('utf-8', 'ignore'), \
        (err or b'').decode('utf-8', 'ignore')


def install_ollama(progress=None, timeout=1800):
    """用 winget 装 Ollama；装不了返回 (False, 原因)。"""
    def log(msg):
        if progress:
            progress(msg)

    winget = shutil.which('winget')
    if not winget:
        return False, '这台机器没有 winget，请手动到 ollama.com 下载安装'
    log('正在用 winget 安装 Ollama（约 1 GB，可能要几分钟）…')
    code, out, err = _run([winget, 'install', '--id', 'Ollama.Ollama', '-e',
                           '--accept-package-agreements', '--accept-source-agreements',
                           '--silent'], timeout=timeout)
    if code == 0 or 'already installed' in (out + err).lower():
        return True, ''
    return False, (err or out or 'winget 安装失败')[:120]


def pull_model(exe, model, progress=None, timeout=3600):
    """下载模型，边下边回报。"""
    def log(msg):
        if progress:
            progress(msg)

    log('开始下载模型 %s（3B 约 2 GB，看网速）…' % model)
    cmd = [exe, 'pull', model]
    proc = _spawn(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    last = 0.0
    tail = ''
    try:
        for raw in iter(proc.stdout.readline, b''):
            line = raw.decode('utf-8', 'ignore').strip()
            if line:
                tail = line
            now = time.time()
            if now - last > 1.5:
                last = now
                log('下载中… %s' % tail[:60])
        proc.wait(timeout=timeout)
    except Exception as exc:
        try:
            proc.kill()
        except Exception:
            pass
        return False, str(exc)[:80]
    if proc in _ACTIVE:
        _ACTIVE.remove(proc)
    if proc.returncode == 0:
        return True, ''
    return False, tail[:80] or '下载失败'


def install_and_prepare(model='qwen2.5:3b', progress=None, host=DEFAULT_HOST):
    """完整流程：没装就装 → 拉模型 → 返回 (ok, 消息)。"""
    def log(msg):
        if progress:
            progress(msg)

    exe = cli_path()
    if not exe:
        ok, why = install_ollama(progress=progress)
        if not ok:
            return False, why
        for _ in range(30):
            time.sleep(2)
            exe = cli_path()
            if exe:
                break
        if not exe:
            return False, '装完了但没找到 ollama 命令，重开一次设置试试'

    info = probe(host, timeout=2.0)
    if not info.get('alive'):
        log('启动 Ollama 服务…')
        try:
            subprocess.Popen([exe, 'serve'], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception:
            pass
        for _ in range(15):
            time.sleep(2)
            if probe(host, timeout=2.0).get('alive'):
                break

    ok, why = pull_model(exe, model, progress=progress)
    if not ok:
        return False, why
    log('模型下载完成 ✓')
    info = paths_info()
    log('装好了：程序 %s，模型 %s' % (info['cli'] or '(已装)', info['models']))
    return True, model


# ------------------------------------------------------------------ 自定义位置安装
INSTALLER_URL = 'https://ollama.com/download/OllamaSetup.exe'


def _download(url, dest, progress=None, timeout=1800):
    def log(msg):
        if progress:
            progress(msg)

    req = urllib.request.Request(url, headers={'User-Agent': 'lingling'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get('Content-Length') or 0)
        got = 0
        with open(dest, 'wb') as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    log('下载安装包… %.0f%%（%.0f/%.0f MB）'
                        % (got * 100.0 / total, got / 1048576.0, total / 1048576.0))
                else:
                    log('下载安装包… %.0f MB' % (got / 1048576.0))
    return os.path.getsize(dest)


def _set_user_env(name, value):
    """写入用户环境变量（新开的进程都能读到）。"""
    try:
        subprocess.run(['setx', name, value], capture_output=True, timeout=30,
                       creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return True
    except Exception:
        return False


def has_model(model, host=DEFAULT_HOST):
    """本机是否已经有这个模型。"""
    return any(m == model or m.startswith(model + ':') for m in probe(host).get('models') or [])


def models_dir_guess():
    """已有模型的目录：优先环境变量，其次 ~/.ollama/models。"""
    env = os.environ.get('OLLAMA_MODELS')
    if env and os.path.isdir(env):
        return env
    guess = os.path.join(os.path.expanduser('~'), '.ollama', 'models')
    return guess if os.path.isdir(guess) else ''


def install_to(base_dir=None, progress=None, model='qwen2.5:3b', host=DEFAULT_HOST):
    """装 Ollama（已装就跳过）并下载模型。

    base_dir 为空时：已装则沿用现有位置，只下模型。
    返回 (ok, 消息)。
    """
    def log(msg):
        if progress:
            progress(msg)

    exe_now = cli_path()
    if exe_now and not base_dir:
        # 已经装过：不重装，直接下模型（模型目录沿用现有配置）
        log('已经装过 Ollama，直接下载模型 %s …' % model)
        ok, why = pull_model(exe_now, model, progress=progress)
        if not ok:
            return False, why
        log('模型就绪 ✓')
        return True, model

    if base_dir is None:
        base_dir = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                                'Programs')

    base_dir = os.path.abspath(base_dir)
    program_dir = os.path.join(base_dir, 'Ollama')
    models_dir = os.path.join(base_dir, 'models')
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception as exc:
        return False, '这个目录建不了：%s' % str(exc)[:60]

    existing = cli_path()
    if existing:
        log('这台机器已经装过 Ollama，跳过安装，直接用现有那份。')
        models_dir = models_dir_guess() or os.path.join(base_dir, 'models')
        ok_pull, why = pull_model(existing, model, progress=progress)
        if not ok_pull:
            return False, '模型没下完：%s' % why
        log('模型就绪：%s' % models_dir)
        return True, model

    # 1) 下载安装包
    installer = os.path.join(base_dir, 'OllamaSetup.exe')
    try:
        log('开始下载安装包（约 700 MB）…')
        _download(INSTALLER_URL, installer, progress=progress)
    except Exception as exc:
        return False, '下载安装包失败：%s' % str(exc)[:60]

    # 2) 静默安装到指定目录（NSIS 用 /S /D=，Inno 用 /VERYSILENT /DIR=）
    log('正在安装到 %s …' % program_dir)
    ok = False
    for args in ([installer, '/S', '/D=%s' % program_dir],
                 [installer, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                  '/DIR=%s' % program_dir]):
        try:
            proc = _spawn(args)
            proc.wait(timeout=900)
        except Exception:
            continue
        if os.path.isdir(program_dir) and os.path.isfile(os.path.join(program_dir, 'ollama.exe')):
            ok = True
            break
    if not ok:
        return False, '安装没成功（可能被安全软件拦了），可以手动装好再点「本地模型」'

    # 3) 模型目录：已经有一份就沿用，别让用户白下 2 GB
    existing_models = models_dir_guess()
    if existing_models:
        models_dir = existing_models
        log('沿用已有的模型目录：%s' % models_dir)
    else:
        os.makedirs(models_dir, exist_ok=True)
    _set_user_env('OLLAMA_MODELS', models_dir)
    log('模型会存到 %s' % models_dir)

    # 4) 启动服务（带上模型目录）
    env = dict(os.environ)
    env['OLLAMA_MODELS'] = models_dir
    exe = os.path.join(program_dir, 'ollama.exe')
    try:
        subprocess.Popen([exe, 'serve'], env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except Exception:
        pass
    for _ in range(20):
        time.sleep(2)
        if probe(host, timeout=2.0).get('alive'):
            break

    # 5) 拉模型（会落到 models_dir）
    ok_pull, why = pull_model(exe, model, progress=progress)
    if not ok_pull:
        return False, '模型没下完：%s' % why
    log('装好了：程序 %s，模型 %s' % (program_dir, models_dir))
    return True, model
