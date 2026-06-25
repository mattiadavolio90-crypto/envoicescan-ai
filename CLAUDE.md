# ONEFLUX — Contesto per Claude Code

## Cos'è il progetto
Piattaforma SaaS (v5.5) per la gestione automatizzata dei costi di ristoranti.
Analizza fatture elettroniche XML/P7M/PDF, categorizza prodotti con AI (GPT-4o-mini),
genera report su margini, prezzi fornitori, foodcost.

**Owner:** Mattia D'Avolio — sviluppatore singolo. 2 clienti in test + 1 operativo.

---

## Architettura attuale

| Layer | Percorso | Note |
|---|---|---|
| Frontend | `app.py` + `pages/*.py` | Streamlit multi-page — in migrazione a Next.js |
| Business logic | `services/*.py` | DB, AI, upload, notifiche, documenti, margini |
| Componenti riusabili | `components/*.py` | category_editor, dashboard_renderer, ecc. |
| Utilità | `utils/*.py` | Formatters, validatori, sidebar helpers |
| Configurazione | `config/*.py` | Costanti, logger, prompt AI |
| Worker API | `services/fastapi_worker.py` | FastAPI — `/health`, `/api/classify`, `/api/parse` |
| Worker async | `worker/run.py` | Processo separato per operazioni pesanti |
| Edge Functions | `supabase/functions/` | Deno — webhook Invoicetronic |
| Migrations | `supabase/migrations/*.sql` (canonico) | Schema PostgreSQL, RLS, trigger. `migrations/*.sql` è LEGACY storico (vedi `migrations/_LEGGIMI_STATO.md`) |
| Test | `tests/*.py` | ~760 test pytest |

**Database:** Supabase PostgreSQL — chiave `service_role_key` (bypassa RLS).
`auth.uid()` è sempre NULL — auth custom, non Supabase Auth.

---

## Regole di dominio critiche — NON violare mai

1. **Flusso categorizzazione = onesto** (rev. 23/06): una riga si classifica SOLO se dizionario/regole o l'AI la riconoscono con sicurezza. Se nessuno ci riesce resta `"Da Classificare"` (stato esplicito, visibile al cliente dal filtro "Da classificare" in Analisi Fatture → tab Articoli, con `needs_review=True`). **NIENTE fallback travestito in `"SERVIZI E CONSULENZE"`** (vecchio comportamento, eliminato). Il constraint DB ora è `fatture_categoria_not_empty_chk` (vieta solo NULL/vuoto, consente `"Da Classificare"`). Costante: `CATEGORIA_NON_CLASSIFICATA` in `config/constants.py`; `CATEGORIA_FALLBACK` ne è alias. Attenzione grafia: la variante errata `'Da Clasificare'` (una sola "s") resta sbagliata. Le righe `Da Classificare` sono escluse dai margini finché non vengono classificate (per non falsare il MOL).
2. **`"📝 NOTE E DICITURE"`** è consentita SOLO per righe con `totale_riga == 0`. Una dicitura con importo != 0 NON può restare in NOTE: il guardrail (`_applica_guardrail_note_con_importo`) la riporta a `"Da Classificare"` (non più SERVIZI), così resta visibile in coda e non entra nei margini con una categoria inventata.
3. **Chiave Supabase**: usare sempre `service_role_key` (non `key`) — non toccare `services/__init__.py` senza capire l'auth flow.
4. **`ADMIN_EMAILS`** normalizzato lowercase — confronti email sempre `.strip().lower()`.
5. **Soft delete**: query su `fatture` e `prodotti` devono filtrare `deleted_at IS NULL`. Usare `filter_active()` da `services.db_service`. Non rimuovere `.not_.is_("deleted_at", "null")` nelle query cestino (quelle sono intenzionali).
6. **Worker separato**: operazioni pesanti (classificazione AI, parsing fatture) vanno nel worker — non bloccare il thread Streamlit.

---

## Stato della migrazione Next.js

Riferimento: `ONEFLUX_MASTER.md` (visione + piano + stato + roadmap)

- **Fase 0-1b** ✅ — Next.js 16 online su `nuovo.oneflux.it`, design system completo
- **Fase 5** ✅ — Ricavi e Margini chiusa e consolidata (hardening 29/5)
- **Prossimo**: Scadenziario → Cestino → Reset password → Home AI

---

## Comandi utili

```powershell
# Test
python -m pytest tests/

# Avvia app locale
streamlit run app.py

# Esporta schema OpenAPI (dopo modifiche a fastapi_worker.py)
python scripts/export_openapi.py

# Verifica drift schema
python scripts/export_openapi.py --check-drift
```

---

## Convenzioni di codice

- Nessun commento nel codice se non per motivi non ovvi
- `filter_active()` da `services.db_service` per tutte le query con soft-delete
- Le migration SQL vanno SOLO in `supabase/migrations/` con nome timestamp `AAAAMMGGHHMMSS_nome.sql` (formato Supabase CLI). La cartella `migrations/` (numerazione `001`–`082`) è storica e congelata: non aggiungere file lì. Stato reale applicato = DB live, non i file.
- I file in `scripts/` e `tools/` sono operativi/manutentivi — non fanno parte del runtime

---

## Sicurezza

- Password: Argon2 (m=65536, t=3) — non cambiare parametri
- Sessioni: token `secrets.token_urlsafe(32)`, scadenza 30 giorni
- Rate limiting login: 5 tentativi → blocco 15 min
- File upload: validazione magic bytes (PDF, XML, P7M)
- Non esporre `SUPABASE_KEY`, `OPENAI_API_KEY` lato client
