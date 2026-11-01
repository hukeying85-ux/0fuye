#!/usr/bin/env python3
"""Render PDF slides to a fresh Xiaohongshu image folder, optionally inpainting verified boxes."""
import argparse
import json
import math
from pathlib import Path

import pymupdf
from PIL import Image


def validate_boxes(data, page_count):
    if not isinstance(data, dict):
        raise ValueError('watermark config must be an object mapping page numbers to boxes')
    result = {}
    for key, boxes in data.items():
        if not isinstance(key, str) or not key.isdigit() or not 1 <= int(key) <= page_count:
            raise ValueError(f'invalid page number: {key!r}')
        if not isinstance(boxes, list):
            raise ValueError(f'boxes for page {key} must be a list')
        result[int(key)] = []
        for box in boxes:
            if not isinstance(box, list) or len(box) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in box):
                raise ValueError(f'invalid box on page {key}: {box!r}')
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                raise ValueError(f'box out of bounds on page {key}: {box!r}')
            result[int(key)].append(box)
    return result


def unique_folder(parent, name):
    if not name or name in ('.', '..') or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('name must be a single folder name')
    parent.mkdir(parents=True, exist_ok=True)
    i = 1
    while True:
        path = parent / (name if i == 1 else f'{name}-{i}')
        try:
            path.mkdir()
            return path
        except FileExistsError:
            i += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output-parent', type=Path, required=True)
    parser.add_argument('--name', default='小红书发布包')
    parser.add_argument('--watermarks', type=Path, help='JSON with manually verified normalized boxes per page')
    args = parser.parse_args()
    with pymupdf.open(args.pdf) as doc:
        boxes = validate_boxes(json.loads(args.watermarks.read_text(encoding='utf-8')) if args.watermarks else {}, len(doc))
        if any(boxes.values()):
            import cv2
            import numpy as np
        folder = unique_folder(args.output_parent, args.name)
        digits = max(2, len(str(len(doc))))
        for index, page in enumerate(doc, 1):
            pix = page.get_pixmap(alpha=False, colorspace=pymupdf.csRGB)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            if boxes.get(index):
                arr = np.array(im)
                mask = np.zeros((pix.height, pix.width), dtype=np.uint8)
                for x1, y1, x2, y2 in boxes[index]:
                    mask[math.floor(y1*pix.height):math.ceil(y2*pix.height), math.floor(x1*pix.width):math.ceil(x2*pix.width)] = 255
                im = Image.fromarray(cv2.inpaint(arr, mask, 5, cv2.INPAINT_TELEA))
            # Expand to 4:3 landscape only as needed, retaining the whole original page.
            width, height = im.size
            canvas_w = max(width, math.ceil(height * 4 / 3))
            canvas_h = max(height, math.ceil(width * 3 / 4))
            canvas = Image.new('RGB', (canvas_w, canvas_h), (248, 245, 232))
            canvas.paste(im, ((canvas_w-width)//2, (canvas_h-height)//2))
            canvas.save(folder / f'{index:0{digits}d}.jpg', quality=95, subsampling=0, optimize=True)
        print(f'Created {len(doc)} images in {folder}. Inspect every page; create 发布文案.txt separately.')


if __name__ == '__main__':
    main()
