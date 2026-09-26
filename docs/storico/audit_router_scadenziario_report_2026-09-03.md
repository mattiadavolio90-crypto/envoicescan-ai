# Voce §3 #6 (router) — 1ª passata: scadenziario — 03/09/2026

La voce #6 (16.617 righe di router) va «affrontata per router, non in blocco»
(roadmap): questa è la prima passata, sul router indicato dalla pista aperta
dalle voci #4/#5. Le passate successive sono un programma a sé.

## Chiuso: le scadenze tornano a parlare (`routers/scadenziario.py`)

**Il difetto, misurato.** `POST /api/scadenziario/notifica` (chiamato a ogni
apertura della pagina Scadenziario) era MUTO da giugno per due difetti insieme:

1. upsert con `on_conflict="user_id,ristorante_id,topic_key"`, ma quel vincolo
   unico **non esiste** su `notification_inbox` (misurato su `pg_indexes`:
   l'unico unique è su `dedupe_key`): ogni chiamata cadeva nell'`except`, e il
   frontend la fa best-effort → **silenzio totale, 0 notifiche di sempre**;
2. il topic che provava a scrivere (`scadenze_aggregate`) era comunque
   **sconosciuto al briefing**, che conosce solo i topic canonici
   `scadenza_superata`/`scadenza_imminente` — con copy, priorità (60/61),
   toggle del configuratore e bucket settimanale già pronti, e nessun
   generatore vivo dall'1/6.

Intanto lo scadenziario mostrava **300 fatture scadute per 4,4 M€** e il
cliente non ha mai ricevuto un avviso — né campanella né briefing. In più il
body usava il formato inglese (`€{tot:,.0f}` → "€4,400,000").

**Il fix.** Endpoint riscritto sulla factory ufficiale
(`build_notification_record` + `upsert_inbox_notifications`, RPC idempotente):
i DUE topic canonici con payload `{count, totale}` che il briefing sa
raccontare (i bullet italiani sistemati oggi nella voce #4 li aspettano),
spegnimento degli avvisi quando la condizione rientra (`dismiss_inbox_topics`,
come incasso_mancante), importi in formato italiano.
Presidio `tests/test_scadenziario_notifica_topics.py` (5 test), **3 mutanti /
3 uccisi** (topic aggregato reintrodotto, spegnimento rimosso, formato
inglese). Suite scadenziario: 136 verdi.

**Effetto atteso in produzione**: alla prima apertura della pagina Scadenziario
di un cliente con scadenze, la campanella e il briefing del mattino dopo
iniziano ad avvisare. Da verificare a DB dopo il deploy
(`notification_inbox`, topic `scadenza_superata`).

## Annotato

- Il trigger resta **all'apertura della pagina** (design esistente, come
  incasso_mancante): un cliente che non apre mai lo Scadenziario non genera
  l'avviso. Spostarlo su un giro notturno del worker è una **decisione di
  prodotto**, registrata qui, non presa.
- `gruppo.py` e `margini.py` hanno avuto letture sostanziali oggi (quadratura)
  e a luglio (ciclo 07): restano 🟠 nel contatore finché non passano da una
  lettura integrale dichiarata.

## Il programma per le prossime passate (per router, misurato al 3/9)

I router mai letti o parziali, in ordine di rischio cliente:
`margini.py` e `gruppo.py` (numeri che il cliente vede — già percorsi dalla
quadratura, da chiudere a lettura integrale), `fatture.py`, `ricavi.py`,
`riparto.py` (toccati oggi dalla Fase 5 in punti mirati), poi `admin.py`
(solo staff), `workspace.py`, `account.py`, `prezzi.py`, `chat.py`,
`documenti.py`, `notifiche.py`. L'«agent notturno» in `fastapi_worker.py`
appartiene a queste passate.
