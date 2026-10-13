# -*- coding: utf-8 -*-
"""Shared RapidOCR recognizer.

Page text is read as whole lines. A tight four-character crop was smearing
the strokes of these small newspaper columns.
"""

import difflib
import threading

import cv2
import numpy as np


class OcrEngine:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        # Dilation and a wide unclip merge neighboring vertical columns.
        self._engine = RapidOCR(
            det_donot_use_dilation=True,
            det_unclip_ratio=1.3,
            det_box_thresh=0.35,
            det_max_candidates=2000,
            max_side_len=2400,
            text_score=0.2,
            use_cls=False,
        )
        self._lock = threading.Lock()

    def recognize_batch(self, images):
        """Return [(text, score), ...] aligned with images. Blank crops score 0."""
        if not images:
            return []
        prepared = []
        index = []
        results = [("", 0.0)] * len(images)
        for i, img in enumerate(images):
            if img is None or img.size == 0:
                continue
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            h, w = img.shape[:2]
            if h < 8 or w < 8:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
            bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            bh, bw = bgr.shape[:2]
            if bh < 42:
                scale = 48.0 / max(1, bh)
                bgr = cv2.resize(bgr, (max(8, int(bw * scale)), 48), interpolation=cv2.INTER_CUBIC)
            bgr = cv2.copyMakeBorder(
                bgr, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255)
            )
            prepared.append(bgr)
            index.append(i)
        if not prepared:
            return results
        with self._lock:
            rec, _elapse = self._engine.text_rec(prepared)
        for slot, item in zip(index, rec):
            if isinstance(item, (list, tuple)):
                text = item[0] or ""
                score = float(item[1] or 0.0)
            else:
                text, score = str(item), 0.0
            results[slot] = (text.strip(), score)
        return results

    def read_lines(self, image):
        """Detect and read text lines. Returns [{text, score, box}] in image coordinates."""
        if image is None or getattr(image, "size", 0) == 0:
            return []
        with self._lock:
            found, _elapse = self._engine(
                image,
                use_cls=False,
                box_thresh=0.35,
                unclip_ratio=1.3,
                text_score=0.2,
            )
        lines = []
        for item in found or []:
            box, text, score = item[0], item[1], item[2]
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            text = (text or "").strip()
            if not text:
                continue
            lines.append(
                {
                    "text": text,
                    "score": float(score or 0.0),
                    "box": (min(xs), min(ys), max(xs), max(ys)),
                }
            )
        return lines

    def read_page(self, image, on_step=None):
        """Read a full newspaper page.

        Vertical pages are turned sideways and read in bands. One pass over a
        whole dense page merges neighboring columns; a band keeps each column
        separate, which is what made the sample sentences readable.
        """
        if image is None or getattr(image, "size", 0) == 0:
            return []
        if _page_is_vertical(image):
            return self._read_vertical_page(image, on_step=on_step)
        lines = self.read_lines(image)
        if on_step:
            on_step(1.0)
        return _drop_specks(lines)

    def _read_vertical_page(self, image, on_step=None):
        height, width = image.shape[:2]
        rotated = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        rot_h, rot_w = rotated.shape[:2]
        band_h = 640
        overlap = 90
        lines = []
        y = 0
        steps = max(1, int((rot_h + band_h - overlap - 1) / max(1, band_h - overlap)))
        done = 0
        while y < rot_h:
            y1 = min(rot_h, y + band_h)
            if rot_h - y1 < 120:
                y1 = rot_h
            tile = rotated[y:y1, :]
            for line in self.read_lines(tile):
                x0, ty0, x1, ty1 = line["box"]
                ty0 += y
                ty1 += y
                ox0 = width - 1 - ty1
                ox1 = width - 1 - ty0
                oy0 = x0
                oy1 = x1
                if ox0 > ox1:
                    ox0, ox1 = ox1, ox0
                if oy0 > oy1:
                    oy0, oy1 = oy1, oy0
                lines.append(
                    {
                        "text": line["text"],
                        "score": line["score"],
                        "box": (ox0, oy0, ox1, oy1),
                    }
                )
            done += 1
            if on_step:
                on_step(min(1.0, done / float(steps)))
            if y1 >= rot_h:
                break
            y = y1 - overlap
        lines = _drop_specks(_dedupe_lines(lines))
        # A sideways pass glues a horizontal headline onto the column under it.
        # Read those wide lines upright and drop the glued echo.
        heads = self._upright_headlines(image)
        if not heads:
            return lines
        return _drop_specks(_dedupe_lines(_merge_headlines(lines, heads)))

    def _upright_headlines(self, image):
        height = image.shape[0]
        found = []
        for line in self.read_lines(image):
            x0, y0, x1, y1 = line["box"]
            width = x1 - x0
            tall = y1 - y0
            cjk = sum(1 for ch in line.get("text") or "" if "\u4e00" <= ch <= "\u9fff")
            if cjk < 2 or width < 36:
                continue
            if width < tall * 2.0:
                continue
            if tall > height * 0.09:
                continue
            found.append(self._reread_sparse(image, line))
        return found

    def _reread_sparse(self, image, line):
        """A calligraphy headline often collapses to one or two characters.

        Reading that crop on its own lets the detector separate the strokes.
        """
        x0, y0, x1, y1 = line["box"]
        wide = x1 - x0
        tall = max(1.0, y1 - y0)
        text = line.get("text") or ""
        cjk = len(_cjk_only(text))
        if cjk >= 4 or wide < 120 or tall < 36:
            return line
        if wide / max(cjk, 1) < tall * 1.5:
            return line
        pad = 8
        height, width = image.shape[:2]
        crop = image[max(0, int(y0) - pad) : min(height, int(y1) + pad), max(0, int(x0) - pad) : min(width, int(x1) + pad)]
        if crop.size == 0:
            return line
        best = None
        best_n = cjk
        for item in self.read_lines(crop):
            n = len(_cjk_only(item.get("text") or ""))
            if n > best_n:
                best = item
                best_n = n
        if best is None:
            return line
        bx0, by0, bx1, by1 = best["box"]
        updated = dict(line)
        updated["text"] = best.get("text") or text
        updated["score"] = best.get("score") or line.get("score") or 0.0
        updated["box"] = (
            max(0.0, x0 - pad) + bx0,
            max(0.0, y0 - pad) + by0,
            max(0.0, x0 - pad) + bx1,
            max(0.0, y0 - pad) + by1,
        )
        return updated


