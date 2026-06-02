#!/usr/bin/env python3
"""
PDF structure-tree tag editor.

  uv run --with pikepdf python3 tagtool.py [compito.pdf] [--port 8000]

Opens a local web app that:
  - reads the PDF's REAL structure tree (StructTreeRoot) + computes a bounding
    box for every structure element from its marked content (MCID),
  - lets you reassign the PDF/UA tag (/S) of each element from a dropdown,
  - writes the changes back into the structure tree (/S + RoleMap) and serves
    the corrected PDF for download.

Nothing here depends on compito.json: tags are keyed on the structure tree's
own reading-order index, so the edits land on the exact element you picked.
"""
import sys, json, io, os, argparse, threading, subprocess, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pikepdf

# ---------------------------------------------------------------- geometry ---
def mat_mul(m, n):
    a, b, c, d, e, f = m; A, B, C, D, E, F = n
    return (a*A+b*C, a*B+b*D, c*A+d*C, c*B+d*D, e*A+f*C+E, e*B+f*D+F)

def apply_mat(m, x, y):
    a, b, c, d, e, f = m
    return (a*x+c*y+e, b*x+d*y+f)

def _font_widths(font):
    fc = font.get("/FirstChar")
    fc = int(fc) if fc is not None else 0
    w = {}
    if "/Widths" in font:
        for i, wd in enumerate(font.Widths):
            w[fc + i] = float(wd)
    return w

def page_mcid_data(page):
    """Return {mcid: {'bbox':[x0,y0,x1,y1], 'text':str}} for one page."""
    res = page.get("/Resources", pikepdf.Dictionary())
    fonts = {}
    if "/Font" in res:
        for name, f in res.Font.items():
            fonts[str(name)] = {"w": _font_widths(f),
                                "two_byte": str(f.get("/Subtype")) == "/Type0"}
    data = {}
    def slot(mcid):
        if mcid is None: return None
        d = data.get(mcid)
        if d is None:
            d = data[mcid] = {"bbox": None, "text": ""}
        return d
    def grow(mcid, x, y):
        d = slot(mcid)
        if d is None: return
        b = d["bbox"]
        if b is None: d["bbox"] = [x, y, x, y]
        else:
            b[0]=min(b[0],x); b[1]=min(b[1],y); b[2]=max(b[2],x); b[3]=max(b[3],y)
    def addtext(mcid, s):
        d = slot(mcid)
        if d is not None: d["text"] += s

    ctm_stack, ctm = [], (1,0,0,1,0,0)
    Tm = Tlm = (1,0,0,1,0,0)
    fontsize = 0.0; cur_w = {}; two_byte = False
    char_sp = word_sp = leading = 0.0
    mc_stack, cur = [], None

    for operands, op in pikepdf.parse_content_stream(page):
        o = str(op)
        if o == "q": ctm_stack.append(ctm)
        elif o == "Q":
            if ctm_stack: ctm = ctm_stack.pop()
        elif o == "cm": ctm = mat_mul(tuple(float(x) for x in operands), ctm)
        elif o == "BT": Tm = Tlm = (1,0,0,1,0,0)
        elif o == "Tm": Tm = Tlm = tuple(float(x) for x in operands)
        elif o in ("Td","TD"):
            tx, ty = float(operands[0]), float(operands[1])
            if o == "TD": leading = -ty
            Tlm = mat_mul((1,0,0,1,tx,ty), Tlm); Tm = Tlm
        elif o == "T*": Tlm = mat_mul((1,0,0,1,0,-leading), Tlm); Tm = Tlm
        elif o == "TL": leading = float(operands[0])
        elif o == "Tc": char_sp = float(operands[0])
        elif o == "Tw": word_sp = float(operands[0])
        elif o == "Tf":
            fi = fonts.get(str(operands[0]), {})
            fontsize = float(operands[1])
            cur_w = fi.get("w", {}); two_byte = fi.get("two_byte", False)
        elif o in ("BDC","BMC"):
            mcid = None
            if o == "BDC" and len(operands) >= 2 and isinstance(operands[1], pikepdf.Dictionary):
                if "/MCID" in operands[1]: mcid = int(operands[1].MCID)
            mc_stack.append(mcid if mcid is not None else cur)
            cur = mc_stack[-1]
        elif o == "EMC":
            if mc_stack: mc_stack.pop()
            cur = mc_stack[-1] if mc_stack else None
        elif o == "Do":
            for ux, uy in ((0,0),(1,0),(0,1),(1,1)):
                dx, dy = apply_mat(ctm, ux, uy); grow(cur, dx, dy)
        elif o in ("Tj","TJ","'","\""):
            if o == "'": Tlm = mat_mul((1,0,0,1,0,-leading), Tlm); Tm = Tlm
            elements = operands[0]
            if o == "\"":
                word_sp = float(operands[0]); char_sp = float(operands[1]); elements = operands[2]
            seq = elements if (o == "TJ" and isinstance(elements, pikepdf.Array)) else [elements]
            for el in seq:
                if isinstance(el, (int, float)):
                    Tm = mat_mul((1,0,0,1,-float(el)/1000.0*fontsize,0), Tm); continue
                raw = bytes(el)
                if two_byte:
                    codes = [(raw[i]<<8)|raw[i+1] for i in range(0, len(raw)-1, 2)]
                else:
                    codes = list(raw)
                    try: addtext(cur, raw.decode("cp1252"))
                    except Exception: pass
                for code in codes:
                    w0 = cur_w.get(code, 500.0)/1000.0
                    trm = mat_mul(Tm, ctm)
                    x0, y0 = apply_mat(trm, 0, -0.21*fontsize)
                    x1, y1 = apply_mat(trm, w0*fontsize, 0.79*fontsize)
                    grow(cur, x0, y0); grow(cur, x1, y1)
                    adv = w0*fontsize + char_sp + (word_sp if code == 32 else 0.0)
                    Tm = mat_mul((1,0,0,1,adv,0), Tm)
    return data

