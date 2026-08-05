---
description: Revisiona la fase/implementazione appena chiusa — diff + verifica di chiusura reale (commit, CI, regole di dominio ONEFLUX, cache, timing deploy, doc)
---

Richiama l'agente `code-reviewer` (subagent_type: code-reviewer) sulla fase o
implementazione appena completata. Se l'utente ha specificato quale fase o
ambito, passalo come contesto all'agente; altrimenti l'agente deduce l'ambito
dai commit/modifiche recenti.

Riporta all'utente il verdetto finale e la tabella degli 8 controlli così come
prodotti dall'agente, senza riassumere via i dettagli dei blocchi 🔴.
