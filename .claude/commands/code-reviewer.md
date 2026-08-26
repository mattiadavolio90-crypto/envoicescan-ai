---
description: Revisiona la fase/implementazione appena chiusa — diff + verifica di chiusura reale (commit, CI, regole di dominio ONEFLUX, cache, timing deploy, doc)
---

Richiama l'agente `code-reviewer` (subagent_type: code-reviewer) sulla fase o
implementazione appena completata. Se l'utente ha specificato quale fase o
ambito, passalo come contesto all'agente; altrimenti l'agente deduce l'ambito
dai commit/modifiche recenti.

Riporta all'utente il verdetto finale e la tabella degli 8 controlli così come
prodotti dall'agente, senza riassumere via i dettagli dei blocchi 🔴.

Dopo aver ricevuto la risposta dell'agente (qualunque sia il verdetto — questo
comando certifica che la review è avvenuta, non che sia stata positiva),
scrivi il file marker `.claude/.reviewer_gate_ok` (contenuto: timestamp ISO
va bene) — sblocca l'hook Stop `claude_hook_reviewer_gate.py`, che altrimenti
richiede una code-review prima di chiudere una sessione con modifiche
"complesse". Non serve leggere il file prima: scrivilo direttamente.
