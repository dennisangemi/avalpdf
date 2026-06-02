#!/usr/bin/env python3
"""
Viewer HTML: mostra le pagine di un PDF con sovrapposti i bounding box dei tag
rilevati da opendataloader-pdf (auto-tagging via layout engine, oppure struct tree).

Per ogni elemento (heading/paragraph/table/cell/list/image/...) disegna il box,
colorato per tipo, con etichetta e tooltip sul contenuto. Legenda con conteggi e
checkbox per mostrare/nascondere ciascun tipo. Output: un singolo file HTML
autosufficiente (immagini pagina embeddate in base64).

Uso:
    python make_viewer.py <pdf> [--use-struct-tree] [--scale 2.0] [-o out.html]

--use-struct-tree usa i tag GIA' presenti nel PDF; di default (auto) ignora i tag
esistenti e mostra cosa rileva il layout engine da zero.
"""

import argparse
import base64
import glob
import html
import json
import os
import tempfile
from pathlib import Path

import fitz  # pymupdf
import opendataloader_pdf

HERE = Path(__file__).resolve().parent

# Colore per tipo di elemento (bordo, sfondo trasparente)
COLORS = {
    "heading":     "#e11d48",  # rosso
    "paragraph":   "#2563eb",  # blu
    "table":       "#16a34a",  # verde
    "table row":   "#65a30d",
    "table cell":  "#84cc16",  # verde chiaro
    "list":        "#0891b2",  # teal
    "list item":   "#06b6d4",
    "image":       "#9333ea",  # viola
    "caption":     "#f59e0b",  # ambra
    "header":      "#6b7280",  # grigio
    "footer":      "#6b7280",
    "text block":  "#3b82f6",
    "formula":     "#db2777",
}
DEFAULT_COLOR = "#111827"


def collect_elements(node, page_dict):
    """Raccoglie ricorsivamente gli elementi con bounding box, per pagina (1-based)."""
    if not isinstance(node, dict):
        return
    t = node.get("type")
    bb = node.get("bounding box")
    page = node.get("page number")
    if t and bb and page:
        page_dict.setdefault(page, []).append({
            "type": t,
            "bbox": bb,
            "pdfua_tag": node.get("pdfua_tag"),
            "level": node.get("heading level"),
            "content": (node.get("content") or "")[:240],
        })
    for key in ("kids", "rows", "cells", "list items"):
        for c in (node.get(key) or []):
            collect_elements(c, page_dict)


def run_opendataloader(pdf_path, use_struct_tree, tmp):
    opendataloader_pdf.convert(
        input_path=pdf_path, output_dir=tmp, format="json",
        use_struct_tree=use_struct_tree, image_output="off", quiet=True,
    )
    jf = glob.glob(os.path.join(tmp, "*.json"))
    if not jf:
        raise RuntimeError("opendataloader non ha prodotto JSON")
    return json.load(open(jf[0], encoding="utf-8"))


def render_pages(pdf_path, scale):
    """Restituisce lista di (png_base64, width_pt, height_pt) per pagina."""
    doc = fitz.open(pdf_path)
    pages = []
    mat = fitz.Matrix(scale, scale)
    for p in doc:
        pix = p.get_pixmap(matrix=mat, alpha=False)
        b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
        pages.append((b64, p.rect.width, p.rect.height))
    doc.close()
    return pages


