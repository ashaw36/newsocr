# -*- coding: utf-8 -*-
"""Split a newspaper page into articles.

Vertical pages are read top to bottom, columns right to left. A headline owns
the text under it and the columns to its left, until the next headline starts.
Horizontal headlines on those pages are read right to left, which is how these
papers set a title such as a magazine name.
"""

import re
from dataclasses import dataclass, field

from newspaper_app import text as T
from newspaper_app.layout import Article, _CJK, _clean_paragraph, _kind_of, _median

_PUNCT = re.compile(r"[\u3002\uff01\uff1f\uff1b\u3001\uff0c,.;:!?]")
_BULLET = re.compile(r"^[\u25a1\u25a0\u25cf\u25cb\u25ef\u25ce\u2022\u00b7\u2605\u2606\u25b2\u53e3\u3007]+")
_BULLET_CHAR = set("\u25a1\u25a0\u25cf\u25cb\u25ef\u25ce\u2022\u00b7\u2605\u2606\u25b2\u53e3\u3007")


@dataclass
class Piece:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float = 0.9
    vertical: bool = True

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

    def font(self):
        if self.vertical and self.h > self.w * 1.8:
            return self.w
        if (not self.vertical) and self.w > self.h * 1.8:
            return self.h
        return max(self.w, self.h)

    def cjk(self):
        return "".join(_CJK.findall(self.text or ""))


@dataclass
class Seg:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    score: float
    vertical: bool
    parts: list = field(default_factory=list)

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2.0

    @property
    def h(self):
        return max(1.0, self.y1 - self.y0)

    @property
    def w(self):
        return max(1.0, self.x1 - self.x0)

    def cjk(self):
        return "".join(_CJK.findall(self.text or ""))


def _cjk_n(text):
    return len(_CJK.findall(text or ""))


# Words that show which way a horizontal headline was printed.
_ORDER_HINTS = (
    "\u96d9\u5341",
    "\u53cc\u5341",
    "\u7279\u865f",
    "\u7279\u53f7",
    "\u81ea\u50b3",
    "\u81ea\u4f20",
    "\u7518\u5730",
    "\u4e0a\u6d77",
    "\u5317\u5e73",
    "\u6c11\u570b",
    "\u6c11\u56fd",
    "\u7533\u5831",
    "\u7533\u62a5",
    "\u9752\u5e74",
    "\u904b\u52d5",
    "\u8fd0\u52a8",
    "\u6210\u7acb",
    "\u7cbe\u795e",
    "\u5ee3\u544a",
    "\u5e7f\u544a",
    "\u9280\u884c",
    "\u94f6\u884c",
    "\u9032\u53e3",
    "\u8fdb\u53e3",
    "\u81ea\u7531",
    "\u5c0f\u8aaa",
    "\u5c0f\u8bf4",
    "\u5148\u751f",
    "\u65b0\u805e",
    "\u65b0\u95fb",
    "\u653f\u5e9c",
    "\u7e3d\u7d71",
    "\u603b\u7edf",
    "\u6703\u8b70",
    "\u4f1a\u8bae",
    "\u5b78\u6821",
    "\u5b66\u6821",
    "\u5152\u7ae5",
    "\u513f\u7ae5",
    "\u4e2d\u570b",
    "\u4e2d\u56fd",
    "\u516c\u5802",
    "\u5584\u5802",
    "\u6350\u6b3e",
    "\u62cd\u8ce3",
    "\u62cd\u5356",
    "\u826f\u53cb",
)


def _order_hits(text):
    return sum(1 for word in _ORDER_HINTS if word in (text or ""))


def _reverse_cjk_line(text):
    """Turn a right-to-left headline around only when that order reads as words."""
    cjk = _cjk_n(text)
    latin = len(re.findall(r"[A-Za-z]", text or ""))
    if cjk < 3 or cjk < latin:
        return text or ""
    flipped = (text or "")[::-1]
    if _order_hits(flipped) > _order_hits(text or ""):
        return flipped
    return text or ""


def _strip_title(text):
    text = _BULLET.sub("", text or "")
    text = re.sub(r"^[\s\u3000]+|[\s\u3000]+$", "", text)
    return text.strip()


