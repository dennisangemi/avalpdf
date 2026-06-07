# avalpdf web

Interfaccia web locale per il motore di analisi accessibilità **avalpdf**.

Carichi un PDF, l'app esegue tutti i controlli di accessibilità (PDF/UA) del
motore avalpdf e ti mostra:

- **punteggio pesato** complessivo e **punteggio per categoria** (tag, titolo,
  lingua, titoli, alt text, tabelle, elenchi, link, formattazione, …);
- **elenco dei controlli** suddiviso in *problemi*, *warning* e *superati*,
  filtrabile per gravità;
- **informazioni del documento** (titolo, lingua, taggato, pagine, software, …);
- **anteprima del PDF** (pdf.js) con i **bounding box** dei problemi
  evidenziati: immagini senza testo alternativo, elementi vuoti, link sospetti,
  titoli, tabelle, elenchi. Cliccando un controllo localizzabile l'area
  corrispondente viene evidenziata sul documento.

Tutto gira **localmente**: il PDF non viene salvato su disco dal server, è
tenuto in memoria solo per la durata della singola analisi e renderizzato nel
browser.

## Avvio

```bash
cd experiments/web
./serve.sh
```

Lo script usa [`uv`](https://docs.astral.sh/uv/) e scarica al volo le dipendenze
(`pdfix-sdk`, `pikepdf`, `rich`, `requests`) — non serve preparare un
virtualenv. All'avvio viene aperto il browser su `http://127.0.0.1:8000/`.

Opzioni utili:

```bash
./serve.sh --port 9000      # porta diversa
./serve.sh --no-open        # non aprire il browser
```

## Come funziona (architettura)

```
browser ──(PDF bytes)──▶  POST /api/analyze  ──▶  avalpdf engine (report)
   │                                          └─▶  pikepdf (struttura + bbox)
   └─ pdf.js render + overlay bbox  ◀── JSON {report, structure}
```

- `app.py` — server HTTP (stdlib), endpoint `/api/analyze`. Esegue il vero
  motore avalpdf (`pdf_to_json` → `extract_content` → `create_simplified_json`
  → `AccessibilityValidator` con tutti i 14 validatori) e restituisce il report
  JSON arricchito (categorie con etichette IT, gravità).
- `bbox.py` — estrazione della struttura (StructTreeRoot) con un **bounding box
  per ogni elemento**, ricostruito dal content stream con pikepdf. È un
  adattamento di sola lettura dell'estrattore di
  `../tool-manual-tagging/tagtool.py`. avalpdf di suo **non** esporta le
  coordinate: i box vengono calcolati qui per poterli disegnare sul PDF.
- `static/` — SPA con [Bootstrap Italia](https://italia.github.io/bootstrap-italia/)
  (design system `.italia`) + CSS/JS personalizzati.

## Note

- I controlli a livello di testo o di documento (tagging, titolo, lingua,
  accenti, maiuscole spaziate, spazi/underscore) non hanno un'area univoca e
  non vengono evidenziati sul PDF; restano comunque elencati nel report.
- L'overlay usa le coordinate utente del PDF: documenti con pagine ruotate o
  con `MediaBox` non standard potrebbero mostrare box leggermente disallineati.
