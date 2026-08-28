# Prompt prossima sessione

> **Ciclo audit 2026-08 APERTO il 28/8/2026.** Il ciclo 2026-07 è chiuso
> (indice e storico in `docs/storico/`).
>
> **F1 e F2 chiuse il 28/8** (verbali nello STORICO). F1: 1 HIGH attivo sui
> dati veri + 5 findings minori, tutti fixati tranne `F-DRIFT`. F2: 1 HIGH
> (open redirect sul login), 2 MEDIUM, 1 LOW — tutti fixati; resta aperto
> `F2-NOTEST` (zero test frontend). La prossima fase ⚪ APERTA è
> **F3 — Frontend `components/` condivisi**.
>
> **Due cose che F2 ha insegnato e che F3 eredita:**
> 1. **Il perimetro dichiarato elenca le pagine, non il percorso.** In F2 due
>    difetti su quattro — incluso l'HIGH — stavano nelle route API e in
>    `proxy.ts`, che il perimetro non nominava. Prima di leggere, misura anche
>    *chi chiama* e *chi è chiamato dai* file elencati.
> 2. **Leggi il consumatore, non fidarti del produttore.** L'open redirect
>    esisteva perché `proxy.ts` scriveva sempre un valore sicuro e nessuno
>    validava chi lo leggeva. È la stessa asimmetria del HIGH di F1.

## Mandato

Apri **`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08.md`** ed esegui **la prima
fase con stato ⚪ APERTA**. Solo quella. Non anticipare le successive.

Il file contiene, per ogni fase: perimetro con **path completi già misurati**,
ipotesi numerate da confermare o smontare, criterio di chiusura, comandi.
Non serve leggere le altre fasi né lo storico del ciclo precedente per iniziare.

## A fine sessione (obbligatorio)

1. Aggiorna lo **stato della fase** nella roadmap di
   `AUDIT_ONEFLUX_STATO_2026-08.md` (⚪→🟢 chiusa, o 🟡 con residui espliciti).
2. Scrivi il verbale dettagliato in
   **`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`**
   (creato con F1 — il nome matcha l'eccezione `.gitignore`
   `!AUDIT_ONEFLUX_STATO*.md`, quindi è tracciato da git).
3. `code-reviewer` sul diff cumulativo — **sempre**, anche sui fix piccoli.
4. Committa il doc **insieme** al codice che documenta.

## Le tre regole che sono costate di più

- **Ogni severità si riverifica sul DB live.** Nel ciclo 2026-07 è caduta
  **8 volte** una severità ereditata o proposta da un agente. Si fixa ciò che
  è attivo, non ciò che sembra grave.
- **Un perimetro dichiarato va misurato, non ricordato.** È risultato incompleto
  **4 volte** (chat 4 simboli→25, feature Tag 2 file→3, gli "11 file grandi" mai
  elencati, il "perimetro non letto" di §3c che nascondeva 2 HIGH da 70k e 730k).
- **Audit read-only prima di ogni fix**; remediation solo dopo conferma esplicita
  di Mattia. Ogni fix nuovo → test verificato **per mutazione, su copia in
  scratchpad**, mai sul file del branch.

## Stato di partenza (misurato il 28/8/2026)

- **~48.300 righe su 109.215 mai lette riga per riga (44%)** — il grosso è
  frontend (66% scoperto); le Edge Functions sono l'unico perimetro davvero
  completo.
- **Zero test frontend** (`0` file `.test.ts*`/`.spec.ts*`): l'unica rete è
  `tsc --noEmit` + `next build`.
- Suite Python: **11.239 passed**, gate coverage 45 in CI.

## Voci aperte che NON sono fasi

Due, entrambe deliberatamente rimandate il 28/8 con la loro ragione (dettaglio
nel file del ciclo): la **migrazione Argon2→Argon2** (`check_needs_rehash()` mai
chiamato) va fatta **quando** si alzano i parametri, non prima; la **copertura a
test delle 8 `@_make_cache`** va aperta **quando** serve un test su una di esse.
Si riprendono in **F7**, non prima.

## Verificato il 28/8 — l'auto-deploy in orario cliente è reale

Era annotato qui come "da verificare a mano su Railway". **Verificato: sì**, e il
problema è più generale del singolo push Argon2.

`/health` di Railway risponde `commit: 4c1d402cc6f4`, cioè l'HEAD di `main`,
mergiato alle **16:49 CEST**. Il commit Argon2 era entrato col merge delle
**12:36**. Fra le 12:44 e le 16:49 del 28/8 sono stati mergiati **5 PR**
(#37→#42): ognuno è un auto-deploy in fascia di servizio.

**Il punto strutturale**: CLAUDE.md dice "deploy solo fuori orario", ma con
auto-deploy su `main` **il momento del deploy è il momento del merge**. Finché
resta così, "mergio ora e deployo stasera" non è un'opzione disponibile — la
protezione va messa sul merge o disattivando l'auto-deploy Railway, non sulla
buona volontà di chi mergia. **Decisione aperta per Mattia**, non un'azione
già presa.
