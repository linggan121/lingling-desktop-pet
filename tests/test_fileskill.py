# -*- coding: utf-8 -*-
"""文件技能：内置转换引擎 + 意图解析 + 拖放接收。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ling import convert_engine as engine  # noqa: E402
from ling import intent  # noqa: E402

FORMATS = ['png', 'jpg', 'webp', 'pdf', 'gif', 'mp4', 'mp3', 'zip']
PRESETS = []


def tmpdir():
    path = os.path.join(HERE, '_tmp', 'engine_%d' % (len(os.listdir(os.path.join(HERE, '_tmp'))) if os.path.isdir(os.path.join(HERE, '_tmp')) else 0))
    os.makedirs(path, exist_ok=True)
    return path


class KindTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(engine.kind_of('a.png'), 'image')
        self.assertEqual(engine.kind_of('a.HEIC'), 'image')
        self.assertEqual(engine.kind_of('a.pdf'), 'pdf')
        self.assertEqual(engine.kind_of('a.docx'), 'doc')
        self.assertEqual(engine.kind_of('a.zip'), 'archive')
        self.assertEqual(engine.kind_of('a.mp4'), 'media')
        self.assertEqual(engine.kind_of('a.unknownext'), 'other')


class ImageConvertTest(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.dir = tmpdir()
        self.src = os.path.join(self.dir, 'pic.png')
        Image.new('RGB', (400, 300), (90, 60, 200)).save(self.src)

    def test_png_to_webp(self):
        res = engine.convert([self.src], 'webp')
        self.assertTrue(res['ok'], res)
        self.assertEqual(len(res['outputs']), 1)
        self.assertTrue(res['outputs'][0].endswith('.webp'))
        self.assertTrue(os.path.isfile(res['outputs'][0]))

    def test_png_to_jpg_quality(self):
        res = engine.convert([self.src], 'jpg', quality=60)
        self.assertTrue(res['ok'])
        self.assertTrue(os.path.isfile(res['outputs'][0]))

    def test_png_to_ico(self):
        res = engine.convert([self.src], 'ico')
        self.assertTrue(res['ok'])
        self.assertTrue(res['outputs'][0].endswith('.ico'))

    def test_png_to_pdf(self):
        res = engine.convert([self.src], 'pdf')
        self.assertTrue(res['ok'])
        self.assertTrue(res['outputs'][0].endswith('.pdf'))

    def test_resize_long_side(self):
        from PIL import Image
        res = engine.convert([self.src], 'png', resize=200)
        self.assertTrue(res['ok'])
        with Image.open(res['outputs'][0]) as im:
            self.assertLessEqual(max(im.size), 200)

    def test_no_overwrite(self):
        first = engine.convert([self.src], 'webp')
        second = engine.convert([self.src], 'webp')
        self.assertNotEqual(first['outputs'][0], second['outputs'][0])


class OfficeTest(unittest.TestCase):
    def test_docx_to_text(self):
        import docx
        d = tmpdir()
        src = os.path.join(d, 'doc.docx')
        doc = docx.Document()
        doc.add_paragraph('第一段')
        doc.add_paragraph('第二段')
        doc.save(src)
        res = engine.convert([src], 'txt')
        self.assertTrue(res['ok'], res)
        text = open(res['outputs'][0], encoding='utf-8').read()
        self.assertIn('第一段', text)

    def test_xlsx_to_csv(self):
        import openpyxl
        d = tmpdir()
        src = os.path.join(d, 'book.xlsx')
        wb = openpyxl.Workbook()
        wb.active['A1'] = 'name'
        wb.active['B1'] = 'qty'
        wb.active['A2'] = 'apple'
        wb.active['B2'] = 3
        wb.save(src)
        res = engine.convert([src], 'csv')
        self.assertTrue(res['ok'], res)
        text = open(res['outputs'][0], encoding='utf-8-sig').read()
        self.assertIn('apple', text)


class ArchiveTest(unittest.TestCase):
    def test_zip_roundtrip(self):
        import zipfile
        d = tmpdir()
        src = os.path.join(d, 'note.txt')
        open(src, 'w', encoding='utf-8').write('hello')
        res = engine.convert([src], 'zip')
        self.assertTrue(res['ok'], res)
        self.assertTrue(zipfile.is_zipfile(res['outputs'][0]))
        outs, errs = engine.extract_archives([res['outputs'][0]])
        self.assertTrue(outs)
        self.assertFalse(errs)


class EmptyTest(unittest.TestCase):
    def test_empty(self):
        self.assertFalse(engine.convert([], 'webp')['ok'])


class WatcherTest(unittest.TestCase):
    def test_watcher_detects_new_file(self):
        import time
        from PIL import Image
        d = tmpdir()
        w = engine.FolderWatcher(d, 'jpg', interval=0.3)
        w.start()
        try:
            Image.new('RGB', (60, 40), (10, 120, 90)).save(os.path.join(d, 'new.png'))
            out_dir = os.path.join(d, 'converted')
            for _ in range(30):
                if os.path.isdir(out_dir) and any(n.endswith('.jpg') for n in os.listdir(out_dir)):
                    break
                time.sleep(0.2)
            self.assertTrue(os.path.isdir(out_dir))
            self.assertTrue(any(n.endswith('.jpg') for n in os.listdir(out_dir)))
        finally:
            w.stop()


class IntentTest(unittest.TestCase):
    def test_convert_chinese_verb(self):
        act = intent.parse('转成 webp', FORMATS)
        self.assertEqual(act['action'], 'convert')
        self.assertEqual(act['to'], 'webp')

    def test_preset(self):
        act = intent.parse('用 to-pdf 预设', FORMATS, [('to-pdf', 'PDF', 'pdf')])
        self.assertEqual(act['action'], 'convert')

    def test_watch(self):
        act = intent.parse('盯着这个文件夹转成 webp', FORMATS, (), ['D:\\tmp'])
        self.assertEqual(act['action'], 'watch')

    def test_stop(self):
        self.assertEqual(intent.parse('停止监听', FORMATS)['action'], 'stop_watch')

    def test_empty(self):
        self.assertIsNone(intent.parse('', FORMATS))


if __name__ == '__main__':
    unittest.main()


class OptionsTest(unittest.TestCase):
    def test_image_options(self):
        from PIL import Image
        d = tmpdir()
        src = os.path.join(d, 'sq.png')
        Image.new('RGB', (256, 256), (10, 10, 10)).save(src)
        labels = [o[0] for o in engine.options_for([src])]
        self.assertTrue(any('webp' in x for x in labels))
        self.assertTrue(any('ico' in x for x in labels))
        self.assertTrue(any('PDF' in x or 'pdf' in x for x in labels))

    def test_docx_options_follow_content(self):
        import docx
        d = tmpdir()
        src = os.path.join(d, 'rich.docx')
        doc = docx.Document()
        doc.add_paragraph('hello')
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = 'a'
        doc.save(src)
        labels = [o[0] for o in engine.options_for([src])]
        self.assertTrue(any('Markdown' in x for x in labels))
        self.assertTrue(any('CSV' in x for x in labels))

    def test_docx_md_op(self):
        import docx
        d = tmpdir()
        src = os.path.join(d, 'm.docx')
        doc = docx.Document()
        doc.add_paragraph('正文')
        doc.save(src)
        res = engine.run_op([src], {'op': 'docx_md'})
        self.assertTrue(res['ok'], res)
        self.assertTrue(res['outputs'][0].endswith('.md'))

    def test_zip_list_op(self):
        import zipfile
        d = tmpdir()
        src = os.path.join(d, 'z.zip')
        with zipfile.ZipFile(src, 'w') as z:
            z.writestr('a.txt', 'hi')
        res = engine.run_op([src], {'op': 'zip_list'})
        self.assertTrue(res['ok'])
        self.assertIn('a.txt', res['message'])

    def test_pdf_split_op(self):
        from PIL import Image
        d = tmpdir()
        img = os.path.join(d, 'p.png')
        Image.new('RGB', (120, 90), (0, 0, 0)).save(img)
        pdf = engine.convert([img], 'pdf')['outputs'][0]
        res = engine.run_op([pdf], {'op': 'pdf_split'})
        self.assertTrue(res['ok'], res)
        self.assertTrue(res['outputs'])
