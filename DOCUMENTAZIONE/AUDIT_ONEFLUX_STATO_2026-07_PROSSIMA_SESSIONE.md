# Prompt per la prossima sessione di audit — ciclo ONEFLUX 2026-07

> Copia il blocco qui sotto come primo messaggio della nuova sessione.
> Scritto il 24/8/2026 a valle della sessione sulla feature Tag.

---

Continua il ciclo di audit ONEFLUX 2026-07. Leggi prima
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07.md` (indice, ~1 minuto) e apri
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07_STORICO.md` solo per il dettaglio
della sezione che riapri (la sessione Tag è §22).

## PRIMA DI TUTTO: chiudere il deploy rimasto in sospeso

La sessione del 24/8 (feature Tag) è **completa e verificata in locale ma NON
deployata**. Il branch `audit-s3b-tag` è pushato su origin con 5 commit, ma:
- la **PR non è stata aperta** e la **CI non è mai girata** su questo codice
- in quella sessione `gh` non era installato e l'API GitHub era bloccata
- il merge locale era possibile ma è stato **deliberatamente evitato**: è
  l'errore già registrato nel caso Database del 30/7

Primo compito: aprire la PR `audit-s3b-tag` → `main`, attendere i 4 check
(pytest, deno-test, check-drift, verify-requirements), mergiare e **verificare
`/health` del worker Railway** (espone il commit deployato). Solo dopo,
aggiornare l'indice sostituendo il blocco "⏳ NON ancora deployato" con gli
estremi reali del merge, e barrare la voce.

Se la CI fosse rossa, il fix va fatto **prima** di qualunque nuovo audit.

## Poi: l'ultima voce di §3b

Resta solo la **chat di `fastapi_worker.py`**: `_chat_query_costi`,
`_chat_loop_openai`, `_build_chat_system_prompt`, `_chat_trend_prezzo`.

Cosa si sa già, da non rimisurare:
- esposizione **bassa**: 4 chiamate negli ultimi 30 giorni (misurato l'11/8)
- **nessun `@retry`/tenacity** nel file, quindi non eredita il problema del mock
  globale di `conftest.py`
- `fastapi_worker.py` è già passato da 37% a 46% con la tranche MOL+briefing
  (10/8, §19). `_run_agent_notturno` resta escluso per scelta: 125 statement
  scoperti ma `agent_notturno.enabled=false` dal 30/5, coprirlo non difende
  nessun cliente

Quando anche questa è chiusa, **§3b è vuota** e resta solo §2 per chiudere il
ciclo (vedi "Chiusura del ciclo" in fondo all'indice).

## Metodo del ciclo (non derogare)

- Audit read-only con `oneflux-audit` (Sonnet) **prima** di qualunque fix.
- Remediation **solo dopo conferma esplicita di Mattia** — mai auto-fixare.
- **Riverifica sempre severità e conteggi dell'agente** sul DB live (Supabase
  MCP) o eseguendo il codice. In questo ciclo è successo **4 volte** che una
  severità cadesse a una query: l'ultima il 24/8, quando l'agente dava per
  attivo un difetto che 0 righe su 2.016 attivavano.
  ⚠️ **Se l'agente dichiara "non ho accesso al DB, questo numero va misurato",
  quel numero è quasi sempre quello che decide la severità: misuralo tu.**
- `code-reviewer` sul diff cumulativo a fine sessione, **sempre**. Il 24/8 ha
  intercettato un fix che *spostava* l'incoerenza invece di eliminarla.
- Ogni fix richiede test nuovi **verificati per mutazione** (rimuovi il fix, il
  test deve cadere). Mutazione su **copia in scratchpad** finché il lavoro non è
  committato — il criterio non è "il diff è piccolo" ma "esiste un commit a cui
  tornare".
- "Deployato" non è una prova: verifica con `git log -- <file>` e con `/health`.
- Migration solo con conferma esplicita, e **applicata prima del deploy**.
- Aggiorna indice **e** STORICO a fine sessione, barrando con `~~voce~~ — CHIUSA il gg/mm`.

## Tre lezioni della sessione Tag, che valgono per la prossima

1. **Il perimetro dichiarato nel piano può essere incompleto.** §3b diceva "2
   file"; la feature ne aveva un terzo mai citato (`tag_analytics_service.py`),
   e **3 dei 6 difetti stavano lì**. Mappa la feature prima di fidarti della lista.
2. **Un fix su un endpoint non è consegnato finché il consumatore non lo usa.**
   I fix erano corretti lato worker ma il frontend scartava i campi nuovi:
   dal punto di vista del cliente il difetto restava identico.
3. **Se correggi una regola scritta in più posti, cercali tutti.** La regola
   dell'unità dominante era in 3 funzioni; correggerne 2 ha prodotto tre numeri
   diversi nella stessa risposta API — peggio del difetto originale, dove almeno
   erano sbagliati insieme.

## Nota separata, NON parte della sessione salvo richiesta esplicita

§2 ha ancora aperto il refactor del mock globale di `tests/conftest.py`
(`openai`, `requests`, `argon2`, `xmltodict`, `supabase`, `tenacity` sono tutti
installati davvero ma mockati, il che rende vacui i test sui rami `except`).
È lavoro lungo (rilancia ~11.000 test), esplicitamente rimandato: non aprirlo
senza tempo dedicato e senza che l'utente lo chieda.
