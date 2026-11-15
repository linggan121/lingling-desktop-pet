# -*- coding: utf-8 -*-
"""长期记忆：本地明文事实卡 + 关键词检索。

不引向量库（ChromaDB 要 100MB+），用「字面重叠 + 时间衰减」打分，
对桌宠这种小规模记忆（上限 120 条）足够用。
"""
from __future__ import annotations

import json
import math
import time

from . import paths

MAX_FACTS = 120
DEFAULT_IMPORTANCE = 0.6


def _tokens(text):
    """粗分词：中文按 2 字滑窗，英文按单词。"""
    text = (text or '').lower()
    out = set()
    buf = ''
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            if buf:
                out.add(buf)
                buf = ''
            continue
        if ch.isalnum():
            buf += ch
        else:
            if buf:
                out.add(buf)
                buf = ''
    if buf:
        out.add(buf)
    cjk = [c for c in text if '\u4e00' <= c <= '\u9fff']
    for i in range(len(cjk) - 1):
        out.add(cjk[i] + cjk[i + 1])
    return out


class Memory(object):
    def __init__(self, path=None):
        self.path = path or paths.data_path('memory.json')
        self.facts = []
        self.load()

    # ---------------- 存取 ----------------
    def load(self):
        data = paths.read_json(self.path, [])
        if isinstance(data, dict):
            data = data.get('facts') or []
        facts = []
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict) and item.get('text'):
                facts.append({
                    'text': str(item['text'])[:200],
                    'importance': float(item.get('importance', DEFAULT_IMPORTANCE)),
                    'ts': float(item.get('ts') or 0),
                })
            elif isinstance(item, str) and item.strip():
                facts.append({'text': item.strip()[:200],
                              'importance': DEFAULT_IMPORTANCE, 'ts': 0})
        self.facts = facts[-MAX_FACTS:]

    def save(self):
        return paths.write_json(self.path, {'version': 1, 'facts': self.facts})

    # ---------------- 写入 ----------------
    def add(self, text, importance=DEFAULT_IMPORTANCE):
        text = (text or '').strip()
        if not text or len(text) < 2:
            return False
        for f in self.facts:                       # 重复的就提权重，不重复记
            if f['text'] == text:
                f['importance'] = max(f['importance'], float(importance))
                f['ts'] = time.time()
                return True
        self.facts.append({'text': text[:200],
                           'importance': max(0.0, min(1.0, float(importance))),
                           'ts': time.time()})
        if len(self.facts) > MAX_FACTS:
            self.facts.sort(key=lambda f: f['importance'])
            self.facts = self.facts[-MAX_FACTS:]
        return True

    def add_many(self, items):
        """items: [{'text':..., 'importance':0.8}] 或 [str]"""
        added = 0
        for it in items or []:
            if isinstance(it, dict):
                ok = self.add(it.get('text', ''), it.get('importance', DEFAULT_IMPORTANCE))
            else:
                ok = self.add(str(it), DEFAULT_IMPORTANCE)
            added += 1 if ok else 0
        if added:
            self.save()
        return added

    def clear(self):
        self.facts = []
        self.save()

    # ---------------- 读取 ----------------
    def top(self, n=5, min_importance=0.8):
        picked = [f for f in self.facts if f['importance'] >= min_importance]
        picked.sort(key=lambda f: (f['importance'], f['ts']), reverse=True)
        return [f['text'] for f in picked[:n]]

    def search(self, query, k=3):
        qt = _tokens(query)
        if not qt or not self.facts:
            return []
        now = time.time()
        scored = []
        for f in self.facts:
            ft = _tokens(f['text'])
            if not ft:
                continue
            overlap = len(qt & ft) / math.sqrt(len(ft) + 2)
            days = max(0.0, (now - (f['ts'] or now)) / 86400.0)
            score = overlap + 0.15 * math.exp(-days / 30.0) + 0.1 * f['importance']
            if overlap > 0:
                scored.append((score, f['text']))
        scored.sort(reverse=True)
        return [t for _, t in scored[:k]]

    def prompt_block(self, query=None, n=5):
        """给系统提示词用：核心事实 + 与本次问题相关的事实，去重后最多 n 条。"""
        merged = []
        for text in self.top(3) + self.search(query or '', 3) + self.top(n, 0.7):
            if text not in merged:
                merged.append(text)
        return merged[:n]


# ---------------- 让模型提炼记忆 ----------------
EXTRACT_SYSTEM = (
    '你是一个信息抽取器。从下面的对话里，抽取「关于用户本人的、长期有用的稳定事实」'
    '（例如称呼、职业、作息、喜好、忌讳、正在做的项目）。'
    '不要抽取一次性的临时信息，不要抽取关于桌宠自己的事。'
    '只输出 JSON 数组，每个元素形如 {"text": "一句话事实", "importance": 0.0~1.0}；'
    '没有值得记的就输出 []。不要输出任何解释。'
)


def extract_messages(history_lines, limit=12):
    tail = '\n'.join(history_lines[-limit:])
    return [
        {'role': 'system', 'content': EXTRACT_SYSTEM},
        {'role': 'user', 'content': '对话如下：\n' + tail},
    ]


def parse_extracted(text):
    """把模型返回的 JSON 数组解析成事实列表；解析失败返回空列表。"""
    raw = (text or '').strip()
    if not raw:
        return []
    if raw.startswith('```'):
        raw = raw.strip('`')
        if raw.lower().startswith('json'):
            raw = raw[4:]
    start, end = raw.find('['), raw.rfind(']')
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get('text'):
            try:
                imp = float(item.get('importance', DEFAULT_IMPORTANCE))
            except Exception:
                imp = DEFAULT_IMPORTANCE
            out.append({'text': str(item['text'])[:200], 'importance': max(0.0, min(1.0, imp))})
        elif isinstance(item, str) and item.strip():
            out.append({'text': item.strip()[:200], 'importance': DEFAULT_IMPORTANCE})
    return out[:8]
