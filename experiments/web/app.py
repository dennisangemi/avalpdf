#!/usr/bin/env python3
"""avalpdf web — local web UI for the avalpdf accessibility engine.

Run it (self-contained, deps fetched by uv):

    ./serve.sh                 # or: uv run --with pdfix-sdk --with pikepdf \
                               #          --with rich --with requests python3 app.py

It starts a small stdlib HTTP server that:
  - serves the single-page UI (static/),
  - exposes POST /api/analyze : receives PDF bytes, runs the REAL avalpdf
    engine (all 14 validators) and, in addition, extracts the structure tree
    with a bounding box for every element so the browser can draw the problems
    on top of the pdf.js render.

The PDF never leaves this machine and is not stored on disk by the server: the
browser keeps the file for rendering, the bytes are only held in memory for the
duration of one analysis request.
"""
import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
# Make the in-repo avalpdf package importable without installing it.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from avalpdf.converter import pdf_to_json                          # noqa: E402
from avalpdf.extractor import extract_content, create_simplified_json  # noqa: E402
from avalpdf.validator import AccessibilityValidator               # noqa: E402

import bbox as bboxmod                                             # noqa: E402

# --------------------------------------------------------------- categories ---
# Maps each avalpdf detailed-score key to a human label (IT) + thematic group +
# weight (taken from the validator) so the UI can rank and explain categories.
CATEGORY_META = {
    "tagging":          {"label": "Documento taggato",      "group": "Base",         "weight": 35},
    "title":            {"label": "Titolo del documento",   "group": "Base",         "weight": 20},
    "language":         {"label": "Lingua dichiarata",      "group": "Base",         "weight": 20},
    "headings":         {"label": "Struttura dei titoli",   "group": "Struttura",    "weight": 5},
    "alt_text":         {"label": "Testo alternativo",      "group": "Contenuti",    "weight": 4},
    "figures":          {"label": "Immagini",               "group": "Contenuti",    "weight": 4},
    "tables":           {"label": "Tabelle",                "group": "Struttura",    "weight": 4},
    "lists":            {"label": "Elenchi",                "group": "Struttura",    "weight": 4},
    "consecutive_lists":{"label": "Elenchi consecutivi",    "group": "Struttura",    "weight": 2},
    "empty_elements":   {"label": "Elementi vuoti",         "group": "Contenuti",    "weight": 1},
    "underlining":      {"label": "Sottolineature finte",   "group": "Formattazione","weight": 1},
    "spacing":          {"label": "Maiuscole spaziate",     "group": "Formattazione","weight": 1},
    "italian_accents":  {"label": "Accenti italiani",       "group": "Formattazione","weight": 2},
    "extra_spaces":     {"label": "Spazi superflui",        "group": "Formattazione","weight": 0.5},
    "links":            {"label": "Collegamenti",           "group": "Contenuti",    "weight": 0.5},
}

# Keyword -> category. First match wins; order matters (specific before generic).
_CLASSIFY_RULES = [
    ("not tagged", "tagging"),
    ("tagged", "tagging"),
    ("title", "title"),
    ("language", "language"),
    ("alt text", "alt_text"),
    ("alternative text", "alt_text"),
    ("heading", "headings"),
    ("h1", "headings"),
    ("hierarchy", "headings"),
    ("table", "tables"),
    ("list", "lists"),
    ("underscore", "underlining"),
    ("underlining", "underlining"),
    ("spaced capital", "spacing"),
    ("accent", "italian_accents"),
    ("apostrophe", "italian_accents"),
    ("extra space", "extra_spaces"),
    ("consecutive space", "extra_spaces"),
    ("link", "links"),
    ("url", "links"),
    ("figure", "figures"),
    ("image", "figures"),
    ("empty", "empty_elements"),
]


def classify_message(msg):
    low = msg.lower()
    for kw, cat in _CLASSIFY_RULES:
        if kw in low:
            return cat
    return "other"


def annotate(messages, severity):
    """Turn a list of avalpdf message strings into structured records."""
    out = []
    for m in messages:
        cat = classify_message(m)
        meta = CATEGORY_META.get(cat, {"label": "Altro", "group": "Altro"})
        out.append({
            "text": m,
            "severity": severity,
            "category": cat,
            "categoryLabel": meta["label"],
            "group": meta["group"],
        })
    return out


