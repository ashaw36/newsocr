# -*- coding: utf-8 -*-
import argparse
import json
import os

from newspaper_app.pipeline import export_text, list_library, process_file, slug_for, workspace_root
from newspaper_app.server import main as serve


def _run_index(index, max_pages):
    root = workspace_root()
    items = list_library(root)
    if index < 0 or index >= len(items):
        raise SystemExit("index out of range, library size %d" % len(items))
    item = items[index]
    rel = item["rel"]
    out = os.path.join(root, "output", slug_for(root, item["path"]))
    print("process", rel, flush=True)

    def on_progress(frac, page_no, page_total):
        print("  page %s/%s  %.0f%%" % (page_no, page_total, frac * 100), flush=True)

    result = process_file(item["path"], out, on_progress=on_progress, max_pages=max_pages)
    result["rel"] = rel.replace("\\", "/")
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(export_text(result, fmt="txt"))
    print("saved", out, flush=True)


def main():
    parser = argparse.ArgumentParser(description="newspaper article OCR")
    parser.add_argument("--index", type=int, default=None, help="process library item by index and exit")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.index is not None:
        _run_index(args.index, args.max_pages)
        return
    serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
