# -*- coding: utf-8 -*-
"""大模型接入：一个接口同时支持「云端 OpenAI 兼容」和「本地 Ollama」。

全程只用标准库 urllib，不新增依赖。设计参考：
- luna-desktop-pet 的 app/chat/client.py（SSE 流式、错误转人话，MIT）
- Sparton 的 app/llm.py（供应商抽象，无 LICENSE → 只借思路，代码自己写）

三条铁律：
1. 5~8 秒拿不到第一个字就放弃，绝不让界面干等；
2. 任何异常都只是「这次没说话」，由调用方退回内置台词；
3. 不编造数字：失败时不假装成功。
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request

PROVIDERS = {
    'deepseek': {'label': 'DeepSeek', 'base_url': 'https://api.deepseek.com', 'model': 'deepseek-chat'},
    'moonshot': {'label': 'Moonshot (Kimi)', 'base_url': 'https://api.moonshot.cn/v1', 'model': 'moonshot-v1-8k'},
    'zhipu': {'label': '智谱 GLM', 'base_url': 'https://open.bigmodel.cn/api/paas/v4', 'model': 'glm-4-flash'},
    'openai': {'label': 'OpenAI', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini'},
    'doubao': {'label': '豆包（火山方舟）', 'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
               'model': 'doubao-seed-2-1-turbo-260628'},
    'qwen': {'label': '通义千问（阿里百炼）',
             'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
             'model': 'qwen-plus'},
    'siliconflow': {'label': '硅基流动 SiliconFlow', 'base_url': 'https://api.siliconflow.cn/v1',
                    'model': 'Qwen/Qwen2.5-7B-Instruct'},
    'openrouter': {'label': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1',
                   'model': 'openai/gpt-4o-mini'},
    'ollama': {'label': '本地 Ollama（免费离线）', 'base_url': 'http://127.0.0.1:11434/v1',
               'model': 'qwen2.5:7b', 'api_key': 'ollama'},
    'custom': {'label': '自定义（任意 OpenAI 兼容）', 'base_url': '', 'model': ''},
}

DEFAULT_LLM = {
    'provider': 'deepseek',
    'base_url': '',
    'model': '',
    'api_key': '',
}


class LLMError(Exception):
    pass


# ---------------- 配置 ----------------
def thinking_payload(cfg):
    """豆包这类模型的「深度思考」默认开着，首字要 20 秒；

    桌宠聊天用不着它，默认关掉（想开就在设置里加 "thinking": "enabled"）。
    """
    provider = (cfg or {}).get('provider')
    if provider != 'doubao':
        return None
    mode = ((cfg or {}).get('thinking') or 'disabled').lower()
    if mode in ('auto', ''):
        return None
    return {'type': mode}


def clean_key(raw):
    """清掉粘贴 Key 时最容易混进来的东西：空格、换行、零宽字符、引号、Bearer 前缀。"""
    text = (raw or '')
    for ch in ('\u200b', '\u200c', '\u200d', '\ufeff', ' ', '\t', '\r', '\n'):
        text = text.replace(ch, '')
    text = text.strip('"\'`')
    for prefix in ('Bearer', 'bearer', 'BEARER'):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip()


def key_hint(provider, api_key):
    """钥匙长得不像这家的，就给个提示。"""
    k = clean_key(api_key)
    if not k:
        return '还没填 Key'
    if k.startswith('sk-or-'):
        return '这把钥匙像 OpenRouter 的，把服务商换成「OpenRouter」再试'
    if k.startswith('sk-') and provider == 'deepseek' and len(k) > 45:
        return 'DeepSeek 的 Key 通常是 sk- 开头 35 位左右，你这把有 %d 位，可能属于别的服务商' % len(k)
    if not k.startswith('sk-') and provider in ('deepseek', 'openai', 'siliconflow', 'openrouter'):
        return '这家服务商的 Key 一般以 sk- 开头，检查是不是复制漏了'
    return ''


def friendly_error_401(provider, api_key):
    base = '钥匙不对呢，去设置里把 Key 填对'
    hint = key_hint(provider, api_key)
    return base + ('（提示：' + hint + '）' if hint else '')


def resolve(cfg):
    """把 settings 里的 llm 配置解析成可直接用的 (base_url, model, api_key)。"""
    cfg = cfg or {}
    provider = cfg.get('provider') or DEFAULT_LLM['provider']
    preset = PROVIDERS.get(provider, PROVIDERS['deepseek'])
    base_url = (cfg.get('base_url') or '').strip() or preset.get('base_url', '')
    model = (cfg.get('model') or '').strip() or preset.get('model', '')
    api_key = clean_key(cfg.get('api_key') or '') or preset.get('api_key', '')
    return provider, base_url.rstrip('/'), model, api_key


def ready(cfg):
    """能不能真的发起对话：Ollama 不需要填 Key，其它必须有 Key。"""
    provider, base_url, model, api_key = resolve(cfg)
    if not base_url or not model:
        return False
    if provider == 'ollama':
        return True
    return bool(api_key)


def endpoint(base_url):
    """拼出 /chat/completions 的完整地址。

    兼容三种写法：域名、域名+/v1、以及带版本号的（豆包的 /api/v3）。
    """
    url = (base_url or '').rstrip('/')
    if not url:
        raise LLMError('还没有填接口地址')
    if url.endswith('/chat/completions'):
        return url
    if re.search(r'/v\d+$', url):
        return url + '/chat/completions'
    return url + '/v1/chat/completions'


def models_url(base_url):
    url = (base_url or '').rstrip('/')
    if url.endswith('/chat/completions'):
        url = url[:-len('/chat/completions')]
    if not re.search(r'/v\d+$', url):
        url += '/v1'
    return url + '/models'


def list_models(cfg, timeout=10.0):
    """列一下这家服务商有哪些模型（GET /models）。拿不到就抛异常。"""
    provider, base_url, model, api_key = resolve(cfg)
    if not base_url:
        raise LLMError('还没有填接口地址')
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    req = urllib.request.Request(models_url(base_url), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        raise LLMError(friendly_error(e.code))
    except Exception as e:
        raise LLMError(friendly_error(None, str(e)))
    try:
        data = json.loads(body)
    except Exception:
        raise LLMError('模型列表看不懂')
    items = data.get('data') or data.get('models') or []
    out = []
    for item in items if isinstance(items, list) else []:
        mid = item.get('id') or item.get('name') if isinstance(item, dict) else str(item)
        if mid:
            out.append(str(mid))
    if not out:
        raise LLMError('这家没返回模型列表')
    return out


# 常见服务商的备用模型名（默认模型 404 时挨个试）
FALLBACK_MODELS = {
    'doubao': ['doubao-seed-2-1-turbo-260628', 'doubao-seed-2-1-pro-260628',
               'doubao-seed-1-6-250615', 'doubao-1-5-pro-32k-250115',
               'doubao-pro-32k', 'doubao-lite-32k'],
    'qwen': ['qwen-plus', 'qwen-turbo', 'qwen-max'],
    'siliconflow': ['Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen2.5-72B-Instruct'],
    'deepseek': ['deepseek-chat', 'deepseek-reasoner'],
    'moonshot': ['moonshot-v1-8k', 'moonshot-v1-32k'],
    'zhipu': ['glm-4-flash', 'glm-4-air', 'glm-4'],
    'openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo'],
    'openrouter': ['openai/gpt-4o-mini', 'anthropic/claude-3.5-sonnet'],
}


_BAD_WORDS = ('embed', 'tts', 'whisper', 'rerank', 'moderation', 'dall', 'stable-diffusion',
              'image', 'ocr', 'audio', 'speech', 'vl-', '-vl')
_GOOD_WORDS = ('chat', 'instruct', 'qwen', 'doubao', 'deepseek', 'gpt-4', 'gpt-3.5',
               'glm-4', 'moonshot', 'abab', 'yi-')


def pick_chat_model(models, provider=''):
    """从模型列表里挑一个适合聊天的。"""
    cands = [m for m in models if not any(w in m.lower() for w in _BAD_WORDS)]
    if not cands:
        return ''
    for m in cands:
        if any(w in m.lower() for w in _GOOD_WORDS):
            return m
    return cands[0]


def friendly_error(status=None, detail=''):
    if status == 401:
        return '钥匙不对呢，去设置里把 Key 填对'
    if status == 402:
        return '余额不够啦，得先去充点钱'
    if status == 403:
        return '那边不让我说话（403），检查下 Key 的权限'
    if status == 404:
        return '对方说找不到（404）：要么接口地址不对，要么模型名不存在'
    if status == 429:
        return '说得太急了被限流，等一下再试'
    if status and 500 <= status < 600:
        return '那边服务器抽风了，等会儿再来'
    if status:
        return '请求失败（HTTP %d）' % status
    return '连不上那边：%s' % (detail[:60] or '网络或地址有问题')


# ---------------- 同步调用（记忆提炼等后台小任务用） ----------------
def complete(cfg, messages, temperature=0.6, timeout=20.0):
    tune = local_params(cfg)
    if tune:
        temperature = tune['temperature']
    provider, base_url, model, api_key = resolve(cfg)
    if not ready(cfg):
        raise LLMError('还没有配置模型')
    payload = {'model': model, 'messages': messages, 'temperature': temperature, 'stream': False}
    think = thinking_payload(cfg)
    if think:
        payload['thinking'] = think
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(endpoint(base_url), data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'ignore')
        except Exception:
            pass
        if e.code == 401:
            raise LLMError(friendly_error_401(provider, api_key))
        raise LLMError(friendly_error(e.code, detail))
    except (urllib.error.URLError, socket.timeout) as e:
        raise LLMError(friendly_error(None, str(e)))
    except Exception as e:
        raise LLMError(friendly_error(None, str(e)))

    try:
        packet = json.loads(body)
        return (packet.get('choices') or [{}])[0].get('message', {}).get('content', '') or ''
    except Exception:
        raise LLMError('那边回的内容看不懂')


# ---------------- 看图（多模态） ----------------
def complete_vision(cfg, model, prompt, image_b64, timeout=45.0):
    """把一张 base64 图片 + 一句话发给多模态模型，返回一句回复。"""
    provider, base_url, model_default, api_key = resolve(cfg)
    if not ready(cfg):
        raise LLMError('还没有配置模型')
    model = (model or '').strip() or model_default
    payload = {
        'model': model,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url',
                 'image_url': {'url': 'data:image/png;base64,' + image_b64}},
            ],
        }],
        'temperature': 0.7,
        'stream': False,
    }
    think = thinking_payload(cfg)
    if think:
        payload['thinking'] = think
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(endpoint(base_url), data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'ignore')
        except Exception:
            pass
        if e.code == 400:
            raise LLMError('这个模型好像不能看图，去设置里换个视觉模型')
        if e.code == 401:
            raise LLMError(friendly_error_401(provider, api_key))
        raise LLMError(friendly_error(e.code, detail))
    except (urllib.error.URLError, socket.timeout) as e:
        raise LLMError(friendly_error(None, str(e)))
    except Exception as e:
        raise LLMError(friendly_error(None, str(e)))
    try:
        packet = json.loads(body)
        return (packet.get('choices') or [{}])[0].get('message', {}).get('content', '') or ''
    except Exception:
        raise LLMError('那边回的内容看不懂')


# ---------------- 流式调用（界面用，必须在子线程里跑） ----------------
def local_params(cfg):
    """本地小模型的默认参数：回复更短、温度更低，别跑题。"""
    provider = (cfg or {}).get('provider')
    if provider != 'ollama':
        return None
    if (cfg or {}).get('local_tuned') is False:
        return None
    return {'temperature': 0.75, 'max_tokens': 120}


def stream(cfg, messages, on_chunk=None, on_done=None, on_error=None,
           temperature=0.9, connect_timeout=8.0, total_timeout=90.0, stop_flag=None,
           max_tokens=160):
    """阻塞式流式请求。回调都可能在工作线程里被调用，调用方自己负责切回主线程。"""
    tune = local_params(cfg)
    if tune:
        temperature = tune['temperature']
        max_tokens = tune['max_tokens']
    try:
        provider, base_url, model, api_key = resolve(cfg)
        if not ready(cfg):
            raise LLMError('还没配置模型')
        payload = {'model': model, 'messages': messages, 'temperature': temperature,
                   'stream': True}
        if max_tokens:
            payload['max_tokens'] = max_tokens
        think = thinking_payload(cfg)
        if think:
            payload['thinking'] = think
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = 'Bearer ' + api_key
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(endpoint(base_url), data=data, headers=headers, method='POST')

        collected = []
        with urllib.request.urlopen(req, timeout=connect_timeout) as resp:
            resp.fp.raw._sock.settimeout(total_timeout)  # 首字之后放宽
            for raw in resp:
                if stop_flag is not None and stop_flag.is_set():
                    break
                line = raw.decode('utf-8', 'ignore').strip()
                if not line or not line.startswith('data:'):
                    continue
                payload_text = line[5:].strip()
                if payload_text == '[DONE]':
                    break
                try:
                    packet = json.loads(payload_text)
                except Exception:
                    continue
                choices = packet.get('choices') or []
                if not choices:
                    continue
                delta = choices[0].get('delta') or {}
                piece = delta.get('content') or ''
                if piece:
                    collected.append(piece)
                    if on_chunk:
                        on_chunk(piece)

        text = ''.join(collected).strip()
        if not text:
            raise LLMError('那边什么也没说')
        if on_done:
            on_done(text)
        return text
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'ignore')
        except Exception:
            pass
        if e.code == 401:
            err = friendly_error_401(provider, api_key)
        else:
            err = friendly_error(e.code, detail)
    except (urllib.error.URLError, socket.timeout) as e:
        err = friendly_error(None, str(e))
    except LLMError as e:
        err = str(e)
    except Exception as e:
        err = friendly_error(None, str(e))
    if on_error:
        on_error(err)
    return ''
