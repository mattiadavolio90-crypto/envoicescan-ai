# Prompt per la prossima sessione — chiusura ciclo audit 2026-07

Contesto: leggi `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07.md` (indice, 1
minuto) e `..._STORICO.md §29` (dettaglio dell'ultima sessione, 26/8/2026) prima
di iniziare. Il ciclo NON è chiuso: restano §2 e §3c.

## Priorità, in ordine

### 0. Prima di tutto: conferma deploy
La sessione del 26/8 ha mergiato in `main` (PR #24, commit `188d11f`) ma non
ha potuto verificare `/health` del worker Railway (nessun URL disponibile
nell'ambiente). Verificalo prima di aprire qualunque nuovo lavoro:
```
curl <url-worker-railway>/health
```
Controlla anche che il commit visibile in `/health` coincida con `188d11f` o
successivo, e fai un giro su Analisi Fatture/Margini in produzione.

### 1. Il MEDIUM residuo (richiede tua conferma esplicita, poi Opus)
Divergenza sede-singola↔catena sulle note di credito: **236,23 €**
(402.182,19 vs 402.418,42), 3 righe con `prezzo_unitario <= 0` escluse da
6 RPC `gruppo_tag_*`. Serve una **migration** che filtri `prezzo_unitario > 0`
in modo coerente — cambia totali di catena già mostrati ai clienti, quindi
non partire senza che Mattia l'abbia vista e confermata esplicitamente.
Dettaglio: STORICO §25 e §28.

### 2. `stash@{0}` sul branch (ex `audit-s3c-passata1`, ora solo remoto)
Contiene modifiche della sessione parallela di Mattia (hook/skill Claude
Code) che potrebbero già essere sovrapposte al commit `5c03119` già in
`main`. Va verificato e recuperato o scartato esplicitamente — non toccarlo
alla cieca, potrebbe contenere lavoro non ancora salvato altrove.

### 3. Perimetro §3c non ancora letto
Audit read-only con `oneflux-audit`, poi remediation solo dopo conferma:
- `carica-ricavi-dialog.tsx` — dove si SCRIVE la modalità mensile (il
  perimetro già chiuso ha corretto solo la lettura)
- `pivot-tab.tsx`, `score-tab.tsx`
- `catena/*`
- altri tab di `workspace/` e `admin/`
- `m/diario/*`

### 4. Quattro punti aperti da §27
Canale SDI (decisione di policy), `pagata_at` locale vs UTC (residuo),
flush PROP-1 prima del blocco, `get_trial_info` per file. Dettaglio STORICO
§27.

### 5. §2 — resta intatta
Il mock globale di `tests/conftest.py`. Lavoro lungo, dichiarato apposta:
non aprirlo senza tempo dedicato e senza che Mattia l'abbia deciso per quella
sessione specifica.

## Metodo (non derogabile, vale per tutte le voci sopra)

- Audit **read-only** prima di qualunque fix; remediation solo dopo conferma
  esplicita di Mattia.
- Ogni severità dell'agente **si riverifica** sul DB live (Supabase MCP) o
  eseguendo il codice — non fidarsi del report a occhio. In questo ciclo è
  già capitato più volte che un numero riportato fosse gonfiato o sbagliato.
- `code-reviewer` sul diff cumulativo **a fine sessione, sempre** — anche sui
  fix che sembrano piccoli. È dove è saltato in passato, ed è quello che il
  26/8 ha trovato il bug più serio della sessione (contaminazione fornitore
  in `ricategorizza_sede.py`), su un fix che sembrava innocuo.
- Ogni fix nuovo richiede test verificati **per mutazione, su copia in
  scratchpad**, mai sul file del branch di lavoro.
- Migration solo con conferma esplicita, applicata **prima** del deploy.
- CI parte solo su `pull_request` o push a `main`/`progetto` — un branch
  pushato da solo non attiva nulla. Serve aprire la PR (richiede intervento
  umano: niente `gh` autenticato in questo ambiente).
- Deploy solo fuori orario clienti (sera/notte/mattina presto), salvo
  conferma esplicita e specifica di Mattia per un'eccezione — non basta un
  "sì" generico dato prima di sapere l'orario.
- Aggiorna indice e STORICO a fine sessione, in una sezione nuova numerata in
  sequenza (prossima: §30).
