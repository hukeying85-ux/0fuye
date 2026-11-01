import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import pymupdf
    from PIL import Image
except ImportError:
    pymupdf = None

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/xiaohongshu-pdf/render.py'


@unittest.skipIf(pymupdf is None, 'requires PyMuPDF and Pillow')
class XiaohongshuPdfTest(unittest.TestCase):
    def test_render_does_not_overwrite_and_retains_page(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / 'input.pdf'
            doc = pymupdf.open()
            doc.new_page(width=400, height=200)
            doc.new_page(width=200, height=400)
            doc.save(pdf)
            doc.close()
            cmd = [sys.executable, str(SCRIPT), str(pdf), '--output-parent', str(root), '--name', 'output']
            subprocess.run(cmd, check=True, capture_output=True)
            first = root / 'output' / '01.jpg'
            first.write_bytes(b'untouched')
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(first.read_bytes(), b'untouched')
            second = root / 'output-2'
            self.assertEqual(sorted(p.name for p in second.iterdir()), ['01.jpg', '02.jpg'])
            with Image.open(second / '01.jpg') as image:
                self.assertEqual(image.size, (400, 300))
            with Image.open(second / '02.jpg') as image:
                self.assertEqual(image.size, (534, 400))

    def test_verified_watermark_box_is_processed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = pymupdf.open()
            page = doc.new_page(width=400, height=200)
            page.draw_rect(pymupdf.Rect(360, 180, 400, 200), color=(0, 0, 0), fill=(0, 0, 0))
            doc.save(root / 'input.pdf')
            doc.close()
            (root / 'boxes.json').write_text(json.dumps({'1': [[0.9, 0.9, 1, 1]]}))
            subprocess.run([sys.executable, str(SCRIPT), str(root / 'input.pdf'), '--output-parent', str(root), '--watermarks', str(root / 'boxes.json')], check=True, capture_output=True)
            with Image.open(root / '小红书发布包' / '01.jpg') as image:
                self.assertGreater(min(image.getpixel((390, 240))), 100)

    def test_invalid_boxes_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = pymupdf.open()
            doc.new_page()
            doc.save(root / 'input.pdf')
            doc.close()
            (root / 'boxes.json').write_text(json.dumps({'1': [[0, 0, 2, 1]]}))
            result = subprocess.run([sys.executable, str(SCRIPT), str(root / 'input.pdf'), '--output-parent', str(root), '--watermarks', str(root / 'boxes.json')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / '小红书发布包').exists())

if __name__ == '__main__':
    unittest.main()
