# Prompt per la sessione — Fase 3: isolamento fra clienti, provato eseguendo

> **ESEGUITO e CHIUSO il 14/09/2026.** Questo file e' archiviato: si legge
> come storia di cosa era stato previsto, non come lavoro da fare. Esito reale
> nel verbale del 14/09 in `AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`.

> **Come si usa.** Imposta **Fable, effort `ultrathink`** (è sicurezza
> multi-tenant), apri una sessione nuova e incolla la sezione «PROMPT» qui
> sotto. Tutto il resto di questo file è contesto che la sessione leggerà da
> sola: non serve incollarlo.

---

## PROMPT (copia da qui)

ultrathink

Apri la **Fase 3 della sessione trasversale di audit: L2 — isolamento fra
clienti provato eseguendo**. È la terza delle nove lenti trasversali; L3 e L1
sono chiuse il 14/09/2026.

Leggi prima, in quest'ordine:
1. `DOCUMENTAZIONE/AUDIT_COPERTURA.md` → sezione «Lenti trasversali» (cosa è
   chiuso, cosa resta, con quale metro)
2. `WORKFLOW.md` §6 → come si conduce un audit **e la regola sul costo**
3. `docs/piani/PROMPT_FASE3_ISOLAMENTO_TENANT.md` → il perimetro misurato, il
   metodo e i criteri di chiusura di questa fase specifica

**Il problema in una riga:** i tre cicli di audit hanno certificato «216/216
endpoint protetti», ma quello misura che sono **autenticati** — non che il
cliente A non possa leggere o scrivere i dati del cliente B passando l'id di B.
L'ownership è stata *letta*, mai *eseguita*. Con `auth.uid()` sempre NULL e ogni
client su `service_role` (che bypassa RLS), **i filtri `user_id`/`ristorante_id`
nel codice Python SONO l'unica sicurezza multi-tenant che esiste**.

**Vincolo di costo, non negoziabile.** Rilevatori, script e misure si fanno **in
sessione**: niente workflow multi-agente. L'unico sub-agente è il
`code-reviewer` a fine fase. Il motivo sta in `WORKFLOW.md` §6: nella sessione
del 13-14/09 il fan-out ha bruciato 2,5M token producendo triage, non prove.
La velocità non è il vincolo; il budget dell'abbonamento sì.

**Non pushare.** Si lavora su `main` locale; il push è una decisione serale di
Mattia. In coda ci sono già 4 commit miei del 14/09.

Apri con `/apertura-sessione`, poi dichiara il perimetro che hai **misurato tu**
(non quello che leggi qui: le sessioni parallele committano) e parti.

## (fine prompt)

---

## Contesto della fase — perimetro misurato il 13-14/09/2026

Cifre da **ri-misurare** all'apertura, non da ereditare (regola: una cifra
ripresa da un documento non è una cifra misurata).

| Cosa | Misura del 13/09 |
|---|---|
| Operazioni OpenAPI | 198 path, **240 operazioni** (`openapi/openapi.json`) |
| `_verify_worker_key` | 235 usi — **autenticazione**, non ownership |
| `_verify_admin` | 77 usi |
| Ownership esplicita | `_assert_tag_ownership` 8, `_assert_gruppo_tag` 4 — **12 in tutto** |
| `ristorante_id`/`rid` presi dal client | `gruppo.py` **38 punti**, `workspace.py` 19, `scadenziario.py` 9 (quest'ultimo valida via `_resolve_ristorante_scrivibile`) |
| Secondo tenant nei test | seminato **solo** in `test_sql_funzioni_soldi.py` (`SEDE_B`) |

**Precedenti che provano che la classe esiste** (dai tre cicli): 1 CRITICAL
cross-tenant nel ciclo 07, un `update` senza `user_id` nel ciclo 09, un endpoint
senza guardia di sede nel 07, l'export GDPR che leggeva la sede attiva nel 09.

## Metodo (§3 del piano approvato)

1. **Estrazione in locale** (script, nessun agente): da `openapi/openapi.json`
   ricava le operazioni con un parametro di risorsa tenant-scoped —
   `ristorante_id`, `rid`, o un `id` di fattura/tag/gruppo/turno/ricavo/riparto
   in path, query o body. Salva l'elenco in scratchpad.
2. **Harness**: `tests/conftest_sql.py` (Postgres vero, marker `-m sql`) +
   `TestClient`. Semina **2 account × 2 sedi + 1 gruppo ciascuno**.
3. **Sweep eseguito**: per ogni operazione, chiamala con la sessione di A e
   l'id di B, e viceversa. Classifica l'esito:
   - `403/404/vuoto` → ok
   - **dati di B** → leak
   - **scrittura su B** → critico
   - `500` → da guardare (non è né ok né leak)
4. Stesso giro sulle **7 RPC `gruppo_*`** e sulle RPC della chat, con due gruppi.
5. **Fix** dei confermati, ognuno con mutante sul **call site**: togliere il
   filtro tenant deve far diventare rosso il test.
6. **Presidio permanente**: `tests/test_isolamento_per_risorsa.py`,
   parametrizzato sull'OpenAPI con allowlist motivata (modello:
   `tests/test_route_api_auth_dichiarativa.py`). Così **la 241ª operazione nasce
   coperta** — è questo che impedisce la ricomparsa, non i fix.

## Criteri di chiusura (WORKFLOW §5 — «una cosa alla volta, chiusa davvero»)

- [ ] Ogni operazione dell'elenco ha un esito classificato (nessun «non provata»)
- [ ] Ogni fix ha il suo mutante ucciso, mutato sul call site
- [ ] `tests/test_isolamento_per_risorsa.py` esiste, è parametrizzato, e la sua
      allowlist ha una motivazione per riga
- [ ] `python -m pytest tests/ -q` e `python -m pytest -q -m sql` verdi
- [ ] `python scripts/export_openapi.py --check-drift` senza drift
- [ ] `python scripts/check_documentazione.py` pulito
- [ ] Verbale (≤ 40 righe) in
      `docs/storico/audit-2026-09/AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`
- [ ] Riga **L2** nella tabella «Lenti trasversali» di
      `DOCUMENTAZIONE/AUDIT_COPERTURA.md`, con metro e «si riapre se…»
- [ ] `code-reviewer` sul cumulativo `origin/main..main` — **un solo agente**
- [ ] Commit su `main` locale. **Nessun push.**

## Trappole note su questa fase

- **`-m sql` gira sullo snapshot dello schema live**, non sulle migration: il
  repo non sa ricostruire il DB (230 migration su Postgres vuoto = 18 tabelle su
  59). Vedi `supabase/schema_snapshot.sql`.
- **Con un solo cliente seminato 7 test SQL erano verdi senza isolamento**: il
  secondo tenant non è un dettaglio della fixture, è ciò che misura.
- **Il client Supabase è un singleton condiviso**: i suoi header sono stato
  globale. Mai usarli per dati per-richiesta — ha già rotto la produzione.
- **`500` non è «protetto»**: spesso è una guardia che esplode invece di negare,
  e a volte è un leak mascherato dall'errore. Va guardato uno per uno.

## Dopo la Fase 3

Restano L4-L9, ognuna una sessione a sé, in ordine e col modello consigliato
nella tabella «Le lenti ancora da fare» di `DOCUMENTAZIONE/AUDIT_COPERTURA.md`.
