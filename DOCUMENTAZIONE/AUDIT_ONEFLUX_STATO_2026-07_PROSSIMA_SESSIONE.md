# Prompt per la prossima sessione di audit — ciclo ONEFLUX 2026-07

> Copia il blocco qui sotto come primo messaggio della nuova sessione.
> Scritto il 25/8/2026 a valle del deploy della feature Tag.

---

Continua il ciclo di audit ONEFLUX 2026-07. Leggi prima
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07.md` (indice, ~1 minuto) e apri
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07_STORICO.md` solo per il dettaglio
della sezione che riapri (la sessione Tag è §22, deploy incluso).

## Stato: la feature Tag è chiusa e deployata

Il branch `audit-s3b-tag` è stato mergiato in `main` (`ff-only`, commit
`ebb842f`) e pushato il 25/8/2026 mattina, confermato su `/health` del worker
Railway. Non c'è nulla da riprendere su Tag.

## Prossimo passo: l'ultima voce di §3b

Resta solo la **chat di `fastapi_worker.py`**: `_chat_query_costi`,
`_chat_loop_openai`, `_build_chat_system_prompt`, `_chat_trend_prezzo`.

Cosa si sa già, da non rimisurare:
- esposizione **bassa**: 4 chiamate negli ultimi 30 giorni (misurato l'11/8,
  da riverificare se sono passate molte settimane)
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
  severità cadesse a una query.
  ⚠️ **Se l'agente dichiara "non ho accesso al DB, questo numero va misurato",
  quel numero è quasi sempre quello che decide la severità: misuralo tu.**
- `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
- Ogni fix richiede test nuovi **verificati per mutazione** (rimuovi il fix, il
  test deve cadere). Mutazione **solo su copia in scratchpad**, mai sul file
  nel branch di lavoro — anche se il branch sembra quello giusto: se durante
  la sessione l'HEAD è cambiato per qualunque motivo (checkout non voluto,
  lavoro concorrente di Mattia sullo stesso repo), un mutation test diretto sul
  file rischia di troncare il file sbagliato. Verifica `git branch --show-current`
  prima di ogni mutazione se non sei sicuro.
- "Deployato" non è una prova: verifica con `git log -- <file>` e con `/health`
  del worker Railway (`https://worker-production-a552.up.railway.app/health`,
  espone il commit deployato).
- **Prima di dichiarare "CI bloccata", leggi i trigger nei file
  `.github/workflows/*.yml`.** In questo ciclo un push a un branch feature non
  ha mai fatto partire nulla — i workflow scattano solo su push a
  `main`/`progetto` o su `pull_request`. Se non puoi aprire una PR (`gh` non
  installato, API bloccata), il sostituto è rieseguire in locale i comandi che
  la CI userebbe (leggili nei workflow file), non dichiarare il lavoro
  bloccato.
- Migration solo con conferma esplicita, e **applicata prima del deploy**.
- Aggiorna indice **e** STORICO a fine sessione, barrando con `~~voce~~ — CHIUSA il gg/mm`.

## Lezioni della sessione Tag (23-25/8), che valgono per la prossima

1. **Il perimetro dichiarato nel piano può essere incompleto.** §3b diceva "2
   file"; la feature ne aveva un terzo mai citato (`tag_analytics_service.py`),
   e 3 dei 6 difetti stavano lì. Mappa la feature prima di fidarti della lista.
2. **Un fix su un endpoint non è consegnato finché il consumatore non lo usa.**
   I fix erano corretti lato worker ma il frontend scartava i campi nuovi.
3. **Se correggi una regola scritta in più posti, cercali tutti.** Correggerne
   solo alcune ha prodotto numeri diversi nella stessa risposta API — peggio
   del difetto originale.
4. **"Non posso aprire una PR" e "non posso verificare niente" sono due
   affermazioni diverse.** La seconda va dimostrata leggendo i trigger CI, non
   assunta dalla prima — vedi punto dedicato sopra nel metodo.
5. **Se durante la sessione noti cambi di branch che non hai comandato tu,
   qualcun altro sta scrivendo sullo stesso repository.** Fermati e chiedi
   prima di qualunque merge, non dopo. In questa sessione Mattia ha
   committato in concorrenza sullo stesso branch audit; risolto con un
   `git rebase` (git ha scartato da solo il commit duplicato, patch-equivalente)
   e una verifica rifatta da capo sul branch riallineato — mai un force-push
   o uno sconfitto silenzioso del lavoro altrui.

## Nota separata, NON parte della sessione salvo richiesta esplicita

§2 ha ancora aperto il refactor del mock globale di `tests/conftest.py`
(`openai`, `requests`, `argon2`, `xmltodict`, `supabase`, `tenacity` sono tutti
installati davvero ma mockati, il che rende vacui i test sui rami `except`).
È lavoro lungo (rilancia ~11.000 test), esplicitamente rimandato: non aprirlo
senza tempo dedicato e senza che l'utente lo chieda.
