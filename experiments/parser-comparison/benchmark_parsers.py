#!/usr/bin/env python3
"""
Benchmark di estrazione dell'albero dei tag: pdfix-sdk (avalpdf) vs opendataloader-pdf.

Misura, su più documenti PDF, il tempo di estrazione della struttura dei tag con i due parser.

Metodologia (documentata per onestà del confronto):
  - pdfix-sdk: in-process via avalpdf.converter.pdf_to_json(). La SDK viene
    inizializzata una volta (GetPdfix singleton); ogni misura apre/estrae/chiude il doc.
  - opendataloader-pdf: ogni chiamata lancia una JVM Java (subprocess), costo di
    avvio incluso in ogni misura per-file -> e' il costo reale dell'uso da CLI.
    Per contesto misuriamo anche la modalita' BATCH (una sola JVM per tutti i file),
    che ammortizza l'avvio e mostra il throughput a regime.
  - Estrazione immagini disattivata (image_output='off') per misurare solo la struttura.
  - Per ogni file: 1 run di warmup scartato + N run cronometrati; si riportano
    mediana, minimo e deviazione standard.

Output: CSV + JSON con i tempi, e un grafico PNG (scala log) di confronto per documento
piu' un riepilogo aggregato.
"""

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

# --- pdfix (via avalpdf) ---
from avalpdf.converter import pdf_to_json

# --- opendataloader ---
import opendataloader_pdf


def time_pdfix(pdf_path: str) -> float:
    """Tempo (s) per estrarre l'albero dei tag con pdfix-sdk."""
    t0 = time.perf_counter()
    pdf_to_json(pdf_path)
    return time.perf_counter() - t0


def time_odl(pdf_path: str, out_dir: str) -> float:
    """Tempo (s) per estrarre la struttura con opendataloader (JSON, struct tree)."""
    t0 = time.perf_counter()
    opendataloader_pdf.convert(
        input_path=pdf_path,
        output_dir=out_dir,
        format="json",
        use_struct_tree=True,
        image_output="off",
        quiet=True,
    )
    return time.perf_counter() - t0


def time_odl_batch(pdf_paths, out_dir: str) -> float:
    """Tempo (s) totale per estrarre TUTTI i file in una sola invocazione (JVM unica)."""
    t0 = time.perf_counter()
    opendataloader_pdf.convert(
        input_path=list(pdf_paths),
        output_dir=out_dir,
        format="json",
        use_struct_tree=True,
        image_output="off",
        quiet=True,
    )
    return time.perf_counter() - t0


