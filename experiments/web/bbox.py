#!/usr/bin/env python3
"""Structure-tree + bounding-box extraction for the avalpdf web UI.

This module reads a PDF's real structure tree (StructTreeRoot) with pikepdf and
computes a bounding box (in PDF user-space coordinates) for every structure
element from its marked content (MCID), by replaying the page content stream.

It is a trimmed, read-only adaptation of the extractor in
``experiments/tool-manual-tagging/tagtool.py`` — here we only need to *read*
boxes so they can be overlaid on the pdf.js render in the browser, never to
write the PDF back.

The element reading-order index produced by :func:`walk_elements` is the stable
key used by the frontend to link an element to an avalpdf issue.
"""
import io
import re
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

    Subsetted fonts encode glyphs as custom codes (1,2,3…); the real text lives
    in this CMap. Without it, decoding raw bytes as cp1252 yields garbage for
    headings using subsetted fonts."""
    tu = font.get("/ToUnicode")
    if tu is None:
        return {}
    try:
        text = tu.read_bytes().decode("latin-1", "replace")
    except Exception:
        return {}
    out = {}
    def dec(h):
        try:
            return bytes.fromhex(h).decode("utf-16-be", "replace")
        except Exception:
            return ""
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            out[int(src, 16)] = dec(dst)
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        def _arr(m):
            start = int(m.group(1), 16)
            for i, h in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", m.group(3))):
                out[start + i] = dec(h)
            return " "
        blk = re.sub(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", _arr, blk, flags=re.S)
        for s, e, d in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            start, end, nb, base = int(s, 16), int(e, 16), len(d) // 2, int(d, 16)
            for off in range(end - start + 1):
                try:
                    out[start + off] = (base + off).to_bytes(nb, "big").decode("utf-16-be", "replace")
                except Exception:
                    out[start + off] = ""
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
        if mcid is None:
            return None
        d = data.get(mcid)
        if d is None:
            d = data[mcid] = {"bbox": None, "text": ""}
        return d
    def grow(mcid, x, y):
        d = slot(mcid)
        if d is None:
            return
        b = d["bbox"]
        if b is None:
            d["bbox"] = [x, y, x, y]
        else:
            b[0] = min(b[0], x); b[1] = min(b[1], y); b[2] = max(b[2], x); b[3] = max(b[3], y)
    def addtext(mcid, s):
        d = slot(mcid)
        if d is not None:
            d["text"] += s

    ctm_stack, ctm = [], (1, 0, 0, 1, 0, 0)
    Tm = Tlm = (1, 0, 0, 1, 0, 0)
    fontsize = 0.0; cur_w = {}; two_byte = False; cur_tu = {}
    char_sp = word_sp = leading = 0.0
    mc_stack, cur = [], None

    try:
        ops = pikepdf.parse_content_stream(page)
    except Exception:
        return data
    for operands, op in ops:
        o = str(op)
        if o == "q":
            ctm_stack.append(ctm)
        elif o == "Q":
            if ctm_stack:
                ctm = ctm_stack.pop()
        elif o == "cm":
            ctm = mat_mul(tuple(float(x) for x in operands), ctm)
        elif o == "BT":
            Tm = Tlm = (1, 0, 0, 1, 0, 0)
        elif o == "Tm":
            Tm = Tlm = tuple(float(x) for x in operands)
        elif o in ("Td", "TD"):
            tx, ty = float(operands[0]), float(operands[1])
            if o == "TD":
                leading = -ty
            Tlm = mat_mul((1, 0, 0, 1, tx, ty), Tlm); Tm = Tlm
        elif o == "T*":
            Tlm = mat_mul((1, 0, 0, 1, 0, -leading), Tlm); Tm = Tlm
        elif o == "TL":
            leading = float(operands[0])
        elif o == "Tc":
            char_sp = float(operands[0])
        elif o == "Tw":
            word_sp = float(operands[0])
        elif o == "Tf":
            fi = fonts.get(str(operands[0]), {})
            fontsize = float(operands[1])
            cur_w = fi.get("w", {}); two_byte = fi.get("two_byte", False); cur_tu = fi.get("tu", {})
        elif o in ("BDC", "BMC"):
            mcid = None
            if o == "BDC" and len(operands) >= 2 and isinstance(operands[1], pikepdf.Dictionary):
                if "/MCID" in operands[1]:
                    mcid = int(operands[1].MCID)
            mc_stack.append(mcid if mcid is not None else cur)
            cur = mc_stack[-1]
        elif o == "EMC":
            if mc_stack:
                mc_stack.pop()
            cur = mc_stack[-1] if mc_stack else None
        elif o == "Do":
            for ux, uy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                dx, dy = apply_mat(ctm, ux, uy); grow(cur, dx, dy)
        elif o in ("Tj", "TJ", "'", "\""):
            if o == "'":
                Tlm = mat_mul((1, 0, 0, 1, 0, -leading), Tlm); Tm = Tlm
            elements = operands[0]
            if o == "\"":
                word_sp = float(operands[0]); char_sp = float(operands[1]); elements = operands[2]
            seq = elements if (o == "TJ" and isinstance(elements, pikepdf.Array)) else [elements]
            for el in seq:
                if isinstance(el, (int, float)):
                    Tm = mat_mul((1, 0, 0, 1, -float(el) / 1000.0 * fontsize, 0), Tm); continue
                raw = bytes(el)
                if two_byte:
                    codes = [(raw[i] << 8) | raw[i + 1] for i in range(0, len(raw) - 1, 2)]
                else:
                    codes = list(raw)
                for code in codes:
                    ch = cur_tu.get(code)
                    if ch is None and not two_byte and code >= 32:
                        try:
                            ch = bytes([code]).decode("cp1252")
                        except Exception:
                            ch = ""
                    if ch:
                        addtext(cur, ch)
                    w0 = cur_w.get(code, 500.0) / 1000.0
                    trm = mat_mul(Tm, ctm)
                    x0, y0 = apply_mat(trm, 0, -0.21 * fontsize)
                    x1, y1 = apply_mat(trm, w0 * fontsize, 0.79 * fontsize)
                    grow(cur, x0, y0); grow(cur, x1, y1)
                    adv = w0 * fontsize + char_sp + (word_sp if code == 32 else 0.0)
                    Tm = mat_mul((1, 0, 0, 1, adv, 0), Tm)
    return data

# ------------------------------------------------------- structure walking ---
STD_TYPES = {"Document", "Part", "Art", "Sect", "Div", "BlockQuote", "Caption", "TOC",
             "TOCI", "Index", "P", "H1", "H2", "H3", "H4", "H5", "H6", "L", "LI", "Lbl",
             "LBody", "Table", "TR", "TH", "TD", "THead", "TBody", "TFoot", "Span",
             "Quote", "Note", "Reference", "BibEntry", "Figure", "Formula", "Form",
             "Link", "Annot", "Ruby", "Warichu", "Code", "NonStruct", "Private"}

LINKABLE_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}|https?://\S+|www\.\S+", re.I)

def _read_bbox_attr(elem):
    A = elem.get("/A")
    if A is None:
        return None
    for a in (list(A) if isinstance(A, pikepdf.Array) else [A]):
        if isinstance(a, pikepdf.Dictionary) and str(a.get("/O")) == "/Layout" and "/BBox" in a:
            try:
                return [float(v) for v in a.BBox]
            except Exception:
                return None
    return None

def walk_elements(pdf):
    """Deterministic reading-order walk of every StructElem (depth-first)."""
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
        if alt:
            rec["alt"] = str(alt)
        ab = _read_bbox_attr(elem)
        if ab:
            rec["bbox_attr"] = ab
        pg = elem.get("/Pg")
        if pg is not None and pg.objgen in pageidx:
            rec["page"] = pageidx[pg.objgen]
        out.append(rec)
        K = elem.get("/K")
        if K is None:
            return
        for k in (K if isinstance(K, pikepdf.Array) else [K]):
            if isinstance(k, pikepdf.Dictionary) and "/S" in k:
                rec["nkids"] += 1
                walk(k, depth + 1, rec["tag"], elem.objgen)
            elif isinstance(k, int):
                rec["mcids"].append((rec["page"], k))
            elif isinstance(k, pikepdf.Dictionary) and str(k.get("/Type")) == "/MCR":
                p = k.get("/Pg"); pi = pageidx.get(p.objgen) if p is not None else rec["page"]
                rec["mcids"].append((pi, int(k.MCID)))
    K = root.get("/K")
    if K is not None:
        for k in (K if isinstance(K, pikepdf.Array) else [K]):
            walk(k, 0, None, None)
    return out

def resolve_role(tag, rolemap, _seen=None):
    """Follow the RoleMap chain until a standard type (or a dead end)."""
    if _seen is None:
        _seen = set()
    if tag in STD_TYPES or rolemap is None or tag in _seen:
        return tag
    _seen.add(tag)
    mapped = rolemap.get("/" + tag)
    if mapped is None:
        return tag
    return resolve_role(str(mapped).lstrip("/"), rolemap, _seen)

def build_structure(pdf_bytes):
    """Open the PDF bytes and return a structure dict with per-element boxes.

    Returns ``{"tagged": bool, "pages": [{w,h}], "elements": [...]}``. When the
    PDF has no structure tree, ``tagged`` is False and ``elements`` is empty
    (the page list is still returned so the viewer can render the document)."""
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    pages = []
    for p in pdf.pages:
        box = p.get("/MediaBox") or p.get("/CropBox")
        try:
            x0, y0, x1, y1 = [float(v) for v in box]
            w, h = abs(x1 - x0), abs(y1 - y0)
        except Exception:
            w, h = 612.0, 792.0
        rot = 0
        try:
            rot = int(p.get("/Rotate", 0)) % 360
        except Exception:
            rot = 0
        if rot in (90, 270):
            w, h = h, w
        pages.append({"w": round(w, 2), "h": round(h, 2), "rotate": rot})

    if "/StructTreeRoot" not in pdf.Root:
        pdf.close()
        return {"tagged": False, "pages": pages, "elements": []}

    elems = walk_elements(pdf)
    rolemap = pdf.Root.StructTreeRoot.get("/RoleMap")
    cache = {}
    def mc(page):
        if page not in cache:
            cache[page] = page_mcid_data(pdf.pages[page])
        return cache[page]
    def _merge(box, b):
        return b[:] if box is None else [min(box[0], b[0]), min(box[1], b[1]),
                                         max(box[2], b[2]), max(box[3], b[3])]
    for e in elems:
        pb = {}; txt = ""
        for (pg, m) in e["mcids"]:
            if pg is None:
                continue
            if e["page"] is None:
                e["page"] = pg
            d = mc(pg).get(m)
            if not d or not d["bbox"]:
                continue
            pb[pg] = _merge(pb.get(pg), d["bbox"])
            txt += d["text"]
        e["_pb"] = pb
        e["text"] = (e["alt"] or txt or "").strip()
    for i in range(len(elems) - 1, -1, -1):
        e = elems[i]
        if not e["_pb"]:
            d = e["depth"]; pb = {}
            for j in range(i + 1, len(elems)):
                if elems[j]["depth"] <= d:
                    break
                for pg, cb in elems[j]["_pb"].items():
                    pb[pg] = _merge(pb.get(pg), cb)
            e["_pb"] = pb
            if e["page"] is None and pb:
                e["page"] = min(pb.keys())

    result = []
    for e in elems:
        if e["tag"] == "Document":
            continue
        eff = resolve_role(e["tag"], rolemap)
        if e.get("bbox_attr") and e["page"] is not None:
            boxes = [[e["page"], [round(v, 2) for v in e["bbox_attr"]]]]
        else:
            boxes = [[pg, [round(v, 2) for v in bb]] for pg, bb in sorted(e["_pb"].items())]
        eff_tag = eff if eff in STD_TYPES else e["tag"]
        is_fig = eff == "Figure" or e["tag"] == "Figure"
        is_heading = bool(re.fullmatch(r"H[1-6]", eff_tag))
        linkable = (e["nkids"] == 0 and eff != "Link" and e["parent"] != "Link"
                    and bool(LINKABLE_RE.search(e["text"] or "")))
        result.append({
            "idx": e["idx"],
            "tag": e["tag"],
            "eff": eff_tag,
            "depth": e["depth"],
            "parent": e["parent"],
            "page": e["page"],
            "leaf": e["nkids"] == 0,
            "empty": (not e["text"]) and e["nkids"] == 0 and not is_fig,
            "figure": is_fig,
            "heading": is_heading,
            "headingLevel": int(eff_tag[1]) if is_heading else None,
            "table": eff_tag == "Table",
            "list": eff_tag == "L",
            "link": eff_tag == "Link" or e["tag"] == "Link",
            "linkable": linkable,
            "hasAlt": bool(e["alt"]),
            "alt": e["alt"] or "",
            "boxes": boxes,
            "text": e["text"][:300],
        })
    pdf.close()
    return {"tagged": True, "pages": pages, "elements": result}