def run_analysis(pdf_bytes, expected_lang=None):
    """Run the full avalpdf engine + structure/bbox extraction on PDF bytes."""
    # avalpdf's converter opens a path, so spill the bytes to a temp file.
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp.write(pdf_bytes)
        tmp.flush()
        tmp.close()

        pdf_json = pdf_to_json(tmp.name)
        if "StructTreeRoot" in pdf_json:
            results = extract_content(pdf_json["StructTreeRoot"])
        else:
            results = []
        simplified = create_simplified_json(pdf_json, results)

        v = AccessibilityValidator(expected_lang=expected_lang)
        content = simplified.get("content", [])
        meta = simplified.get("metadata", {})
        v.validate_metadata(meta)
        v.validate_empty_elements(content)
        v.validate_figures(content)
        v.validate_heading_structure(content)
        v.validate_tables(content)
        v.validate_possible_unordered_lists(content)
        v.validate_possible_ordered_lists(content)
        v.validate_misused_unordered_lists(content)
        v.validate_consecutive_lists(content)
        v.validate_excessive_underscores(content)
        v.validate_spaced_capitals(content)
        v.validate_extra_spaces(content)
        v.validate_links(content)
        v.validate_italian_accents(content)

        report = v.generate_json_report()["validation_results"]
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    # Structure + bounding boxes (independent, read-only).
    try:
        structure = bboxmod.build_structure(pdf_bytes)
    except Exception as e:  # never let bbox extraction break the report
        structure = {"tagged": meta.get("tagged") == "true", "pages": [], "elements": [],
                     "error": str(e)}

    issues = annotate(report.get("issues", []), "issue")
    warnings = annotate(report.get("warnings", []), "warning")
    successes = annotate(report.get("successes", []), "success")

    score = report.get("weighted_score", 0)
    detailed = report.get("detailed_scores", {})
    categories = []
    for key, m in CATEGORY_META.items():
        if key in detailed:
            categories.append({
                "key": key,
                "label": m["label"],
                "group": m["group"],
                "weight": m["weight"],
                "score": detailed[key],
            })

    return {
        "metadata": meta,
        "score": score,
        "categories": categories,
        "counts": {
            "issues": len(issues),
            "warnings": len(warnings),
            "successes": len(successes),
        },
        "issues": issues,
        "warnings": warnings,
        "successes": successes,
        "structure": structure,
    }


# ------------------------------------------------------------------ server ---
class Handler(BaseHTTPRequestHandler):
    server_version = "avalpdf-web/1.0"

    def log_message(self, fmt, *args):  # quieter logging
        sys.stderr.write("· %s\n" % (fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, val in extra.items():
                self.send_header(k, val)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(HERE, "static", rel))
        static_root = os.path.join(HERE, "static")
        if not full.startswith(static_root) or not os.path.isfile(full):
            self._send(404, json.dumps({"error": "not found"}))
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._serve_static(self.path.split("?", 1)[0])

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/analyze":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self._send(400, json.dumps({"error": "empty body"}))
            return
        body = self.rfile.read(length)
        # Optional ?lang=it query for expected-language validation.
        expected_lang = None
        if "?" in self.path:
            q = self.path.split("?", 1)[1]
            for part in q.split("&"):
                if part.startswith("lang="):
                    val = part[5:].strip()
                    expected_lang = val or None
        try:
            result = run_analysis(body, expected_lang=expected_lang)
        except Exception as e:
            traceback.print_exc()
            self._send(500, json.dumps({"error": str(e)}))
            return
        self._send(200, json.dumps(result, ensure_ascii=False))


def _free_port(preferred=0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", preferred))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    ap = argparse.ArgumentParser(description="avalpdf web UI")
    ap.add_argument("--port", type=int, default=8000, help="port (default 8000, 0 = auto)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = ap.parse_args()

    port = args.port
    try:
        httpd = ThreadingHTTPServer((args.host, port), Handler)
    except OSError:
        port = _free_port(0)
        httpd = ThreadingHTTPServer((args.host, port), Handler)

    url = f"http://{args.host}:{port}/"
    print("\n  avalpdf web  ──────────────────────────────")
    print(f"  ▶  {url}")
    print("  premi CTRL+C per fermare\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  arrivederci 👋")
        httpd.shutdown()


if __name__ == "__main__":
    main()