# ------------------------------------------------------- structure walking ---
STD_TYPES = {"Document","Part","Art","Sect","Div","BlockQuote","Caption","TOC",
             "TOCI","Index","P","H1","H2","H3","H4","H5","H6","L","LI","Lbl",
             "LBody","Table","TR","TH","TD","THead","TBody","TFoot","Span",
             "Quote","Note","Reference","BibEntry","Figure","Formula","Form",
             "Link","Annot","Ruby","Warichu","Code","NonStruct","Private"}
# NB: "Title" is NOT a standard PDF structure type — Word emits it as a custom
# type and remaps it (Title -> H1) via the StructTreeRoot /RoleMap.

def walk_elements(pdf):
    """Deterministic reading-order walk of every StructElem (depth-first).

    Returns a flat list of dicts in walk order; index in this list is the
    STABLE KEY used to apply edits back. Same for extract and apply because we
    always start from the same on-disk PDF."""
    root = pdf.Root.StructTreeRoot
    pageidx = {p.objgen: i for i, p in enumerate(pdf.pages)}
    out = []
    def walk(elem, depth, parent_tag):
        if not isinstance(elem, pikepdf.Dictionary) or "/S" not in elem:
            return
        idx = len(out)
        rec = {"idx": idx, "tag": str(elem.S).lstrip("/"), "depth": depth,
               "parent": parent_tag, "page": None, "mcids": [], "alt": None,
               "_obj": elem.objgen}
        alt = elem.get("/Alt") or elem.get("/ActualText")
        if alt: rec["alt"] = str(alt)
        pg = elem.get("/Pg")
        if pg is not None and pg.objgen in pageidx: rec["page"] = pageidx[pg.objgen]
        out.append(rec)
        K = elem.get("/K")
        if K is None: return
        for k in (K if isinstance(K, pikepdf.Array) else [K]):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                walk(k, depth+1, rec["tag"])
            elif isinstance(k, int):
                rec["mcids"].append((rec["page"], k))
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/MCR":
                p = k.get("/Pg"); pi = pageidx.get(p.objgen) if p is not None else rec["page"]
                rec["mcids"].append((pi, int(k.MCID)))
    K = root.get("/K")
    for k in (K if isinstance(K, pikepdf.Array) else [K]):
        walk(k, 0, None)
    return out

def resolve_role(tag, rolemap, _seen=None):
    """Follow the RoleMap chain until a standard type (or a dead end)."""
    if _seen is None: _seen = set()
    if tag in STD_TYPES or rolemap is None or tag in _seen:
        return tag
    _seen.add(tag)
    mapped = rolemap.get("/" + tag)
    if mapped is None:
        return tag
    return resolve_role(str(mapped).lstrip("/"), rolemap, _seen)

