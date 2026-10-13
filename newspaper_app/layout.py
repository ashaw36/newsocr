# -*- coding: utf-8 -*-
"""Turn a newspaper page image into articles with title, author and body.

Vertical pages are read top-to-bottom, columns right-to-left.
Horizontal character rows on those pages are read right-to-left.
"""

import re
import statistics
from dataclasses import dataclass, field

import cv2
import numpy as np

from newspaper_app import text as T

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_PUNCT = " \t\r\n\u3000.,;:!?\"'`~^_|\\/<>[]{}()+=*\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f\u300c\u300d\u300e\u300f\uff08\uff09\u3010\u3011\u00b7\u2026\u2014\u2013-_\u25a1\u25a0\u25cb\u25cf\u203b\u25b2\u2605\u2606"


@dataclass
class Run:
    boxes: list
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    kind: str  # "v" or "h"
    text: str = ""
    score: float = 0.0
    header: bool = False
    upright: bool = False
    byline_for: int = 0
    author_hint: str = ""

    @property
    def n(self):
        return len(self.boxes)

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2.0

    @property
    def w(self):
        return max(1.0, self.x1 - self.x0)

    @property
    def h(self):
        return max(1.0, self.y1 - self.y0)

    def cjk_text(self):
        return "".join(_CJK.findall(self.text or ""))


@dataclass
class Article:
    title: str
    author: str
    body: str
    bbox: tuple
    kind: str = "article"
    page: int = 1
    score: float = 0.0
    featured: bool = False
    id: str = ""
    tokens: list = field(default_factory=list)