_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def _drop_specks(lines):
    kept = []
    for line in lines:
        text = line.get("text") or ""
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        if cjk == 0 and len(text.strip()) <= 2:
            continue
        x0, y0, x1, y1 = line["box"]
        if cjk == 0 and max(x1 - x0, y1 - y0) > 180:
            continue
        kept.append(line)
    return kept


def _dedupe_lines(lines):
    kept = []
    for line in lines:
        x0, y0, x1, y1 = line["box"]
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        replaced = False
        for old in kept:
            ox0, oy0, ox1, oy1 = old["box"]
            if abs(cx - (ox0 + ox1) / 2.0) < 14 and abs(cy - (oy0 + oy1) / 2.0) < 14:
                if line["score"] > old["score"]:
                    old["text"] = line["text"]
                    old["score"] = line["score"]
                    old["box"] = line["box"]
                replaced = True
                break
        if not replaced:
            kept.append(dict(line))
    return kept


def _box_cover(inner, outer):
    ix0 = max(inner[0], outer[0])
    iy0 = max(inner[1], outer[1])
    ix1 = min(inner[2], outer[2])
    iy1 = min(inner[3], outer[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area = max(1.0, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return inter / area


def _boxes_touch(a, b):
    ix0 = max(a[0], b[0])
    iy0 = max(a[1], b[1])
    ix1 = min(a[2], b[2])
    iy1 = min(a[3], b[3])
    return ix1 - ix0 > 6 and iy1 - iy0 > 6


def _cjk_only(text):
    return "".join(ch for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")


def _cut_echo(text, headline):
    """Remove a column fragment that is the same headline read sideways."""
    cand = _cjk_only(headline)
    if len(cand) < 3 or not text:
        return text
    best = None
    for variant in (cand, cand[::-1]):
        n = len(variant)
        for extra in (0, 1, 2):
            width = n + extra
            if width > len(text):
                continue
            for i in range(0, len(text) - width + 1):
                window = text[i : i + width]
                ratio = difflib.SequenceMatcher(None, _cjk_only(window), variant).ratio()
                if ratio >= 0.72 and (best is None or ratio > best[0]):
                    best = (ratio, i, i + width)
    if best is None:
        return text
    return (text[: best[1]] + text[best[2] :]).strip()


def _merge_headlines(column_lines, headlines):
    kept = []
    for line in column_lines:
        box = line["box"]
        if any(_box_cover(box, head["box"]) > 0.55 for head in headlines):
            continue
        text = line.get("text") or ""
        for head in headlines:
            if _boxes_touch(box, head["box"]):
                text = _cut_echo(text, head.get("text") or "")
        if len(_cjk_only(text)) < 1:
            continue
        item = dict(line)
        item["text"] = text
        kept.append(item)
    kept.extend(headlines)
    return kept


def _page_is_vertical(image):
    """True when characters stack in columns rather than in horizontal rows."""
    from newspaper_app.layout import _nearest_is_horizontal, detect_boxes

    height, width = image.shape[:2]
    scale = 720.0 / max(height, width, 1)
    if scale < 1:
        small = cv2.resize(image, (max(8, int(width * scale)), max(8, int(height * scale))), interpolation=cv2.INTER_AREA)
    else:
        small = image
    boxes, _v, _h, body = detect_boxes(small)
    if len(boxes) < 40:
        return height >= width * 0.9
    horizontal = _nearest_is_horizontal(boxes, body)
    return len(horizontal) < len(boxes) * 0.42


def get_engine():
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = OcrEngine()
        return _ENGINE
