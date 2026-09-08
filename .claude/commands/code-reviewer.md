---
description: Revisiona la fase/implementazione appena chiusa — diff + verifica di chiusura reale (commit, CI, regole di dominio ONEFLUX, cache, timing deploy, doc)
---

Richiama l'agente `code-reviewer` (subagent_type: code-reviewer) sulla fase o
implementazione appena completata. Se l'utente ha specificato quale fase o
ambito, passalo come contesto all'agente; altrimenti l'agente deduce l'ambito
dai commit/modifiche recenti.

Riporta all'utente il verdetto finale e la tabella degli 8 controlli così come
prodotti dall'agente, senza riassumere via i dettagli dei blocchi 🔴.

Il marker `.claude/.reviewer_gate_ok` — quello che sblocca l'hook Stop
`claude_hook_reviewer_gate.py` — **lo scrive l'agente come ultimo passo, e solo
se il verdetto è 🟢 CHIUSA CORRETTAMENTE** (vedi «ULTIMO PASSO» in
`.claude/agents/code-reviewer.md`). **Questo comando non lo scrive.** Se il
verdetto è 🔴, non scriverlo tu al posto suo: il gate deve continuare a bloccare
finché i blocchi non sono chiusi, e dopo i fix la review si rilancia **sul
cumulativo** — l'08/09 un Punto è stato dichiarato chiuso con i fix mai
ri-revisionati, perché il marker era stato scritto dopo il primo verdetto.

Il marker è **uno solo per tutte le sessioni** (non porta il session id nel
nome): se `git status` mostra lavoro altrui su path sensibili, chi lo scrive
certifica anche quello. In quel caso non scriverlo — il tuo Stop passa comunque
grazie al marker anti-loop per sessione — e lascia che l'altra sessione faccia
la sua review.
