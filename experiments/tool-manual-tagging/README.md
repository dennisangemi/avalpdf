# tool-manual-tagging

Editor web per **ispezionare e correggere manualmente i tag di struttura (PDF/UA)** di un PDF
taggato. Mostra il PDF con i *bounding box* di ogni elemento dello *structure tree* sovrapposti,
permette di riassegnare il tag di ciascun elemento da un menu a tendina e di **scaricare il PDF
con i tag riscritti**, opzionalmente marcato come **PDF/UA-1**.

A differenza di una semplice visualizzazione, le modifiche vengono scritte **dentro lo structure
tree del PDF** (`StructTreeRoot → StructElem → /S`), non in un overlay: il PDF scaricato è un PDF
realmente ritaggato.

---

## A cosa serve

I PDF generati da Word/Office sono taggati, ma spesso con errori (es. tutti i titoli a `H1`, il
titolo del documento come tipo custom `Title`, gerarchia dei heading assente, ecc.). Questo
strumento serve a:

- **vedere** la struttura reale del PDF, elemento per elemento, sovrapposta al contenuto;
- **capire** il tipo effettivo di ogni elemento risolvendo la `RoleMap` (es. `Title → H1`);
- **correggere** i tag manualmente e produrre un PDF aggiornato;
- **dichiarare PDF/UA-1** aggiungendo il marcatore e i prerequisiti di base.

---

## Requisiti

- [`uv`](https://docs.astral.sh/uv/) (gestione dipendenze Python). L'unica dipendenza è
  `pikepdf`, installata al volo da `uv` — non serve installare nulla manualmente.
- Un browser moderno. `PDF.js` viene caricato da CDN (serve connessione a Internet).

## Avvio

Il modo più semplice è lo script `serve.sh`: sceglie **una porta libera automaticamente** e apre
il browser.

```bash
cd tool-manual-tagging

./serve.sh                       # parte senza PDF: caricalo dalla pagina
./serve.sh /percorso/al/file.pdf # con un PDF iniziale
```

In alternativa, direttamente:

```bash
uv run --with pikepdf python3 tagtool.py                 # porta libera + apre il browser
uv run --with pikepdf python3 tagtool.py file.pdf        # con PDF iniziale
uv run --with pikepdf python3 tagtool.py --port 8080     # porta fissa
uv run --with pikepdf python3 tagtool.py --no-open       # non aprire il browser
```

Opzioni: `--port N` (0 = porta libera automatica, default) · `--no-open` (non aprire il browser).
L'URL effettivo viene stampato all'avvio (es. `http://localhost:36029/`).

## Flusso d'uso

1. Carica un PDF taggato (📄 *Carica PDF* o trascinandolo nella finestra).
2. Nella sidebar vedi tutti gli elementi in ordine di lettura, con gerarchia (`Lbl` dentro `LI`
   dentro `L`…), il testo e — se rimappati — il tipo effettivo (`Title → H1`).
3. Cambia il tag di un elemento dal menu a tendina: il box sul PDF e l'etichetta si ricolorano,
   l'elemento è marcato come *modificato*.
4. (Opzionale) lascia attiva la casella **PDF/UA** per marcare il file come PDF/UA-1.
5. **Scarica PDF taggato** → ottieni `<nome>.ua.tagged.pdf` con i `/S` riscritti.

---

## Architettura

| File | Ruolo |
|------|-------|
| `tagtool.py` | **Backend**: server HTTP (stdlib) + tutta la logica PDF (`pikepdf`). |
| `viewer.html` | **Frontend**: pagina servita dal backend; rendering PDF (`PDF.js`) e UI. |
| `serve.sh` | Launcher: avvia su porta libera e apre il browser. |

Il backend tiene il PDF **in memoria** (`CURRENT`): non scrive nulla su disco finché non scarichi
il risultato. `viewer.html` viene letto da disco a ogni richiesta (basta ricaricare la pagina per
vedere le modifiche al frontend); il codice di `tagtool.py` invece è caricato all'avvio, quindi
dopo averlo modificato va **riavviato il server**.

### Endpoint HTTP

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET`  | `/` | la pagina (`viewer.html`) |
| `GET`  | `/structure.json` | struttura del PDF corrente (elementi + bbox + tag) |
| `GET`  | `/document.pdf` | i byte del PDF corrente (per il rendering) |
| `POST` | `/upload` | carica un nuovo PDF (body = byte del file, header `X-Filename`) |
| `POST` | `/apply` | applica le modifiche e restituisce il PDF ritaggato |

`POST /apply` accetta `{"tags": {"<idx>": "<NuovoTag>", ...}, "pdfua": true}` e risponde con
`application/pdf` (header `X-Tags-Changed`, `X-PDFUA`, `Content-Disposition`).

---

## Come funziona (dettagli tecnici)

### 1. Lettura dello structure tree
`walk_elements()` attraversa `StructTreeRoot` in profondità (ordine di lettura) e produce una
lista piatta di elementi. La **posizione nella lista è la chiave stabile** usata per applicare le
modifiche: estrazione e applicazione ripartono sempre dagli stessi byte, quindi l'indice è
deterministico (non si usano i numeri d'oggetto, che `pikepdf` rinumera al salvataggio).

### 2. Bounding box da MCID
Ogni `StructElem` foglia punta a un *marked content* (MCID) su una pagina. `page_mcid_data()`
**parsa il content stream** (`pikepdf.parse_content_stream`) tracciando:
- la matrice CTM (`q`/`Q`/`cm`),
- lo stato del testo (`BT`/`ET`/`Tm`/`Td`/`TD`/`T*`/`Tf`/`Tc`/`Tw`),
- lo stack del marked content (`BDC`/`BMC`/`EMC`, leggendo `/MCID`),
- gli operatori di disegno (`Tj`/`TJ`/`'`/`"` per il testo con le `Widths` dei font; `Do` per le
  immagini, bbox = quadrato unitario trasformato dalla CTM).

