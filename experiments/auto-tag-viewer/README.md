# Auto-tag viewer

Visualizzatore HTML che mostra le pagine di un PDF con sovrapposti i **bounding box
dei tag rilevati da opendataloader-pdf**, e test sulla capacità di **auto-tagging**
(generare tag su un PDF non taggato).

> Cartella di ricerca, separata dal package `avalpdf/`. Vedi anche
> [`../README.md`](../README.md) per il quadro completo dell'indagine.

## Setup

```bash
# dalla root del repo
source .venv/bin/activate
uv pip install -e . opendataloader-pdf pymupdf
```

Richiede una JVM (opendataloader, testato con Java 21).

## 1. Viewer dei bounding box

`make_viewer.py` produce un singolo file HTML autosufficiente (immagini pagina
embeddate in base64) con i box dei tag, colorati per tipo, etichette, tooltip sul
contenuto, legenda con conteggi e checkbox per mostrare/nascondere ogni tipo.

```bash
# auto-tagging (layout engine, ignora i tag esistenti) — mostra cosa "scopre"
python make_viewer.py ../../pdfs/bugs/compito.pdf

# tag GIA' presenti nel PDF (struct tree)
python make_viewer.py ../../pdfs/bugs/compito.pdf --use-struct-tree -o out/compito_structtree_viewer.html

# scala di rendering e output personalizzati
python make_viewer.py <pdf> --scale 2.0 -o out/mio_viewer.html
```

Per navigare i viewer in `out/`:

```bash
cd out && python3 -m http.server 8888
# poi apri http://localhost:8888/
```

### File generati in `out/`

| File | Contenuto |
|---|---|
| `compito_viewer.html` | Auto-tagging su PDF con testo → 21 elementi (4 heading, 9 paragrafi, tabella, immagine) |
| `compito_structtree_viewer.html` | Stesso PDF, tag esistenti (struct tree), per confronto |
| `notags_viewer.html` | PDF scansionato → solo 4 Figure (una per pagina) |

## 2. Test di auto-tagging

opendataloader può generare un PDF taggato da uno non taggato
(`AutoTaggingProcessor`):

```bash
opendataloader-pdf -f tagged-pdf -o out ../../pdfs/bugs/compito.pdf   # -> compito_tagged.pdf
```

### Esempi salvati in `out/`

| File | Sorgente | Struttura generata (verificata con pdfix) |
|---|---|---|
| `compito_autotagged.pdf` | PDF **con testo** | `Document > H1, H2×2, H3, P×9, Link, Table(TR×3 → TH×2 + TD×4), Figure` |
| `notags_autotagged.pdf` | PDF **scansionato** | `Document > Figure×4 + Form` (solo immagini) |

**Conclusioni:**

- Su PDF **con testo** l'auto-tagging produce tag semantici reali, **comprese le celle
  header `TH`** — quindi il motore conosce gli header (e li scrive nel PDF), confermando
  che la perdita TH→TD è solo nel JSON (vedi issue upstream nel README generale).
- Su PDF **scansionato** (`notags.pdf`, nessun layer di testo) può solo marcare Figure:
  servirebbe l'OCR (modalità hybrid) per estrarre e taggare il testo.

### Punteggio di accessibilità (avalpdf) — sorpresa

Lanciando `avalpdf` sui due `compito`:

| | Auto-taggato (opendataloader) | Originale (taggato a mano) |
|---|---|---|
| **Weighted Accessibility Score** | **77.64%** | 75.72% |
| Header tabella | ✅ TH corretti | ❌ tabella senza header (solo TD) |
| Heading | 4 | 3 |
| Elementi vuoti | 1 cella | 5 (4 paragrafi + 1 cella) |

Su questo documento **l'auto-tagging ha superato il tagging manuale**, soprattutto perché
ha riconosciuto la riga di intestazione della tabella (TH) che l'autore aveva lasciato
come TD. Caveat: un solo documento, PDF semplice, title metadata non impostato in entrambi.
