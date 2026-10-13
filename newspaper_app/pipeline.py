# -*- coding: utf-8 -*-
"""Render a newspaper file and split it into articles."""

import difflib
import os
import re

import cv2
import numpy as np

from newspaper_app import text as T
from newspaper_app.layout import (
    _CJK,
    _apply_author_hints,
    apply_ocr,
    assemble,
    build_runs,
    crop_slices,
    detect_boxes,
    guess_dpi,
    supplement_bylines,
)
from newspaper_app.ocr_engine import get_engine
from newspaper_app.textlayer import analyze_text_layer

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def workspace_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render_pixmap(pix):
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img.copy()


def render_pdf_page(page, dpi):
    import pymupdf

    mat = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return render_pixmap(pix)


def load_image_file(path):
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("cannot read image")
    return img


def _save_jpeg(path, img, quality=82):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    with open(path, "wb") as f:
        f.write(buf.tobytes())


def _preview(img, max_w=1500):
    h, w = img.shape[:2]
    if w <= max_w:
        return img, 1.0
    scale = max_w / float(w)
    out = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return out, scale


def _ocr_runs(img, runs, engine, on_step=None):
    crops = []
    counts = []
    for run in runs:
        parts = crop_slices(img, run, slice_n=1 if getattr(run, "upright", False) else 4)
        counts.append(len(parts))
        crops.extend(parts)
    rec = []
    step = 36
    total = max(1, len(crops))
    for i in range(0, len(crops), step):
        rec.extend(engine.recognize_batch(crops[i : i + step]))
        if on_step:
            on_step(min(1.0, (i + step) / total))
    if not crops and on_step:
        on_step(1.0)
    per_run = []
    cursor = 0
    for count in counts:
        chunk = rec[cursor : cursor + count]
        cursor += count
        if not chunk:
            per_run.append(("", 0.0))
            continue
        text = "".join(t for t, _s in chunk)
        scores = [s for t, s in chunk if t]
        score = float(sum(scores) / len(scores)) if scores else 0.0
        per_run.append((text, score))
    v_n = sum(r.n for r in runs if r.kind == "v")
    h_n = sum(r.n for r in runs if r.kind == "h")
    rtl = v_n >= max(1, h_n) * 0.75
    apply_ocr(runs, per_run, rtl_horizontal=rtl)
    return rtl


