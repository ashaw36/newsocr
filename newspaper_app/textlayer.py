# -*- coding: utf-8 -*-
"""Read a PDF text layer when the page already has positioned characters.

News pages and court columns in this collection were extracted once already.
Image OCR then garbles them. The positioned glyphs are the text to keep.
Article cuts follow the usual newspaper practice: a larger headline starts a
piece, and a circle mark starts a short item.
"""

import re

from newspaper_app.layout import (
    Article,
    _CJK,
    _kind_of,
    _median,
    _reading_sort,
    _run_from_boxes,
    assemble,
)
from newspaper_app.segment import segment_glyphs

_MARK = re.compile(r"[\u3007\u25cb\u25ef\u25ce]")
_SECTION = re.compile(
    r"([\u4e00-\u9fff]{2,8}(?:\u7d00\u4e8b|\u7410\u6848|\u8a0a\u6848))[0-9\u4e00\u4e8c\u4e09\u56db]*$"
)
_PUNCT = re.compile(r"[\u3002\uff01\uff1f\uff1b\u3001\uff0c]")
_NOISE = re.compile(r"[\u2605\u2606\u25a1\u25a0\u25cf\u203b]")


def _glyphs(page, img_w, img_h):
    sx = img_w / float(page.rect.width or 1)
    sy = img_h / float(page.rect.height or 1)
    out = []
    data = page.get_text("dict") or {}
    for block in data.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            text = "".join(span.get("text") or "" for span in line.get("spans") or [])
            text = text.replace("\u3000", "").strip()
            if not text:
                continue
            x0, y0, x1, y1 = line["bbox"]
            box = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
            direc = line.get("dir") or (1, 0)
            vertical = abs(direc[0]) < 0.5
            out.append((box, text, vertical))
    return out


def _usable(glyphs):
    cjk = 0
    noise = 0
    for _box, text, _vertical in glyphs:
        cjk += len(_CJK.findall(text))
        noise += len(_NOISE.findall(text))
    if cjk < 220:
        return False
    # A field of star marks means the stored text layer is not the article.
    if noise > max(12, int(cjk * 0.04)):
        return False
    return True


def _clean_glyphs(glyphs):
    """Drop punctuation-only specks when they outnumber real breaks.

    Some extracted pages put a comma or a star between every character.
    Keeping those marks makes the column unreadable. A normal page keeps
    its commas.
    """
    cjk = 0
    punct = 0
    noise = 0
    for _box, text, _vertical in glyphs:
        cjk += len(_CJK.findall(text))
        punct += len(_PUNCT.findall(text))
        noise += len(_NOISE.findall(text))
    if cjk and (punct > cjk * 0.18 or noise > max(8, int(cjk * 0.02))):
        kept = []
        for glyph in glyphs:
            text = glyph[1]
            if _CJK.search(text):
                kept.append(glyph)
        return kept
    return glyphs


def _column_runs(glyphs, body):
    cols = []
    thresh = max(4.0, body * 0.5)
    ordered = sorted(glyphs, key=lambda g: -((g[0][0] + g[0][2]) / 2.0))
    for glyph in ordered:
        box, text, _vertical = glyph
        cx = (box[0] + box[2]) / 2.0
        placed = False
        for col in cols:
            if abs(cx - col["cx"]) <= thresh:
                col["glyphs"].append(glyph)
                col["cx"] = sum((g[0][0] + g[0][2]) / 2.0 for g in col["glyphs"]) / len(col["glyphs"])
                placed = True
                break
        if not placed:
            cols.append({"cx": cx, "glyphs": [glyph]})
    runs = []
    for col in cols:
        glyphs_in_col = sorted(col["glyphs"], key=lambda g: g[0][1])
        group = [glyphs_in_col[0]]
        for glyph in glyphs_in_col[1:]:
            prev = group[-1]
            gap = glyph[0][1] - prev[0][3]
            prev_h = _median([g[0][3] - g[0][1] for g in group])
            gh = glyph[0][3] - glyph[0][1]
            jump = gh > prev_h * 1.48 or (len(group) >= 2 and gh < prev_h * 0.68)
            if gap > max(body * 0.8, prev_h * 0.9) or jump:
                runs.append(_finish_run(group, "v"))
                group = [glyph]
            else:
                group.append(glyph)
        runs.append(_finish_run(group, "v"))
    return [run for run in runs if run is not None]


def _finish_run(group, kind):
    boxes = [g[0] for g in group]
    if kind == "h":
        group = sorted(group, key=lambda g: -g[0][0])
        boxes = [g[0] for g in group]
    text = "".join(g[1] for g in group)
    if not text.strip():
        return None
    run = _run_from_boxes(boxes, kind)
    run.text = text
    run.score = 0.95
    run.size = _median([b[3] - b[1] for b in boxes], run.size)
    return run


