#!/usr/bin/env python3
"""
PDF structure-tree tag editor.

  uv run --with pikepdf --with opendataloader-pdf python3 tagtool.py [compito.pdf] [--port 8000]

Opens a local web app that:
  - reads the PDF's REAL structure tree (StructTreeRoot) + computes a bounding
    box for every structure element from its marked content (MCID),
  - lets you reassign the PDF/UA tag (/S) of each element from a dropdown,
  - writes the changes back into the structure tree (/S + RoleMap) and serves
    the corrected PDF for download.

If you upload a PDF that is NOT tagged (no StructTreeRoot), it is first
auto-tagged on the fly with opendataloader-pdf (a temporary tagged PDF is
generated under the hood and loaded into the editor), so you can review and
correct the proposed tags instead of starting from scratch.

Nothing here depends on compito.json: tags are keyed on the structure tree's
own reading-order index, so the edits land on the exact element you picked.
"""
import sys, json, io, os, re, glob, tempfile, argparse, threading, subprocess, shutil
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

def _parse_tounicode(font):
    """Parse a font's /ToUnicode CMap into {char_code:int -> unicode_str}.

    Subsetted / Type3 fonts encode glyphs as custom codes (1,2,3…); the real
    text lives in this CMap. Without it, decoding raw bytes as cp1252 yields the
    control-character garbage seen for headings like 'Comune di Palermo'."""
    tu = font.get("/ToUnicode")
    if tu is None: return {}
    try:
        text = tu.read_bytes().decode("latin-1", "replace")
    except Exception:
        return {}
    out = {}
    def dec(h):
        try: return bytes.fromhex(h).decode("utf-16-be", "replace")
        except Exception: return ""
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            out[int(src, 16)] = dec(dst)
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        # array form: <start> <end> [ <u1> <u2> ... ] — one dst per code
        def _arr(m):
            start = int(m.group(1), 16)
            for i, h in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", m.group(3))):
                out[start + i] = dec(h)
            return " "
        blk = re.sub(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", _arr, blk, flags=re.S)
        # range form: <start> <end> <dstStart> — dst increments across the range
        for s, e, d in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            start, end, nb, base = int(s, 16), int(e, 16), len(d) // 2, int(d, 16)
            for off in range(end - start + 1):
                try: out[start + off] = (base + off).to_bytes(nb, "big").decode("utf-16-be", "replace")
                except Exception: out[start + off] = ""
    return out

def page_mcid_data(page):
    """Return {mcid: {'bbox':[x0,y0,x1,y1], 'text':str}} for one page."""
    res = page.get("/Resources", pikepdf.Dictionary())
    fonts = {}
    if "/Font" in res:
        for name, f in res.Font.items():
            fonts[str(name)] = {"w": _font_widths(f),
                                "two_byte": str(f.get("/Subtype")) == "/Type0",
                                "tu": _parse_tounicode(f)}
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
    fontsize = 0.0; cur_w = {}; two_byte = False; cur_tu = {}
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
            cur_w = fi.get("w", {}); two_byte = fi.get("two_byte", False); cur_tu = fi.get("tu", {})
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
                for code in codes:
                    # real text comes from /ToUnicode; cp1252 is only a fallback
                    ch = cur_tu.get(code)
                    if ch is None and not two_byte and code >= 32:
                        try: ch = bytes([code]).decode("cp1252")
                        except Exception: ch = ""
                    if ch: addtext(cur, ch)
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

def _read_bbox_attr(elem):
    """Return an explicit Layout /BBox [x0 y0 x1 y1] (PDF coords) if the element
    carries one via /A, else None."""
    A = elem.get("/A")
    if A is None: return None
    for a in (list(A) if isinstance(A, pikepdf.Array) else [A]):
        if isinstance(a, pikepdf.Dictionary) and str(a.get("/O")) == "/Layout" and "/BBox" in a:
            try: return [float(v) for v in a.BBox]
            except Exception: return None
    return None

def walk_elements(pdf):
    """Deterministic reading-order walk of every StructElem (depth-first).

    Returns a flat list of dicts in walk order; index in this list is the
    STABLE KEY used to apply edits back. Same for extract and apply because we
    always start from the same on-disk PDF."""
    root = pdf.Root.StructTreeRoot
    pageidx = {p.objgen: i for i, p in enumerate(pdf.pages)}
    out = []
    def walk(elem, depth, parent_tag, parent_objgen):
        if not isinstance(elem, pikepdf.Dictionary) or "/S" not in elem:
            return
        idx = len(out)
        rec = {"idx": idx, "tag": str(elem.S).lstrip("/"), "depth": depth,
               "parent": parent_tag, "page": None, "mcids": [], "alt": None,
               "bbox_attr": None, "nkids": 0, "_obj": elem.objgen, "_parent": parent_objgen}
        alt = elem.get("/Alt") or elem.get("/ActualText")
        if alt: rec["alt"] = str(alt)
        ab = _read_bbox_attr(elem)
        if ab: rec["bbox_attr"] = ab
        pg = elem.get("/Pg")
        if pg is not None and pg.objgen in pageidx: rec["page"] = pageidx[pg.objgen]
        out.append(rec)
        K = elem.get("/K")
        if K is None: return
        for k in (K if isinstance(K, pikepdf.Array) else [K]):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                rec["nkids"] += 1
                walk(k, depth+1, rec["tag"], elem.objgen)
            elif isinstance(k, int):
                rec["mcids"].append((rec["page"], k))
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/MCR":
                p = k.get("/Pg"); pi = pageidx.get(p.objgen) if p is not None else rec["page"]
                rec["mcids"].append((pi, int(k.MCID)))
    # _parent = None marks a top-level element (its container is StructTreeRoot)
    K = root.get("/K")
    for k in (K if isinstance(K, pikepdf.Array) else [K]):
        walk(k, 0, None, None)
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
    def _merge(box, b):
        return b[:] if box is None else [min(box[0],b[0]),min(box[1],b[1]),
                                         max(box[2],b[2]),max(box[3],b[3])]
    # own per-page boxes/text from direct mcids — a box PER PAGE, never unioned
    # across pages (page coordinate systems differ; a cross-page union would
    # otherwise blow up to the whole page height).
    for e in elems:
        pb = {}; txt = ""        # pb: {page -> bbox} on that page only
        for (pg, m) in e["mcids"]:
            if pg is None: continue
            if e["page"] is None: e["page"] = pg   # leaf w/o /Pg: take page from its MCR
            d = mc(pg).get(m)
            if not d or not d["bbox"]: continue
            pb[pg] = _merge(pb.get(pg), d["bbox"])
            txt += d["text"]
        e["_pb"] = pb
        e["text"] = (e["alt"] or txt or "").strip()
    # containers (no direct mcids): per-page union of descendant per-page boxes
    for i in range(len(elems)-1, -1, -1):
        e = elems[i]
        if not e["_pb"]:
            d = e["depth"]; pb = {}
            for j in range(i+1, len(elems)):
                if elems[j]["depth"] <= d: break
                for pg, cb in elems[j]["_pb"].items():
                    pb[pg] = _merge(pb.get(pg), cb)
            e["_pb"] = pb
            if e["page"] is None and pb:
                e["page"] = min(pb.keys())
    result = []
    for e in elems:
        if e["tag"] == "Document":   # spans whole doc; not useful to retag/draw
            continue
        eff = resolve_role(e["tag"], rolemap)
        if e.get("bbox_attr") and e["page"] is not None:   # explicit /BBox override (single page)
            boxes = [[e["page"], [round(v,2) for v in e["bbox_attr"]]]]
        else:
            boxes = [[pg, [round(v,2) for v in bb]] for pg, bb in sorted(e["_pb"].items())]
        linkable = (e["nkids"] == 0 and eff != "Link" and e["parent"] != "Link"
                    and bool(LINKABLE_RE.search(e["text"] or "")))
        result.append({"idx": e["idx"], "tag": e["tag"], "depth": e["depth"],
                       "parent": e["parent"], "page": e["page"],
                       "eff": eff if eff != e["tag"] else None,
                       "leaf": e["nkids"] == 0,
                       "empty": (not e["text"]) and e["nkids"] == 0,
                       "figure": eff == "Figure" or e["tag"] == "Figure",
                       "linkable": linkable,
                       "alt": e["alt"] or "",
                       "boxes": boxes,                       # one [page, bbox] per page
                       "bbox": boxes[0][1] if boxes else None,
                       "bboxAttr": bool(e.get("bbox_attr")),
                       "text": e["text"][:160]})
    return {"file": CURRENT["name"] or "document.pdf",
            "pages": len(pdf.pages),
            "title": str(pdf.docinfo.get("/Title", "")) if pdf.docinfo else "",
            "author": str(pdf.docinfo.get("/Author", "")) if pdf.docinfo else "",
            "lang": str(pdf.Root.get("/Lang") or ""),
            "autotagged": bool(CURRENT.get("autotagged")),
            "elements": result}

# ------------------------------------------------------- learned rules store ---
# Tiny JSON memory of how the user fixes recurring structures, so the same
# template (e.g. Word's custom "Text body" -> P) can be suggested next time.
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_rules.json")

def load_rules():
    try:
        with open(RULES_PATH, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_rules(rules):
    try:
        with open(RULES_PATH, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=1)
    except Exception: pass

def merge_observations(seen, acted):
    """Accumulate observations across documents. seen: {key: count present};
    acted: [{key, action, text}]. We also remember the DISTINCT texts seen for
    each (key, action): generalized keys (structure-only) only become trustworthy
    once the same action repeats across several different texts -> the system
    learns broader contextual rules the more documents you process, without
    blindly generalizing from a single case."""
    rules = load_rules()
    for key, n in (seen or {}).items():
        e = rules.setdefault(key, {"actions": {}, "seen": 0, "texts": {}})
        e["seen"] += int(n)
    for o in (acted or []):
        key, action = o.get("key"), o.get("action")
        if not key or not action: continue
        e = rules.setdefault(key, {"actions": {}, "seen": 0, "texts": {}})
        e["actions"][action] = e["actions"].get(action, 0) + 1
        txt = (o.get("text") or "")[:80]
        if txt:
            lst = e.setdefault("texts", {}).setdefault(action, [])
            if txt not in lst and len(lst) < 60: lst.append(txt)
    save_rules(rules)
    return rules

# ----------------------------------------------------- auto-tagging (untagged) ---
def autotag_pdf(data):
    """Auto-tag an UNtagged PDF with opendataloader-pdf and return the tagged
    bytes (or raise RuntimeError). We write the upload to a temp file, run the
    layout engine in `tagged-pdf` mode (produces `<stem>_tagged.pdf`), read it
    back, and sanity-check that it now carries a StructTreeRoot. The user then
    reviews/corrects these auto-proposed tags like any other tagged PDF."""
    try:
        import opendataloader_pdf
    except Exception as e:
        raise RuntimeError(
            "PDF non taggato e auto-tagging non disponibile: manca "
            "opendataloader-pdf. Avvia con "
            "`uv run --with pikepdf --with opendataloader-pdf python3 tagtool.py` "
            f"(serve anche una JVM). Dettaglio: {e}")
    with tempfile.TemporaryDirectory(prefix="odl_autotag_") as tmp:
        src = os.path.join(tmp, "input.pdf")
        with open(src, "wb") as f:
            f.write(data)
        try:
            opendataloader_pdf.convert(input_path=src, output_dir=tmp,
                                       format="tagged-pdf", image_output="off", quiet=True)
        except Exception as e:
            raise RuntimeError(f"auto-tagging fallito (opendataloader-pdf): {e}")
        out = os.path.join(tmp, "input_tagged.pdf")
        if not os.path.exists(out):
            cand = [c for c in glob.glob(os.path.join(tmp, "*.pdf"))
                    if os.path.abspath(c) != os.path.abspath(src)]
            if not cand:
                raise RuntimeError("auto-tagging non ha prodotto alcun PDF taggato")
            out = cand[0]
        with open(out, "rb") as f:
            tagged = f.read()
    try:
        p = pikepdf.open(io.BytesIO(tagged))
        ok = "/StructTreeRoot" in p.Root
        p.close()
    except Exception as e:
        raise RuntimeError(f"il PDF auto-taggato non è valido: {e}")
    if not ok:
        raise RuntimeError("auto-tagging non ha generato uno structure tree "
                           "(il PDF è probabilmente scansionato / senza testo: "
                           "servirebbe l'OCR).")
    return tagged

# ------------------------------------------------- current in-memory document ---
# the PDF being edited (replaceable via /upload); "autotagged" flags an upload
# that arrived untagged and was auto-tagged on the fly before loading.
CURRENT = {"bytes": None, "name": None, "autotagged": False}

def open_current():
    if CURRENT["bytes"] is None:
        raise RuntimeError("nessun PDF caricato")
    return pikepdf.open(io.BytesIO(CURRENT["bytes"]))

def set_current(data, name):
    """Validate an uploaded PDF and make it the working document. An untagged
    PDF is auto-tagged first (opendataloader-pdf) so there are tags to review."""
    try:
        pdf = pikepdf.open(io.BytesIO(data))
    except Exception as e:
        return {"ok": False, "error": f"PDF non valido: {e}"}
    tagged = "/StructTreeRoot" in pdf.Root
    pdf.close()
    autotagged = False
    if not tagged:
        try:
            data = autotag_pdf(data)
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}
        autotagged = True
    try:
        pdf = pikepdf.open(io.BytesIO(data))   # reopen (possibly the tagged copy)
        pages = len(pdf.pages)
        pdf.close()
    except Exception as e:
        return {"ok": False, "error": f"PDF non valido: {e}"}
    CURRENT["bytes"] = data
    CURRENT["name"] = name or "document.pdf"
    CURRENT["autotagged"] = autotagged
    return {"ok": True, "name": CURRENT["name"], "pages": pages,
            "tagged": True, "autotagged": autotagged}

# ------------------------------------------------------------- apply edits ---
def mark_pdfua(pdf, lang=None):
    """Idempotently set the PDF/UA-1 structural prerequisites (MarkInfo, Lang,
    DisplayDocTitle). Metadata (pdfuaid, dc:title) is handled by the caller."""
    root = pdf.Root
    mi = root.get("/MarkInfo")
    if mi is None:
        root.MarkInfo = pikepdf.Dictionary(); mi = root.MarkInfo
    mi.Marked = True
    if lang:
        root.Lang = pikepdf.String(lang)
    elif not root.get("/Lang"):
        root.Lang = pikepdf.String("it-IT")
    vp = root.get("/ViewerPreferences")
    if vp is None:
        root.ViewerPreferences = pikepdf.Dictionary(); vp = root.ViewerPreferences
    vp.DisplayDocTitle = True

# ---- structure-tree surgery helpers (used by delete / merge) ----
def _kids(obj):
    """Return /K as a Python list (MCID ints, MCR dicts, child StructElems)."""
    K = obj.get("/K")
    if K is None: return []
    return list(K) if isinstance(K, pikepdf.Array) else [K]

def _numtree_get(node, key):
    """Look up `key` in a PDF number tree (/Nums flat, or /Kids hierarchy)."""
    nums = node.get("/Nums")
    if nums is not None:
        for i in range(0, len(nums), 2):
            if int(nums[i]) == key: return nums[i+1]
        return None
    for kid in (node.get("/Kids") or []):
        lim = kid.get("/Limits")
        if lim is None or int(lim[0]) <= key <= int(lim[1]):
            r = _numtree_get(kid, key)
            if r is not None: return r
    return None

def _ptree_set(pdf, page, mcid, val):
    """Repoint the page's ParentTree slot for `mcid` to `val` (a StructElem) or
    to null (content became an artifact). Keeps MCID->element mapping valid."""
    sp = page.get("/StructParents")
    pt = pdf.Root.StructTreeRoot.get("/ParentTree")
    if sp is None or pt is None: return
    arr = _numtree_get(pt, int(sp))
    if isinstance(arr, pikepdf.Array) and 0 <= mcid < len(arr):
        arr[mcid] = val if val is not None else pikepdf.Object.parse(b"null")

def _artifact_page(pdf, page, mcids):
    """Demote the marked-content sequences whose /MCID is in `mcids` to
    `/Artifact BMC` (dropping the MCID) — the PDF/UA way to remove meaningless
    content from the structure without deleting bytes from the page."""
    res = page.get("/Resources")
    props = res.get("/Properties") if isinstance(res, pikepdf.Dictionary) else None
    out, changed = [], False
    for instr in pikepdf.parse_content_stream(page):
        if str(instr.operator) == "BDC" and len(instr.operands) >= 2:
            d = instr.operands[1]
            if isinstance(d, pikepdf.Name) and props is not None:
                d = props.get(str(d))
            if isinstance(d, pikepdf.Dictionary) and "/MCID" in d and int(d.MCID) in mcids:
                out.append(pikepdf.ContentStreamInstruction(
                    [pikepdf.Name("/Artifact")], pikepdf.Operator("BMC")))
                changed = True
                continue
        out.append(instr)
    if changed:
        page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(out))