Da qui calcola la bbox (e il testo) di ogni MCID, poi le unisce per elemento (i contenitori senza
MCID propri, come `L`/`LI`, ricevono l'unione delle bbox dei figli). Le bbox risultano accurate
(immagini esatte, testo entro ~1pt; la minima differenza viene dalla stima ascender/descender,
ininfluente per l'overlay).

### 3. Risoluzione della RoleMap
`Title` non è un tipo standard PDF: Word lo emette come tipo custom e lo rimappa via
`StructTreeRoot/RoleMap` (`Title → H1`, `Header/Footer → Sect`, `Footnote → Note`, …).
`resolve_role()` segue la catena della RoleMap fino a un tipo standard, così la UI mostra il
**tipo effettivo** accanto a quello grezzo (`Title → H1`) e colora i box di conseguenza.

### 4. Scrittura dei tag
`apply_tags()` riapre il PDF dai byte correnti, ricammina con `walk_elements()`, e per ogni indice
nella mappa imposta `elem.S = /NuovoTag`. Se il tag scelto **non** è standard, aggiunge la voce
corrispondente alla `RoleMap` (mappandolo a `Span`). Salva su un buffer in memoria.

### 5. Marcatura PDF/UA-1
`mark_pdfua()` imposta in modo idempotente i prerequisiti raggiungibili a questo livello:
- `MarkInfo/Marked = true`,
- `/Lang` sul catalogo (se assente),
- `ViewerPreferences/DisplayDocTitle = true`,
- `pdfuaid:part = 1` nei metadati XMP (`open_metadata()`).

---

## Limiti e note

- **Richiede un PDF già taggato**: un PDF senza `StructTreeRoot` viene rifiutato (non ci sono tag
  da modificare; questo strumento corregge, non crea ex-novo la struttura).
- **Conformità PDF/UA**: la marcatura fa *dichiarare* il file PDF/UA-1 e soddisfa i prerequisiti
  di metadati/struttura di base, ma **non garantisce** la conformità piena. Validare con
  [veraPDF](https://verapdf.org/) o PAC. La sostanza resta la correttezza dei tag assegnati.
- **Stato in memoria**: caricare un nuovo PDF scarta le modifiche non ancora scaricate del
  precedente. Nessuna persistenza tra riavvii del server.
- **Indipendente da `compito.json`**: non usa annotazioni esterne; lavora solo sulla struttura
  reale del PDF.
