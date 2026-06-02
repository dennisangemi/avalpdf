# Parser comparison: pdfix-sdk vs opendataloader-pdf

Esperimento di valutazione per capire se conviene affiancare/sostituire il parser
di avalpdf (**pdfix-sdk**) con **opendataloader-pdf** per l'estrazione dell'albero
dei tag dai PDF già taggati.

> Cartella di **ricerca**, separata dal package `avalpdf/`. Non fa parte del tool
> distribuito e non influisce su `setup.py`. Gli output in `results/` sono versionati
> come istantanea dell'ultima esecuzione; si rigenerano lanciando lo script.

## Setup

```bash
# dalla root del repo
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e .                       # avalpdf + pdfix-sdk
uv pip install opendataloader-pdf matplotlib
```

opendataloader-pdf richiede una JVM (testato con Java 21).

## Eseguire il benchmark

```bash
python experiments/parser-comparison/benchmark_parsers.py            # tutti i PDF in pdfs/
python experiments/parser-comparison/benchmark_parsers.py --runs 5   # piu' ripetizioni
python experiments/parser-comparison/benchmark_parsers.py <file_o_glob> --out results
```

Output in `results/`: `results.csv`, `results.json`, `benchmark_chart.png`
(confronto per documento, scala log) e `benchmark_summary.png` (riepilogo aggregato).

## Metodologia

- **pdfix**: in-process via `avalpdf.converter.pdf_to_json()`. SDK inizializzata una
  volta; ogni misura apre/estrae/chiude il documento.
- **opendataloader**: ogni chiamata lancia una JVM (subprocess) — il costo di avvio
  e' incluso in ogni misura per-file, com'e' nell'uso reale da CLI. Si misura anche
  la modalita' **batch** (una JVM per tutti i file) per il throughput a regime.
- Estrazione immagini disattivata (`image_output='off'`): si misura solo la struttura.
- 1 run di warmup scartato + N run cronometrati per file; si riportano mediana, min, stdev.

## Risultati (2026-06-02, 33 doc, 3 run/file)

| | pdfix-sdk | opendataloader (per-file) | opendataloader (batch) |
|---|---|---|---|
| Tempo medio/doc | **508 ms** | 2.19 s | **213 ms** |
| Range | 16 ms – 8.3 s | 1.48 – 2.97 s | — |

- **Per documento singolo** (modello attuale di avalpdf, un file per processo):
  pdfix ~4x piu' veloce. opendataloader paga ~1.5 s di avvio JVM ad ogni chiamata.
- **Insight**: opendataloader e' lento ad *avviarsi*, non a *estrarre*. In batch
  (JVM ammortizzata) fa 213 ms/file, piu' veloce e piu' regolare di pdfix.
- pdfix ha varianza alta e outlier (un doc: 8.3 s, vs 2.8 s di odl sullo stesso file);
  opendataloader resta sempre 1.5–3 s.

### Nota di accuratezza (non solo velocita')

Il JSON di opendataloader e' lossy per l'accessibilita': serializza tutte le celle
come `TD` (nessun flag header — l'info TH sopravvive solo nell'output HTML), e fonde
`Lbl`/`LBody` delle liste in un unico `content`. pdfix restituisce l'albero dei tag
fedele (`S`/`K`/`Alt`), che e' cio' che serve al validatore. Dettagli nella memoria
di progetto `opendataloader-parser-evaluation`.