def stats(times):
    return {
        "median": statistics.median(times),
        "min": min(times),
        "max": max(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
        "runs": times,
    }


def collect_pdfs(patterns):
    import glob
    files = []
    for p in patterns:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.pdf"), recursive=True)
        else:
            files += glob.glob(p, recursive=True)
    # dedup mantenendo l'ordine
    seen = set()
    out = []
    for f in sorted(files):
        if f not in seen and f.lower().endswith(".pdf"):
            seen.add(f)
            out.append(f)
    return out


# Percorsi risolti rispetto alla posizione dello script: il benchmark funziona
# da qualunque cwd. REPO_ROOT = .../avalpdf (due livelli sopra questo file).
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_PDFS = str(REPO_ROOT / "pdfs")
DEFAULT_OUT = str(HERE / "results")


def main():
    ap = argparse.ArgumentParser(description="Benchmark pdfix vs opendataloader (estrazione tag tree)")
    ap.add_argument("inputs", nargs="*", default=[DEFAULT_PDFS],
                    help="File/dir/glob dei PDF (default: <repo>/pdfs)")
    ap.add_argument("--runs", "-n", type=int, default=3, help="Run cronometrati per file (default 3)")
    ap.add_argument("--out", "-o", default=DEFAULT_OUT,
                    help="Cartella output (default: ./results accanto allo script)")
    args = ap.parse_args()

    pdfs = collect_pdfs(args.inputs or [DEFAULT_PDFS])
    if not pdfs:
        print("Nessun PDF trovato.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="odl_bench_")

    print(f"Documenti: {len(pdfs)} | run/file: {args.runs}\n")

    results = []
    # Warmup globale: prima invocazione paga inizializzazioni varie
    print("Warmup...", flush=True)
    try:
        time_pdfix(pdfs[0])
        time_odl(pdfs[0], tmp)
    except Exception as e:
        print(f"  warmup err: {e}")

    for i, pdf in enumerate(pdfs, 1):
        name = os.path.basename(pdf)
        size_kb = os.path.getsize(pdf) / 1024
        # metadati: pagine + tagged (da pdfix)
        pages, tagged = None, None
        try:
            j = pdf_to_json(pdf)
            pages = j.get("num_pages")
            tagged = j.get("tagged")
        except Exception:
            pass

        rec = {"file": name, "path": pdf, "size_kb": round(size_kb, 1),
               "pages": pages, "tagged": tagged}

        # pdfix
        try:
            pt = [time_pdfix(pdf) for _ in range(args.runs)]
            rec["pdfix"] = stats(pt)
        except Exception as e:
            rec["pdfix"] = {"error": str(e)}

        # opendataloader (per-file, include avvio JVM)
        try:
            ot = [time_odl(pdf, tmp) for _ in range(args.runs)]
            rec["odl"] = stats(ot)
        except Exception as e:
            rec["odl"] = {"error": str(e)}

        results.append(rec)
        pm = rec["pdfix"].get("median")
        om = rec["odl"].get("median")
        pm_s = f"{pm*1000:8.1f} ms" if pm is not None else "   ERR  "
        om_s = f"{om:6.2f} s " if om is not None else "  ERR  "
        ratio = f"{om/pm:6.0f}x" if (pm and om) else "  -  "
        print(f"[{i:2}/{len(pdfs)}] {name[:40]:40} pdfix {pm_s} | odl {om_s} | {ratio}", flush=True)

    # Batch opendataloader (JVM unica per tutti)
    print("\nBatch opendataloader (una sola JVM per tutti i file)...", flush=True)
    ok_pdfs = [r["path"] for r in results if "error" not in r.get("odl", {})]
    batch_time = None
    try:
        batch_time = time_odl_batch(ok_pdfs, tmp)
        print(f"  totale: {batch_time:.2f} s su {len(ok_pdfs)} file -> {batch_time/len(ok_pdfs):.2f} s/file ammortizzato")
    except Exception as e:
        print(f"  batch err: {e}")

    # Aggregati
    pdfix_meds = [r["pdfix"]["median"] for r in results if "median" in r.get("pdfix", {})]
    odl_meds = [r["odl"]["median"] for r in results if "median" in r.get("odl", {})]
    summary = {
        "n_docs": len(results),
        "runs_per_file": args.runs,
        "pdfix_total_median_s": sum(pdfix_meds),
        "odl_total_median_s": sum(odl_meds),
        "pdfix_mean_per_doc_s": statistics.mean(pdfix_meds) if pdfix_meds else None,
        "odl_mean_per_doc_s": statistics.mean(odl_meds) if odl_meds else None,
        "odl_batch_total_s": batch_time,
        "odl_batch_per_doc_s": (batch_time / len(ok_pdfs)) if batch_time else None,
    }

    # Salvataggi
    (out_dir / "results.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False))

    # CSV
    import csv
    with open(out_dir / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "pages", "tagged", "size_kb",
                    "pdfix_median_ms", "pdfix_min_ms", "pdfix_stdev_ms",
                    "odl_median_s", "odl_min_s", "odl_stdev_s", "ratio_odl_over_pdfix"])
        for r in results:
            p = r.get("pdfix", {})
            o = r.get("odl", {})
            pm = p.get("median")
            om = o.get("median")
            w.writerow([
                r["file"], r["pages"], r["tagged"], r["size_kb"],
                round(pm*1000, 2) if pm else "",
                round(p.get("min", 0)*1000, 2) if "min" in p else "",
                round(p.get("stdev", 0)*1000, 2) if "stdev" in p else "",
                round(om, 3) if om else "",
                round(o.get("min", 0), 3) if "min" in o else "",
                round(o.get("stdev", 0), 3) if "stdev" in o else "",
                round(om/pm, 1) if (pm and om) else "",
            ])

    make_charts(results, summary, out_dir)

    print(f"\nFatto. Output in: {out_dir.resolve()}")
    print(f"  - results.csv / results.json")
    print(f"  - benchmark_chart.png (confronto per documento)")
    print(f"  - benchmark_summary.png (riepilogo)")
    print(f"\nRiepilogo: pdfix medio {summary['pdfix_mean_per_doc_s']*1000:.1f} ms/doc | "
          f"odl medio {summary['odl_mean_per_doc_s']:.2f} s/doc (per-file) | "
          f"odl batch {summary['odl_batch_per_doc_s']:.2f} s/doc" if summary['odl_batch_per_doc_s'] else "")


def make_charts(results, summary, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [r for r in results
            if "median" in r.get("pdfix", {}) and "median" in r.get("odl", {})]
    rows.sort(key=lambda r: r["odl"]["median"])
    labels = [r["file"][:34] for r in rows]
    pdfix_ms = [r["pdfix"]["median"] * 1000 for r in rows]
    odl_ms = [r["odl"]["median"] * 1000 for r in rows]
    y = np.arange(len(rows))
    h = 0.38

    # --- Chart 1: per documento (scala log perche' i due ordini di grandezza differiscono) ---
    fig, ax = plt.subplots(figsize=(11, max(6, 0.42 * len(rows))))
    ax.barh(y + h/2, pdfix_ms, h, label="pdfix-sdk (in-process)", color="#2563eb")
    ax.barh(y - h/2, odl_ms, h, label="opendataloader (JVM/file)", color="#f97316")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("Tempo mediano di estrazione (ms, scala log)")
    ax.set_title("Estrazione albero dei tag: pdfix-sdk vs opendataloader-pdf\n"
                 f"{summary['n_docs']} documenti, mediana su {summary['runs_per_file']} run")
    ax.legend(loc="lower right")
    ax.grid(axis="x", which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "benchmark_chart.png", dpi=130)
    plt.close(fig)

    # --- Chart 2: riepilogo aggregato ---
    fig, ax = plt.subplots(figsize=(8, 5))
    cats = ["pdfix\n(per-doc)", "odl per-file\n(con avvio JVM)", "odl batch\n(JVM ammortizzata)"]
    vals = [
        summary["pdfix_mean_per_doc_s"] * 1000,
        summary["odl_mean_per_doc_s"] * 1000,
        (summary["odl_batch_per_doc_s"] * 1000) if summary["odl_batch_per_doc_s"] else 0,
    ]
    colors = ["#2563eb", "#f97316", "#16a34a"]
    bars = ax.bar(cats, vals, color=colors)
    ax.set_yscale("log")
    ax.set_ylabel("Tempo medio per documento (ms, scala log)")
    ax.set_title("Riepilogo: tempo medio di estrazione per documento")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v, f"{v:.0f} ms" if v < 1000 else f"{v/1000:.2f} s",
                ha="center", va="bottom", fontsize=10)
    ax.grid(axis="y", which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "benchmark_summary.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
