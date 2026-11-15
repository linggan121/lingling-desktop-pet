# -*- coding: utf-8 -*-
"""灵灵的内置转换引擎：不依赖任何外部程序（视频/音频除外，首次使用时下载 FFmpeg）。

支持：
  · 图片互转（Pillow：png/jpg/webp/bmp/gif/tiff/ico/avif/psd 读/eps…），质量、缩放、灰度
  · HEIC（iPhone 照片）→ jpg/png
  · 图片 → PDF、PDF → 图片、PDF → 文本
  · Word / Excel / PPT → 文本、CSV
  · zip 打包 / 解压、7z 解压
  · 视频/音频：转 mp4 / mp3 / gif（需要 FFmpeg，会自动下载到本地数据目录）
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

CREATE_NO_WINDOW = 0x08000000


def _pdf_mod():
    try:
        import pymupdf as fitz
        return fitz
    except Exception:
        try:
            import fitz
            return fitz
        except Exception:
            return None

IMAGE_READ = {'png', 'jpg', 'jpeg', 'jfif', 'webp', 'bmp', 'gif', 'tif', 'tiff', 'ico',
              'avif', 'psd', 'ppm', 'tga', 'pcx', 'eps', 'dds', 'qoi', 'heic', 'heif',
              'j2k', 'jp2', 'wmf', 'xbm', 'xpm', 'sgi', 'im', 'msp', 'dib', 'cur'}
IMAGE_WRITE = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff', 'ico', 'avif',
               'pdf', 'ppm', 'tga', 'pcx', 'dds', 'qoi', 'eps', 'jp2', 'xbm'}
DOC_EXT = {'docx', 'xlsx', 'pptx'}
ARCHIVE_READ = {'zip', '7z'}
MEDIA_EXT = {'mp4', 'mov', 'mkv', 'avi', 'webm', 'flv', 'wmv', 'm4v', 'ts',
             'mp3', 'wav', 'flac', 'aac', 'm4a', 'ogg', 'opus', 'wma'}

TARGETS = ['png', 'jpg', 'webp', 'bmp', 'gif', 'tiff', 'ico', 'avif', 'pdf',
           'txt', 'csv', 'zip', 'mp4', 'mp3']


def _ext(path):
    return os.path.splitext(str(path))[1].lower().lstrip('.')


def kind_of(path):
    """返回 image / pdf / doc / archive / media / folder / other"""
    if os.path.isdir(path):
        return 'folder'
    e = _ext(path)
    if e in ('pdf',):
        return 'pdf'
    if e in IMAGE_READ:
        return 'image'
    if e in DOC_EXT:
        return 'doc'
    if e in ARCHIVE_READ:
        return 'archive'
    if e in MEDIA_EXT:
        return 'media'
    return 'other'


def _pillow():
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    return Image


def _dst_path(src, target, out_dir=None):
    base = os.path.splitext(os.path.basename(src))[0]
    folder = out_dir or os.path.dirname(os.path.abspath(src))
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, '%s.%s' % (base, target))
    n = 1
    while os.path.exists(dst):
        dst = os.path.join(folder, '%s (%d).%s' % (base, n, target))
        n += 1
    return dst


# ------------------------------------------------------------------ 图片
def _resize(im, mode):
    if not mode:
        return im
    w, h = im.size
    if mode == 'half':
        return im.resize((max(1, w // 2), max(1, h // 2)), 1)
    if isinstance(mode, int) and mode > 0:
        scale = mode / float(max(w, h))
        if scale < 1:
            return im.resize((max(1, int(w * scale)), max(1, int(h * scale))), 1)
    return im


def convert_images(files, target, quality=85, resize=None, out_dir=None):
    Image = _pillow()
    target = 'jpg' if target == 'jpeg' else target
    outputs, errors = [], []
    for src in files:
        try:
            im = Image.open(src)
            im.load()
            if target in ('jpg', 'pdf', 'bmp') and im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            elif target in ('png', 'webp', 'ico', 'gif') and im.mode == 'P':
                im = im.convert('RGBA')
            im = _resize(im, resize)
            dst = _dst_path(src, target, out_dir)
            if target == 'jpg':
                im.save(dst, 'JPEG', quality=int(quality), optimize=True)
            elif target == 'webp':
                im.save(dst, 'WEBP', quality=int(quality), method=6)
            elif target == 'png':
                im.save(dst, 'PNG', optimize=True)
            elif target == 'pdf':
                im.save(dst, 'PDF', resolution=150.0)
            elif target == 'ico':
                im.save(dst, 'ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                                           (128, 128), (256, 256)])
            else:
                im.save(dst)
            outputs.append(dst)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


# ------------------------------------------------------------------ PDF
def pdf_to_images(files, target='png', out_dir=None):
    outputs, errors = [], []
    fitz = _pdf_mod()
    if fitz is None:
        return [], ['还没安装 PDF 引擎']
    for src in files:
        try:
            doc = fitz.open(src)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=150)
                base = os.path.splitext(os.path.basename(src))[0]
                folder = out_dir or os.path.dirname(os.path.abspath(src))
                dst = os.path.join(folder, '%s-%02d.%s' % (base, i + 1, target))
                pix.save(dst)
                outputs.append(dst)
            doc.close()
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


def pdf_to_text(files, out_dir=None):
    outputs, errors = [], []
    fitz = _pdf_mod()
    if fitz is None:
        return [], ['还没安装 PDF 引擎']
    for src in files:
        try:
            doc = fitz.open(src)
            text = '\n'.join(page.get_text() for page in doc)
            doc.close()
            dst = _dst_path(src, 'txt', out_dir)
            with io.open(dst, 'w', encoding='utf-8') as f:
                f.write(text)
            outputs.append(dst)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


# ------------------------------------------------------------------ Office
def office_to_text(files, out_dir=None):
    outputs, errors = [], []
    for src in files:
        e = _ext(src)
        try:
            if e == 'docx':
                import docx
                doc = docx.Document(src)
                text = '\n'.join(p.text for p in doc.paragraphs)
                dst = _dst_path(src, 'txt', out_dir)
                with io.open(dst, 'w', encoding='utf-8') as f:
                    f.write(text)
            elif e == 'xlsx':
                import csv
                import openpyxl
                wb = openpyxl.load_workbook(src, data_only=True)
                dst = _dst_path(src, 'csv', out_dir)
                with io.open(dst, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    for row in wb[wb.sheetnames[0]].iter_rows(values_only=True):
                        writer.writerow(['' if v is None else v for v in row])
            elif e == 'pptx':
                from pptx import Presentation
                prs = Presentation(src)
                lines = []
                for i, slide in enumerate(prs.slides, 1):
                    lines.append('--- 第 %d 页 ---' % i)
                    for shape in slide.shapes:
                        if getattr(shape, 'has_text_frame', False):
                            lines.append(shape.text_frame.text)
                dst = _dst_path(src, 'txt', out_dir)
                with io.open(dst, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
            else:
                errors.append('%s：这个格式还不支持' % os.path.basename(src))
                continue
            outputs.append(dst)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


# ------------------------------------------------------------------ 压缩包
def extract_archives(files, out_dir=None):
    outputs, errors = [], []
    for src in files:
        e = _ext(src)
        base = os.path.splitext(os.path.basename(src))[0]
        folder = out_dir or os.path.dirname(os.path.abspath(src))
        dst_dir = os.path.join(folder, base)
        n = 1
        while os.path.exists(dst_dir):
            dst_dir = os.path.join(folder, '%s (%d)' % (base, n))
            n += 1
        try:
            os.makedirs(dst_dir, exist_ok=True)
            if e == 'zip':
                with zipfile.ZipFile(src) as z:
                    z.extractall(dst_dir)
            elif e == '7z':
                import py7zr
                with py7zr.SevenZipFile(src) as z:
                    z.extractall(dst_dir)
            else:
                errors.append('%s：不支持的压缩格式' % os.path.basename(src))
                continue
            outputs.append(dst_dir)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


def pack_zip(files, out_dir=None):
    outputs, errors = [], []
    for src in files:
        base = os.path.basename(src.rstrip('\\/')) or 'pack'
        folder = out_dir or os.path.dirname(os.path.abspath(src))
        dst = _dst_path(os.path.join(folder, base + '.x'), 'zip', folder)
        try:
            with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
                if os.path.isdir(src):
                    for root, _dirs, names in os.walk(src):
                        for name in names:
                            full = os.path.join(root, name)
                            z.write(full, os.path.relpath(full, os.path.dirname(src)))
                else:
                    z.write(src, os.path.basename(src))
            outputs.append(dst)
        except Exception as exc:
            errors.append('%s：%s' % (base, str(exc)[:60]))
    return outputs, errors


# ------------------------------------------------------------------ FFmpeg
FFMPEG_URLS = [
    'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
    'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
]


def ffmpeg_path(data_dir):
    local = os.path.join(data_dir, 'ffmpeg.exe')
    if os.path.isfile(local):
        return local
    alt = os.path.join(data_dir, 'ffmpeg', 'ffmpeg.exe')
    if os.path.isfile(alt):
        return alt
    found = shutil.which('ffmpeg')
    return found or ''


def download_ffmpeg(data_dir, progress=None, timeout=600):
    """下载 FFmpeg 到数据目录，返回可执行文件路径（失败返回空）。"""
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    target = os.path.join(data_dir, 'ffmpeg.exe')
    last_err = ''
    for url in FFMPEG_URLS:
        try:
            if progress:
                progress('正在下载 FFmpeg（约 80MB）…')
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = resp.read()
            tmp = os.path.join(data_dir, 'ffmpeg_download.zip')
            with open(tmp, 'wb') as f:
                f.write(data)
            with zipfile.ZipFile(tmp) as z:
                for name in z.namelist():
                    if name.endswith('/ffmpeg.exe') or name == 'ffmpeg.exe':
                        with z.open(name) as s, open(target, 'wb') as d:
                            shutil.copyfileobj(s, d)
                        break
            os.remove(tmp)
            if os.path.isfile(target):
                return target
        except Exception as exc:
            last_err = str(exc)[:80]
    if progress:
        progress('FFmpeg 下载失败：%s' % last_err)
    return ''


def convert_media(files, target, data_dir, quality=85, out_dir=None, progress=None):
    exe = ffmpeg_path(data_dir)
    if not exe:
        exe = download_ffmpeg(data_dir, progress=progress)
    if not exe:
        return [], ['还没装 FFmpeg，视频/音频转换需要它（可以让我自动下载）']
    outputs, errors = [], []
    for src in files:
        dst = _dst_path(src, target, out_dir)
        args = [exe, '-y', '-i', src]
        if target == 'gif':
            args += ['-vf', 'fps=12,scale=480:-1:flags=lanczos', dst]
        elif target == 'mp3':
            args += ['-vn', '-q:a', '2', dst]
        else:
            args += ['-c:v', 'libx264', '-crf', str(max(18, min(40, 40 - int(quality) // 4))),
                     '-preset', 'veryfast', '-c:a', 'aac', '-b:a', '128k', dst]
        try:
            proc = subprocess.run(args, capture_output=True, timeout=1800,
                                  creationflags=CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if proc.returncode == 0 and os.path.isfile(dst):
                outputs.append(dst)
            else:
                errors.append('%s：转换失败' % os.path.basename(src))
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


# ------------------------------------------------------------------ 统一入口
def available_targets(files):
    """当前这批文件能转成哪些目标（给指令解析用）。"""
    kinds = {kind_of(f) for f in files}
    out = set()
    if kinds & {'image'}:
        out |= IMAGE_WRITE - {'pdf'}
        out.add('pdf')
    if kinds & {'pdf'}:
        out |= {'png', 'jpg', 'txt'}
    if kinds & {'doc'}:
        out |= {'txt', 'csv'}
    if kinds & {'archive'}:
        out |= {'zip'}
    if kinds & {'media'}:
        out |= {'mp4', 'mp3', 'gif'}
    if kinds & {'folder'}:
        out |= {'zip'}
    return sorted(out)


def convert(files, target, quality=85, resize=None, out_dir=None, data_dir=None,
            progress=None):
    """执行转换，返回和以前一致的结果字典。"""
    files = [f for f in files if f]
    if not files:
        return {'ok': False, 'converted': 0, 'failed': 0, 'skipped': 0,
                'outputs': [], 'errors': ['没有文件'], 'message': '没有要转换的文件'}
    target = (target or '').lower()

    images = [f for f in files if kind_of(f) == 'image']
    pdfs = [f for f in files if kind_of(f) == 'pdf']
    docs = [f for f in files if kind_of(f) == 'doc']
    archives = [f for f in files if kind_of(f) == 'archive']
    media = [f for f in files if kind_of(f) == 'media']
    folders = [f for f in files if kind_of(f) == 'folder']

    outputs, errors = [], []

    if target in IMAGE_WRITE and target != 'pdf':
        if images:
            outputs, errors = convert_images(images, target, quality, resize, out_dir)
        elif pdfs and target in ('png', 'jpg'):
            outputs, errors = pdf_to_images(pdfs, target, out_dir)
        else:
            return _fail('这批文件里没有能转成 %s 的图片' % target)
    elif target == 'pdf':
        if images:
            outputs, errors = convert_images(images, 'pdf', quality, resize, out_dir)
        else:
            return _fail('转 PDF 现在只支持图片')
    elif target == 'txt':
        if pdfs:
            outs, errs = pdf_to_text(pdfs, out_dir)
            outputs += outs
            errors += errs
        if docs:
            outs, errs = office_to_text(docs, out_dir)
            outputs += outs
            errors += errs
        if not (pdfs or docs):
            return _fail('这些文件里没有能提取文字的 PDF / 文档')
    elif target == 'csv':
        if not docs:
            return _fail('转 CSV 需要 Excel 文件')
        outputs, errors = office_to_text(docs, out_dir)
        outputs = [o for o in outputs if o.lower().endswith('.csv')]
    elif target == 'zip':
        if archives:
            outs, errs = extract_archives(archives, out_dir)
            outputs += outs
            errors += errs
        packable = folders or [f for f in files if kind_of(f) != 'archive']
        if packable:
            outs, errs = pack_zip(packable, out_dir)
            outputs += outs
            errors += errs
    elif target in ('mp4', 'mp3', 'gif'):
        media_sources = media or [f for f in files if _ext(f) == 'gif']
        if not media_sources:
            return _fail('这些文件里没有视频/音频')
        outputs, errors = convert_media(media_sources, target, data_dir or '.', quality,
                                        out_dir, progress)
    elif target in ('', None):
        if archives:
            outputs, errors = extract_archives(archives, out_dir)
        else:
            return _fail('想让我做什么？可以回数字选一项')
    else:
        return _fail('这个转换我还做不了')

    skipped = len(files) - len(images) - len(pdfs) - len(docs) - len(archives) - len(media) - len(folders)
    converted = len(outputs)
    failed = len(errors)
    if converted and not failed:
        message = '好了，%d个都完成了' % converted
    elif converted:
        message = '%d个成功，%d个失败' % (converted, failed)
    elif failed:
        message = '没成功：' + errors[0]
    else:
        message = '没有需要处理的文件'
    return {'ok': converted > 0, 'converted': converted, 'failed': failed,
            'skipped': max(0, skipped), 'outputs': outputs, 'errors': errors,
            'message': message}


def _fail(msg):
    return {'ok': False, 'converted': 0, 'failed': 0, 'skipped': 0,
            'outputs': [], 'errors': [msg], 'message': msg}


class FolderWatcher(object):
    """内置的文件夹监听：新文件自动转到 converted 子目录。"""

    def __init__(self, folder, target, data_dir=None, quality=85, resize=None,
                 on_done=None, interval=1.5):
        self.folder = folder
        self.target = target
        self.data_dir = data_dir or ''
        self.quality = quality
        self.resize = resize
        self.on_done = on_done
        self.interval = interval
        self._stop = threading.Event()
        self._seen = set()
        self._thread = None

    def _scan(self):
        found = set()
        try:
            for name in os.listdir(self.folder):
                path = os.path.join(self.folder, name)
                if not os.path.isfile(path):
                    continue
                if name.lower().endswith(('.tmp', '.part', '.crdownload')):
                    continue
                try:
                    found.add((path, os.path.getsize(path)))
                except Exception:
                    pass
        except Exception:
            pass
        return found

    def _loop(self):
        while not self._stop.is_set():
            time.sleep(self.interval)
            if self._stop.is_set():
                break
            current = self._scan()
            fresh = [p for p, _sz in (current - self._seen)]
            self._seen = current
            fresh = [p for p in fresh if not p.lower().endswith('.' + self.target.lower())]
            if not fresh:
                continue
            out_dir = os.path.join(self.folder, 'converted')
            res = convert(fresh, self.target, quality=self.quality, resize=self.resize,
                          out_dir=out_dir, data_dir=self.data_dir)
            if self.on_done:
                try:
                    self.on_done(res)
                except Exception:
                    pass

    def start(self):
        self._seen = self._scan()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()


# ------------------------------------------------------------------ 看内容 / 出选项
def inspect(path):
    """快速看一眼文件，返回可以用来决定选项的信息。"""
    e = _ext(path)
    info = {'kind': kind_of(path), 'ext': e}
    try:
        info['size'] = os.path.getsize(path) if os.path.isfile(path) else 0
    except Exception:
        info['size'] = 0
    try:
        if info['kind'] == 'image':
            Image = _pillow()
            with Image.open(path) as im:
                info['w'], info['h'] = im.size
                info['mode'] = im.mode
                info['alpha'] = im.mode in ('RGBA', 'LA') or 'transparency' in im.info
        elif e == 'pdf':
            fitz = _pdf_mod()
            if fitz is not None:
                doc = fitz.open(path)
                info['pages'] = doc.page_count
                text = ''
                for i in range(min(2, doc.page_count)):
                    text += doc[i].get_text()
                info['has_text'] = bool(text.strip())
                doc.close()
        elif e == 'docx':
            import docx
            doc = docx.Document(path)
            info['paragraphs'] = len(doc.paragraphs)
            info['tables'] = len(doc.tables)
            info['images'] = sum(1 for r in doc.part.rels.values() if 'image' in r.reltype)
        elif e == 'xlsx':
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True)
            info['sheets'] = [ws.title for ws in wb.worksheets]
            wb.close()
        elif e == 'pptx':
            from pptx import Presentation
            prs = Presentation(path)
            info['slides'] = len(prs.slides)
        elif e == 'zip':
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                info['entries'] = len(names)
                info['preview'] = names[:8]
        elif e == '7z':
            import py7zr
            with py7zr.SevenZipFile(path) as z:
                names = z.getnames()
                info['entries'] = len(names)
                info['preview'] = names[:8]
        elif info['kind'] == 'folder':
            count = 0
            for _root, _dirs, files in os.walk(path):
                count += len(files)
            info['files'] = count
    except Exception as exc:
        info['error'] = str(exc)[:60]
    return info


def options_for(files):
    """按文件内容给编号选项；每项 (label, act)。"""
    kinds = {kind_of(f) for f in files}
    infos = [inspect(f) for f in files[:3]]
    opts = []

    if 'image' in kinds:
        opts += [
            ('转成 webp', {'op': 'convert', 'target': 'webp'}),
            ('转成 jpg（质量 80）', {'op': 'convert', 'target': 'jpg', 'quality': 80}),
            ('转成 png', {'op': 'convert', 'target': 'png'}),
            ('长边缩到 1080', {'op': 'convert', 'target': 'webp', 'resize': 1080}),
        ]
        if any((i.get('w') or 0) >= 128 and abs((i.get('w') or 1) - (i.get('h') or 1)) <= max(i.get('w') or 1, i.get('h') or 1) * 0.35 for i in infos):
            opts.append(('转成 ico 图标', {'op': 'convert', 'target': 'ico'}))
        opts.append(('转成 PDF', {'op': 'convert', 'target': 'pdf'}))

    if 'pdf' in kinds:
        opts.append(('逐页转成图片', {'op': 'convert', 'target': 'png'}))
        if any(i.get('has_text') for i in infos):
            opts.append(('提取全部文字', {'op': 'convert', 'target': 'txt'}))
        opts.append(('按页拆成单个 PDF', {'op': 'pdf_split'}))

    if 'doc' in kinds:
        opts.append(('提取文字', {'op': 'convert', 'target': 'txt'}))
        opts.append(('转成 Markdown', {'op': 'docx_md'}))
        if any(i.get('tables') for i in infos):
            opts.append(('导出里面的表格（CSV）', {'op': 'docx_tables'}))
        if any(i.get('images') for i in infos):
            opts.append(('把里面的图片提取出来', {'op': 'docx_images'}))

    if 'archive' in kinds:
        opts.append(('先看看里面有什么', {'op': 'zip_list'}))
        opts.append(('解压到旁边', {'op': 'extract'}))

    if 'folder' in kinds:
        opts.append(('打包成 zip', {'op': 'convert', 'target': 'zip'}))

    if 'media' in kinds:
        opts += [
            ('转成 mp4', {'op': 'convert', 'target': 'mp4'}),
            ('提取音频 mp3', {'op': 'convert', 'target': 'mp3'}),
            ('转成 gif', {'op': 'convert', 'target': 'gif'}),
        ]

    if not opts:
        opts = [('看看能做什么', {'op': 'help'})]
    opts = opts[:8]

    # 混合拖入时给每项加类型前缀，避免分不清
    kinds_used = {k for k in kinds if k in ('image', 'pdf', 'doc', 'archive', 'folder', 'media')}
    if len(kinds_used) > 1:
        tag = {'image': '图片', 'pdf': 'PDF', 'doc': '文档',
               'archive': '压缩包', 'folder': '文件夹', 'media': '音视频'}
        guess = []
        for label, act in opts:
            t = act.get('target') or ''
            op = act.get('op')
            if op == 'extract' or op == 'zip_list':
                k = 'archive'
            elif op in ('pdf_split',):
                k = 'pdf'
            elif op in ('docx_md', 'docx_tables', 'docx_images'):
                k = 'doc'
            elif t in ('zip',):
                k = 'folder'
            elif t in ('mp4', 'mp3', 'gif'):
                k = 'media'
            elif t in ('txt', 'csv'):
                k = 'doc'
            elif t == 'pdf':
                k = 'image'
            else:
                k = 'image'
            guess.append(('%s：%s' % (tag.get(k, ''), label), act))
        opts = guess
    return opts


# ------------------------------------------------------------------ 额外操作
def pdf_split(files, out_dir=None):
    fitz = _pdf_mod()
    if fitz is None:
        return [], ['还没安装 PDF 引擎']
    outputs, errors = [], []
    for src in files:
        try:
            doc = fitz.open(src)
            base = os.path.splitext(os.path.basename(src))[0]
            folder = out_dir or os.path.dirname(os.path.abspath(src))
            page_dir = os.path.join(folder, base + '-pages')
            os.makedirs(page_dir, exist_ok=True)
            for i in range(doc.page_count):
                out = fitz.open()
                out.insert_pdf(doc, from_page=i, to_page=i)
                path = os.path.join(page_dir, '%s-p%02d.pdf' % (base, i + 1))
                out.save(path)
                out.close()
                outputs.append(path)
            doc.close()
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


def docx_to_markdown(files, out_dir=None):
    outputs, errors = [], []
    for src in files:
        try:
            import docx
            doc = docx.Document(src)
            lines = ['# ' + os.path.splitext(os.path.basename(src))[0], '']
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                style = (para.style.name or '').lower()
                if 'heading 1' in style or '标题 1' in style:
                    lines.append('# ' + text)
                elif 'heading 2' in style or '标题 2' in style:
                    lines.append('## ' + text)
                elif 'heading' in style or '标题' in style:
                    lines.append('### ' + text)
                else:
                    lines.append(text)
                lines.append('')
            dst = _dst_path(src, 'md', out_dir)
            with io.open(dst, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            outputs.append(dst)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


def docx_tables(files, out_dir=None):
    outputs, errors = [], []
    for src in files:
        try:
            import csv
            import docx
            doc = docx.Document(src)
            base = os.path.splitext(os.path.basename(src))[0]
            folder = out_dir or os.path.dirname(os.path.abspath(src))
            for idx, table in enumerate(doc.tables, 1):
                dst = os.path.join(folder, '%s-table%d.csv' % (base, idx))
                with io.open(dst, 'w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    for row in table.rows:
                        writer.writerow([cell.text.strip() for cell in row.cells])
                outputs.append(dst)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


def docx_images(files, out_dir=None):
    outputs, errors = [], []
    for src in files:
        try:
            base = os.path.splitext(os.path.basename(src))[0]
            folder = out_dir or os.path.dirname(os.path.abspath(src))
            dst_dir = os.path.join(folder, base + '-images')
            os.makedirs(dst_dir, exist_ok=True)
            n = 0
            with zipfile.ZipFile(src) as z:
                for name in z.namelist():
                    if name.startswith('word/media/'):
                        n += 1
                        with z.open(name) as s, open(os.path.join(dst_dir, os.path.basename(name)), 'wb') as d:
                            shutil.copyfileobj(s, d)
            outputs.append(dst_dir)
        except Exception as exc:
            errors.append('%s：%s' % (os.path.basename(src), str(exc)[:60]))
    return outputs, errors


def run_op(files, act, data_dir=None):
    """统一执行：按 act['op'] 分派，返回结果字典。"""
    op = (act or {}).get('op') or 'convert'
    files = [f for f in files if f]
    if op == 'convert':
        return convert(files, act.get('target') or '', quality=act.get('quality') or 85,
                       resize=act.get('resize'), data_dir=data_dir)
    if op == 'extract':
        outputs, errors = extract_archives(files)
        return _pack_result(outputs, errors, '解压好了')
    if op == 'zip_list':
        lines = []
        for f in files:
            info = inspect(f)
            lines.append('%s：%d 个条目' % (os.path.basename(f), info.get('entries') or 0))
            for name in (info.get('preview') or [])[:8]:
                lines.append('  · ' + name)
        msg = '\n'.join(lines) if lines else '没看出里面有什么'
        return {'ok': bool(lines), 'converted': 0, 'failed': 0, 'skipped': 0,
                'outputs': [], 'errors': [], 'message': msg}
    if op == 'pdf_split':
        return _pack_result(*pdf_split(files), ok_msg='按页拆好了')
    if op == 'docx_md':
        return _pack_result(*docx_to_markdown(files), ok_msg='转成 Markdown 了')
    if op == 'docx_tables':
        return _pack_result(*docx_tables(files), ok_msg='表格导出好了')
    if op == 'docx_images':
        return _pack_result(*docx_images(files), ok_msg='图片提取好了')
    if op == 'help':
        return {'ok': True, 'converted': 0, 'failed': 0, 'skipped': 0, 'outputs': [],
                'errors': [], 'message': '我可以转图片、拆 PDF、提取文档文字、打包解压、转视频'}
    return {'ok': False, 'converted': 0, 'failed': 0, 'skipped': 0,
            'outputs': [], 'errors': ['不支持的操作'], 'message': '这个我还不会'}


def _pack_result(outputs, errors, ok_msg='完成了'):
    converted, failed = len(outputs), len(errors)
    if converted and not failed:
        message = '%s，%d个' % (ok_msg, converted)
    elif converted:
        message = '%d个成功，%d个失败' % (converted, failed)
    elif failed:
        message = '没成功：' + errors[0]
    else:
        message = '没有需要处理的文件'
    return {'ok': converted > 0, 'converted': converted, 'failed': failed, 'skipped': 0,
            'outputs': outputs, 'errors': errors, 'message': message}