def _page_mcids(page):
    """Set of MCIDs that actually appear in a page's content stream."""
    res = page.get("/Resources")
    props = res.get("/Properties") if isinstance(res, pikepdf.Dictionary) else None
    out = set()
    for instr in pikepdf.parse_content_stream(page):
        if str(instr.operator) == "BDC" and len(instr.operands) >= 2:
            d = instr.operands[1]
            if isinstance(d, pikepdf.Name) and props is not None:
                d = props.get(str(d))
            if isinstance(d, pikepdf.Dictionary) and "/MCID" in d:
                out.add(int(d.MCID))
    return out

def rebuild_parent_tree(pdf):
    """Recompute /StructTreeRoot/ParentTree from scratch off the FINAL structure
    tree, so every MCID and tagged object maps to the right StructElem. Run after
    all edits — guarantees the structural parent tree is consistent (ISO 32000-1)
    even after delete / merge / unwrap, which otherwise leave it stale."""
    root = pdf.Root.get("/StructTreeRoot")
    if root is None: return
    pages = list(pdf.pages)
    pageidx = {p.objgen: i for i, p in enumerate(pages)}

    page_owners = {}   # page index -> {mcid: StructElem}
    obj_owners = {}    # tagged-object objgen -> StructElem (annotations via /OBJR)
    def owner_page(elem, mcr=None):
        pg = (mcr.get("/Pg") if mcr is not None else None) or elem.get("/Pg")
        return pageidx.get(pg.objgen) if pg is not None else None
    def walk(elem):
        if not isinstance(elem, pikepdf.Dictionary) or "/S" not in elem: return
        K = elem.get("/K")
        for k in ([] if K is None else (list(K) if isinstance(K, pikepdf.Array) else [K])):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                walk(k)
            elif isinstance(k, int):
                pi = owner_page(elem)
                if pi is not None: page_owners.setdefault(pi, {})[k] = elem
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/MCR":
                pi = owner_page(elem, k)
                if pi is not None: page_owners.setdefault(pi, {})[int(k.MCID)] = elem
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/OBJR":
                o = k.get("/Obj")
                if isinstance(o, pikepdf.Dictionary): obj_owners[o.objgen] = elem
    rk = root.get("/K")
    for k in ([] if rk is None else (list(rk) if isinstance(rk, pikepdf.Array) else [rk])):
        walk(k)

    # next free key, kept disjoint from keys already on pages/annotations
    used = []
    for pg in pages:
        if pg.get("/StructParents") is not None: used.append(int(pg.StructParents))
        for a in (pg.get("/Annots") or []):
            if isinstance(a, pikepdf.Dictionary) and a.get("/StructParent") is not None:
                used.append(int(a.StructParent))
    next_key = (max(used) + 1) if used else 0

    entries = {}   # key -> Array (page) | StructElem (object)
    for i, pg in enumerate(pages):
        owners = page_owners.get(i, {})
        mcids = set(owners) | _page_mcids(pg)
        if not mcids:
            if pg.get("/StructParents") is not None: del pg.StructParents
            continue
        n = max(mcids) + 1
        arr = pikepdf.Array([pikepdf.Object.parse(b"null")] * n)
        for m, elem in owners.items():
            arr[m] = elem
        sp = pg.get("/StructParents")
        if sp is None:
            sp = next_key; next_key += 1; pg.StructParents = sp
        entries[int(sp)] = pdf.make_indirect(arr)
    for objgen, elem in obj_owners.items():
        obj = pdf.get_object(objgen)
        sp = obj.get("/StructParent")
        if sp is None:
            sp = next_key; next_key += 1; obj.StructParent = sp
        entries[int(sp)] = elem

    nums = []
    for key in sorted(entries):
        nums.append(key); nums.append(entries[key])
    root.ParentTree = pdf.make_indirect(pikepdf.Dictionary(Nums=pikepdf.Array(nums)))
    root.ParentTreeNextKey = next_key

