# tool-manual-tagging

Editor web per **ispezionare e correggere manualmente i tag di struttura (PDF/UA)** di un PDF
taggato. Mostra il documento con i *bounding box* di ogni elemento dello *structure tree*
sovrapposti, a fianco dell'**albero dei tag** modificabile, e produce un **PDF realmente
ritaggato** e conforme ai principali controlli PDF/UA.

A differenza di una semplice visualizzazione, le modifiche vengono scritte **dentro lo structure
tree del PDF** (`StructTreeRoot → StructElem`), non in un overlay: il PDF scaricato è un PDF
ritaggato, con `ParentTree`, annotazioni, metadati e segnalibri coerenti.

---

## A cosa serve

I PDF generati da Word/Office sono taggati, ma spesso con errori (titoli sbagliati, link orfani,
paragrafi vuoti, liste non valide, immagini senza alt, lingua errata, niente segnalibri…). Lo
strumento serve a **vedere** la struttura reale, **capirla** (nomi leggibili, gerarchia, tipo
effettivo via `RoleMap`), **correggerla** e produrre un PDF aggiornato — imparando dai pattern
ricorrenti per velocizzare i documenti successivi.

---

## Requisiti e avvio

- [`uv`](https://docs.astral.sh/uv/) — l'unica dipendenza è `pikepdf`, installata al volo. Niente
  da installare a mano.
- Un browser moderno. `PDF.js` è caricato da CDN (serve Internet).

```bash
cd experiments/tool-manual-tagging
./serve.sh                       # porta libera automatica + apre il browser
./serve.sh /percorso/al/file.pdf # con un PDF iniziale
./serve.sh --no-open             # non aprire il browser
```

L'URL effettivo è stampato all'avvio (es. `http://localhost:36029/`).

> **Nota importante:** `viewer.html` viene riletto a ogni richiesta (basta ricaricare la pagina per
> vedere le modifiche al frontend), ma `tagtool.py` è caricato **all'avvio**: dopo averlo
> modificato **va riavviato il server**.

---

## Interfaccia

Schermo diviso in due metà (divisore trascinabile):

- **Sinistra — documento**: pagine renderizzate con i bbox colorati di ogni elemento; zoom
  (`− / % / +`), toggle etichette/box.
- **Destra — albero dei tag**: ricerca, chip-filtro (per tipo + Vuoti + Suggeriti + Link mancanti +
  Modificati), e l'elenco degli elementi con **nomi leggibili** ("Paragrafo", "Tabella", "Cella di
  intestazione"…), **icone**, codice tecnico (`P`, `Table`…), **guide ad albero** che mostrano
  l'annidamento, e azioni per riga.

Altre comodità: **tema chiaro/scuro** (persistito), pulsante **? Guida** in linguaggio semplice,
hover su un elemento che evidenzia anche ciò che contiene, scorciatoie (`/` ricerca, `Canc`/`M`
sulla selezione), pannello **⚙ Metadati** e pannello **✨ Regole apprese**.

---

## Funzioni di correzione

Tutte le modifiche restano **in sospeso** finché non premi *Scarica PDF taggato*; solo allora
vengono scritte in una **copia** del PDF (l'originale non viene toccato).

| Funzione | Cosa fa |
|---|---|
| **Cambia tag** | menu a tendina per riga (nomi leggibili, es. "Titolo 1 (H1)"). |
| **Elimina tag** (🗑) | rimuove il tag ma **mantiene i figli**: i tag interni vengono riagganciati al primo genitore superstite (*unwrap*); il **contenuto proprio** del tag diventa un **Artifact**. |
| **Elimina P vuoti** | un clic elimina tutti i paragrafi con contenuto vuoto (spazio/a-capo). |
| **Unisci** (⤵) | seleziona più elementi → vengono fusi nel primo (keeper); il contenuto degli altri viene spostato nel keeper. |
| **Decorativa** (🎨, sulle Figure) | all'export l'immagine diventa un **Artifact** (non più una Figure): risolve l'avviso "inappropriate use of a figure". |
| **Alt text** | campo `ALT` per le immagini: legge/scrive `/Alt`. |
| **Riquadro / bbox** (⤢) | editor a rettangolo con maniglie; la geometria viene scritta come attributo `/A /O /Layout /BBox`. |
| **Racchiudi in Link** (🔗) | il testo linkabile (URL/email) viene avvolto in un vero `Link`: retag a Link + **annotazione cliccabile** (`/URI` o `mailto:`) + `OBJR`. |

### Correzioni automatiche all'export (con PDF/UA attivo)

- **Liste valide** — dopo un retag a `LI`, la struttura viene completata in `L > LI > LBody`:
  ogni LI ottiene un `LBody` attorno al contenuto e gli LI consecutivi vengono raggruppati in un
  `L`. Risolve *"invalid use of an LI structure element"*.
- **Segnalibri** — se ci sono titoli (`H1…H6`) ma nessun outline, viene costruito l'albero dei
  **bookmark** annidato per livello (con destinazione alla posizione del titolo). Risolve
  *"headings without bookmarks"*.
- **Link orfani** — qualsiasi annotazione `Link` non contenuta in un elemento `Link` viene rimossa
  (insieme all'eventuale `OBJR` orfano). Risolve *"link annotation is not nested inside a Link
  structure element"* (es. dopo aver cambiato un `Link` in `P`).
- **ParentTree** — l'albero dei genitori strutturali (`/StructTreeRoot/ParentTree`) viene
  **ricostruito da zero** dopo ogni modifica strutturale, mappando ogni MCID e ogni annotazione al
  `StructElem` corretto e aggiornando `/StructParentsNextKey`. Previene gli errori *"Structural
  Parent Tree (ISO 32000-1)"*.
- **Metadati PDF/UA** — `MarkInfo/Marked`, `/Lang`, `ViewerPreferences/DisplayDocTitle`,
  `pdfuaid:part = 1`, e (dal pannello ⚙) **Titolo** (`/Title` + `dc:title`) e **Lingua** (default
  **it-IT**, modificabile).

---

## Memoria delle correzioni (regole apprese, contestuali)

Lo strumento **impara dai tuoi interventi** e li **suggerisce** (✨) quando ritrova lo stesso
pattern su documenti nuovi. Le regole sono salvate in **`learned_rules.json`** accanto a
`tagtool.py` → **persistono tra i riavvii** (nessun DB).

Ogni azione è registrata su **firme contestuali** a specificità decrescente — *mai* una regola
cieca tipo "tutti i P":

| Livello | Chiave | Significato |
|---|---|---|
| `c` | tag + tipo effettivo + genitore + **testo** | il caso preciso (es. «città di messina» in una Cella) |
| `t` | tag + **testo** | stesso tag e testo, qualsiasi contesto |
| `x` | tag + genitore + **forma** (insieme dei tag discendenti) | es. "Tabella contenente [Figure, P]" — qualsiasi testo |
| `s` | tag + tipo + genitore | struttura pura — qualsiasi testo |
| `g` | tag (solo per i **vuoti**) | es. "P vuoto" |

**Generalizzazione intelligente:** i livelli generali (`x`, `s`) si **attivano solo dopo** che la
stessa azione si ripete su **testi diversi** e con **alta coerenza** (`x`: ≥2 testi distinti e
≥75%; `s`: ≥3 testi e ≥85%). Si tiene traccia delle **varianti di testo** distinte per azione. Di
conseguenza:

- più documenti elabori, più il tool generalizza pattern reali (es. "elimina la tabella con questa
  struttura", indipendentemente dalla città);
- ma se elimini solo elementi *specifici*, la regola generale **non** si attiva (coerenza bassa) →
  non cancella mai tutto. Il pannello ✨ mostra ogni regola con livello, varianti e stato
  (*attiva* / *in apprendimento*) e permette di azzerare.

---

## Architettura

| File | Ruolo |
|------|-------|
| `tagtool.py` | **Backend**: server HTTP (stdlib) + tutta la logica PDF (`pikepdf`). |
| `viewer.html` | **Frontend**: pagina servita dal backend; rendering PDF (`PDF.js`) e UI. |
| `serve.sh` | Launcher: avvia su porta libera e apre il browser. |
| `learned_rules.json` | Memoria delle regole apprese (creato al primo apprendimento). |

Il backend tiene il PDF **in memoria** (`CURRENT`): non scrive nulla su disco finché non scarichi.

### Endpoint HTTP

| Metodo | Path | Descrizione |
|--------|------|-------------|
| `GET`  | `/` | la pagina (`viewer.html`) |
| `GET`  | `/structure.json` | struttura del PDF corrente (elementi + bbox + tag + flag) |
| `GET`  | `/document.pdf` | i byte del PDF corrente (per il rendering) |
| `POST` | `/upload` | carica un nuovo PDF (body = byte, header `X-Filename`) |
| `POST` | `/apply` | applica le modifiche e restituisce il PDF ritaggato |
| `GET`  | `/rules` | regole apprese (JSON) |
| `POST` | `/rules` | apprende osservazioni `{seen, acted}` |
| `POST` | `/rules/clear` | azzera le regole |

`POST /apply` accetta:

```jsonc
{
  "retag":  {"<idx>": "<NuovoTag>"},      // cambia /S (+ RoleMap per tipi custom)
  "delete": [<idx>, ...],                  // unwrap: tieni i figli, contenuto -> Artifact
  "merge":  [[keeper, other, ...], ...],   // fondi nel keeper
  "alt":    {"<idx>": "testo alternativo"},
  "bbox":   {"<idx>": [x0,y0,x1,y1]},      // attributo Layout /BBox
  "link":   [<idx>, ...],                   // testo linkabile -> vero Link + annotazione
  "title":  "Titolo del documento",
  "lang":   "it-IT",
  "pdfua":  true
}
```

Risponde con `application/pdf` e header di conteggio: `X-Retag`, `X-Deleted`, `X-Merged`, `X-Alt`,
`X-Bbox`, `X-Linked` (link creati), `X-Links` (orfani rimossi), `X-Lists` (liste sistemate),
`X-Outline` (segnalibri), `X-PDFUA`, `Content-Disposition`.

---

## Dettagli tecnici

- **Indice stabile** — `walk_elements()` attraversa lo `StructTreeRoot` in profondità (ordine di
  lettura); la posizione nella lista è la **chiave stabile** per applicare le modifiche
  (estrazione e applicazione ripartono sempre dagli stessi byte).
- **Bounding box da MCID** — `page_mcid_data()` parsa il content stream (CTM, stato del testo,
  stack `BDC/BMC/EMC`, `Tj/TJ/'/"`, `Do`) e calcola bbox + testo per ogni MCID. Le bbox sono
  calcolate **per pagina**: un elemento a cavallo di due pagine ottiene **un box per pagina**
  (niente più box giganti).
- **Testo via `/ToUnicode`** — i font sottoinsiemati/Type3 usano codici custom (1,2,3…); il testo
  reale è nel CMap `/ToUnicode`, che viene interpretato (`beginbfchar`/`beginbfrange`). Senza,
  intestazioni come "Comune di Palermo" apparirebbero come caratteri di controllo.
- **Pagina da MCR** — gli elementi senza `/Pg` proprio ricevono la pagina dal loro `/MCR`.
- **RoleMap** — `resolve_role()` segue la catena (`Title → H1`, …) fino a un tipo standard, mostrato
  come "tipo effettivo".
- **Eliminazione = unwrap + artifact** — un tag eliminato non porta via il sottoalbero: i figli
  salgono al genitore reale (individuato scansionando l'albero **vivo**), il contenuto proprio
  diventa `/Artifact BMC` nel content stream (l'MCID sparisce, niente contenuto reale non taggato).

---

## Controlli PDF/UA / qualità affrontati

- Marked Content / Structural Parent Tree (ISO 32000-1) — ricostruzione `ParentTree`.
- Link annotation not nested inside a Link structure element — rimozione orfani.
- Completeness of "Link" elements — testo linkabile → vero `Link`.
- Invalid use of an `LI` structure element — `L > LI > LBody`.
- Headings without bookmarks — outline generato dai titoli.
- Possibly inappropriate use of a Figure — "segna come decorativa" (Artifact).
- Figure senza alt, lingua mancante/errata, titolo mancante — alt / lingua (default it-IT) /
  titolo nei metadati.

---

## Limiti e note

- **Richiede un PDF già taggato** (con `StructTreeRoot`): corregge, non crea la struttura ex-novo.
- **Non garantisce** la piena conformità PDF/UA: valida sempre con [veraPDF](https://verapdf.org/)
  o PAC. Lo strumento risolve i controlli sopra ma il giudizio finale resta la correttezza dei tag.
- **Racchiudi in Link** usa il testo estratto dell'elemento: se l'estrazione è parziale (alcuni
  font perdono parte del testo) l'URL può non essere riconosciuto; avvolge l'intero elemento (non
  una sottostringa).
- **ParentTree**: la ricostruzione copre pagine e annotazioni; strutture marcate dentro
  form-XObject annidati (rare) non sono gestite.
- Vedi **`OPEN_POINTS.md`** per i miglioramenti pianificati.