def build_structure(pdf):
    elems = walk_elements(pdf)
    rolemap = pdf.Root.StructTreeRoot.get("/RoleMap")
    # per-page mcid bbox/text cache
    cache = {}
    def mc(page):
        if page not in cache: cache[page] = page_mcid_data(pdf.pages[page])
        return cache[page]
    # assign own bbox/text from direct mcids
    for e in elems:
        box = None; txt = ""
        for (pg, m) in e["mcids"]:
            if pg is None: continue
            d = mc(pg).get(m)
            if not d or not d["bbox"]: continue
            b = d["bbox"]
            box = b[:] if box is None else [min(box[0],b[0]),min(box[1],b[1]),
                                            max(box[2],b[2]),max(box[3],b[3])]
            txt += d["text"]
        e["_box"] = box
        e["text"] = (e["alt"] or txt or "").strip()
    # containers (no direct mcids): bbox = union of descendant boxes
    for i in range(len(elems)-1, -1, -1):
        e = elems[i]
        if e["_box"] is None:
            d = e["depth"]; b = None
            for j in range(i+1, len(elems)):
                if elems[j]["depth"] <= d: break
                cb = elems[j]["_box"]
                if cb: b = cb[:] if b is None else [min(b[0],cb[0]),min(b[1],cb[1]),
                                                    max(b[2],cb[2]),max(b[3],cb[3])]
            e["_box"] = b
            if e["page"] is None:
                for j in range(i+1, len(elems)):
                    if elems[j]["depth"] <= d: break
                    if elems[j]["page"] is not None: e["page"] = elems[j]["page"]; break
    result = []
    for e in elems:
        if e["tag"] == "Document":   # spans whole doc; not useful to retag/draw
            continue
        eff = resolve_role(e["tag"], rolemap)
        result.append({"idx": e["idx"], "tag": e["tag"], "depth": e["depth"],
                       "parent": e["parent"], "page": e["page"],
                       "eff": eff if eff != e["tag"] else None,
                       "bbox": [round(v,2) for v in e["_box"]] if e["_box"] else None,
                       "text": e["text"][:160]})
    return {"file": CURRENT["name"] or "document.pdf",
            "pages": len(pdf.pages),
            "title": str(pdf.docinfo.get("/Title", "")) if pdf.docinfo else "",
            "author": str(pdf.docinfo.get("/Author", "")) if pdf.docinfo else "",
            "elements": result}

# ------------------------------------------------- current in-memory document ---
CURRENT = {"bytes": None, "name": None}   # the PDF being edited (replaceable via /upload)

def open_current():
    if CURRENT["bytes"] is None:
        raise RuntimeError("nessun PDF caricato")
    return pikepdf.open(io.BytesIO(CURRENT["bytes"]))

def set_current(data, name):
    """Validate an uploaded PDF and make it the working document."""
    try:
        pdf = pikepdf.open(io.BytesIO(data))
    except Exception as e:
        return {"ok": False, "error": f"PDF non valido: {e}"}
    tagged = "/StructTreeRoot" in pdf.Root
    pages = len(pdf.pages)
    pdf.close()
    if not tagged:
        return {"ok": False, "error": "Il PDF non ha uno structure tree (non è taggato): "
                                      "non ci sono tag da modificare."}
    CURRENT["bytes"] = data
    CURRENT["name"] = name or "document.pdf"
    return {"ok": True, "name": CURRENT["name"], "pages": pages, "tagged": tagged}

# ------------------------------------------------------------- apply edits ---
def mark_pdfua(pdf):
    """Idempotently set the PDF/UA-1 prerequisites + the pdfuaid:part marker."""
    root = pdf.Root
    mi = root.get("/MarkInfo")
    if mi is None:
        root.MarkInfo = pikepdf.Dictionary(); mi = root.MarkInfo
    mi.Marked = True
    if not root.get("/Lang"):
        root.Lang = pikepdf.String("it-IT")
    vp = root.get("/ViewerPreferences")
    if vp is None:
        root.ViewerPreferences = pikepdf.Dictionary(); vp = root.ViewerPreferences
    vp.DisplayDocTitle = True
    with pdf.open_metadata() as m:        # update_docinfo syncs Title -> dc:title
        m["pdfuaid:part"] = "1"