def _set_kids(obj, kids):
    if not kids:
        if "/K" in obj: del obj.K
    elif len(kids) == 1:
        obj.K = kids[0]
    else:
        obj.K = pikepdf.Array(kids)

def _remove_child(parent, child_objgen):
    """Drop the indirect StructElem child_objgen from parent's /K."""
    K = parent.get("/K")
    if K is None: return
    if isinstance(K, pikepdf.Array):
        keep = [k for k in K
                if not (getattr(k, "is_indirect", False) and k.objgen == child_objgen)]
        _set_kids(parent, keep)
    elif getattr(K, "is_indirect", False) and K.objgen == child_objgen:
        del parent.K

def _remove_annot(pdf, ann):
    """Remove an annotation object from every page's /Annots array."""
    for pg in pdf.pages:
        annots = pg.get("/Annots")
        if not isinstance(annots, pikepdf.Array): continue
        keep = [a for a in annots
                if not (getattr(a, "is_indirect", False) and a.objgen == ann.objgen)]
        if len(keep) != len(annots):
            if keep: pg.Annots = pikepdf.Array(keep)
            else: del pg.Annots

def _neutralize_link(pdf, elem):
    """Drop the element's OBJR child(ren) that point to Link annotations and
    delete those annotations from the page. Used when a <Link> is retagged to
    something else (or deleted): otherwise the orphan Link annotation fails
    PDF/UA ('link annotation not nested inside a Link structure element')."""
    keep, removed = [], 0
    for k in _kids(elem):
        if isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/OBJR":
            ann = k.get("/Obj")
            if isinstance(ann, pikepdf.Dictionary) and str(ann.get("/Subtype")) == "/Link":
                _remove_annot(pdf, ann); removed += 1; continue
        keep.append(k)
    if removed: _set_kids(elem, keep)
    return removed