def _seg_from_parts(parts, vertical):
    if not parts:
        return None
    text = "".join(p.text or "" for p in parts)
    if not text.strip():
        return None
    return Seg(
        text=text,
        x0=min(p.x0 for p in parts),
        y0=min(p.y0 for p in parts),
        x1=max(p.x1 for p in parts),
        y1=max(p.y1 for p in parts),
        size=_median([p.font() for p in parts]),
        score=_median([p.score for p in parts], 0.8),
        vertical=vertical,
        parts=list(parts),
    )


def _seg_from_piece(piece):
    return Seg(
        text=piece.text or "",
        x0=piece.x0,
        y0=piece.y0,
        x1=piece.x1,
        y1=piece.y1,
        size=piece.font(),
        score=piece.score,
        vertical=piece.vertical,
        parts=[piece],
    )


def _body_size(pieces):
    sizes = sorted(p.font() for p in pieces if p.font() > 1)
    if not sizes:
        return 12.0
    return sizes[int(len(sizes) * 0.62)]


def _vertical_page(pieces):
    vert = 0
    horiz = 0
    for piece in pieces:
        n = _cjk_n(piece.text)
        if piece.vertical:
            vert += max(n, 1)
        else:
            horiz += max(n, 1)
    return vert >= max(8, horiz) * 0.85


def _cluster_columns(pieces, thresh):
    """Group vertical pieces into columns.

    The column anchor stays put. Updating it toward each new piece walks
    into the next column and weaves the two texts together.
    """
    cols = []
    ordered = sorted(pieces, key=lambda p: -p.cx)
    for piece in ordered:
        placed = False
        for col in cols:
            if abs(piece.cx - col["anchor"]) <= thresh:
                col["items"].append(piece)
                placed = True
                break
        if not placed:
            cols.append({"anchor": piece.cx, "cx": piece.cx, "items": [piece]})
    for col in cols:
        col["items"].sort(key=lambda p: p.y0)
        col["cx"] = sum(p.cx for p in col["items"]) / len(col["items"])
    cols.sort(key=lambda c: -c["cx"])
    return cols


def _column_segments(chars, body):
    if not chars:
        return []
    thresh = max(5.0, body * 0.55)
    segments = []
    for col in _cluster_columns(chars, thresh):
        items = col["items"]
        group = [items[0]]
        for piece in items[1:]:
            prev = group[-1]
            gap = piece.y0 - prev.y1
            med = _median([p.font() for p in group])
            title_starts = piece.font() >= body * 1.42 and piece.font() > med * 1.45
            title_ends = med >= body * 1.42 and piece.font() < med * 0.75
            bullet = (piece.text or "") in _BULLET_CHAR and gap > body * 0.25
            big_gap = gap > body * 2.05
            if big_gap or title_starts or title_ends or bullet:
                seg = _seg_from_parts(group, True)
                if seg is not None:
                    segments.append(seg)
                group = [piece]
            else:
                group.append(piece)
        seg = _seg_from_parts(group, True)
        if seg is not None:
            segments.append(seg)
    return segments


def _group_horizontal(pieces, body):
    """Join single glyphs that sit on one horizontal line."""
    glyphs = []
    kept = []
    for piece in pieces:
        if piece.vertical or _cjk_n(piece.text) > 2:
            kept.append(piece)
        else:
            glyphs.append(piece)
    if not glyphs:
        return kept
    glyphs.sort(key=lambda p: (p.cy, p.x0))
    rows = []
    for piece in glyphs:
        placed = False
        for row in rows:
            if abs(piece.cy - row["cy"]) <= max(piece.font(), body) * 0.55:
                row["items"].append(piece)
                row["cy"] = sum(p.cy for p in row["items"]) / len(row["items"])
                placed = True
                break
        if not placed:
            rows.append({"cy": piece.cy, "items": [piece]})
    for row in rows:
        items = sorted(row["items"], key=lambda p: p.x0)
        # A lone glyph stays itself. A real line is joined left to right.
        if len(items) == 1:
            kept.append(items[0])
            continue
        piece = Piece(
            text="".join(p.text or "" for p in items),
            x0=min(p.x0 for p in items),
            y0=min(p.y0 for p in items),
            x1=max(p.x1 for p in items),
            y1=max(p.y1 for p in items),
            score=_median([p.score for p in items], 0.8),
            vertical=False,
        )
        kept.append(piece)
    return kept