def apply_tags(mapping, pdfua=True):
    """mapping: {idx(str|int): new_tag}. Re-walk the working pdf and set /S."""
    pdf = open_current()
    elems = walk_elements(pdf)
    by_idx = {e["idx"]: e for e in elems}
    root = pdf.Root.StructTreeRoot
    rolemap = root.get("/RoleMap")
    changed = 0
    for k, tag in mapping.items():
        idx = int(k); tag = str(tag).lstrip("/")
        e = by_idx.get(idx)
        if e is None: continue
        obj = pdf.get_object(e["_obj"])
        if str(obj.S).lstrip("/") == tag:  # no change
            continue
        obj.S = pikepdf.Name("/" + tag)
        if tag not in STD_TYPES:           # map custom type -> Span in RoleMap
            if rolemap is None:
                rolemap = pikepdf.Dictionary(); root.RoleMap = rolemap
            rolemap[pikepdf.Name("/" + tag)] = pikepdf.Name("/Span")
        changed += 1
    if pdfua:
        mark_pdfua(pdf)
    buf = io.BytesIO()
    pdf.save(buf)
    pdf.close()
    return buf.getvalue(), changed

# ------------------------------------------------------------------ server ---
def viewer_html():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer.html"),
              "rb") as f:
        return f.read()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)
    def _json(self, code, obj): self._send(code, "application/json", json.dumps(obj).encode())

    def do_GET(self):
        if self.path in ("/", "/index.html", "/viewer.html"):
            self._send(200, "text/html; charset=utf-8", viewer_html())
        elif self.path.startswith("/structure.json"):
            if CURRENT["bytes"] is None:
                self._json(404, {"error": "nessun PDF caricato"}); return
            pdf = open_current()
            body = json.dumps(build_structure(pdf)).encode()
            pdf.close()
            self._send(200, "application/json", body)
        elif self.path.startswith("/document.pdf"):
            if CURRENT["bytes"] is None: self._send(404, "text/plain", b"no pdf"); return
            self._send(200, "application/pdf", CURRENT["bytes"])
        else:
            self._send(404, "text/plain", b"not found")

    def _read_body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_POST(self):
        if self.path == "/upload":
            name = self.headers.get("X-Filename", "document.pdf")
            info = set_current(self._read_body(), name)
            self._json(200 if info.get("ok") else 400, info)
        elif self.path == "/apply":
            if CURRENT["bytes"] is None:
                self._json(404, {"error": "nessun PDF caricato"}); return
            payload = json.loads(self._read_body() or b"{}")
            mapping = payload.get("tags", payload if "tags" not in payload else {})
            pdfua = bool(payload.get("pdfua", True))
            pdf_bytes, changed = apply_tags(mapping, pdfua)
            base = os.path.splitext(CURRENT["name"] or "document.pdf")[0]
            out = base + (".ua" if pdfua else "") + ".tagged.pdf"
            self._send(200, "application/pdf", pdf_bytes,
                       {"Content-Disposition": f'attachment; filename="{out}"',
                        "X-Tags-Changed": str(changed), "X-PDFUA": "1" if pdfua else "0"})
        else:
            self._send(404, "text/plain", b"not found")

def open_browser(url):
    """Best-effort: apri il browser di sistema (anche da WSL). Ignora i fallimenti."""
    try:
        if shutil.which("wslview"):                       # WSL: apre il browser Windows
            subprocess.Popen(["wslview", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("xdg-open"):                    # Linux desktop
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.path.exists("/mnt/c/Windows/explorer.exe"):  # WSL senza wslview
            subprocess.Popen(["/mnt/c/Windows/explorer.exe", url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            import webbrowser; webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    try: sys.stdout.reconfigure(line_buffering=True)   # mostra subito l'URL anche se rediretto
    except Exception: pass
    ap = argparse.ArgumentParser(description="Editor web dei tag di struttura PDF/UA.")
    ap.add_argument("pdf", nargs="?", default=None, help="PDF iniziale (opzionale)")
    ap.add_argument("--port", type=int, default=0,
                    help="porta (0 = sceglie automaticamente una libera, default)")
    ap.add_argument("--no-open", action="store_true", help="non aprire il browser")
    a = ap.parse_args()

    if a.pdf:
        path = os.path.abspath(a.pdf)
        if os.path.exists(path):
            with open(path, "rb") as f:
                info = set_current(f.read(), os.path.basename(path))
            print(f"  PDF iniziale: {path}" + ("" if info.get("ok") else f"  [{info.get('error')}]"))
        else:
            print(f"  PDF non trovato: {path} — si parte vuoti.")
    else:
        print("  Nessun PDF iniziale — caricane uno dalla pagina.")

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    except OSError:                                       # porta occupata -> libera scelta dall'OS
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    url = f"http://localhost:{port}/"
    print(f"\n  Tag editor su  {url}")
    print("  Ctrl-C per fermare.\n")
    if not a.no_open:
        threading.Timer(0.6, open_browser, args=(url,)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\n  fermato.")