def neutralize_orphan_links(pdf):
    """Remove every Link annotation that is NOT nested inside a <Link> structure
    element (and any orphan OBJR that referenced it). Guarantees the PDF/UA rule
    'a link annotation must sit in a Link structure element' can't be violated."""
    root = pdf.Root.get("/StructTreeRoot")
    if root is None: return 0
    rolemap = root.get("/RoleMap")
    keep = set()                  # annotation objgens that are legitimately in a <Link>
    orphan_objr = []              # (containing elem, annotation objgen) to unlink
    def walk(elem):
        if not isinstance(elem, pikepdf.Dictionary) or "/S" not in elem: return
        is_link = resolve_role(str(elem.S).lstrip("/"), rolemap) == "Link"
        K = elem.get("/K")
        for k in ([] if K is None else (list(K) if isinstance(K, pikepdf.Array) else [K])):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                walk(k)
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/OBJR":
                o = k.get("/Obj")
                if isinstance(o, pikepdf.Dictionary) and str(o.get("/Subtype")) == "/Link":
                    (keep.add(o.objgen) if is_link else orphan_objr.append((elem, o.objgen)))
    rk = root.get("/K")
    for k in ([] if rk is None else (list(rk) if isinstance(rk, pikepdf.Array) else [rk])):
        walk(k)
    for elem, anngen in orphan_objr:              # drop the orphan OBJR from its element
        _set_kids(elem, [k for k in _kids(elem)
                         if not (isinstance(k, pikepdf.Dictionary)
                                 and str(k.get("/Type")) == "/OBJR"
                                 and isinstance(k.get("/Obj"), pikepdf.Dictionary)
                                 and k.Obj.objgen == anngen)])
    removed = 0
    for pg in pdf.pages:                          # drop orphan Link annotations from pages
        annots = pg.get("/Annots")
        if not isinstance(annots, pikepdf.Array): continue
        new = [a for a in annots
               if not (isinstance(a, pikepdf.Dictionary) and str(a.get("/Subtype")) == "/Link"
                       and a.objgen not in keep)]
        if len(new) != len(annots):
            removed += len(annots) - len(new)
            if new: pg.Annots = pikepdf.Array(new)
            else: del pg.Annots
    return removed

