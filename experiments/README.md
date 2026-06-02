# experiments/

Cartella di **ricerca e valutazione**, separata dal package `avalpdf/`. Niente qui
fa parte del tool distribuito o influisce su `setup.py`: sono indagini, benchmark e
prototipi. Gli script e i README si versionano; gli output grossi/derivati sono
rigenerabili lanciando gli script.

## Contesto

Indagine (giugno 2026) per capire se conviene affiancare/sostituire il parser PDF di
avalpdf — **pdfix-sdk** — con **opendataloader-pdf** (parser open-source Java per
dati AI-ready, che si promuove anche per l'accessibilità). avalpdf valida l'albero dei
tag estratto: la domanda è se opendataloader estrae quell'albero meglio, più veloce, o
abilita funzionalità nuove (auto-tagging).

Ambiente:

```bash
uv venv .venv --python 3.11 && source .venv/bin/activate
uv pip install -e .                                  # avalpdf + pdfix-sdk 9.0.0
uv pip install opendataloader-pdf matplotlib pymupdf # opendataloader 2.4.7 (richiede Java, testato Java 21)
```

## Sotto-cartelle

| Cartella | Cosa contiene |
|---|---|
| [`parser-comparison/`](parser-comparison/) | Benchmark di **velocità** di estrazione dell'albero dei tag: pdfix vs opendataloader, su 33 PDF, con grafici |
| [`auto-tag-viewer/`](auto-tag-viewer/) | **Viewer HTML** dei bounding box dei tag + test di **auto-tagging** (generare tag su PDF non taggati) + confronto punteggi accessibilità |

## Sintesi dei risultati

### 1. Fedeltà di estrazione dei tag

opendataloader legge fedelmente l'albero dei tag esistente: heading con livello,
paragrafi, tabelle (righe/colonne/span), liste (chiave JSON `list items`), figure con
`alt` (+ estrae l'immagine), link. In più dà dati che pdfix non ha: `bounding box`,
`font`, `font size`, `text color`.

**Limite (nel JSON):** ogni cella tabella è serializzata come `pdfua_tag: "TD"` — nessun
flag header (`TH`/`scope`/`is_header`). L'informazione esiste (l'output HTML e il PDF
taggato hanno i `<th>`/`TH` corretti) ma il **serializzatore JSON la perde**. Anche
`Lbl`/`LBody` delle liste vengono fusi in un unico `content`.

→ Segnalato upstream: **[opendataloader-pdf#549](https://github.com/opendataloader-project/opendataloader-pdf/issues/549)**.

Conseguenza per avalpdf: usare il **solo JSON** di opendataloader regredirebbe il check
"tabella con header" (falsi positivi). Recuperabile via output HTML o un adapter.

### 2. Velocità (vedi `parser-comparison/`)

| | pdfix-sdk | opendataloader (per-file) | opendataloader (batch) |
|---|---|---|---|
| Tempo medio/doc | 508 ms | 2.19 s | 213 ms |

opendataloader è lento ad **avviarsi** (~1.5 s di JVM a ogni invocazione), non a estrarre.
Per singolo documento (modello attuale di avalpdf) pdfix vince ~4×; in batch (JVM
ammortizzata) opendataloader è più veloce e più regolare (pdfix ha varianza alta, fino
a un outlier da 8.3 s).

### 3. Auto-tagging (vedi `auto-tag-viewer/`)

opendataloader può **generare tag su PDF non taggati** (`-f tagged-pdf`):

- PDF **con testo** → tag semantici reali, comprese le celle header `TH`.
- PDF **scansionato** (senza layer di testo) → solo Figure (servirebbe OCR).

Sorpresa: su `compito.pdf` il PDF **auto-taggato** ha ottenuto un punteggio avalpdf
**superiore** all'originale taggato a mano (**77.64% vs 75.72%**), soprattutto perché ha
riconosciuto l'header di tabella che l'autore aveva lasciato come TD. (Un solo documento,
caso semplice — non una statistica.)

## Verdetto operativo

- **Parser di validazione**: tenere **pdfix** (albero dei tag fedele, più veloce per file
  singolo, è ciò su cui è scritto `validator.py`).
- **opendataloader** è prezioso come **complemento**: auto-tagging di PDF non taggati,
  dati di layout (font/bbox) per check nuovi (es. titoli visivi non taggati), batch veloce.
  Come sostituto del solo JSON regredisce gli header di tabella finché non si risolve #549.