def _horizontal_runs(glyphs):
    if not glyphs:
        return []
    glyphs = sorted(glyphs, key=lambda g: ((g[0][1] + g[0][3]) / 2.0, -g[0][0]))
    rows = []
    for glyph in glyphs:
        cy = (glyph[0][1] + glyph[0][3]) / 2.0
        height = max(4.0, glyph[0][3] - glyph[0][1])
        placed = False
        for row in rows:
            if abs(cy - row["cy"]) <= height * 0.6:
                row["glyphs"].append(glyph)
                row["cy"] = sum((g[0][1] + g[0][3]) / 2.0 for g in row["glyphs"]) / len(row["glyphs"])
                placed = True
                break
        if not placed:
            rows.append({"cy": cy, "glyphs": [glyph]})
    runs = []
    for row in rows:
        run = _finish_run(row["glyphs"], "h")
        if run is not None:
            runs.append(run)
    return runs


def _body_size(glyphs):
    heights = [box[3] - box[1] for box, _text, vertical in glyphs if vertical and box[3] > box[1]]
    if not heights:
        heights = [box[3] - box[1] for box, _text, _vertical in glyphs if box[3] > box[1]]
    return _median(heights, 12.0)


def _split_marked(text):
    """Turn a court-style column into (title, body) items."""
    pieces = _MARK.split(text or "")
    items = []
    pending = ""
    for piece in pieces:
        piece = (piece or "").strip()
        if not piece:
            continue
        cjk = "".join(_CJK.findall(piece))
        if 2 <= len(cjk) <= 12 and not _PUNCT.search(piece):
            pending = cjk
            continue
        title = pending
        pending = ""
        section = _SECTION.search(piece)
        if section and len(section.group(1)) <= 8 and len(piece) > len(section.group(1)) + 8:
            pending = "".join(_CJK.findall(section.group(1)))
            piece = piece[: section.start()].strip()
        if len(_CJK.findall(piece)) < 8 and not title:
            pending = "".join(_CJK.findall(piece))[:12]
            continue
        items.append((title, piece))
    if pending and items:
        title, body = items[-1]
        items[-1] = (title, (body + pending).strip())
    elif pending:
        items.append((pending, ""))
    return [(title, body) for title, body in items if len(_CJK.findall(title + body)) >= 8]


def _digest_articles(runs, body):
    plain = [run for run in runs if run.cjk_text() and not run.header]
    ordered = _join_order(plain)
    blob = ""
    owned = []
    chunks = []
    for run in ordered:
        start = len(blob)
        blob += run.text or ""
        chunks.append((start, len(blob), run))
    items = _split_marked(blob)
    if len(items) < 2:
        return None
    articles = []
    cursor = 0
    for title, text in items:
        begin = blob.find(text[:12], cursor) if text else cursor
        if begin < 0:
            begin = cursor
        end = begin + max(len(text), 1)
        cursor = end
        used = [run for start, stop, run in chunks if stop > begin and start < end]
        if not used:
            used = [chunks[0][2]] if chunks else []
        articles.append(
            Article(
                title=title,
                author="",
                body=text,
                bbox=_union(used),
                kind=_kind_of(title, text),
                score=0.9,
                tokens=used,
            )
        )
    return articles


def _join_order(runs):
    return _reading_sort(runs)


def _union(runs):
    if not runs:
        return (0, 0, 0, 0)
    return (
        float(min(r.x0 for r in runs)),
        float(min(r.y0 for r in runs)),
        float(max(r.x1 for r in runs)),
        float(max(r.y1 for r in runs)),
    )


def _layout_name(articles, digest):
    titles = [a for a in articles if len(_CJK.findall(a.title or "")) >= 4]
    if digest:
        return "digest"
    if len(titles) >= 3:
        return "news"
    return "essay"


def analyze_text_layer(page, img_w, img_h):
    """Return (articles, masthead, header, layout) or None when the page is a scan."""
    raw = _glyphs(page, img_w, img_h)
    if not _usable(raw):
        return None
    glyphs = _clean_glyphs(raw)
    body = _body_size(glyphs)
    vertical = [g for g in glyphs if g[2]]
    horizontal = [g for g in glyphs if not g[2]]
    # Drop specks that are much smaller than the body type.
    vertical = [g for g in vertical if (g[0][3] - g[0][1]) >= body * 0.45]
    runs = _column_runs(vertical, body) + _horizontal_runs(horizontal)
    if not runs:
        return None
    marker_count = len(_MARK.findall("".join(run.text or "" for run in runs)))
    headline_count = sum(1 for run in runs if run.size >= body * 1.55 and len(run.cjk_text()) >= 4)
    digest = marker_count >= 4 and headline_count < 2
    if digest:
        articles = _digest_articles(runs, body)
        if not articles:
            digest = False
    if not digest:
        kept = vertical + horizontal
        articles, mast, header = segment_glyphs(kept, img_w, img_h)
        got = sum(len(_CJK.findall((a.title or "") + (a.body or ""))) for a in articles)
        have = sum(len(_CJK.findall(g[1])) for g in kept)
        if got < max(40, have * 0.45):
            articles, mast, header = assemble(runs, body, [], [], (img_w, img_h))
    else:
        articles_mast = assemble(
            [r for r in runs if r.kind == "h"],
            body,
            [],
            [],
            (img_w, img_h),
        )
        mast = articles_mast[1]
        header = articles_mast[2]
    layout = _layout_name(articles, digest)
    return articles, mast if not digest else mast, header if not digest else header, layout
