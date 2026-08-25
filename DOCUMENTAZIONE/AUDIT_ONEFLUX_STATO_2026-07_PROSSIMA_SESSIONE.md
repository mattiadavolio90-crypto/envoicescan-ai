# Prompt per la prossima sessione di audit — ciclo ONEFLUX 2026-07

> Copia il blocco qui sotto come primo messaggio della nuova sessione.
> Scritto il 25/8/2026 all'apertura di §3c, dopo la chiusura di §3b (chat
> `fastapi_worker.py`, deploy `d92de1d`).

---

Continua il ciclo di audit ONEFLUX 2026-07. Leggi prima
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07.md` (indice, ~1 minuto) — in
particolare §3c e "Chiusura del ciclo" in fondo. Apri
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07_STORICO.md` solo per il dettaglio
della sezione che riapri.

## Stato del ciclo

**§1 e §3b sono vuote.** Restano aperte **§2** e **§3c** — il ciclo si chiude
solo quando entrambe sono vuote, non quando la tabella delle 10 dimensioni è
tutta 🟢 (lo è già dal 4/8: "tabella verde" non vuol dire "app coperta", è la
lezione che ha aperto sia §3b che §3c).

## Ordine di lavoro per questa sessione: prima chiudere il ciclo, poi nuove dimensioni

Priorità decisa da Mattia: **completare §3c (e se c'è tempo/volontà anche §2)
prima di aprire qualunque nuova dimensione o nuovo ciclo**. Non iniziare lavoro
su "nuove dimensioni" finché §3c non è almeno avviata con una prima passata
chiusa — altrimenti si ripete l'errore già corretto due volte in questo ciclo
(dichiarare coperto qualcosa mentre resta un gap noto e non tracciato).

### Passo 1 — §3c: lettura sistematica del frontend (nuovo, mai iniziato)

Obiettivo: lo stesso tipo di lettura riga-per-riga già fatta in §3b sul Python,
applicata ai client component grandi del frontend Next.js — con l'obiettivo
dichiarato di trovare **divergenze frontend↔backend** (campi ignorati, calcoli
duplicati lato client che il backend ha già cambiato, stati derivati invece che
letti dall'API) e **incoerenze fra pagine** che mostrano lo stesso dato in punti
diversi. Non è un audit di stile — quello la dimensione 6 (Qualità/UI) l'ha già
fatto il 4/8.

**Perché non è teorico**: nel ciclo, senza mai cercarlo apposta, sono già
emersi 3 precedenti di questa classe di bug:
1. Tag: un fix corretto lato worker che il frontend scartava (campi nuovi
   ignorati dal client).
2. Tag: la stessa regola corretta in un solo punto di calcolo su due — KPI e
   trend mostravano due prezzi diversi nella stessa risposta.
3. Admin: un `Select` shadcn con API sbagliata (componente muto, `return null`
   di design) — il filtro periodo dei costi AI non apriva nulla.

**Perimetro**: gli 11 file grandi già nominati nel verbale della dimensione 6
(STORICO §6, 4/8) come "letti solo per grep mirato, non riga per riga". Tre
sono già noti: `scadenziario-client.tsx`, `analisi-e-tag-client.tsx`,
`calcolo-tab.tsx`. **Prima cosa da fare in sessione**: aprire STORICO §6 e
recuperare l'elenco completo degli altri 8 prima di scegliere l'ordine — non
indovinarli.

**Non ancora iniziata**: nessuna passata `oneflux-audit` lanciata su questo
perimetro. Parti da qui.

### Passo 2 — se resta tempo/volontà: §2

Il mock globale di `tests/conftest.py` (`openai`, `requests`, `argon2`,
`xmltodict`, `supabase`, `tenacity` — tutti installati davvero ma mockati,
il che rende vacui i test sui rami `except`). Lavoro lungo e dichiarato
(rilancia ~11.000 test): **non aprirlo di default**, solo se Mattia lo chiede
esplicitamente in sessione o se §3c si chiude presto e resta tempo.

### Passo 3 — solo a ciclo chiuso: nuove dimensioni / nuovo ciclo

Quando sia §2 sia §3c sono vuote, la procedura di chiusura è già scritta in
fondo all'indice ("Chiusura del ciclo"): timbro data, spostare index+STORICO in
`docs/storico/`, aprire `AUDIT_ONEFLUX_STATO_2026-10.md` per il ciclo
successivo. **Non farlo preventivamente** — solo su richiesta esplicita di
Mattia a quel punto, e solo dopo aver verificato che entrambe le sezioni siano
davvero vuote (non "quasi", vuote).

## Metodo del ciclo (non derogare)

- Audit read-only con `oneflux-audit` (Sonnet) **prima** di qualunque fix.
- Remediation **solo dopo conferma esplicita di Mattia** — mai auto-fixare.
- **Riverifica sempre severità e conteggi dell'agente** sul DB live (Supabase
  MCP) o eseguendo il codice. In questo ciclo è successo **4 volte** che una
  severità cadesse a una query, quasi sempre quando l'agente stesso dichiarava
  "non ho accesso al DB, questo numero va misurato" — quel numero è quasi
  sempre quello che decide la severità.
- `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
- Ogni fix richiede test nuovi **verificati per mutazione** (rimuovi il fix, il
  test deve cadere). Mutazione **solo su copia in scratchpad**, mai sul file
  nel branch di lavoro. Verifica `git branch --show-current` prima di ogni
  mutazione se non sei sicuro di essere sul branch giusto.
- "Deployato" non è una prova: verifica con `git log -- <file>` e con `/health`
  del worker Railway (`https://worker-production-a552.up.railway.app/health`,
  espone il commit deployato).
- La CI di GitHub Actions parte solo su push a `main`/`progetto` o su
  `pull_request`, mai su push a un branch feature qualsiasi. Se non puoi aprire
  una PR, il sostituto è rieseguire in locale i comandi che la CI userebbe
  (leggili nei workflow file), non dichiarare il lavoro bloccato.
- Per il frontend: non esiste alcun test (`0` file `.test.ts*`/`.spec.ts*`),
  quindi la mutazione va verificata leggendo/eseguendo il comportamento
  (`tsc --noEmit`, `next build`, o eseguendo manualmente il percorso) — non
  aspettarti una suite Jest/Vitest da far cadere.
- Migration solo con conferma esplicita, e **applicata prima del deploy**.
- Aggiorna indice **e** STORICO a fine sessione, barrando con
  `~~voce~~ — CHIUSA il gg/mm`.

## Lezioni recenti che valgono ancora

1. **Il perimetro dichiarato può essere incompleto.** In §3b è successo 4
   volte (l'ultima: la chat dichiarava "4 funzioni", erano 25 simboli). Per
   §3c: non fermarti ai file nominati esplicitamente se durante la lettura
   trovi un import/consumatore imprevisto.
2. **Un fix su un endpoint non è consegnato finché il consumatore non lo usa**
   — la ragione stessa per cui §3c esiste.
3. **Se una regola è scritta in più punti, cercali tutti.** Correggerne solo
   alcuni produce numeri diversi per lo stesso dato nella stessa vista.
4. **Se durante la sessione noti cambi di branch/commit che non hai comandato
   tu, qualcun altro sta scrivendo sullo stesso repository.** Fermati e chiedi
   prima di qualunque merge — mai un force-push o uno sconfitto silenzioso del
   lavoro altrui.
