# Open points — tool-manual-tagging

Idee e miglioramenti pianificati / da valutare. Non sono bug: lo strumento è funzionante, questi
sono passi successivi.

## UI / visualizzazione dell'albero

- [ ] **Alberatura collapsible** — poter espandere/comprimere i nodi contenitori (`L`, `Table`,
      `Sect`…) nell'albero dei tag, per navigare documenti grandi senza scroll infinito. Stato
      espanso/compresso per nodo, con "espandi/comprimi tutto".
- [ ] **Vista completa della struttura come sarà esportata** — accanto (o al posto di) la vista
      "sorgente", una vista che mostra **subito l'albero risultante dopo le mie modifiche**, già
      con le correzioni automatiche applicate. Esempi:
      - se trasformo un `P` in voce di elenco, vedere live la **terna completa** `L > LI > LBody`
        (non solo "LI"), così com'è nel PDF finale;
      - eliminazioni mostrate come *unwrap* (i figli risalgono) e contenuto come Artifact;
      - link creati mostrati come `Link` con la loro annotazione;
      - segnalibri generati dai titoli.
      In pratica: un "diff" o "anteprima dell'esportato" del tag tree.
- [ ] **Drag & drop** nell'albero per riordinare / re-annidare elementi (spostare un elemento
      sotto un altro genitore) senza passare da elimina+ricrea.

## Regole apprese

- [ ] **Clustering per ente** — raggruppare le regole per fonte/ente (es. "Comune di Messina") e
      distinguere regole che valgono quasi sempre per un ente da quelle universali. Oggi il
      clustering è implicito (il testo dell'ente è nelle firme); renderlo esplicito e mostrabile.
- [ ] **Modifica/eliminazione singola regola** dal pannello ✨ (oggi si può solo azzerare tutto).
- [ ] **Pruning / limiti** del file regole (LRU sulle chiavi `c`/`t` a bassa frequenza) per
      evitarne la crescita illimitata su molti documenti.
- [ ] **Spiegazione del suggerimento** — al passaggio del mouse, "perché lo suggerisco" (quale
      regola/firma e con quante conferme).
- [ ] Migrazione a **DB** (sostituendo solo `load_rules`/`save_rules`) se il volume cresce.

## Estrazione e link

- [ ] **Estrazione testo parziale** su certi font (alcune email risultano "@dominio…" senza la
      parte locale) → migliorare il fallback di decodifica / gestione encoding custom.
- [ ] **Link su sottostringa** — racchiudere in `Link` solo la porzione di testo linkabile dentro
      un paragrafo più lungo (oggi si avvolge l'intero elemento), con split del marked content.

## Conformità

- [ ] **ParentTree** per strutture marcate dentro **form-XObject** annidati (caso raro, oggi non
      gestito).
- [ ] **Validazione integrata** — eseguire veraPDF/PAC (o un sottoinsieme di regole) e mostrare gli
      esiti dentro lo strumento, per chiudere il ciclo correggi→valida.
- [ ] **Reading order** — strumento per ispezionare/riordinare l'ordine di lettura quando diverge
      dall'ordine visivo.