def build_html(pdf_name, mode, pages, page_elems, scale):
    from collections import Counter
    counts = Counter()
    for elems in page_elems.values():
        for e in elems:
            counts[e["type"]] += 1

    # Legenda + toggle
    legend = []
    for t, n in sorted(counts.items(), key=lambda x: -x[1]):
        color = COLORS.get(t, DEFAULT_COLOR)
        safe = t.replace(" ", "-")
        legend.append(
            f'<label class="leg"><input type="checkbox" checked data-type="{html.escape(t)}">'
            f'<span class="sw" style="background:{color}"></span>{html.escape(t)} '
            f'<b>{n}</b></label>'
        )
    legend_html = "\n".join(legend)

    # Pagine
    page_blocks = []
    for i, (b64, wpt, hpt) in enumerate(pages, 1):
        w_px = wpt * scale
        h_px = hpt * scale
        boxes = []
        for e in page_elems.get(i, []):
            x0, y0, x1, y1 = e["bbox"]
            left = min(x0, x1); right = max(x0, x1)
            ybot = min(y0, y1); ytop = max(y0, y1)
            L = left * scale
            T = (hpt - ytop) * scale          # flip asse y (PDF origin in basso)
            W = (right - left) * scale
            H = (ytop - ybot) * scale
            t = e["type"]
            color = COLORS.get(t, DEFAULT_COLOR)
            label = t + (f" H{e['level']}" if e.get("level") else "")
            tip = html.escape(e["content"]) if e["content"] else ""
            tag = f" · {e['pdfua_tag']}" if e.get("pdfua_tag") else ""
            boxes.append(
                f'<div class="box" data-type="{html.escape(t)}" '
                f'style="left:{L:.1f}px;top:{T:.1f}px;width:{W:.1f}px;height:{H:.1f}px;'
                f'border-color:{color}" title="{html.escape(label)}{html.escape(tag)}&#10;{tip}">'
                f'<span class="lbl" style="background:{color}">{html.escape(label)}</span></div>'
            )
        page_blocks.append(
            f'<div class="pagewrap"><div class="pageno">Pagina {i}</div>'
            f'<div class="page" style="width:{w_px:.0f}px;height:{h_px:.0f}px">'
            f'<img src="data:image/png;base64,{b64}" width="{w_px:.0f}" height="{h_px:.0f}">'
            f'{"".join(boxes)}</div></div>'
        )
    pages_html = "\n".join(page_blocks)

    total = sum(counts.values())
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="utf-8">
<title>Tag viewer · {html.escape(pdf_name)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; background:#f3f4f6; color:#111827; }}
  header {{ position:sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid #e5e7eb;
           padding:14px 20px; box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  header h1 {{ margin:0 0 2px; font-size:16px; }}
  header .sub {{ color:#6b7280; font-size:13px; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:10px; }}
  .leg {{ display:inline-flex; align-items:center; gap:6px; cursor:pointer; user-select:none;
          background:#f9fafb; border:1px solid #e5e7eb; border-radius:6px; padding:3px 8px; font-size:13px; }}
  .leg .sw {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}
  .leg b {{ color:#6b7280; font-weight:600; }}
  main {{ padding:24px; display:flex; flex-direction:column; align-items:center; gap:28px; }}
  .pagewrap {{ }}
  .pageno {{ font-size:12px; color:#6b7280; margin-bottom:6px; text-align:center; }}
  .page {{ position:relative; background:#fff; box-shadow:0 2px 12px rgba(0,0,0,.12); }}
  .page img {{ display:block; }}
  .box {{ position:absolute; border:1.5px solid; border-radius:2px; background:rgba(0,0,0,0);
          transition:background .1s; }}
  .box:hover {{ background:rgba(37,99,235,.08); }}
  .box .lbl {{ position:absolute; top:-15px; left:-1px; font-size:9px; line-height:1.3;
               color:#fff; padding:0 4px; border-radius:3px 3px 0 0; white-space:nowrap;
               opacity:.92; pointer-events:none; }}
  .hidden {{ display:none !important; }}
  .toolbar {{ margin-top:8px; display:flex; gap:8px; }}
  .toolbar button {{ font-size:12px; padding:3px 10px; border:1px solid #d1d5db; background:#fff;
                     border-radius:6px; cursor:pointer; }}
</style></head>
<body>
<header>
  <h1>🏷️ Tag viewer — {html.escape(pdf_name)}</h1>
  <div class="sub">Sorgente: <b>{mode}</b> · opendataloader-pdf · {total} elementi su {len(pages)} pagine</div>
  <div class="toolbar">
    <button id="all">Mostra tutti</button>
    <button id="none">Nascondi tutti</button>
  </div>
  <div class="legend">{legend_html}</div>
</header>
<main>{pages_html}</main>
<script>
  const cbs = [...document.querySelectorAll('.leg input')];
  function apply() {{
    const on = new Set(cbs.filter(c=>c.checked).map(c=>c.dataset.type));
    document.querySelectorAll('.box').forEach(b=>{{
      b.classList.toggle('hidden', !on.has(b.dataset.type));
    }});
  }}
  cbs.forEach(c=>c.addEventListener('change', apply));
  document.getElementById('all').onclick = ()=>{{ cbs.forEach(c=>c.checked=true); apply(); }};
  document.getElementById('none').onclick = ()=>{{ cbs.forEach(c=>c.checked=false); apply(); }};
  apply();
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Viewer HTML dei bounding box dei tag (opendataloader)")
    ap.add_argument("pdf", help="PDF di input")
    ap.add_argument("--use-struct-tree", action="store_true",
                    help="usa i tag esistenti nel PDF invece dell'auto-tagging")
    ap.add_argument("--scale", type=float, default=2.0, help="scala di rendering pagine (default 2.0)")
    ap.add_argument("-o", "--out", help="file HTML di output (default: ./out/<nome>_viewer.html)")
    args = ap.parse_args()

    pdf_path = args.pdf
    mode = "tag esistenti (struct tree)" if args.use_struct_tree else "auto-tagging (layout engine)"
    name = os.path.basename(pdf_path)

    tmp = tempfile.mkdtemp(prefix="odl_viewer_")
    j = run_opendataloader(pdf_path, args.use_struct_tree, tmp)
    page_elems = {}
    for k in j.get("kids", []):
        collect_elements(k, page_elems)
    pages = render_pages(pdf_path, args.scale)

    out = args.out or str(HERE / "out" / (Path(name).stem + "_viewer.html"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(build_html(name, mode, pages, page_elems, args.scale), encoding="utf-8")

    n = sum(len(v) for v in page_elems.values())
    print(f"OK · {name} · {mode}")
    print(f"  {n} elementi su {len(pages)} pagine")
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