# Traditional forms folded to simplified so a filename can match an OCR title.
_FOLD = str.maketrans(
    "\u9109\u904b\u52d5\u6703\u58be\u570b\u5831\u6771\u4f86\u9019\u8aaa\u66f8\u9577\u9580\u958b\u95dc\u6642\u70ba\u8207\u767c\u7d93\u904e\u9084\u5c0d\u5f9e\u500b\u5011\u5f8c\u9ede\u7121\u96fb\u8eca\u5b78\u9ad4\u5ee3\u83ef\u696d\u7522\u5be6\u969b\u73fe\u898b\u89c0\u8a71\u8a9e\u8acb\u8ad6\u8b70\u8a18\u865f\u7d19\u689d\u5099\u50b3\u50c5\u50f9\u5152\u5167\u5beb\u8ecd\u8fb2\u908a\u9054\u9060\u9069\u9078\u90f5\u9280\u9322\u9435\u554f\u805e\u96dc\u96e3\u96f2\u9748\u9801\u98a8\u98db\u9918\u99ac\u9b1a\u9b25\u9f4a\u9f52\u9f8d\u9f9c\u7d05\u85dd\u5287\u5be9\u64ec\u64da\u5c08\u820a\u9ede",
    "\u4e61\u8fd0\u52a8\u4f1a\u57a6\u56fd\u62a5\u4e1c\u6765\u8fd9\u8bf4\u4e66\u957f\u95e8\u5f00\u5173\u65f6\u4e3a\u4e0e\u53d1\u7ecf\u8fc7\u8fd8\u5bf9\u4ece\u4e2a\u4eec\u540e\u70b9\u65e0\u7535\u8f66\u5b66\u4f53\u5e7f\u534e\u4e1a\u4ea7\u5b9e\u9645\u73b0\u89c1\u89c2\u8bdd\u8bed\u8bf7\u8bba\u8bae\u8bb0\u53f7\u7eb8\u6761\u5907\u4f20\u4ec5\u4ef7\u513f\u5185\u5199\u519b\u519c\u8fb9\u8fbe\u8fdc\u9002\u9009\u90ae\u94f6\u94b1\u94c1\u95ee\u95fb\u6742\u96be\u4e91\u7075\u9875\u98ce\u98de\u4f59\u9a6c\u53d1\u6597\u9f50\u9f7f\u9f99\u9f9f\u7ea2\u827a\u5267\u5ba1\u62df\u636e\u4e13\u65e7\u70b9",
)
# Variants these papers actually print, on top of the usual traditional forms.
_FOLD.update(
    {
        0x9115: 0x4E61,  # ?
        0x7232: 0x4E3A,  # ?
        0x798D: 0x7978,  # ?
        0x654E: 0x6559,  # ?
        0x6FDF: 0x6D4E,  # ?
        0x6B73: 0x5C81,  # ?
        0x842C: 0x4E07,  # ?
        0x7A05: 0x7A0E,  # ?
        0x8AC7: 0x8C08,  # ?
        0x6232: 0x620F,  # ?
        0x95A9: 0x95FD,  # ?
        0x7CB5: 0x7CA4,  # ?
        0x9032: 0x8FDB,  # ?
        0x6A6B: 0x6A2A,  # ?
        0x6FF1: 0x6EE8,  # ?
        0x5713: 0x5706,  # ?
        0x79AE: 0x793C,  # ?
        0x8CE3: 0x5356,  # ?
        0x6B78: 0x5F52,  # ?
        0x7344: 0x72F1,  # ?
        0x8CA1: 0x8D22,  # ?
        0x8CE0: 0x8D54,  # ?
        0x6B3D: 0x6B3E,  # ?
        0x7159: 0x70DF,  # ?
        0x8CED: 0x8D4C,  # ?
        0x7F70: 0x7F5A,  # ?
        0x9370: 0x9515,  # ?
        0x9214: 0x949E,  # ?
        0x5C07: 0x5C06,  # ?
        0x65BC: 0x4E8E,  # ?
        0x5F5A: 0x6C47,  # ?
        0x5F59: 0x6C47,  # ?
        0x7463: 0x7410,  # ?
    }
)


def _norm_name(value):
    raw = "".join(_CJK.findall(value or ""))
    return raw.translate(_FOLD)


def _mark_featured(articles, stem):
    key = _norm_name(stem)
    best_i = -1
    best = 0.0
    if not key:
        return
    probe = key[: min(8, len(key))]
    for i, art in enumerate(articles):
        title = _norm_name(art.title)
        body = _norm_name(art.body)[:320]
        blob = title + body
        score = 0.0
        if title and (title in key or key in title):
            score = 0.95
        elif title:
            score = difflib.SequenceMatcher(None, key, title).ratio()
        if key and key in blob:
            score = max(score, 0.9)
        elif len(probe) >= 4 and probe in blob:
            score = max(score, 0.72)
        else:
            score = max(score, difflib.SequenceMatcher(None, key, blob[:80]).ratio())
        if score > best:
            best = score
            best_i = i
    if best_i >= 0 and best >= 0.45:
        articles[best_i].featured = True
        fav = articles.pop(best_i)
        articles.insert(0, fav)


def _article_dict(art, page, index):
    x0, y0, x1, y1 = art.bbox
    return {
        "id": "p%da%d" % (page, index),
        "page": page,
        "title": art.title or "",
        "author": art.author or "",
        "body": art.body or "",
        "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
        "kind": art.kind,
        "score": round(float(art.score or 0), 3),
        "featured": bool(art.featured),
    }


