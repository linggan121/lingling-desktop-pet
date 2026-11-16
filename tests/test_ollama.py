# -*- coding: utf-8 -*-
"""本地模型探测 + 设置窗口切换。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ling import ollama  # noqa: E402


class OllamaParseTest(unittest.TestCase):
    def test_parse_tags(self):
        payload = '{"models": [{"name": "qwen2.5:7b"}, {"model": "llama3.2:3b"}]}'
        self.assertEqual(ollama.parse_tags(payload), ['qwen2.5:7b', 'llama3.2:3b'])

    def test_parse_tags_bad(self):
        self.assertEqual(ollama.parse_tags('not json'), [])
        self.assertEqual(ollama.parse_tags('{"models": "x"}'), [])

    def test_parse_version(self):
        self.assertEqual(ollama.parse_version('{"version": "0.5.1"}'), '0.5.1')
        self.assertEqual(ollama.parse_version('nope'), '')

    def test_apply_model(self):
        cfg = ollama.apply_model({'provider': 'deepseek', 'api_key': 'sk-x'}, 'qwen2.5:7b')
        self.assertEqual(cfg['provider'], 'ollama')
        self.assertEqual(cfg['model'], 'qwen2.5:7b')
        self.assertEqual(cfg['base_url'], 'http://127.0.0.1:11434/v1')
        self.assertEqual(cfg['api_key'], 'ollama')

    def test_apply_model_strips_v1(self):
        cfg = ollama.apply_model({}, 'x', 'http://127.0.0.1:11434/v1')
        self.assertEqual(cfg['base_url'], 'http://127.0.0.1:11434/v1')

    def test_probe_offline(self):
        orig = ollama._get

        def boom(url, timeout=2.5):
            raise OSError('refused')

        ollama._get = boom
        try:
            info = ollama.probe()
        finally:
            ollama._get = orig
        self.assertFalse(info['alive'])
        self.assertTrue(info['error'])

    def test_probe_online(self):
        orig = ollama._get

        def fake(url, timeout=2.5):
            if url.endswith('/api/version'):
                return '{"version": "0.6.0"}'
            return '{"models": [{"name": "qwen2.5:7b"}]}'

        ollama._get = fake
        try:
            info = ollama.probe()
        finally:
            ollama._get = orig
        self.assertTrue(info['alive'])
        self.assertEqual(info['version'], '0.6.0')
        self.assertEqual(info['models'], ['qwen2.5:7b'])


if __name__ == '__main__':
    unittest.main()


class LocalTuneTest(unittest.TestCase):
    def test_local_params(self):
        from ling import llm
        self.assertEqual(llm.local_params({'provider': 'ollama'})['max_tokens'], 120)
        self.assertIsNone(llm.local_params({'provider': 'ollama', 'local_tuned': False}))
        self.assertIsNone(llm.local_params({'provider': 'doubao'}))

    def test_modelfile_text(self):
        text = ollama.modelfile_text('qwen2.5:3b')
        self.assertIn('FROM qwen2.5:3b', text)
        self.assertIn('num_ctx 4096', text)

    def test_write_modelfile(self):
        import tempfile
        d = tempfile.mkdtemp()
        path = ollama.write_modelfile(d, 'qwen2.5:3b')
        self.assertTrue(os.path.isfile(path))
        body = open(path, encoding='utf-8').read()
        self.assertIn('num_ctx 4096', body)