def _set_alt(elem, text):
    """Set (or clear, if empty) the /Alt alternative text of a StructElem."""
    if text:
        elem.Alt = pikepdf.String(str(text))
    elif "/Alt" in elem:
        del elem.Alt

def _set_bbox_attr(elem, bbox):
    """Write an explicit Layout bounding box: /A << /O /Layout /BBox [...] >>.
    Merges into an existing Layout attribute if present, else appends one."""
    arr = pikepdf.Array([round(float(v), 2) for v in bbox])
    A = elem.get("/A")
    layout = None
    for a in ([] if A is None else (list(A) if isinstance(A, pikepdf.Array) else [A])):
        if isinstance(a, pikepdf.Dictionary) and str(a.get("/O")) == "/Layout":
            layout = a; break
    if layout is not None:
        layout.BBox = arr
    else:
        newl = pikepdf.Dictionary(O=pikepdf.Name("/Layout"), BBox=arr)
        if A is None:               elem.A = newl
        elif isinstance(A, pikepdf.Array): A.append(newl)
        else:                       elem.A = pikepdf.Array([A, newl])

# ---- bookmarks (document outline) + linkable text -> real Link -----------------
LINKABLE_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}|https?://\S+|www\.\S+", re.I)

def _extract_uri(text):
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}", text or "")
    if m: return "mailto:" + m.group(0).rstrip(".,;:)")
    m = re.search(r"https?://\S+", text or "")
    if m: return m.group(0).rstrip(".,;:)")
    m = re.search(r"www\.\S+", text or "")
    if m: return "http://" + m.group(0).rstrip(".,;:)")
    return None

def _elem_textbox(elem, pageidx, page_mc):
    """Aggregate (text, page_index, bbox) over an element's marked content subtree."""
    texts = []; info = {"page": None, "box": None}
    def rec(e, inh):
        epg = e.get("/Pg"); pi = pageidx.get(epg.objgen) if epg is not None else inh
        K = e.get("/K")
        for k in ([] if K is None else (list(K) if isinstance(K, pikepdf.Array) else [K])):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                rec(k, pi); continue
            mcid, mpi = None, pi
            if isinstance(k, int): mcid = k
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/MCR":
                mcid = int(k.MCID); mp = k.get("/Pg"); mpi = pageidx.get(mp.objgen) if mp is not None else pi
            if mcid is None or mpi is None: continue
            d = page_mc(mpi).get(mcid)
            if not d: continue
            if d["text"]: texts.append(d["text"])
            if d["bbox"]:
                if info["page"] is None: info["page"] = mpi
                if mpi == info["page"]:
                    b, cur = d["bbox"], info["box"]
                    info["box"] = b[:] if cur is None else [min(cur[0],b[0]),min(cur[1],b[1]),
                                                            max(cur[2],b[2]),max(cur[3],b[3])]
    epg = elem.get("/Pg")
    rec(elem, pageidx.get(epg.objgen) if epg is not None else None)
    return ("".join(texts).strip(), info["page"], info["box"])