def _split_bullet_line(seg):
    """A column line sometimes contains a square mark and then the next title."""
    text = seg.text or ""
    match = re.search(r"([\u25a1\u25a0\u25cb\u25ef\u3007\u53e3])([\u4e00-\u9fff]{4,18})$", text)
    if not match or match.start() < 4:
        return [seg]
    head = text[: match.start()]
    tail = text[match.start() :]
    frac = len(head) / max(1, len(text))
    cut = seg.y0 + seg.h * frac
    upper = Seg(head, seg.x0, seg.y0, seg.x1, cut, seg.size, seg.score, seg.vertical, [])
    lower = Seg(tail, seg.x0, cut, seg.x1, seg.y1, max(seg.size, seg.size), seg.score, seg.vertical, [])
    # The title half is usually the larger type. Keep the caller's size on both;
    # title detection also accepts a leading bullet.
    return [s for s in (upper, lower) if _cjk_n(s.text) >= 1]


def _is_title(seg, body):
    raw = seg.text or ""
    text = _strip_title(raw)
    n = _cjk_n(text)
    if n < 2 or n > 18:
        return False
    latin = len(re.findall(r"[A-Za-z0-9]", text))
    if latin >= 2 and n <= 16:
        return False
    if len(_PUNCT.findall(text)) > max(1, n // 6):
        return False
    if any(word in text for word in T.AD_WORDS) and n <= 4:
        return False
    led = bool(_BULLET.match(raw)) and 4 <= n <= 16 and not _PUNCT.search(text)
    if led and seg.size >= body * 1.05:
        return True
    if seg.size >= body * 2.05 and n >= 2:
        return True
    if seg.size >= body * 1.38 and n >= 4:
        return True
    # A short column in clearly larger type is a vertical headline, not a caption.
    if (
        seg.vertical
        and 4 <= n <= 8
        and seg.size >= body * 1.2
        and seg.h <= body * 14
        and not _PUNCT.search(text)
        and not re.search(r"[A-Za-z0-9\uff08\uff09()]", raw)
    ):
        return True
    if seg.size >= body * 1.48 and n >= 3:
        return True
    return False


def _is_mast(seg, body, page_w, page_h):
    n = _cjk_n(_strip_title(seg.text))
    if n < 2 or n > 6 or seg.size < body * 2.35:
        return False
    width = seg.x1 - seg.x0
    height = seg.y1 - seg.y0
    # A wide headline near the top is the article title, not the paper's name.
    if n >= 4 and width > height * 1.6:
        return False
    if seg.cy < page_h * 0.13 and width > page_w * 0.08 and n <= 2:
        return True
    if seg.cx > page_w * 0.78 and seg.y0 < page_h * 0.42 and seg.size >= body * 2.6 and n <= 2:
        return True
    if seg.cy < page_h * 0.11 and seg.size >= body * 2.6 and n <= 2:
        return True
    return False


def _pitch(segments, body):
    xs = sorted(set(round(s.cx / max(body * 0.4, 1.0)) for s in segments))
    if len(xs) < 3:
        return body * 1.35
    gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    gaps = [g * max(body * 0.4, 1.0) for g in gaps if g > 0]
    if not gaps:
        return body * 1.35
    return max(body * 0.8, _median(gaps))


def _band(title, titles, pitch, body, page_h):
    """Vertical span a headline owns.

    The cut between two headlines is the midpoint of the gap, not the next
    headline's top. Body columns often start a little above a large title.
    """
    top = 0.0
    bottom = float(page_h)
    for other in titles:
        if other is title:
            continue
        if other.cx < title.cx - pitch * 10:
            continue
        if other.cx > title.cx + pitch * 8:
            continue
        if other.y1 <= title.y0 + body:
            boundary = (other.y1 + title.y0) / 2.0
            if boundary > top:
                top = boundary
        elif other.y0 >= title.y1 - body:
            boundary = (title.y1 + other.y0) / 2.0
            if boundary < bottom:
                bottom = boundary
    return top, bottom


def _cut_segments(segments, titles, pitch, body, page_h):
    if not titles:
        return segments
    out = []
    for seg in segments:
        if any(seg is t for t in titles):
            out.append(seg)
            continue
        cuts = []
        for title in titles:
            if seg.cx > title.cx + pitch * 0.8:
                continue
            if title.cx - seg.cx > pitch * 14:
                continue
            top, bottom = _band(title, titles, pitch, body, page_h)
            for edge in (top, bottom, title.y0):
                if seg.y0 + body * 1.1 < edge < seg.y1 - body * 1.1:
                    cuts.append(edge)
        if not cuts:
            out.append(seg)
            continue
        out.extend(_split_at_ys(seg, cuts))
    return [s for s in out if s is not None and _cjk_n(s.text) >= 1]


def _split_at_ys(seg, cuts):
    cuts = sorted(set(int(y) for y in cuts))
    if seg.parts and sum(_cjk_n(p.text) for p in seg.parts) >= _cjk_n(seg.text) * 0.6:
        bounds = [seg.y0] + cuts + [seg.y1 + 1]
        made = []
        for y0, y1 in zip(bounds, bounds[1:]):
            parts = [p for p in seg.parts if y0 <= (p.y0 + p.y1) / 2.0 < y1]
            seg_i = _seg_from_parts(parts, seg.vertical)
            if seg_i is not None:
                made.append(seg_i)
        if made:
            return made
    # Fall back to cutting the string in proportion to the vertical cut.
    made = []
    edges = [seg.y0] + cuts + [seg.y1]
    text = seg.text or ""
    for y0, y1 in zip(edges, edges[1:]):
        if y1 - y0 < 1:
            continue
        a = int(round((y0 - seg.y0) / seg.h * len(text)))
        b = int(round((y1 - seg.y0) / seg.h * len(text)))
        a = max(0, min(len(text), a))
        b = max(a, min(len(text), b))
        chunk = text[a:b]
        if _cjk_n(chunk) < 1:
            continue
        made.append(Seg(chunk, seg.x0, y0, seg.x1, y1, seg.size, seg.score, seg.vertical, []))
    return made


def _lower_shelves(titles, plain, pitch, body):
    """Where a right-hand article continues underneath a neighbor.

    Two headlines that sit side by side share the upper part of the page.
    Columns between them that start below the left headline are the right
    article running on. That shared top edge is the shelf.
    """
    found = []
    for left in titles:
        for right in titles:
            if right.cx <= left.cx + pitch:
                continue
            if right.cx - left.cx > pitch * 12:
                continue
            overlap = min(left.y1, right.y1) - max(left.y0, right.y0)
            if overlap < body * 2:
                continue
            starters = []
            for seg in plain:
                if not (left.cx + pitch * 1.15 < seg.cx < right.cx - pitch * 0.2):
                    continue
                if seg.y0 < left.y1 - body:
                    continue
                starters.append(seg)
            if len(starters) < 2:
                continue
            starters.sort(key=lambda s: s.y0)
            shelf = starters[0].y0
            close = [s for s in starters if s.y0 <= shelf + body * 2.5]
            if len(close) < 2:
                continue
            found.append((min(s.y0 for s in close), right, left))
    return found


def _split_on_shelves(plain, shelves, pitch, body):
    out = []
    for seg in plain:
        cuts = []
        for shelf, right, _left in shelves:
            if seg.cx > right.cx + pitch * 0.45:
                continue
            if right.cx - seg.cx > pitch * 22:
                continue
            if seg.y0 + body * 1.2 < shelf < seg.y1 - body * 1.2:
                cuts.append(shelf)
        if cuts:
            out.extend(_split_at_ys(seg, cuts))
        else:
            out.append(seg)
    return [s for s in out if s is not None and _cjk_n(s.text) >= 1]


def _continues_below(seg, titles, pitch, body):
    """The headline whose own column this piece continues."""
    best = None
    best_gap = 1e9
    for title in titles:
        if abs(seg.cx - title.cx) > max(pitch, title.size) * 0.95:
            continue
        gap = seg.y0 - title.y1
        if gap < -body * 0.4 or gap > body * 14:
            continue
        if gap < best_gap:
            best = title
            best_gap = gap
    return best


def _shelf_owner(seg, shelves, pitch):
    """A piece below the shelf belongs to the article that runs underneath."""
    best = None
    best_dx = 1e9
    for shelf, right, left in shelves:
        if seg.y0 < shelf - pitch * 0.2:
            continue
        dx = right.cx - seg.cx
        if dx < -pitch * 0.6 or dx > pitch * 22:
            continue
        if best is None or dx < best_dx:
            best = right
            best_dx = dx
    return best


def _blocked_by_neighbor(seg, title, titles, body, pitch):
    """A headline does not keep the column directly under it once that column runs beside a lower headline."""
    if seg.y0 <= title.y1 + body * 7:
        return False
    if abs(seg.cx - title.cx) > max(pitch, body) * 1.15:
        return False
    for other in titles:
        if other is title or other.cx <= title.cx + 1:
            continue
        overlap = min(seg.y1, other.y1) - max(seg.y0, other.y0)
        if overlap >= body * 1.5:
            return True
    return False


def _owns(seg, title, titles, pitch, body, page_h):
    if seg is title:
        return False
    wide = (not title.vertical) and title.size >= body * 2.2 and title.w > title.h * 1.5
    if not wide:
        if seg.cx > title.cx + pitch * 0.85:
            return False
        if title.cx - seg.cx > pitch * 12:
            return False
    top, bottom = _band(title, titles, pitch, body, page_h)
    if seg.cy < top or seg.y0 > bottom + body * 0.3:
        return False
    # Text sitting above a headline in that same column belongs to the article above.
    if abs(seg.cx - title.cx) <= pitch * 0.75 and seg.y1 <= title.y0 + body * 0.45:
        return False
    return True


def _author_near(title, pool, pitch, body):
    best = None
    best_dist = 1e9
    for seg in pool:
        cjk = seg.cjk()
        if not (2 <= len(cjk) <= 3):
            continue
        if cjk in T.AUTHOR_STOP or any(word in cjk for word in T.AD_WORDS):
            continue
        if seg.size > title.size * 0.95 or seg.h > body * 4.2:
            continue
        if _PUNCT.search(seg.text or ""):
            continue
        if _body_follows(seg, pool, body):
            continue
        under = abs(seg.cx - title.cx) <= max(pitch, title.size) * 1.6 and -body * 0.2 <= (seg.y0 - title.y1) <= body * 5.5
        above = abs(seg.cx - title.cx) <= max(pitch, title.size) * 1.3 and -body * 0.15 <= (title.y0 - seg.y1) <= body * 2.6
        y_over = min(title.y1, seg.y1) - max(title.y0, seg.y0)
        beside = y_over > 0 and -body * 0.35 <= (seg.x0 - title.x1) <= max(body, title.size) * 3.0
        if not under and not beside and not above:
            continue
        dist = abs(seg.cy - title.cy) + abs(seg.cx - title.cx) * 0.3
        if dist < best_dist:
            best_dist = dist
            best = seg
    return best


def _body_follows(seg, pool, body):
    """A short piece with more of the same column under it is the article, not a byline."""
    if (not seg.vertical) and seg.w > seg.h * 1.4:
        return False
    for other in pool:
        if other is seg:
            continue
        if abs(other.cx - seg.cx) > max(body, seg.w) * 0.85:
            continue
        gap = other.y0 - seg.y1
        if -body * 0.25 <= gap <= body * 1.05 and _cjk_n(other.text) >= 4:
            return True
    return False


def _absorb_short_titles(titles, plain, buckets, body, pitch, used):
    """Join a short headline with the two or three characters sitting under it."""
    for title in list(titles):
        if _cjk_n(_strip_title(title.text)) > 3:
            continue
        best = None
        best_gap = 1e9
        for seg in plain:
            if not seg.vertical:
                continue
            if abs(seg.cx - title.cx) > max(body, pitch) * 0.8:
                continue
            gap = seg.y0 - title.y1
            if not (-body * 0.35 <= gap <= body * 1.35):
                continue
            n = len(seg.cjk())
            if not (1 <= n <= 3):
                continue
            if gap < best_gap:
                best = seg
                best_gap = gap
        if best is None:
            continue
        title.text = (title.text or "") + (best.text or "")
        title.y1 = max(title.y1, best.y1)
        title.x0 = min(title.x0, best.x0)
        title.x1 = max(title.x1, best.x1)
        used.add(id(best))
        for bucket in buckets.values():
            if best in bucket:
                bucket.remove(best)
        plain.remove(best)


def _peel_author(body):
    body = (body or "").strip()
    match = re.match(r"^[\uff08(]([\u4e00-\u9fff\u00b7]{2,8})[\uff09)]", body)
    if match and match.group(1) not in T.AUTHOR_STOP:
        return match.group(1), body[match.end() :].lstrip("\n\uff0c\u3002 ")
    match = re.match(
        r"^([\u4e00-\u9fff\u00b7]{2,3})([\u8457\u4f5c\u8bd1\u8b6f\u64b0])([\u3002\uff0c\uff1a\n]|$)",
        body,
    )
    if match and match.group(1) not in T.AUTHOR_STOP:
        return match.group(1), body[match.end() :].lstrip("\n\uff0c\u3002 ")
    return "", body


def _join_segments(segments, pitch, body):
    """Read vertical columns from the right, each column top to bottom.

    A horizontal article stays left to right, row by row.
    """
    if not segments:
        return ""
    vertical = sum(1 for seg in segments if seg.vertical) >= max(1, len(segments)) * 0.6
    if not vertical:
        ordered = sorted(segments, key=lambda s: (round(s.cy / max(body, 1.0)), s.x0))
        parts = []
        prev = None
        for seg in ordered:
            if prev is not None and abs(seg.cy - prev.cy) > body * 0.8:
                parts.append("\n")
            parts.append(seg.text or "")
            prev = seg
        return _clean_paragraph("".join(parts))
    # Tighter than the article pitch: one pitch often covers two columns.
    thresh = max(5.0, min(body * 0.48, pitch * 0.55))
    parts = []
    for col in _cluster_columns(segments, thresh):
        parts.append("".join(seg.text or "" for seg in col["items"]))
    return _clean_paragraph("".join(parts))


def _union(segments):
    if not segments:
        return (0, 0, 0, 0)
    return (
        float(min(s.x0 for s in segments)),
        float(min(s.y0 for s in segments)),
        float(max(s.x1 for s in segments)),
        float(max(s.y1 for s in segments)),
    )


def _article(title, author, body_segs, pitch, body):
    title_text = _strip_title(title.text) if title is not None else ""
    body = _join_segments(body_segs, pitch, body)
    if not author:
        author, body = _peel_author(body)
    if author and author == title_text:
        author = ""
    if title is not None and _cjk_n(title_text) >= 3:
        if _cjk_n(title_text + body) < 3:
            return None
    elif _cjk_n(body) < 8:
        return None
    block = ([title] if title is not None else []) + list(body_segs)
    return Article(
        title=title_text,
        author=author or "",
        body=body,
        bbox=_union(block),
        kind=_kind_of(title_text, body),
        score=float(title.score if title is not None else _median([s.score for s in body_segs], 0.6)),
    )


def _group_leftovers(segments, pitch, body):
    if not segments:
        return []
    remaining = list(segments)
    groups = []
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        changed = True
        while changed:
            changed = False
            for seg in list(remaining):
                if any(_near(seg, other, pitch, body) for other in group):
                    group.append(seg)
                    remaining.remove(seg)
                    changed = True
        groups.append(group)
    articles = []
    for group in groups:
        if _cjk_n("".join(s.text or "" for s in group)) < 12:
            continue
        art = _article(None, "", group, pitch, body)
        if art is not None:
            articles.append(art)
    return articles


def _near(a, b, pitch, body):
    dx = abs(a.cx - b.cx)
    y_over = min(a.y1, b.y1) - max(a.y0, b.y0)
    if dx <= pitch * 1.4 and y_over > -body * 2.5:
        return True
    gap_y = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    if dx <= pitch * 0.8 and gap_y < body * 3:
        return True
    return False


def _header_text(pieces, page_h, body):
    top = [p for p in pieces if (not p.vertical) and p.cy < page_h * 0.07 and p.font() < body * 1.6]
    if not top:
        return ""
    top.sort(key=lambda p: p.x0)
    return _clean_paragraph("".join(p.text or "" for p in top))


def segment_vertical(pieces, page_w, page_h):
    body = _body_size(pieces)
    pieces = _group_horizontal(pieces, body)
    for piece in pieces:
        if not piece.vertical:
            piece.text = _reverse_cjk_line(piece.text)
    chars = []
    lines = []
    for piece in pieces:
        if piece.vertical and _cjk_n(piece.text) <= 2 and piece.h < body * 3.2:
            chars.append(piece)
        else:
            lines.append(piece)
    segments = _column_segments(chars, body)
    for piece in lines:
        seg = _seg_from_piece(piece)
        segments.extend(_split_bullet_line(seg))
    segments = [s for s in segments if _cjk_n(s.text) >= 1]
    mast_segs = [s for s in segments if _is_mast(s, body, page_w, page_h)]
    mast_ids = set(id(s) for s in mast_segs)
    usable = [s for s in segments if id(s) not in mast_ids]
    titles = [s for s in usable if _is_title(s, body)]
    pitch = _pitch(usable, body)
    plain = [s for s in usable if s not in titles]
    plain = _cut_segments(plain, titles, pitch, body, page_h)
    # A cut can reveal a bullet title that was trapped in a body line.
    revealed = [s for s in plain if _is_title(s, body)]
    if revealed:
        titles = titles + revealed
        plain = [s for s in plain if s not in revealed]
        plain = _cut_segments(plain, titles, pitch, body, page_h)
    shelves = _lower_shelves(titles, plain, pitch, body)
    if shelves:
        plain = _split_on_shelves(plain, shelves, pitch, body)
    used = set()
    buckets = {id(title): [] for title in titles}
    for seg in plain:
        shelf_title = _shelf_owner(seg, shelves, pitch)
        below = _continues_below(seg, titles, pitch, body)
        best = None
        if shelf_title is not None:
            best = shelf_title
        elif below is not None:
            best = below
        else:
            best_dx = 1e9
            for title in titles:
                if not _owns(seg, title, titles, pitch, body, page_h):
                    continue
                if _blocked_by_neighbor(seg, title, titles, body, pitch):
                    continue
                dx = title.cx - seg.cx
                if best is None or dx < best_dx - 0.5:
                    best_dx = dx
                    best = title
        if best is not None:
            buckets[id(best)].append(seg)
    _absorb_short_titles(titles, plain, buckets, body, pitch, used)
    author_of = {}
    taken_author = set()
    claims = []
    for title in titles:
        pool = list(buckets[id(title)])
        seen = set(id(s) for s in pool)
        for seg in plain:
            if id(seg) in seen or not (2 <= len(seg.cjk()) <= 3):
                continue
            if abs(seg.cx - title.cx) > max(pitch, body) * 3.0:
                continue
            if abs(seg.cy - title.cy) > body * 8:
                continue
            pool.append(seg)
            seen.add(id(seg))
        seg = _author_near(title, pool, pitch, body)
        if seg is None or title.size < body * 1.65:
            continue
        dist = abs(seg.cy - title.cy) + abs(seg.cx - title.cx) * 0.3
        claims.append((dist, title, seg))
    claims.sort(key=lambda item: item[0])
    for _dist, title, seg in claims:
        if id(title) in author_of or id(seg) in taken_author:
            continue
        author_of[id(title)] = seg
        taken_author.add(id(seg))
    articles = []
    for title in sorted(titles, key=lambda s: (s.y0, -s.cx)):
        owned = buckets[id(title)]
        author_seg = author_of.get(id(title))
        author = ""
        if author_seg is not None:
            author = author_seg.cjk()
            # A two-character headline with the next glyphs labelled as the
            # author is usually one title that was split, such as ?? + ??.
            if _cjk_n(_strip_title(title.text)) <= 3 and abs(author_seg.cx - title.cx) <= max(pitch, body):
                title.text = (title.text or "") + (author_seg.text or "")
                author = ""
            owned = [s for s in owned if s is not author_seg]
            used.add(id(author_seg))
        for seg in owned:
            used.add(id(seg))
        art = _article(title, author, owned, pitch, body)
        if art is not None:
            articles.append(art)
    leftovers = [s for s in plain if id(s) not in used and _cjk_n(s.text) >= 2]
    articles.extend(_group_leftovers(leftovers, pitch, body))
    articles.sort(key=lambda a: (a.bbox[1] // max(body * 4, 1), -a.bbox[2]))
    mast = _strip_title("".join(s.text or "" for s in sorted(mast_segs, key=lambda s: s.y0)))
    header = _header_text(pieces, page_h, body)
    return articles, mast, header


def segment_horizontal(pieces, page_w, page_h):
    """Modern left-to-right rows: a large line is the title, the next short line the author."""
    body = _body_size(pieces)
    pieces = [p for p in pieces if _cjk_n(p.text) >= 1]
    pieces.sort(key=lambda p: (p.cy, p.x0))
    rows = []
    for piece in pieces:
        placed = False
        for row in rows:
            if abs(piece.cy - row["cy"]) <= max(piece.font(), body) * 0.65:
                row["items"].append(piece)
                row["cy"] = sum(p.cy for p in row["items"]) / len(row["items"])
                placed = True
                break
        if not placed:
            rows.append({"cy": piece.cy, "items": [piece]})
    segs = []
    for row in rows:
        items = sorted(row["items"], key=lambda p: p.x0)
        seg = _seg_from_parts(items, False)
        if seg is not None:
            segs.append(seg)
    titles = [s for s in segs if _is_title(s, body)]
    if not titles:
        text = _join_segments(segs, body * 2, body)
        if _cjk_n(text) < 8:
            return [], "", ""
        only = _article(None, "", segs, body * 2, body)
        return ([only] if only else []), "", ""
    articles = []
    used = set()
    for index, title in enumerate(titles):
        nxt = titles[index + 1] if index + 1 < len(titles) else None
        owned = []
        for seg in segs:
            if seg is title or id(seg) in used:
                continue
            if seg.y0 < title.y0 - body * 0.3:
                continue
            if nxt is not None and seg.y0 >= nxt.y0 - body * 0.2:
                continue
            owned.append(seg)
            used.add(id(seg))
        author = ""
        if owned:
            first = min(owned, key=lambda s: s.y0)
            if 2 <= len(first.cjk()) <= 4 and first.size <= title.size * 0.9 and not _PUNCT.search(first.text or ""):
                author = first.cjk()
                owned = [s for s in owned if s is not first]
        art = _article(title, author, owned, page_w, body)
        if art is not None:
            articles.append(art)
    return articles, "", ""


def segment(pieces, page_w, page_h):
    pieces = [p for p in pieces if (p.text or "").strip() and p.x1 > p.x0 and p.y1 > p.y0]
    if not pieces:
        return [], "", ""
    if _vertical_page(pieces):
        return segment_vertical(pieces, page_w, page_h)
    return segment_horizontal(pieces, page_w, page_h)


def segment_glyphs(glyphs, page_w, page_h):
    pieces = []
    for box, text, vertical in glyphs:
        x0, y0, x1, y1 = box
        pieces.append(Piece(text or "", float(x0), float(y0), float(x1), float(y1), 0.95, bool(vertical)))
    return segment(pieces, page_w, page_h)


def segment_lines(lines, page_w, page_h):
    pieces = []
    for line in lines:
        text = (line.get("text") or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = line["box"]
        vertical = (y1 - y0) > (x1 - x0) * 1.35
        pieces.append(
            Piece(text, float(x0), float(y0), float(x1), float(y1), float(line.get("score") or 0.5), vertical)
        )
    return segment(pieces, page_w, page_h)


def lines_are_vertical(lines):
    vert = 0
    horiz = 0
    for line in lines:
        n = max(1, _cjk_n(line.get("text") or ""))
        x0, y0, x1, y1 = line["box"]
        if (y1 - y0) > (x1 - x0) * 1.35:
            vert += n
        else:
            horiz += n
    return vert >= max(8, horiz) * 0.85


def guess_layout(articles, vertical=True):
    titles = [a for a in articles if _cjk_n(a.title) >= 2]
    bodies = [len(a.body or "") for a in articles]
    median_body = _median(bodies, 0)
    if not vertical:
        return "magazine"
    if len(articles) >= 8 and median_body < 80 and len(titles) >= 3:
        return "ads"
    if len(titles) >= 3:
        return "news"
    return "essay"