def _draw_overlay(img, articles):
    vis = img.copy()
    colors = [
        (36, 78, 168),
        (40, 120, 70),
        (40, 90, 170),
        (150, 80, 20),
        (120, 50, 130),
        (30, 110, 140),
    ]
    for i, art in enumerate(articles):
        x0, y0, x1, y1 = [int(v) for v in art.bbox]
        color = colors[i % len(colors)]
        cv2.rectangle(vis, (x0, y0), (x1, y1), color, 3)
        label = str(i + 1)
        cv2.putText(vis, label, (x0 + 4, max(20, y0 + 28)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)
    return vis


def _analyze_by_columns(img, engine, on_step=None):
    runs, v_rules, h_rules, body, page_size = build_runs(img)
    supplement_bylines(img, runs, body)
    _ocr_runs(img, runs, engine, on_step=on_step)
    _apply_author_hints(runs)
    articles, mast, header = assemble(runs, body, v_rules, h_rules, page_size)
    return articles, mast, header, body


def analyze_image(img, engine, on_step=None):
    """Read a page as text lines, then split titles, authors and body.

    The older column-crop reader stays as a fallback when line detection
    finds almost nothing.
    """
    from newspaper_app.segment import guess_layout, lines_are_vertical, segment_lines

    lines = engine.read_page(img, on_step=on_step)
    cjk = sum(len(_CJK.findall(line.get("text") or "")) for line in lines)
    if cjk >= 30:
        articles, mast, header = segment_lines(lines, img.shape[1], img.shape[0])
        kept = sum(len(_CJK.findall((a.title or "") + (a.body or ""))) for a in articles)
        if articles and kept >= cjk * 0.35:
            layout = guess_layout(articles, vertical=lines_are_vertical(lines))
            return articles, mast, header, layout
    articles, mast, header, _body = _analyze_by_columns(img, engine, on_step=on_step)
    return articles, mast, header, "scan"


def process_file(path, out_dir, on_progress=None, max_pages=None):
    """OCR one PDF or image. Writes preview images and returns a result dict."""
    os.makedirs(out_dir, exist_ok=True)
    engine = get_engine()
    ext = os.path.splitext(path)[1].lower()
    stem = os.path.splitext(os.path.basename(path))[0]
    pages_meta = []
    articles = []
    if ext in IMAGE_EXT:
        units = [("image", load_image_file(path))]
    else:
        import pymupdf

        doc = pymupdf.open(path)
        units = []
        count = doc.page_count
        if max_pages:
            count = min(count, max_pages)
        for i in range(count):
            units.append(("pdf", doc[i]))
        # doc must stay open until pages are rendered
        return _process_units(path, stem, units, doc, out_dir, engine, on_progress, close_doc=doc)
    return _process_units(path, stem, units, None, out_dir, engine, on_progress, close_doc=None)


def _process_units(path, stem, units, doc, out_dir, engine, on_progress, close_doc):
    pages_meta = []
    articles = []
    try:
        total = max(1, len(units))
        for index, (kind, obj) in enumerate(units):
            page_no = index + 1

            def page_progress(frac, base=index):
                if on_progress:
                    on_progress((base + frac) / total, page_no, total)

            if on_progress:
                on_progress(index / total, page_no, total)
            if kind == "pdf":
                probe = render_pdf_page(obj, 110)
                _boxes, _v, _h, body_px = detect_boxes(probe)
                dpi = guess_dpi(body_px, 110, obj.rect.width, obj.rect.height)
                long_px = max(obj.rect.width, obj.rect.height) * dpi / 72.0
                if long_px > 2300:
                    dpi = max(140, int(dpi * 2300 / long_px))
                img = render_pdf_page(obj, dpi)
            else:
                img = obj
                dpi = 0
                h, w = img.shape[:2]
                long_side = max(h, w)
                if long_side > 2300:
                    scale = 2300 / float(long_side)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                elif long_side < 1400:
                    scale = 1800 / float(long_side)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
            layer = analyze_text_layer(obj, img.shape[1], img.shape[0]) if kind == "pdf" else None
            if layer is not None:
                found, mast, header, layout = layer
                if on_progress:
                    on_progress((index + 1) / total, page_no, total)
            else:
                found, mast, header, layout = analyze_image(img, engine, on_step=page_progress)
            _mark_featured(found, stem)
            preview, scale = _preview(img)
            preview_name = "page-%d.jpg" % page_no
            _save_jpeg(os.path.join(out_dir, preview_name), preview)
            overlay = _draw_overlay(img, found)
            ov_small, _s = _preview(overlay, max_w=1500)
            _save_jpeg(os.path.join(out_dir, "overlay-%d.jpg" % page_no), ov_small, quality=75)
            for art in found:
                x0, y0, x1, y1 = art.bbox
                art.bbox = (x0 * scale, y0 * scale, x1 * scale, y1 * scale)
            pages_meta.append(
                {
                    "page": page_no,
                    "width": int(preview.shape[1]),
                    "height": int(preview.shape[0]),
                    "image": preview_name,
                    "masthead": mast,
                    "header": header,
                    "dpi": int(dpi),
                    "layout": layout,
                    "layout_label": T.LAYOUT_LABEL.get(layout, ""),
                }
            )
            for i, art in enumerate(found):
                item = _article_dict(art, page_no, len(articles) + i + 1)
                articles.append(item)
    finally:
        if close_doc is not None:
            close_doc.close()
    # renumber ids so they stay unique and stable in this result
    for i, art in enumerate(articles, start=1):
        art["id"] = "a%d" % i
    return {
        "source": path,
        "name": os.path.basename(path),
        "stem": stem,
        "pages": pages_meta,
        "articles": articles,
    }


def export_text(result, fmt="txt"):
    lines = []
    name = result.get("stem") or result.get("name") or ""
    if fmt == "json":
        import json

        payload = {
            "name": result.get("name"),
            "source": result.get("source"),
            "pages": result.get("pages"),
            "articles": [
                {
                    "title": a.get("title") or "",
                    "author": a.get("author") or "",
                    "body": a.get("body") or "",
                    "page": a.get("page"),
                    "kind": a.get("kind"),
                }
                for a in result.get("articles") or []
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    title_l = "\u6807\u9898"
    author_l = "\u4f5c\u8005"
    body_l = "\u6b63\u6587"
    page_l = "\u9875"
    if fmt == "md":
        lines.append("# " + name)
        lines.append("")
        for page in result.get("pages") or []:
            if page.get("masthead"):
                lines.append("*" + page["masthead"] + "*")
                lines.append("")
        for a in result.get("articles") or []:
            lines.append("## " + (a.get("title") or T.UNTITLED))
            lines.append("")
            lines.append("- %s\uff1a%s" % (page_l, a.get("page")))
            if a.get("author"):
                lines.append("- %s\uff1a%s" % (author_l, a.get("author")))
            lines.append("")
            lines.append(a.get("body") or "")
            lines.append("")
        return "\n".join(lines).strip() + "\n"
    lines.append(name)
    lines.append("")
    for a in result.get("articles") or []:
        lines.append("=" * 28)
        lines.append("%s\uff1a%s" % (title_l, a.get("title") or T.UNTITLED))
        lines.append("%s\uff1a%s" % (author_l, a.get("author") or ""))
        lines.append("%s\uff1a%s" % (page_l, a.get("page")))
        if a.get("kind") and a.get("kind") != "article":
            lines.append("\u7c7b\u578b\uff1a%s" % a.get("kind"))
        lines.append("%s\uff1a" % body_l)
        lines.append(a.get("body") or "")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def list_library(root):
    found = []
    for folder_name in ("F", "inbox"):
        folder = os.path.join(root, folder_name)
        if not os.path.isdir(folder):
            continue
        for dirpath, _dirs, files in os.walk(folder):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext == ".pdf" or ext in IMAGE_EXT:
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, root)
                    found.append(
                        {
                            "path": full,
                            "rel": rel,
                            "name": os.path.splitext(name)[0],
                            "file": name,
                        }
                    )
    found.sort(key=lambda item: _natural_key(item["rel"]))
    return found


def _natural_key(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def slug_for(root, path):
    rel = os.path.relpath(path, root)
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", rel).strip("_")
    return slug[:90] or "paper"
