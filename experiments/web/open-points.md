# Punti aperti

Una nota onesta: i problemi a livello di testo/documento (tagging, titolo, lingua, accenti, maiuscole spaziate) non hanno un'area univoca e restano solo nel report; gli elementi vuoti senza contenuto non hanno un box disegnabile (è il caso di inconferibilità.pdf, dove le celle vuote si evidenziano tramite la tabella che le contiene).

- **Sezione "Punteggio per categoria" — da ripensare**: capire come renderla più
  chiara e utile. Oggi mostra per ogni criterio la percentuale (0–100%) e il "peso"
  sul punteggio complessivo, ma resta poco intuitiva. Idee da valutare: spiegare/visualizzare
  meglio il legame peso → punteggio finale (es. contributo effettivo in punti),
  raggruppare i criteri per area (Base / Struttura / Contenuti / Formattazione),
  evidenziare solo i criteri problematici, eventualmente collegare ogni categoria ai
  controlli del "Dettaglio controlli" e agli standard di riferimento. Da ripensare.
- **Drill-down sulle bbox annidate — ancora da sistemare**: il click sulle bbox per
  navigare tra tag contenitori e tag contenuti non è ancora soddisfacente/intuitivo.
  Esiste il navigatore (breadcrumb + ↑ Contenitore / ↓ Contenuto / ← → fratelli e il
  targeting del tag più interno via z-index), ma l'interazione va resa più chiara e
  affidabile (es. evidenziare l'elemento sotto il cursore prima del click, gestire
  meglio i box che si sovrappongono perfettamente, dare un feedback più evidente sul
  livello selezionato). Da rivedere.

## Standard internazionali da controllare

Obiettivo: mappare i check di avalpdf sugli standard di riferimento e indicare, per
ogni risultato, a quale norma/criterio si riferisce (come fanno i validatori di
settore). Ispirazione (da cui prendere spunto, eventualmente adattando il codice):

- <https://pdf4wcag.com/validate/about> — checker PDF/UA + WCAG.
- <https://pdf4wcag.com/validate/wcag-2-2-machine> — elenco dei criteri di successo
  **WCAG 2.2 verificabili automaticamente** (*machine-testable*) sui PDF. Utile per
  separare ciò che avalpdf può controllare in automatico da ciò che richiede
  revisione umana, e per decidere quali nuovi controlli automatizzare.

Standard e linee guida da considerare:

- **PDF/UA-1 — ISO 14289-1**: requisiti di accessibilità per i PDF taggati (è il
  riferimento principale per i check attuali di avalpdf).
- **PDF/UA-2 — ISO 14289-2**: versione su PDF 2.0 (tabelle, MathML, annotazioni…).
- **ISO 32000-1 / ISO 32000-2 (PDF 2.0)**: specifica del formato e del *Tagged PDF*
  (struttura logica, StructTreeRoot, RoleMap) su cui poggiano i controlli.
- **Matterhorn Protocol (PDF Association)**: 31 checkpoint / 136 *failure conditions*
  per verificare la conformità a PDF/UA — utile come checklist per nuovi controlli e
  per distinguere ciò che è verificabile automaticamente da ciò che richiede
  controllo umano.
- **WCAG 2.1 / 2.2 (W3C), livello AA**: criteri di successo applicati ai PDF tramite
  le *W3C PDF Techniques* (es. testo alternativo, ordine di lettura, intestazioni,
  contrasto, lingua, titolo del documento).
- **EN 301 549**: standard europeo richiamato dalla Direttiva UE 2016/2102 e
  dall'European Accessibility Act; il capitolo sui documenti rimanda a WCAG + PDF/UA.
- **Section 508 (USA)** e **Revised 508 / WCAG 2.0 AA**: riferimento extra-UE.
- **Contesto italiano**: Legge Stanca (L. 4/2004) e **Linee guida AgID** sull'accessibilità,
  che adottano WCAG/EN 301 549 per la PA — rilevante perché il tool usa Bootstrap Italia.

Idea di implementazione: aggiungere a ciascun finding del report un riferimento
(es. `PDF/UA 7.1`, `WCAG 1.1.1`, `Matterhorn 09-001`) e un filtro/legenda per standard,
così l'utente capisce quale norma viene violata e perché. Inoltre, sull'esempio della
pagina *wcag-2-2-machine*, distinguere nel report i controlli **automatici** (verificati
da avalpdf) da quelli **da verificare manualmente** (criteri non automatizzabili), per
non dare un falso senso di completezza.

## Idee per il futuro

- **Raccolta lead con form opzionale**: durante/dopo il check, mostrare un **form
  facoltativo** per raccogliere i dati di contatto dell'utente (es. nome, email,
  ente/organizzazione) così da poterlo ricontattare (assistenza, remediation dei PDF,
  offerta di servizi). Deve restare **opzionale**: l'analisi funziona anche senza
  compilarlo.
  - Attenzione privacy/GDPR: il sito oggi è 100% locale e non invia il PDF da nessuna
    parte; introdurre la raccolta di **dati personali** richiede informativa privacy,
    base giuridica/consenso esplicito, finalità chiare (contatto/marketing) e un
    backend dove salvarli. Tenere ben separata questa parte dall'analisi del documento.
