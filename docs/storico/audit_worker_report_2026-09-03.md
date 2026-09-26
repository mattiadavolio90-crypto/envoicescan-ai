# Audit worker asincrono — `worker/` (voce §3 #5) — 03/09/2026

**Perimetro:** `worker/` = 2.403 righe, **lette integralmente**: `run.py` 301,
`queue_processor.py` 1.430, `email_queue_processor.py` 602, `streamlit_stub.py`
69, `__init__.py` 1. Verifica incrociata con le RPC di coda e col DB di
produzione. «Gira non presidiato» era la premessa della roadmap: misurato, è il
contrario — è tra i moduli più presidiati del backend.

## Cosa regge (misurato)

- **Coda fatture in salute**: 647 item `done` (retry fino a 8 tentativi, tutti
  arrivati in fondo), **0 failed/dead in arretrato**, 2 `da_assegnare` freschi
  di oggi (flusso normale multi-sede). Coda email ricavi: 88/88 `done` al primo
  tentativo.
- **Difese vere, non dichiarate**: claim atomico FOR UPDATE SKIP LOCKED con
  recupero lock stantii; watchdog per singolo job (timeout 300s) con
  ri-verifica del claim prima dei side-effect costosi (salvataggio e chiamate
  AI); SSRF whitelist sui download Invoicetronic; purge GDPR (XML 24h,
  raw_body 90gg, XLS ricavi 90gg, retention 2 anni) sotto gate d'intervallo;
  killswitch documentato con log orario; **import degradati dichiarati a ERROR**
  (prima il worker girava azzoppato in silenzio); AI muta segnalata a ERROR
  con conteggio righe.
- **Il percorso email è ownership-safe**: mapping ragione sociale filtrato sui
  ristoranti dell'utente lato DB (niente troncamento a 1000), destinazione
  verificata anche sul fallback, IVA ≠ 10/22 scorporata prima di finire in
  «altri» (che a valle è netto).

## Difetto trovato e CHIUSO (latente)

**`_schedule_retry` della coda email non poteva scrivere il retry.** Passava a
PostgREST la STRINGA `"now() + interval '...'"` come valore di `next_retry_at`:
Postgres la rifiuta come letterale timestamptz (**misurato a DB**: `'now()'`
casta, `'now() + interval …'` → `invalid input syntax`). L'UPDATE intero
falliva: niente `status='failed'`, niente backoff, lock non rilasciato — il
record sarebbe tornato in coda solo col recupero dei lock stantii. **Mai
esercitato in produzione** (88 righe, tutte done al 1º colpo): latente, ma il
primo errore transitorio (Storage giù, XLS malformato) l'avrebbe innescato.
Fix: timestamp calcolato in Python (ISO, con fuso). Presidio
`tests/test_email_queue_retry_timestamp.py` (3 test: parsabilità+finestra di
backoff, dead oltre i tentativi, crescita esponenziale). **1 mutante / 1 ucciso**
(l'espressione SQL reintrodotta → 2 rossi). Suite worker/email: 149 verdi.

## Trovato per strada, di un'altra area (registrato, non toccato qui)

**Le notifiche scadenze sono mute da giugno per un upsert impossibile.**
`POST /api/scadenziario/notifica` (router, non worker) scrive con
`on_conflict="user_id,ristorante_id,topic_key"`, ma **quel vincolo unico non
esiste** su `notification_inbox` (l'unico è su `dedupe_key`): ogni chiamata
fallisce nell'`except` e il frontend la fa best-effort — silenzio totale.
Misurato: 0 righe `scadenze_aggregate` di sempre, vecchi topic fermi all'1/6,
mentre lo scadenziario ha 300 fatture scadute / 4,4 M€. In più il topic nuovo
(`scadenze_aggregate`) è SCONOSCIUTO al briefing, che conosce solo i due topic
vecchi che nessuno genera più; e il body usa il formato inglese (`€{tot:,.0f}`).
**→ da chiudere nella voce §3 #6 (router), dove si audita `scadenziario.py`.**

## Fuori perimetro dichiarato

L'«agent notturno» di revisione righe vive in `fastapi_worker.py` (voce #6),
non in `worker/`. Le RPC di coda (`claim_batch_for_processing`, `schedule_retry`,
`mark_queue_item_done`…) sono state lette come contratto, non ri-auditate:
hanno i loro presidi dai cicli precedenti.
