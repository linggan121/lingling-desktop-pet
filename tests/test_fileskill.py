# -*- coding: utf-8 -*-
"""文件技能：意图解析 + Filee 调用层 + 拖放接收。"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ling import fileops, intent  # noqa: E402

FORMATS = ['png', 'jpg', 'webp', 'pdf', 'gif', 'mp4', 'mp3', 'docx']
PRESETS = [('to-pdf', 'PDF', 'pdf'), ('to-webp', 'WEBP', 'webp'),
           ('half-size', 'Half size', '*'), ('grayscale', 'Grayscale', '*')]


class IntentTest(unittest.TestCase):
    def test_convert_chinese_verb(self):
        act = intent.parse('转成 webp', FORMATS, PRESETS)
        self.assertEqual(act['action'], 'convert')
        self.assertEqual(act['to'], 'webp')

    def test_convert_with_ba(self):
        for text in ('帮我转成 png', '把这三个换成 jpg', '导出为 pdf', '另存为 gif'):
            act = intent.parse(text, FORMATS, PRESETS)
            self.assertIsNotNone(act, text)
            self.assertEqual(act['action'], 'convert', text)

    def test_convert_english(self):
        act = intent.parse('convert to webp', FORMATS, PRESETS)
        self.assertEqual(act['to'], 'webp')

    def test_bare_format(self):
        self.assertEqual(intent.parse('webp', FORMATS, PRESETS)['to'], 'webp')

    def test_format_mentioned_without_verb_is_not_command(self):
        # 普通聊天里提到格式，不应该被当成转换指令
        self.assertIsNone(intent.parse('这个 pdf 是干嘛的', FORMATS, PRESETS))
        self.assertIsNone(intent.parse('webp 和 png 有什么区别', FORMATS, PRESETS))

    def test_preset(self):
        act = intent.parse('用 to-pdf 预设', FORMATS, PRESETS)
        self.assertEqual(act['action'], 'convert')
        self.assertEqual(act['preset'], 'to-pdf')

    def test_preset_by_name(self):
        act = intent.parse('用 Half size 压一下', FORMATS, PRESETS)
        self.assertEqual(act['preset'], 'half-size')

    def test_quality(self):
        act = intent.parse('转成 jpg 质量 80', FORMATS, PRESETS)
        self.assertEqual(act['to'], 'jpg')
        self.assertEqual(act['quality'], 80)

    def test_watch(self):
        act = intent.parse('盯着这个文件夹转成 webp', FORMATS, PRESETS, attached=['D:\\tmp'])
        self.assertEqual(act['action'], 'watch')
        self.assertEqual(act['to'], 'webp')
        self.assertEqual(act['folder'], 'D:\\tmp')

    def test_watch_without_format(self):
        act = intent.parse('帮我盯着下载文件夹', FORMATS, PRESETS)
        self.assertEqual(act['action'], 'watch_need_format')

    def test_stop_watch(self):
        self.assertEqual(intent.parse('停止监听', FORMATS, PRESETS)['action'], 'stop_watch')
        self.assertEqual(intent.parse('别盯了', FORMATS, PRESETS)['action'], 'stop_watch')

    def test_list_formats(self):
        self.assertEqual(intent.parse('你支持哪些格式', FORMATS, PRESETS)['action'], 'list_formats')

    def test_empty(self):
        self.assertIsNone(intent.parse('', FORMATS, PRESETS))
        self.assertIsNone(intent.parse('你好呀', FORMATS, PRESETS))


class FileopsTest(unittest.TestCase):
    def test_build_args_basic(self):
        args = fileops.build_convert_args(['a.png', 'b.png'], to='webp')
        self.assertEqual(args[:3], ['convert', 'a.png', 'b.png'])
        self.assertIn('--to', args)
        self.assertIn('webp', args)
        self.assertIn('--json', args)

    def test_build_args_full(self):
        args = fileops.build_convert_args(['a.png'], preset='to-pdf', quality=70,
                                          out='C:\\out', recursive=True, overwrite=True)
        self.assertIn('--preset', args)
        self.assertIn('to-pdf', args)
        self.assertIn('--quality', args)
        self.assertIn('70', args)
        self.assertIn('--output', args)
        self.assertIn('--recursive', args)
        self.assertIn('--overwrite', args)

    def test_parse_formats(self):
        sample = """Image:
  png        PNG  .png
  jpg        JPG  .jpg .jpeg

Video:
  mp4        MP4  .mp4
"""
        groups = {}
        current = None
        for line in sample.splitlines():
            if line and not line.startswith(' ') and line.strip().endswith(':'):
                current = line.strip().rstrip(':')
                groups[current] = []
            elif line.startswith(' ') and current:
                parts = line.split()
                groups[current].append((parts[0], parts[1],
                                        [p for p in parts[2:] if p.startswith('.')]))
        self.assertEqual([g[0] for g in groups['Image']], ['png', 'jpg'])
        self.assertEqual(groups['Video'][0][0], 'mp4')

    def test_convert_parses_json(self):
        orig = fileops.run
        fileops.run = lambda args, timeout=None: (0, '{"converted": 2, "failed": 0, "skipped": 0, '
                                                    '"files": [{"source": "a.png", "state": "done", '
                                                    '"outputs": ["a.webp"]}, {"source": "b.png", '
                                                    '"state": "done", "outputs": ["b.webp"]}]}', '')
        try:
            res = fileops.convert(['a.png', 'b.png'], to='webp')
        finally:
            fileops.run = orig
        self.assertTrue(res['ok'])
        self.assertEqual(res['converted'], 2)
        self.assertEqual(res['outputs'], ['a.webp', 'b.webp'])
        self.assertIn('2', res['message'])

    def test_convert_reports_failure(self):
        orig = fileops.run
        fileops.run = lambda args, timeout=None: (1, '{"converted": 0, "failed": 1, "skipped": 0, '
                                                    '"files": [{"source": "a.exe", "state": "failed", '
                                                    '"error": "unsupported"}]}', '')
        try:
            res = fileops.convert(['a.exe'], to='webp')
        finally:
            fileops.run = orig
        self.assertFalse(res['ok'])
        self.assertEqual(res['failed'], 1)
        self.assertTrue(res['errors'])

    def test_convert_empty(self):
        res = fileops.convert([], to='webp')
        self.assertFalse(res['ok'])


if __name__ == '__main__':
    unittest.main()