def add_outline(pdf):
    """If the document has headings but no bookmarks, build a /Outlines tree from
    the H1..H6 structure elements (nested by level). Resolves the 'headings
    without bookmarks' quality check."""
    existing = pdf.Root.get("/Outlines")
    if isinstance(existing, pikepdf.Dictionary) and existing.get("/First") is not None:
        return 0                                   # already has bookmarks
    root = pdf.Root.get("/StructTreeRoot")
    if root is None: return 0
    rolemap = root.get("/RoleMap")
    pages = list(pdf.pages)
    pageidx = {p.objgen: i for i, p in enumerate(pages)}
    cache = {}
    def page_mc(i):
        if i not in cache: cache[i] = page_mcid_data(pages[i])
        return cache[i]
    headings = []
    def walk(elem):
        if not isinstance(elem, pikepdf.Dictionary) or "/S" not in elem: return
        m = re.match(r"H([1-6])$", resolve_role(str(elem.S).lstrip("/"), rolemap))
        if m:
            text, page, box = _elem_textbox(elem, pageidx, page_mc)
            if page is not None:
                headings.append((int(m.group(1)), text or "Titolo", page, box[3] if box else None))
        K = elem.get("/K")
        for k in ([] if K is None else (list(K) if isinstance(K, pikepdf.Array) else [K])):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k: walk(k)
    rk = root.get("/K")
    for k in ([] if rk is None else (list(rk) if isinstance(rk, pikepdf.Array) else [rk])):
        walk(k)
    if not headings: return 0
    outlines = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name("/Outlines")))
    nodes = []
    for level, title, page, top in headings:
        it = pikepdf.Dictionary(Title=pikepdf.String((title or "Titolo")[:240]))
        it.Dest = pikepdf.Array([pages[page].obj, pikepdf.Name("/XYZ"),
                                 pikepdf.Object.parse(b"null"),
                                 round(top, 2) if top is not None else pikepdf.Object.parse(b"null"),
                                 pikepdf.Object.parse(b"null")])
        nodes.append((level, pdf.make_indirect(it)))
    parents, stack = [], [(0, outlines)]
    for level, node in nodes:
        while len(stack) > 1 and stack[-1][0] >= level: stack.pop()
        parent = stack[-1][1]; node.Parent = parent; parents.append(parent); stack.append((level, node))
    kidsmap = {}
    for (level, node), parent in zip(nodes, parents):
        kidsmap.setdefault(parent.objgen, []).append(node)
    def link(parent, kids):
        for i, k in enumerate(kids):
            if i > 0: k.Prev = kids[i-1]
            if i < len(kids)-1: k.Next = kids[i+1]
        if kids: parent.First = kids[0]; parent.Last = kids[-1]
        tot = 0
        for k in kids:
            c = link(k, kidsmap.get(k.objgen, []))
            if c: k.Count = c
            tot += 1 + c
        return tot
    outlines.Count = link(outlines, kidsmap.get(outlines.objgen, []))
    pdf.Root.Outlines = outlines
    return len(nodes)

def make_links(pdf, idxs, by_idx, obj_of):
    """Wrap each element's linkable text in a real <Link>: retag to Link, add a
    URI/mailto Link annotation over its bbox + an OBJR. Resolves 'linkable text
    not contained in a Link tag'."""
    pages = list(pdf.pages)
    pageidx = {p.objgen: i for i, p in enumerate(pages)}
    cache = {}
    def page_mc(i):
        if i not in cache: cache[i] = page_mcid_data(pages[i])
        return cache[i]
    made = 0
    for idx in idxs:
        idx = int(idx)
        if idx not in by_idx: continue
        elem = obj_of(idx)
        text, page, box = _elem_textbox(elem, pageidx, page_mc)
        uri = _extract_uri(text)
        if uri is None or page is None or box is None: continue
        elem.S = pikepdf.Name("/Link")
        ann = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name("/Annot"), Subtype=pikepdf.Name("/Link"),
            Rect=pikepdf.Array([round(v, 2) for v in box]),
            Border=pikepdf.Array([0, 0, 0]),
            A=pikepdf.Dictionary(S=pikepdf.Name("/URI"), URI=pikepdf.String(uri))))
        pg = pages[page]
        annots = pg.get("/Annots")
        pg.Annots = pikepdf.Array(list(annots) + [ann]) if isinstance(annots, pikepdf.Array) else pikepdf.Array([ann])
        objr = pikepdf.Dictionary(Type=pikepdf.Name("/OBJR"), Obj=ann, Pg=pg.obj)
        elem.K = pikepdf.Array(_kids(elem) + [objr])
        made += 1
    return made

def fix_lists(pdf):
    """Make <LI> elements valid: ensure each LI's content sits in an <LBody>, and
    group runs of sibling LIs (not already inside an <L>) into a new <L>. Fixes
    'invalid use of an LI structure element' after retagging paragraphs to LI."""
    root = pdf.Root.get("/StructTreeRoot")
    if root is None: return 0
    rolemap = root.get("/RoleMap")
    def role(e):
        return resolve_role(str(e.S).lstrip("/"), rolemap) if isinstance(e, pikepdf.Dictionary) and "/S" in e else None
    def newelem(s, parent, pg=None):
        d = pikepdf.Dictionary(Type=pikepdf.Name("/StructElem"), S=pikepdf.Name("/"+s), P=parent)
        if pg is not None: d.Pg = pg
        return pdf.make_indirect(d)
    fixed = 0
    # PASS 1: wrap each LI's direct content in an LBody (if it has none)
    def pass1(elem):
        nonlocal fixed
        if not isinstance(elem, pikepdf.Dictionary) or "/S" not in elem: return
        if role(elem) == "LI":
            kids = _kids(elem)
            child_roles = [role(k) for k in kids if isinstance(k, pikepdf.Dictionary) and "/S" in k]
            has_body = any(r in ("LBody", "Lbl") for r in child_roles)
            has_mc = any(isinstance(k, int) or (isinstance(k, pikepdf.Dictionary)
                          and str(k.get("/Type")) == "/MCR") for k in kids)
            if has_mc and not has_body:
                body = newelem("LBody", elem, elem.get("/Pg"))
                _set_kids(body, kids)
                for k in kids:
                    if isinstance(k, pikepdf.Dictionary) and "/S" in k: k.P = body
                elem.K = body
                fixed += 1
        for k in _kids(elem):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k: pass1(k)
    # PASS 2: group consecutive sibling LIs (whose parent isn't already an L) into an L
    def pass2(parent):
        nonlocal fixed
        kids = _kids(parent); is_L = role(parent) == "L"
        out, i = [], 0
        while i < len(kids):
            k = kids[i]
            if (not is_L) and isinstance(k, pikepdf.Dictionary) and "/S" in k and role(k) == "LI":
                run = []
                while i < len(kids) and isinstance(kids[i], pikepdf.Dictionary) and "/S" in kids[i] and role(kids[i]) == "LI":
                    run.append(kids[i]); i += 1
                L = newelem("L", parent if isinstance(parent, pikepdf.Dictionary) and "/S" in parent else parent)
                for li in run: li.P = L
                _set_kids(L, run)
                out.append(L); fixed += 1
            else:
                out.append(k); i += 1
        if len(out) != len(kids): _set_kids(parent, out)
        for k in _kids(parent):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k: pass2(k)
    rk = root.get("/K")
    for k in ([] if rk is None else (list(rk) if isinstance(rk, pikepdf.Array) else [rk])):
        pass1(k)
    pass2(root)
    return fixed

