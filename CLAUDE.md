# ONEFLUX — Contesto per Claude Code

## Cos'è il progetto
Piattaforma SaaS (v5.5) per la gestione automatizzata dei costi di ristoranti.
Analizza fatture elettroniche XML/P7M/PDF, categorizza prodotti con AI (GPT-4o-mini),
genera report su margini, prezzi fornitori, foodcost.

**Owner:** Mattia D'Avolio — sviluppatore singolo, nessun cliente reale in produzione.

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
| Migrations | `supabase/migrations/*.sql`, `migrations/*.sql` | Schema PostgreSQL, RLS, trigger |
| Test | `tests/*.py` | ~760 test pytest |

**Database:** Supabase PostgreSQL — chiave `service_role_key` (bypassa RLS).
`auth.uid()` è sempre NULL — auth custom, non Supabase Auth.

---

## Regole di dominio critiche — NON violare mai

1. **`categoria = 'Da Clasificare'` è VIETATA** nel DB — constraint `fatture_categoria_not_unclassified_chk`. Fallback corretto: `"SERVIZI E CONSULENZE"`.
2. **`"📝 NOTE E DICITURE"`** è consentita SOLO per righe con `totale_riga == 0`. Su qualsiasi importo > 0 va usata una categoria reale.
3. **Chiave Supabase**: usare sempre `service_role_key` (non `key`) — non toccare `services/__init__.py` senza capire l'auth flow.
4. **`ADMIN_EMAILS`** normalizzato lowercase — confronti email sempre `.strip().lower()`.
5. **Soft delete**: query su `fatture` e `prodotti` devono filtrare `deleted_at IS NULL`. Usare `filter_active()` da `services.db_service`. Non rimuovere `.not_.is_("deleted_at", "null")` nelle query cestino (quelle sono intenzionali).
6. **Worker separato**: operazioni pesanti (classificazione AI, parsing fatture) vanno nel worker — non bloccare il thread Streamlit.

---

## Stato della migrazione Next.js

Riferimento: `PIANO_MIGRAZIONE_NEXTJS_DEFINITIVO.md`

- **Phase 0** ✅ — `filter_active()` helper, `openapi/openapi.json`, CI drift check
- **Phase 0.5** — prossimo step: rimuovere `@st.cache_data` da `db_service.py`, `margine_service.py`, `documenti_service.py`
- **Phase 1+** — scaffold Next.js 14 in `apps/web`, ShadcnUI + Tailwind (`#0ea5e9`), deploy Vercel

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
- Le migration SQL vanno in `supabase/migrations/` (numerazione sequenziale)
- I file in `scripts/` e `tools/` sono operativi/manutentivi — non fanno parte del runtime

---

## Sicurezza

- Password: Argon2 (m=65536, t=3) — non cambiare parametri
- Sessioni: token `secrets.token_urlsafe(32)`, scadenza 30 giorni
- Rate limiting login: 5 tentativi → blocco 15 min
- File upload: validazione magic bytes (PDF, XML, P7M)
- Non esporre `SUPABASE_KEY`, `OPENAI_API_KEY` lato client
