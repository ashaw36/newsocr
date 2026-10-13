# -*- coding: utf-8 -*-
"""Local review server."""

import json
import os
import queue
import re
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from newspaper_app import text as T
from newspaper_app.pipeline import (
    export_text,
    list_library,
    process_file,
    slug_for,
    workspace_root,
)
from newspaper_app.ui import render_page

ROOT = workspace_root()
OUT = os.path.join(ROOT, "output")
INBOX = os.path.join(ROOT, "inbox")
JOBS = {}
JOB_QUEUE = queue.Queue()
_SEQ = 0
_SEQ_LOCK = threading.Lock()


def _inside(root, path):
    root = os.path.abspath(root)
    path = os.path.abspath(path)
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def _result_paths(rel):
    full = os.path.abspath(os.path.join(ROOT, rel))
    if not _inside(ROOT, full):
        raise ValueError("bad path")
    slug = slug_for(ROOT, full)
    folder = os.path.join(OUT, slug)
    return full, folder, os.path.join(folder, "result.json")


def _read_result(rel):
    _full, _folder, path = _result_paths(rel)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_result(rel, data):
    _full, folder, path = _result_paths(rel)
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _enqueue(rels):
    global _SEQ
    with _SEQ_LOCK:
        _SEQ += 1
        job_id = "job%d" % _SEQ
    JOBS[job_id] = {
        "id": job_id,
        "status": "queued",
        "message": T.UI["working"],
        "rel": rels[0] if rels else "",
        "rels": rels,
    }
    JOB_QUEUE.put(job_id)
    return job_id


def _worker():
    while True:
        job_id = JOB_QUEUE.get()
        job = JOBS.get(job_id)
        if not job:
            continue
        job["status"] = "running"
        rels = job["rels"]
        try:
            total = len(rels)
            for i, rel in enumerate(rels):
                full, folder, _path = _result_paths(rel)

                def on_progress(frac, page_no, page_total, idx=i, rel=rel):
                    job["message"] = "%s %d/%d  %s %s/%s" % (
                        T.UI["working"],
                        idx + 1,
                        total,
                        os.path.basename(rel),
                        page_no,
                        page_total,
                    )
                    job["rel"] = rel

                print(job["message"], flush=True)
                result = process_file(full, folder, on_progress=on_progress)
                result["rel"] = rel
                _write_result(rel, result)
                job["rel"] = rel
            job["status"] = "done"
            job["message"] = T.UI["done"]
            print(job["message"], flush=True)
        except Exception:
            err = traceback.format_exc()
            print(err, flush=True)
            job["status"] = "error"
            job["message"] = T.UI["failed"] + "\n" + err[-500:]


def _start_worker():
    thread = threading.Thread(target=_worker, name="ocr-worker", daemon=True)
    thread.start()


class AppHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type="text/plain; charset=utf-8", filename=None):
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(filename))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _query(self):
        parsed = urllib.parse.urlparse(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self):
        path, qs = self._query()
        try:
            if path == "/" or path == "/index.html":
                self._send(200, render_page(T.UI), "text/html; charset=utf-8")
                return
            if path == "/api/library":
                items = []
                for item in list_library(ROOT):
                    rel = item["rel"].replace("\\", "/")
                    _full, _folder, result_path = _result_paths(rel)
                    items.append(
                        {
                            "rel": rel,
                            "name": item["name"],
                            "file": item["file"],
                            "done": os.path.isfile(result_path),
                        }
                    )
                self._json(200, items)
                return
            if path == "/api/result":
                rel = (qs.get("rel") or [""])[0]
                data = _read_result(rel)
                if not data:
                    self._json(404, {"error": "missing"})
                    return
                self._json(200, data)
                return
            if path == "/api/job":
                job_id = (qs.get("id") or [""])[0]
                job = JOBS.get(job_id)
                if not job:
                    self._json(404, {"error": "missing"})
                    return
                self._json(
                    200,
                    {
                        "id": job["id"],
                        "status": job["status"],
                        "message": job["message"],
                        "rel": job.get("rel") or "",
                    },
                )
                return
            if path == "/api/page":
                rel = (qs.get("rel") or [""])[0]
                page = int((qs.get("page") or ["1"])[0])
                _full, folder, _result = _result_paths(rel)
                img = os.path.join(folder, "page-%d.jpg" % page)
                if not os.path.isfile(img):
                    self._send(404, "missing")
                    return
                with open(img, "rb") as f:
                    self._send(200, f.read(), "image/jpeg")
                return
            if path == "/api/export":
                rel = (qs.get("rel") or [""])[0]
                fmt = (qs.get("fmt") or ["txt"])[0]
                data = _read_result(rel)
                if not data:
                    self._json(404, {"error": "missing"})
                    return
                body = export_text(data, fmt=fmt)
                ext = {"md": "md", "json": "json"}.get(fmt, "txt")
                name = (data.get("stem") or "newspaper") + "." + ext
                ctype = "application/json; charset=utf-8" if fmt == "json" else "text/plain; charset=utf-8"
                self._send(200, body, ctype, filename=name)
                return
            self._send(404, "not found")
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def do_POST(self):
        path, _qs = self._query()
        try:
            if path == "/api/process":
                payload = self._read_json()
                if payload.get("all"):
                    rels = [item["rel"].replace("\\", "/") for item in list_library(ROOT)]
                else:
                    rels = [payload.get("rel") or ""]
                rels = [r for r in rels if r]
                if not rels:
                    self._json(400, {"error": "no files"})
                    return
                job_id = _enqueue(rels)
                self._json(200, {"job": job_id})
                return
            if path == "/api/article":
                payload = self._read_json()
                rel = payload.get("rel") or ""
                data = _read_result(rel)
                if not data:
                    self._json(404, {"error": "missing"})
                    return
                for art in data.get("articles") or []:
                    if art.get("id") == payload.get("id"):
                        art["title"] = payload.get("title") or ""
                        art["author"] = payload.get("author") or ""
                        art["body"] = payload.get("body") or ""
                        break
                _write_result(rel, data)
                self._json(200, {"ok": True})
                return
            if path == "/api/merge":
                payload = self._read_json()
                rel = payload.get("rel") or ""
                data = _read_result(rel)
                if not data:
                    self._json(404, {"error": "missing"})
                    return
                arts = data.get("articles") or []
                idx = next((i for i, a in enumerate(arts) if a.get("id") == payload.get("id")), -1)
                if idx > 0:
                    prev, cur = arts[idx - 1], arts[idx]
                    if not prev.get("title"):
                        prev["title"] = cur.get("title") or ""
                    if not prev.get("author"):
                        prev["author"] = cur.get("author") or ""
                    prev["body"] = ((prev.get("body") or "").rstrip() + "\n" + (cur.get("body") or "")).strip()
                    if prev.get("bbox") and cur.get("bbox") and prev.get("page") == cur.get("page"):
                        b0, b1 = prev["bbox"], cur["bbox"]
                        prev["bbox"] = [
                            min(b0[0], b1[0]),
                            min(b0[1], b1[1]),
                            max(b0[2], b1[2]),
                            max(b0[3], b1[3]),
                        ]
                    del arts[idx]
                _write_result(rel, data)
                self._json(200, {"ok": True})
                return
            if path == "/api/delete":
                payload = self._read_json()
                rel = payload.get("rel") or ""
                data = _read_result(rel)
                if not data:
                    self._json(404, {"error": "missing"})
                    return
                data["articles"] = [a for a in data.get("articles") or [] if a.get("id") != payload.get("id")]
                _write_result(rel, data)
                self._json(200, {"ok": True})
                return
            if path == "/api/upload":
                rel = _handle_upload(self)
                self._json(200, {"rel": rel})
                return
            self._send(404, "not found")
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def _handle_upload(handler):
    ctype = handler.headers.get("Content-Type") or ""
    match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", ctype)
    if not match:
        raise RuntimeError("upload boundary missing")
    boundary = (match.group(1) or match.group(2)).strip().encode("utf-8")
    length = int(handler.headers.get("Content-Length") or 0)
    body = handler.rfile.read(length)
    marker = b"--" + boundary
    name = "paper"
    blob = None
    for part in body.split(marker):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        head, _, content = part.partition(b"\r\n\r\n")
        header = head.decode("utf-8", errors="ignore")
        fname = re.search(r'filename="([^"]*)"', header)
        if not fname:
            continue
        raw_name = os.path.basename(fname.group(1))
        if not raw_name:
            continue
        name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff.\-]+", "_", raw_name)
        blob = content
        if blob.endswith(b"\r\n"):
            blob = blob[:-2]
        break
    if blob is None:
        raise RuntimeError("empty upload")
    os.makedirs(INBOX, exist_ok=True)
    dest = os.path.join(INBOX, name)
    base, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(dest):
        dest = "%s_%d%s" % (base, n, ext)
        n += 1
    with open(dest, "wb") as f:
        f.write(blob)
    rel = os.path.relpath(dest, ROOT).replace("\\", "/")
    return rel


def main(port=8765, open_browser=True):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(INBOX, exist_ok=True)
    _start_worker()
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    url = "http://127.0.0.1:%d/" % port
    print(T.APP_NAME)
    print(url)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstop")
    finally:
        server.server_close()