def apply_ops(retag=None, delete=None, merge=None, alt=None, bbox=None,
              title=None, lang=None, link=None, pdfua=True):
    """Apply structure-tree edits keyed on walk_elements() reading-order index.

      retag  : {idx: new_tag}            -> set /S (+ RoleMap for custom types)
      delete : [idx, ...]                -> unlink the StructElem from its parent
      merge  : [[keeper, other, ...], ]  -> move others' content into keeper, drop others

    Indices are resolved against a fresh walk of the working PDF, so they match
    exactly what the UI showed; object generations stay stable across mutations.
    """
    pdf = open_current()
    elems = walk_elements(pdf)
    by_idx = {e["idx"]: e for e in elems}
    root = pdf.Root.StructTreeRoot
    rolemap = root.get("/RoleMap")
    pageidx = {p.objgen: i for i, p in enumerate(pdf.pages)}
    def obj_of(i):    return pdf.get_object(by_idx[i]["_obj"])
    def parent_of(i):
        p = by_idx[i]["_parent"]
        return root if p is None else pdf.get_object(p)
    def mcid_page(elem, mcr=None):       # page index that owns a (M)CID
        pg = (mcr.get("/Pg") if mcr is not None else None) or elem.get("/Pg")
        return pageidx.get(pg.objgen) if pg is not None else None

    delete_set = set(int(x) for x in (delete or []))
    counts = {"retag": 0, "deleted": 0, "merged": 0, "alt": 0, "bbox": 0,
              "links": 0, "linked": 0, "outline": 0, "lists": 0}

    # 1) retag survivors
    for k, tag in (retag or {}).items():
        idx = int(k)
        if idx in delete_set or idx not in by_idx: continue
        tag = str(tag).lstrip("/")
        obj = obj_of(idx)
        old = str(obj.S).lstrip("/")
        if old == tag: continue
        obj.S = pikepdf.Name("/" + tag)
        if tag not in STD_TYPES:           # map custom type -> Span in RoleMap
            if rolemap is None:
                rolemap = pikepdf.Dictionary(); root.RoleMap = rolemap
            rolemap[pikepdf.Name("/" + tag)] = pikepdf.Name("/Span")
        counts["retag"] += 1
        # Link -> something else: turn it into plain content by removing the
        # underlying Link annotation (else it's an orphan that fails PDF/UA).
        if resolve_role(old, rolemap) == "Link" and resolve_role(tag, rolemap) != "Link":
            counts["links"] += _neutralize_link(pdf, obj)

    # 1b) alt text (/Alt) and explicit bounding box (/A Layout /BBox) on survivors
    for k, txt in (alt or {}).items():
        idx = int(k)
        if idx in delete_set or idx not in by_idx: continue
        _set_alt(obj_of(idx), txt); counts["alt"] += 1
    for k, bb in (bbox or {}).items():
        idx = int(k)
        if idx in delete_set or idx not in by_idx or not bb: continue
        _set_bbox_attr(obj_of(idx), bb); counts["bbox"] += 1

    # 2) merge: fold each group's tail into its head (keeper), then unlink the tail
    for group in (merge or []):
        g = [int(x) for x in group if int(x) in by_idx]
        if len(g) < 2: continue
        keeper = g[0]; kobj = obj_of(keeper)
        # drop any merged-away element that is itself a direct child of the keeper,
        # so rebuilding /K below can't reintroduce it
        away_gens = {obj_of(o).objgen for o in g[1:]}
        kk = [k for k in _kids(kobj)
              if not (getattr(k, "is_indirect", False) and k.objgen in away_gens)]
        for o in g[1:]:
            oobj = obj_of(o); opg = oobj.get("/Pg")
            for child in _kids(oobj):
                if isinstance(child, int):
                    # bare MCID inherits page from its element -> pin it explicitly
                    mcr = pikepdf.Dictionary(Type=pikepdf.Name("/MCR"), MCID=int(child))
                    if opg is not None: mcr.Pg = opg
                    kk.append(mcr)
                    pi = mcid_page(oobj)
                    if pi is not None: _ptree_set(pdf, pdf.pages[pi], int(child), kobj)
                elif isinstance(child, pikepdf.Dictionary) and str(child.get("/Type")) == "/MCR":
                    kk.append(child)
                    pi = mcid_page(oobj, child)
                    if pi is not None: _ptree_set(pdf, pdf.pages[pi], int(child.MCID), kobj)
                else:
                    if isinstance(child, pikepdf.Dictionary) and "/S" in child:
                        child.P = kobj          # reparent moved StructElem
                    kk.append(child)
            _set_kids(oobj, [])
            _remove_child(parent_of(o), oobj.objgen)
            delete_set.discard(o)               # merged-away => already gone
            counts["merged"] += 1
        _set_kids(kobj, kk)

    # 3) delete: UNWRAP each target — remove only the tag itself, splicing its
    # surviving children/content into its real parent at the same position, so
    # children you did NOT delete are kept (re-attached one level up).
    #
    # We locate the parent by scanning the LIVE tree (not the stored /P, which is
    # unreliable in some PDFs, nor the original walk, stale after merge). The map
    # is recomputed each iteration so nested deletes resolve against the current
    # tree regardless of order.
    def live_parents():
        pmap = {}
        def rec(node):
            K = node.get("/K")
            if K is None: return
            for k in (K if isinstance(K, pikepdf.Array) else [K]):
                if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                    pmap[k.objgen] = node
                    rec(k)
        rec(root)
        return pmap
    artifacts = {}      # page index -> set of MCID to demote to /Artifact
    for idx in sorted(delete_set, key=lambda i: -by_idx[i]["depth"]):
        if idx not in by_idx: continue
        x = obj_of(idx)
        parent = live_parents().get(x.objgen)
        if parent is None: continue                # already detached
        promoted = []
        for k in _kids(x):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                k.P = parent; promoted.append(k)               # keep child tag
                continue
            if isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/OBJR":
                ann = k.get("/Obj")                            # object reference (annotation)
                if isinstance(ann, pikepdf.Dictionary) and str(ann.get("/Subtype")) == "/Link":
                    _remove_annot(pdf, ann); counts["links"] += 1   # drop orphan Link
                else:
                    promoted.append(k)                         # keep other refs under parent
                continue
            # the tag's OWN marked content is always demoted to an artifact (even
            # if it has text): once its tag is gone the content must not stay as
            # tagged real content, or it trips "marked content / structure" checks.
            pi, m = (mcid_page(x), k) if isinstance(k, int) else (mcid_page(x, k), int(k.MCID))
            if pi is not None:
                artifacts.setdefault(pi, set()).add(m)
                _ptree_set(pdf, pdf.pages[pi], m, None)
        newk = []                                  # replace x in parent /K with its kids
        for k in _kids(parent):
            if getattr(k, "is_indirect", False) and k.objgen == x.objgen:
                newk.extend(promoted)
            else:
                newk.append(k)
        _set_kids(parent, newk)
        counts["deleted"] += 1
    for pi, mcids in artifacts.items():            # rewrite affected content streams
        _artifact_page(pdf, pdf.pages[pi], mcids)

    # wrap linkable text in real <Link> elements (with URI annotation)
    if link:
        counts["linked"] = make_links(pdf, link, by_idx, obj_of)

    if pdfua:
        # make any LI valid (L > LI > LBody) — collects the missing list tags
        counts["lists"] = fix_lists(pdf)
        # safety net: any Link annotation not inside a <Link> element is an orphan
        counts["links"] += neutralize_orphan_links(pdf)

    # any structural change can leave the parent tree stale -> rebuild it cleanly
    if (counts["deleted"] or counts["merged"] or counts["links"]
            or counts["linked"] or counts["lists"]):
        rebuild_parent_tree(pdf)

    if pdfua:
        mark_pdfua(pdf, lang=lang)
        counts["outline"] = add_outline(pdf)   # bookmarks from headings
    elif lang:
        pdf.Root.Lang = pikepdf.String(lang)
    if title is not None:
        pdf.docinfo[pikepdf.Name("/Title")] = pikepdf.String(title)
    if pdfua or title is not None:
        with pdf.open_metadata() as m:        # update_docinfo syncs Title -> dc:title
            if pdfua: m["pdfuaid:part"] = "1"
            if title is not None: m["dc:title"] = title
    buf = io.BytesIO()
    pdf.save(buf)
    pdf.close()
    return buf.getvalue(), counts

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
        elif self.path.startswith("/rules"):
            self._json(200, load_rules())
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
            retag = payload.get("retag") or payload.get("tags") or {}
            delete = payload.get("delete") or []
            merge = payload.get("merge") or []
            alt = payload.get("alt") or {}
            bbox = payload.get("bbox") or {}
            title = (payload.get("title") or "").strip() or None
            lang = (payload.get("lang") or "").strip() or None
            link = payload.get("link") or []
            pdfua = bool(payload.get("pdfua", True))
            pdf_bytes, counts = apply_ops(retag, delete, merge, alt, bbox, title, lang, link, pdfua)
            total = sum(counts.values())
            base = os.path.splitext(CURRENT["name"] or "document.pdf")[0]
            out = base + (".ua" if pdfua else "") + ".tagged.pdf"
            self._send(200, "application/pdf", pdf_bytes,
                       {"Content-Disposition": f'attachment; filename="{out}"',
                        "X-Tags-Changed": str(total), "X-Retag": str(counts["retag"]),
                        "X-Deleted": str(counts["deleted"]), "X-Merged": str(counts["merged"]),
                        "X-Alt": str(counts["alt"]), "X-Bbox": str(counts["bbox"]),
                        "X-Links": str(counts["links"]), "X-Linked": str(counts["linked"]),
                        "X-Outline": str(counts["outline"]), "X-Lists": str(counts["lists"]),
                        "X-PDFUA": "1" if pdfua else "0"})
        elif self.path == "/rules":          # learn from this document's edits
            payload = json.loads(self._read_body() or b"{}")
            rules = merge_observations(payload.get("seen") or {}, payload.get("acted") or [])
            self._json(200, rules)
        elif self.path == "/rules/clear":
            save_rules({}); self._json(200, {})
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