def _median(values, default=12.0):
    vals = [v for v in values if v and v > 0]
    if not vals:
        return default
    return float(statistics.median(vals))


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def detect_boxes(img):
    """Character-sized components plus long rule lines."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 12
    )
    hk_w = max(28, w // 28)
    vk_h = max(28, h // 22)
    horiz = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hk_w, 1))
    )
    vert = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk_h))
    )
    rules = cv2.dilate(
        cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8), iterations=1
    )
    text = cv2.bitwise_and(bw, cv2.bitwise_not(rules))
    text = cv2.morphologyEx(text, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(text, connectivity=8)
    raw = []
    min_side = max(6, int(min(h, w) * 0.0035))
    for i in range(1, n):
        x, y, ww, hh, area = [int(v) for v in stats[i]]
        if ww < min_side or hh < min_side:
            continue
        if ww > w * 0.5 or hh > h * 0.55:
            continue
        if area < min_side * min_side * 0.35:
            continue
        if hh > ww * 7 or ww > hh * 8:
            continue
        raw.append((x, y, x + ww, y + hh))

    heights = sorted((b[3] - b[1]) for b in raw if (b[3] - b[1]) >= min_side)
    if not heights:
        body = float(min_side * 2)
    else:
        body = heights[int(len(heights) * 0.62)]
    body = float(max(body, min_side))

    boxes = []
    for b in raw:
        bh = b[3] - b[1]
        bw_ = b[2] - b[0]
        if bh < body * 0.42 or bw_ < body * 0.28:
            continue
        if bh > body * 7 or bw_ > body * 7:
            continue
        boxes.append(b)

    v_rules = _rule_segments(vert, axis="v", min_len=h * 0.12)
    h_rules = _rule_segments(horiz, axis="h", min_len=w * 0.08)
    return boxes, v_rules, h_rules, body


def _rule_segments(mask, axis, min_len):
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(mask, connectivity=8)
    segs = []
    for i in range(1, n):
        x, y, w, h, _area = [int(v) for v in stats[i]]
        if axis == "v" and h >= min_len and w <= max(12, h * 0.08):
            segs.append((x + w / 2.0, float(y), float(y + h)))
        if axis == "h" and w >= min_len and h <= max(12, w * 0.08):
            segs.append((y + h / 2.0, float(x), float(x + w)))
    return segs


def _rule_between(rules, pos, span0, span1, cover=0.45):
    """A rule crosses `pos` and overlaps [span0, span1] enough."""
    span = max(1.0, span1 - span0)
    for center, a, b in rules:
        if abs(center - pos) > 4:
            # pos is a point the rule should contain, not a coordinate match
            pass
        lo, hi = min(a, b), max(a, b)
        if center < min(span0, span1) - 2 or center > max(span0, span1) + 2:
            # For vertical rules, `center` is x and span is y. Caller passes the right axes.
            pass
        overlap = min(hi, span1) - max(lo, span0)
        if overlap > span * cover and lo - 3 <= pos <= hi + 3 and abs((lo + hi) / 2 - pos) >= 0:
            # pos must lie beyond the segment? We use this differently below.
            return True
    return False


def _v_rule_between(v_rules, x0, x1):
    for x, y0, y1 in v_rules:
        if x0 < x < x1 and (y1 - y0) > 20:
            return True
    return False


def _h_rule_between(h_rules, y0, y1, x):
    for y, x0, x1 in h_rules:
        if y0 < y < y1 and (x0 - 8) <= x <= (x1 + 8) and (x1 - x0) > 30:
            return True
    return False


def _nearest_is_horizontal(boxes, body):
    """Mark boxes that sit in a horizontal row rather than a vertical column."""
    if len(boxes) < 4:
        return set()
    centers = [((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0, i) for i, b in enumerate(boxes)]
    horiz_ids = set()
    # bucket by y for speed
    order = sorted(range(len(boxes)), key=lambda i: centers[i][1])
    for i, b in enumerate(boxes):
        cx, cy = centers[i][0], centers[i][1]
        bh = b[3] - b[1]
        best_v = 1e9
        best_h = 1e9
        for j in range(len(boxes)):
            if i == j:
                continue
            ox, oy = centers[j][0], centers[j][1]
            dx = abs(ox - cx)
            dy = abs(oy - cy)
            if dy > bh * 3 and dx > bh * 3:
                continue
            if dy < bh * 0.55 and dx < bh * 1.35:
                best_h = min(best_h, dx + dy * 0.2)
            if dx < bh * 0.55 and dy < bh * 1.35:
                best_v = min(best_v, dy + dx * 0.2)
        if best_h < best_v * 0.82 and best_h < body * 2.4:
            horiz_ids.add(i)
    return horiz_ids


def _chain_horizontal(boxes, ids, body):
    """Group boxes that form a real horizontal line. Others stay vertical."""
    chosen = [boxes[i] for i in ids]
    if not chosen:
        return []
    used = [False] * len(chosen)
    order = sorted(range(len(chosen)), key=lambda i: ((chosen[i][1] + chosen[i][3]) / 2.0, chosen[i][0]))
    kept = []
    for si in order:
        if used[si]:
            continue
        chain_idx = [si]
        used[si] = True
        changed = True
        while changed:
            changed = False
            chain = [chosen[i] for i in chain_idx]
            cy = _median([(b[1] + b[3]) / 2.0 for b in chain])
            ch = _median([b[3] - b[1] for b in chain])
            x0 = min(b[0] for b in chain)
            x1 = max(b[2] for b in chain)
            for j, b in enumerate(chosen):
                if used[j]:
                    continue
                by = (b[1] + b[3]) / 2.0
                if abs(by - cy) > max(ch, body) * 0.55:
                    continue
                gap = min(x0 - b[2], b[0] - x1)
                if -ch * 0.35 <= gap <= ch * 1.2:
                    chain_idx.append(j)
                    used[j] = True
                    changed = True
        chain = [chosen[i] for i in chain_idx]
        if len(chain) < 4:
            for i in chain_idx:
                used[i] = False
            continue
        width = max(b[2] for b in chain) - min(b[0] for b in chain)
        height = _median([b[3] - b[1] for b in chain])
        if width <= height * 2.4:
            for i in chain_idx:
                used[i] = False
            continue
        kept.append(sorted(chain, key=lambda b: b[0]))
    return kept


def _cluster_columns(boxes, body, v_rules):
    cols = []
    thresh = max(6.0, body * 0.42)
    for b in sorted(boxes, key=lambda b: (b[0] + b[2]) / 2.0):
        cx = (b[0] + b[2]) / 2.0
        placed = False
        for col in cols:
            ccx = col["cx"]
            if abs(cx - ccx) <= thresh and not _v_rule_between(v_rules, min(cx, ccx), max(cx, ccx)):
                col["boxes"].append(b)
                xs = [(bb[0] + bb[2]) / 2.0 for bb in col["boxes"]]
                col["cx"] = sum(xs) / len(xs)
                placed = True
                break
        if not placed:
            cols.append({"cx": cx, "boxes": [b]})
    cols = [c for c in cols if len(c["boxes"]) >= 2]
    for c in cols:
        c["boxes"].sort(key=lambda b: b[1])
    cols.sort(key=lambda c: -c["cx"])
    return cols


def _split_column_runs(boxes, body, h_rules):
    if not boxes:
        return []
    runs = []
    cur = [boxes[0]]

    def flush():
        if cur:
            runs.append(list(cur))

    for b in boxes[1:]:
        prev = cur[-1]
        gap = b[1] - prev[3]
        bh = b[3] - b[1]
        cur_h = _median([bb[3] - bb[1] for bb in cur])
        cx = (b[0] + b[2]) / 2.0
        size_jump = bh > cur_h * 1.55 or (len(cur) >= 2 and bh < cur_h * 0.62)
        rule = _h_rule_between(h_rules, prev[3] - 1, b[1] + 1, cx)
        if gap > max(body * 0.85, cur_h * 0.9) or size_jump or rule:
            flush()
            cur = [b]
        else:
            cur.append(b)
    flush()
    return runs


def _run_from_boxes(boxes, kind):
    hs = [b[3] - b[1] for b in boxes]
    ws = [b[2] - b[0] for b in boxes]
    size = _median(hs)
    cxs = [(b[0] + b[2]) / 2.0 for b in boxes]
    cys = [(b[1] + b[3]) / 2.0 for b in boxes]
    cx = _median(cxs)
    cy = _median(cys)
    if kind == "v":
        half = max(size, _median(ws)) * 0.58
        x0, x1 = cx - half, cx + half
        y0, y1 = min(b[1] for b in boxes), max(b[3] for b in boxes)
    else:
        half = size * 0.62
        y0, y1 = cy - half, cy + half
        x0, x1 = min(b[0] for b in boxes), max(b[2] for b in boxes)
    return Run(boxes=list(boxes), x0=x0, y0=float(y0), x1=x1, y1=float(y1), size=float(size), kind=kind)


def build_runs(img):
    boxes, v_rules, h_rules, body = detect_boxes(img)
    h, w = img.shape[:2]
    if not boxes:
        return [], v_rules, h_rules, body, (w, h)

    h_ids = _nearest_is_horizontal(boxes, body)
    h_chains = _chain_horizontal(boxes, h_ids, body)
    # Body text on these papers is vertical. A horizontal chain of body-sized
    # characters is usually several columns mistaken for one row.
    header_cut = h * 0.09
    kept_h = []
    for chain in h_chains:
        size = _median([b[3] - b[1] for b in chain])
        cy = _median([(b[1] + b[3]) / 2.0 for b in chain])
        if cy < header_cut or size >= body * 1.75:
            kept_h.append(chain)
    h_chains = kept_h
    consumed = set()
    for chain in h_chains:
        for b in chain:
            consumed.add(tuple(b))
    vertical_boxes = [b for b in boxes if tuple(b) not in consumed]
    # rejected horizontal-looking boxes go back to vertical flow
    # (already not in consumed)

    cols = _cluster_columns(vertical_boxes, body, v_rules)
    runs = []
    for chain in h_chains:
        runs.append(_run_from_boxes(chain, "h"))
    for col in cols:
        for group in _split_column_runs(col["boxes"], body, h_rules):
            if len(group) < 2 and (group[0][3] - group[0][1]) < body * 0.72:
                continue
            runs.append(_run_from_boxes(group, "v"))

    header_cut = h * 0.072
    footer_cut = h * 0.965
    for r in runs:
        if r.kind == "h" and r.cy < header_cut:
            r.header = True
        elif r.y1 < header_cut:
            r.header = True
        elif r.y0 > footer_cut and r.n <= 6:
            r.header = True
    return runs, v_rules, h_rules, body, (w, h)


def crop_slices(img, run, slice_n=4):
    """Tight crops. Vertical slices are rotated so the column reads left to right.

    Short slices stay sharp: the recognizer smears a long vertical column.
    A byline glyph is recognized upright, one character at a time.
    """
    boxes = run.boxes
    if run.kind == "h":
        boxes = sorted(boxes, key=lambda b: b[0])
    else:
        boxes = sorted(boxes, key=lambda b: b[1])
    groups = []
    if getattr(run, "upright", False):
        groups = [(i, i + 1) for i in range(len(boxes))]
    elif len(boxes) <= slice_n + 2:
        # A short headline stays in one crop. Splitting off the last glyph
        # is what misread the final character of a five-character title.
        groups = [(0, len(boxes))]
    else:
        cursor = 0
        while cursor < len(boxes):
            remain = len(boxes) - cursor
            take = slice_n if remain > slice_n + 1 else remain
            groups.append((cursor, cursor + take))
            cursor += take
    slices = []
    h, w = img.shape[:2]
    for start, end in groups:
        chunk = boxes[start:end]
        hs = [b[3] - b[1] for b in chunk]
        ws = [b[2] - b[0] for b in chunk]
        size = _median(hs)
        cxs = [(b[0] + b[2]) / 2.0 for b in chunk]
        cys = [(b[1] + b[3]) / 2.0 for b in chunk]
        if getattr(run, "upright", False):
            pad = max(2.0, size * 0.18)
            x0 = int(_clamp(min(b[0] for b in chunk) - pad, 0, w - 1))
            x1 = int(_clamp(max(b[2] for b in chunk) + pad, x0 + 1, w))
            y0 = int(_clamp(min(b[1] for b in chunk) - pad, 0, h - 1))
            y1 = int(_clamp(max(b[3] for b in chunk) + pad, y0 + 1, h))
        elif run.kind == "v":
            cx = _median(cxs)
            # Stay inside one column. A wider crop pulls in the next column.
            half = max(size, _median(ws)) * 0.46
            x0 = int(_clamp(cx - half, 0, w - 1))
            x1 = int(_clamp(cx + half, x0 + 1, w))
            y0 = int(_clamp(min(b[1] for b in chunk) - size * 0.12, 0, h - 1))
            y1 = int(_clamp(max(b[3] for b in chunk) + size * 0.12, y0 + 1, h))
        else:
            cy = _median(cys)
            half = size * 0.65
            y0 = int(_clamp(cy - half, 0, h - 1))
            y1 = int(_clamp(cy + half, y0 + 1, h))
            x0 = int(_clamp(min(b[0] for b in chunk) - size * 0.1, 0, w - 1))
            x1 = int(_clamp(max(b[2] for b in chunk) + size * 0.1, x0 + 1, w))
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        if getattr(run, "upright", False):
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
            gray = cv2.convertScaleAbs(gray, alpha=1.6, beta=-40)
            crop = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            ch, cw = crop.shape[:2]
            if ch < 72:
                scale = 72.0 / max(1, ch)
                crop = cv2.resize(crop, (max(8, int(cw * scale)), 72), interpolation=cv2.INTER_CUBIC)
        elif run.kind == "v":
            crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        slices.append(crop)
    return slices


def apply_ocr(runs, texts_scores, rtl_horizontal):
    """texts_scores aligns with runs, each item is (text, score) already concatenated."""
    for run, (text, score) in zip(runs, texts_scores):
        text = text or ""
        if run.kind == "h" and rtl_horizontal and _CJK.search(text) and len(_LATIN.findall(text)) < len(_CJK.findall(text)):
            text = _reverse_keep_lines(text)
        run.text = _clean_fragment(text)
        run.score = score


def _reverse_keep_lines(text):
    return "".join(ch for ch in reversed(text))


def _clean_fragment(text):
    text = text.replace("\u3000", "").replace(" ", "")
    text = re.sub(r"[|]+", "", text)
    return text.strip()


def _clean_paragraph(text):
    text = text.replace("\u3000", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])[ ]+(?=[\u4e00-\u9fff])", "", text)
    return text.strip()


def _y_overlap(a, b, ratio=0.18):
    lo = max(a.y0, b.y0)
    hi = min(a.y1, b.y1)
    if hi <= lo:
        return False
    return (hi - lo) >= min(a.h, b.h) * ratio


def _zones_from_runs(runs, v_rules, body, width):
    verticals = [r for r in runs if r.kind == "v" and not r.header]
    if not verticals:
        return [(0.0, width, runs)]
    cols = []
    thresh = body * 0.7
    for r in sorted(verticals, key=lambda r: -r.cx):
        placed = False
        for col in cols:
            if abs(r.cx - col["cx"]) <= thresh:
                col["runs"].append(r)
                col["cx"] = sum(x.cx for x in col["runs"]) / len(col["runs"])
                placed = True
                break
        if not placed:
            cols.append({"cx": r.cx, "runs": [r]})
    cols.sort(key=lambda c: -c["cx"])
    if len(cols) == 1:
        groups = [cols]
    else:
        gaps = []
        for i in range(len(cols) - 1):
            gaps.append(cols[i]["cx"] - cols[i + 1]["cx"])
        pitch = _median([g for g in gaps if g < body * 3.2], body * 1.4)
        groups = [[cols[0]]]
        for i in range(len(cols) - 1):
            left = cols[i + 1]
            right = cols[i]
            gap = right["cx"] - left["cx"]
            rule = _v_rule_between(v_rules, left["cx"], right["cx"])
            if rule or gap > max(pitch * 2.15, body * 2.8):
                groups.append([left])
            else:
                groups[-1].append(left)
    zones = []
    horiz = [r for r in runs if r.kind == "h" and not r.header]
    for group in groups:
        xs = [c["cx"] for c in group]
        pad = body * 1.4
        x0 = max(0.0, min(xs) - pad)
        x1 = min(float(width), max(xs) + pad)
        members = []
        for c in group:
            members.extend(c["runs"])
        for r in horiz:
            if x0 - body <= r.cx <= x1 + body:
                members.append(r)
        zones.append((x0, x1, members))
    # header runs are not zoned
    return zones


def _bands(members, h_rules, body, x0, x1, height):
    if not members:
        return []
    ys = []
    for y, rx0, rx1 in h_rules:
        overlap = min(rx1, x1) - max(rx0, x0)
        if overlap > (x1 - x0) * 0.45 and 8 < y < height - 8:
            ys.append(y)
    # whitespace gaps
    marks = []
    for r in members:
        marks.append((r.y0, 1))
        marks.append((r.y1, -1))
    marks.sort()
    depth = 0
    last = 0.0
    gap_start = None
    for pos, delta in marks:
        if depth == 0 and gap_start is not None:
            if pos - gap_start > body * 1.35 and gap_start > body:
                ys.append((gap_start + pos) / 2.0)
        if depth == 0:
            gap_start = pos
        depth += delta
        if depth == 0:
            gap_start = pos
        last = pos
    ys = sorted(set(int(y) for y in ys))
    # merge close cuts
    merged = []
    for y in ys:
        if not merged or y - merged[-1] > body * 0.8:
            merged.append(y)
    edges = [0.0] + merged + [float(height)]
    bands = []
    for i in range(len(edges) - 1):
        y0, y1 = edges[i], edges[i + 1]
        group = [r for r in members if y0 - 2 <= r.cy <= y1 + 2]
        if group:
            bands.append((y0, y1, group))
    return bands


def _is_title_run(run, body):
    cjk = run.cjk_text()
    n = max(len(cjk), run.n if run.kind == "v" else len(cjk))
    if len(cjk) < 2 or n > 24:
        return False
    if run.score and run.score < 0.4:
        return False
    if run.size < body * 1.58:
        return False
    # Short OCR strings are titles only when the type is clearly a headline.
    if len(cjk) < 4 and run.size < body * 2.15:
        return False
    return True


def _is_masthead(run, body, width, height):
    cjk = run.cjk_text()
    if run.size < body * 2.25:
        return False
    if run.cy < height * 0.16 and run.w > width * 0.12:
        return True
    # A news headline down the right edge is not the masthead.
    if run.cx > width * 0.82 and run.cy < height * 0.2 and len(cjk) <= 6 and run.size >= body * 3.2:
        return True
    if len(cjk) <= 6 and run.size >= body * 2.8 and run.cy < height * 0.2:
        return True
    return False


def _merge_title_runs(runs, body):
    if not runs:
        return []
    items = sorted(runs, key=lambda r: (round(r.cy / max(body, 1)), -r.cx))
    merged = [items[0]]
    for r in items[1:]:
        prev = merged[-1]
        same_col = abs(r.cx - prev.cx) < body * 0.8 and r.y0 - prev.y1 < body * 0.9 and r.kind == "v" and prev.kind == "v"
        same_row = abs(r.cy - prev.cy) < body * 0.8 and r.kind == "h" and prev.kind == "h"
        if same_col or same_row:
            if r.cx > prev.cx:
                text = (r.text or "") + (prev.text or "")
            else:
                text = (prev.text or "") + (r.text or "")
            if same_col:
                text = (prev.text or "") + (r.text or "")
            prev.text = text
            prev.x0 = min(prev.x0, r.x0)
            prev.y0 = min(prev.y0, r.y0)
            prev.x1 = max(prev.x1, r.x1)
            prev.y1 = max(prev.y1, r.y1)
            prev.score = max(prev.score, r.score)
            prev.boxes = prev.boxes + r.boxes
        else:
            merged.append(r)
    return merged


def _reading_sort(tokens):
    """Vertical newspaper order: columns right to left, each column top to bottom."""
    if not tokens:
        return []
    body = _median([t.size for t in tokens])
    thresh = max(4.0, body * 0.42)
    cols = []
    for t in sorted(tokens, key=lambda t: -t.cx):
        placed = False
        for col in cols:
            ccx = sum(item.cx for item in col) / len(col)
            if abs(t.cx - ccx) <= thresh:
                col.append(t)
                placed = True
                break
        if not placed:
            cols.append([t])
    out = []
    for col in cols:
        col.sort(key=lambda t: (t.y0, -t.cx))
        out.extend(col)
    return out


def _join_body(tokens):
    ordered = _reading_sort(tokens)
    parts = []
    prev = None
    for t in ordered:
        if prev is not None:
            same_col = abs(t.cx - prev.cx) <= max(prev.size, t.size) * 0.9
            gap = t.y0 - prev.y1
            if same_col and gap > max(prev.size, t.size) * 2.2:
                parts.append("\n")
        parts.append(t.text or "")
        prev = t
    return _clean_paragraph("".join(parts))


def _peel_author(body, extra_tokens, body_size, title_size=0):
    body = body.strip()
    if extra_tokens and title_size:
        ordered = _reading_sort(extra_tokens)
        if ordered:
            first = ordered[0]
            cjk = first.cjk_text()
            if (
                2 <= len(cjk) <= 4
                and first.n <= 5
                and cjk not in T.AUTHOR_STOP
                and first.size <= min(body_size * 1.15, title_size * 0.82)
                and (len(ordered) == 1 or ordered[1].n >= 6)
                and not any(w in cjk for w in T.AD_WORDS)
            ):
                rest_tokens = ordered[1:]
                return cjk, _join_body(rest_tokens) if rest_tokens else ""
    if not body:
        return "", ""
    m = re.match(
        r"^[\uff08(]([\u4e00-\u9fff\u00b7]{2,8})[\uff09)]",
        body,
    )
    if m and m.group(1) not in T.AUTHOR_STOP:
        return m.group(1), body[m.end() :].lstrip("\n\uff0c\u3002 ")
    m = re.match(
        r"^(?:\u672c\u5831|\u672c\u62a5)?(?:\u8a18\u8005|\u8bb0\u8005|\u901a\u8baf\u5458|\u901a\u8a0a\u54e1)?([\u4e00-\u9fff\u00b7]{1,8})([%s])" % T.AUTHOR_SUFFIX,
        body,
    )
    if m and m.group(1) not in T.AUTHOR_STOP and len(m.group(1)) <= 6:
        return m.group(1), body[m.end() :].lstrip("\n\uff0c\u3002 ")
    return "", body


def _strip_title(text):
    text = text.strip()
    text = re.sub(r"^[\u25a1\u25a0\u25cb\u25cf\u203b\u25b2\u2605\u2606\u53e3\u00b7\.\-\s\u3000]+", "", text)
    text = re.sub(r"[\u25a1\u25a0\u25cb\u25cf\u203b\u25b2\u2605\u2606]+", "", text)
    return text.strip()


def _kind_of(title, body):
    head = (title or "") + (body or "")[:40]
    if any(w in head for w in T.AD_WORDS):
        return "ad"
    if any(w in head for w in T.NOTICE_WORDS):
        return "notice"
    return "article"


def _byline_rank(title, run, body):
    """Lower is better. None means this run is not a byline for the title."""
    cjk = run.cjk_text()
    if cjk in T.AUTHOR_STOP or any(w in cjk for w in T.AD_WORDS):
        return None
    if not (2 <= len(cjk) <= 4) or run.n > 6:
        return None
    if run.size > title.size * 0.95:
        return None
    y_over = min(title.y1, run.y1) - max(title.y0, run.y0)
    # Classic byline: a short column just to the right of the headline (??).
    if run.cx > title.cx - body * 0.2 and y_over > 0:
        gap = run.x0 - title.x1
        if -body * 0.4 <= gap <= max(body, title.size) * 3.2:
            return max(0.0, gap)
    # Or the short name sitting directly under the headline.
    if abs(run.cx - title.cx) <= max(body, title.size) * 0.9:
        dy = run.y0 - title.y1
        if -body * 0.2 <= dy <= body * 1.6:
            return 5000 + max(0.0, dy)
    return None


def _merge_stacked_names(plain, body):
    """Join ? + ? when a byline was split into separate characters."""
    shorts = [r for r in plain if 1 <= len(r.cjk_text()) <= 3 and r.n <= 4]
    shorts.sort(key=lambda r: (round(r.cx / max(body * 0.5, 1.0)), r.y0))
    used = set()
    for i, run in enumerate(shorts):
        if id(run) in used:
            continue
        for other in shorts[i + 1 :]:
            if id(other) in used:
                continue
            if abs(other.cx - run.cx) > body * 0.6:
                continue
            if other.y0 - run.y1 > body * 0.9:
                continue
            if len(run.cjk_text()) + len(other.cjk_text()) > 4:
                continue
            run.text = (run.text or "") + (other.text or "")
            run.y0 = min(run.y0, other.y0)
            run.y1 = max(run.y1, other.y1)
            run.x0 = min(run.x0, other.x0)
            run.x1 = max(run.x1, other.x1)
            run.boxes = list(run.boxes) + list(other.boxes)
            used.add(id(other))
    if used:
        plain[:] = [r for r in plain if id(r) not in used]


def _extract_bylines(titles, plain, body):
    _merge_stacked_names(plain, body)
    taken = set()
    found = {}
    for title in sorted(titles, key=lambda t: -t.cx):
        best = None
        best_rank = 1e9
        for run in plain:
            if id(run) in taken:
                continue
            rank = _byline_rank(title, run, body)
            if rank is None or rank >= best_rank:
                continue
            best_rank = rank
            best = run
        if best is not None:
            found[id(title)] = best
            taken.add(id(best))
    if taken:
        plain[:] = [r for r in plain if id(r) not in taken]
    return found


def _owning_title(token, titles, body):
    """Attach a text run to the title a reader would already have started."""
    best = None
    best_score = 1e18
    for title in titles:
        dx = title.cx - token.cx
        score = 0.0
        if dx < -max(body, title.size) * 0.9:
            score += 8000 + abs(dx)
        else:
            score += max(0.0, dx)
        if token.cy < title.y0 - body * 0.7:
            score += 6000
        else:
            score += max(0.0, token.cy - title.cy) * 0.22
        same_col = abs(token.cx - title.cx) <= max(body, title.size) * 1.2 and token.y0 >= title.y0 - body * 0.4
        if same_col:
            score *= 0.35
        elif token.y0 > title.y1 + body * 0.8:
            # beside-and-below belongs to a lower headline, not this one
            score += 5000
        if len(titles) >= 3:
            floor = 1e9
            for other in titles:
                if other is title or other.y0 < title.y0 + body * 0.4:
                    continue
                if other.cx < title.cx - body * 8:
                    continue
                if other.y0 < floor:
                    floor = other.y0
            if token.cy >= floor - body * 0.1:
                score += 9000
        if dx > body * 16:
            score += 2500
        if score < best_score:
            best_score = score
            best = title
    if best is None or best_score > 6500:
        return None
    return best


def _edge_gap(a, b):
    ax0, ay0, ax1, ay1 = a.bbox
    bx0, by0, bx1, by1 = b.bbox
    if ax1 < bx0:
        gx = bx0 - ax1
    elif bx1 < ax0:
        gx = ax0 - bx1
    else:
        gx = 0.0
    if ay1 < by0:
        gy = by0 - ay1
    elif by1 < ay0:
        gy = ay0 - by1
    else:
        gy = 0.0
    return gx, gy


def _absorb(art, other):
    art.body = _clean_paragraph(((art.body or "").rstrip() + "\n" + (other.body or "")).strip())
    if not art.author:
        art.author = other.author or ""
    art.bbox = (
        min(art.bbox[0], other.bbox[0]),
        min(art.bbox[1], other.bbox[1]),
        max(art.bbox[2], other.bbox[2]),
        max(art.bbox[3], other.bbox[3]),
    )
    art.tokens = list(art.tokens or []) + list(other.tokens or [])


def _stitch(articles, body):
    """Attach untitled blocks that sit beside a headline. Match against the original boxes."""
    titled = [a for a in articles if a.title]
    anchors = {id(a): a.bbox for a in titled}
    claimed = set()
    for block in articles:
        if block.title:
            continue
        best = None
        best_gap = 1e9
        bcx = (block.bbox[0] + block.bbox[2]) / 2.0
        for art in titled:
            box = anchors[id(art)]
            y_over = min(box[3], block.bbox[3]) - max(box[1], block.bbox[1])
            shorter = min(box[3] - box[1], block.bbox[3] - block.bbox[1])
            if shorter <= 1 or y_over < shorter * 0.4:
                continue
            gx, _gy = _edge_gap(type("B", (), {"bbox": box})(), block)
            if gx > body * 2.8:
                continue
            acx = (box[0] + box[2]) / 2.0
            if bcx > acx + body:
                continue
            if gx < best_gap:
                best_gap = gx
                best = art
        if best is not None:
            _absorb(best, block)
            claimed.add(id(block))
    kept = []
    for art in articles:
        if id(art) in claimed:
            continue
        if len(_CJK.findall((art.title or "") + (art.body or ""))) >= 8:
            kept.append(art)
    return kept


def _union_bbox(runs):
    if not runs:
        return (0, 0, 0, 0)
    return (
        float(min(r.x0 for r in runs)),
        float(min(r.y0 for r in runs)),
        float(max(r.x1 for r in runs)),
        float(max(r.y1 for r in runs)),
    )


def _column_bands(gray, x0, x1, y0, y1, body):
    """Character-sized ink rows inside one vertical column."""
    h, w = gray.shape[:2]
    x0 = int(_clamp(x0, 0, w - 2))
    x1 = int(_clamp(x1, x0 + 2, w))
    y0 = int(_clamp(y0, 0, h - 2))
    y1 = int(_clamp(y1, y0 + 2, h))
    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return []
    region = cv2.normalize(region, None, 0, 255, cv2.NORM_MINMAX)
    dark = region < 175
    min_ink = max(3, int((x1 - x0) * 0.08))
    rows = dark.sum(axis=1)
    raw = []
    on = False
    start = 0
    min_h = max(8.0, body * 0.42)
    max_h = body * 1.9
    for i, value in enumerate(rows):
        if value >= min_ink and not on:
            on = True
            start = i
        elif value < min_ink and on:
            on = False
            if min_h <= (i - start) <= max_h:
                raw.append((start, i))
    if on and min_h <= (len(rows) - start) <= max_h:
        raw.append((start, len(rows)))
    bands = []
    for top, bottom in raw:
        cols = dark[top:bottom].sum(axis=0)
        xs = np.where(cols > 0)[0]
        if len(xs) < 2:
            continue
        bx0 = x0 + int(xs[0])
        bx1 = x0 + int(xs[-1]) + 1
        bw = bx1 - bx0
        bh = bottom - top
        if bw < body * 0.28 or bw > body * 1.8 or bw > bh * 2.4:
            continue
        bands.append((y0 + top, y0 + bottom, bx0, bx1))
    merged = []
    for band in bands:
        if merged and band[0] - merged[-1][1] <= body * 0.28:
            prev = merged[-1]
            merged[-1] = (prev[0], band[1], min(prev[2], band[2]), max(prev[3], band[3]))
        else:
            merged.append(band)
    return merged


def _leading_stack(bands, body):
    """A byline is two to four glyphs, then a gap, not the start of a paragraph."""
    if len(bands) < 2:
        return []
    group = [bands[0]]
    for nxt in bands[1:]:
        gap = nxt[0] - group[-1][1]
        if gap > body * 2.6:
            break
        group.append(nxt)
        if len(group) == 4:
            break
    if not (2 <= len(group) <= 4):
        return []
    if len(bands) > len(group):
        gap = bands[len(group)][0] - group[-1][1]
        if gap < body * 2.4:
            return []
    return group


def supplement_bylines(img, runs, body):
    """Add the short name that sits under a headline or just to its right.

    Those glyphs are often too faint to survive the main character detector,
    which is why a name like ?? never became a text run.
    """
    if img is None or not len(getattr(img, "shape", [])):
        return
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    height, width = gray.shape[:2]
    titles = []
    for run in runs:
        if run.kind != "v" or run.header or not (2 <= run.n <= 18):
            continue
        big = run.size >= body * 2.0
        long_head = run.n >= 4 and run.size >= body * 1.52
        if big or long_head:
            titles.append(run)
    titles.sort(key=lambda r: -r.cx)
    used = []
    for title in titles:
        windows = (
            (title.x0 - body * 0.15, title.x1 + body * 0.2, title.y1 + body * 0.35, title.y1 + body * 14),
            (title.x1 + body * 0.08, title.x1 + body * 2.0, title.y0 - body * 0.2, title.y1 + body * 3.0),
        )
        chosen = []
        for x0, x1, y0, y1 in windows:
            bands = _column_bands(gray, x0, x1, y0, y1, body)
            stack = _leading_stack(bands, body)
            if stack:
                chosen = stack
                break
        if not chosen:
            continue
        glyph_h = _median([b[1] - b[0] for b in chosen])
        if glyph_h > title.size * 0.88:
            continue
        if any(abs((b[0] + b[1]) / 2.0 - (u[0] + u[1]) / 2.0) < body for b in chosen for u in used):
            continue
        boxes = [(b[2], b[0], b[3], b[1]) for b in chosen]
        run = _run_from_boxes(boxes, "v")
        run.upright = True
        run.byline_for = id(title)
        run.size = _median([b[1] - b[0] for b in chosen])
        runs.append(run)
        used.extend(chosen)
        if run.y1 > height or run.x1 > width:
            continue


def _apply_author_hints(runs):
    by_id = {id(run): run for run in runs}
    for run in runs:
        target_id = getattr(run, "byline_for", 0) or 0
        target = by_id.get(target_id)
        if target is None:
            continue
        cjk = run.cjk_text()
        if 2 <= len(cjk) <= 4 and cjk not in T.AUTHOR_STOP and not any(w in cjk for w in T.AD_WORDS):
            target.author_hint = cjk


def assemble(runs, body, v_rules, h_rules, page_size):
    width, height = page_size
    masthead_runs = []
    usable = []
    for r in runs:
        if not r.text or not r.cjk_text():
            continue
        if getattr(r, "byline_for", 0):
            continue
        if _is_masthead(r, body, width, height):
            r.header = True
            masthead_runs.append(r)
            continue
        usable.append(r)

    header_text = _join_body([r for r in usable if r.header and r.kind == "h"])
    mast = _join_body(masthead_runs)
    body_runs = [r for r in usable if not r.header]
    zones = _zones_from_runs(body_runs, v_rules, body, width)
    articles = []
    for x0, x1, members in zones:
        for y0, y1, group in _bands(members, h_rules, body, x0, x1, height):
            titles = [r for r in group if _is_title_run(r, body)]
            titles = _merge_title_runs(titles, body)
            title_ids = set(id(r) for r in titles)
            # runs that were merged into titles: drop fragments already concatenated
            # _merge_title_runs mutates the first run and drops the rest from the list,
            # but the originals remain in `group`. Remove runs whose boxes were absorbed.
            absorbed = set()
            for t in titles:
                for b in t.boxes:
                    absorbed.add(tuple(b))
            plain = []
            for r in group:
                if id(r) in title_ids:
                    continue
                if r.boxes and all(tuple(b) in absorbed for b in r.boxes):
                    continue
                plain.append(r)
            bylines = _extract_bylines(titles, plain, body) if titles else {}
            if not titles:
                if not plain:
                    continue
                joined = _join_body(plain)
                _author, joined = _peel_author(joined, [], body)
                if len(_CJK.findall(joined)) < 8:
                    continue
                articles.append(
                    Article(
                        title="",
                        author="",
                        body=joined,
                        bbox=_union_bbox(plain),
                        kind=_kind_of("", joined),
                        score=_median([r.score for r in plain], 0.5),
                        tokens=plain,
                    )
                )
                continue
            buckets = {id(t): [] for t in titles}
            leftovers = []
            for run in plain:
                owner = _owning_title(run, titles, body)
                if owner is None:
                    leftovers.append(run)
                else:
                    buckets[id(owner)].append(run)
            for title in titles:
                toks = buckets[id(title)]
                left = [t for t in toks if t.cx < title.cx - max(body, title.size) * 0.2]
                under = [t for t in toks if t not in left and t.y0 >= title.y0 - body * 0.2]
                byline = bylines.get(id(title))
                joined = _join_body(left)
                if under:
                    extra = _join_body(under)
                    if extra:
                        joined = (joined + "\n" + extra).strip() if joined else extra
                author = (getattr(title, "author_hint", "") or "").strip()
                if not author and byline is not None:
                    author = byline.cjk_text()
                if not author:
                    author, joined = _peel_author(joined, left, body, title_size=title.size)
                title_text = _strip_title(title.text)
                if author and author == title_text:
                    author = ""
                if len(_CJK.findall(title_text + joined)) < 4:
                    continue
                block_runs = [title] + ([byline] if byline is not None else []) + toks
                articles.append(
                    Article(
                        title=title_text,
                        author=author,
                        body=joined,
                        bbox=_union_bbox(block_runs),
                        kind=_kind_of(title_text, joined),
                        score=float(title.score or 0.5),
                        tokens=block_runs,
                    )
                )
            lost = [r for r in leftovers if len(r.cjk_text()) >= 2]
            if lost and len(_CJK.findall(_join_body(lost))) >= 10:
                joined = _join_body(lost)
                articles.append(
                    Article(
                        title="",
                        author="",
                        body=joined,
                        bbox=_union_bbox(lost),
                        kind=_kind_of("", joined),
                        score=_median([r.score for r in lost], 0.4),
                        tokens=lost,
                    )
                )
    articles = _stitch(articles, body)
    articles.sort(key=lambda a: (a.bbox[1] // max(body * 3, 1), -a.bbox[2]))
    return articles, _strip_title(mast), _clean_paragraph(header_text)


def guess_dpi(measure_body_px, measure_dpi, page_w_pt, page_h_pt):
    if measure_body_px < 4:
        dpi = 220
    else:
        dpi = int(measure_dpi * (34.0 / measure_body_px))
    dpi = int(_clamp(dpi, 150, 420))
    long_pt = max(page_w_pt, page_h_pt)
    long_px = long_pt * dpi / 72.0
    if long_px > 5400:
        dpi = int(dpi * 5400 / long_px)
    return max(140, dpi)
