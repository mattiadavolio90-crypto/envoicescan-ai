# MIGRAZIONE APP — Piano switch Streamlit → Next.js

**Creato:** 3 giugno 2026
**Riferimento completo:** `ONEFLUX_MASTER.md` §14-16

> ✅ **MIGRAZIONE COMPLETATA (switch 8/6/2026).** `app.oneflux.it` serve Next.js su
> Vercel; Streamlit e `nuovo.oneflux.it` sono dismessi. Questo documento è il piano
> STORICO dello switch — conservato come traccia, non descrive più lo stato corrente.

---

## Stato attuale

La nuova app Next.js è **funzionalmente completa** (Fasi 0–8 chiuse).
- URL attuale Next.js: `https://nuovo.oneflux.it` (Vercel)
- URL attuale Streamlit: `https://app.oneflux.it` (Railway)
- Database condiviso: entrambi puntano allo stesso Supabase

**Mancano solo:** Fase 9 (test) → Fase 10 (switch DNS) → Fase 11 (spegnimento Streamlit)

---

## Dominio finale

| URL | Destinazione |
|---|---|
| `app.oneflux.it` | Next.js su Vercel (dopo switch) |
| `old.oneflux.it` | Streamlit su Railway (fallback 30 giorni post-switch) |
| `www.oneflux.it` | Tenere libero per landing page pubblica futura |
| `nuovo.oneflux.it` | Redirect → `app.oneflux.it` dopo switch (poi rimuovere) |

**Il link da dare ai clienti oggi:** `https://nuovo.oneflux.it`
**Il link definitivo dopo lo switch:** `https://app.oneflux.it` (stesso che usano già)

---

## Servizi: free vs Pro

| Servizio | Piano attuale | Azione richiesta | Costo post-switch |
|---|---|---|---|
| **Vercel** | Hobby (free) | ⚠️ **Verificare prima dello switch** se `app.oneflux.it` si può aggiungere su Hobby. Se no → upgrade a Pro | €0 → €20/mese |
| **Railway** | Hobby €5/mese | Nessun upgrade. Dopo Fase 11 eliminare solo il servizio Streamlit (non l'intero progetto — FastAPI e queue-worker ci girano) | €5/mese |
| **Supabase** | Free | Nessun upgrade anticipato. Solo se emergono problemi reali (pause inattività, limiti connessioni) | €0 → €25/mese solo se serve |
| **Brevo** | Free (300 email/giorno) | Nessun upgrade | €0 |
| **GitHub Actions** | Free | Nessun upgrade | €0 |
| **OpenAI** | Pay-per-use | Invariato | ~€0,30/cliente/mese |
| **Aruba** | Pagato | Invariato | ~€1/mese |
| **Railway orfano** `exemplary-creation` | Vuoto | **Eliminare** in Fase 11 | risparmio |

**Costo totale stimato post-switch:** ~€26/mese (Vercel Pro + Railway Hobby + OpenAI)

---

## Piano sequenziale

### Fase 9 — Test (prima di toccare qualsiasi DNS)

- [x] Usare `nuovo.oneflux.it` come cliente reale per almeno 5 giorni
- [x] Invitare i 2 clienti di test a usare `nuovo.oneflux.it` in parallelo a Streamlit
- [x] Raccogliere e fixare i bug che emergono
- [ ] Completare la checklist pre-switch qui sotto

### Fase 10 — Switch DNS ✅ chiusa (8/6)

- [x] Verificare se Vercel Hobby supporta dominio custom `app.oneflux.it` → **Hobby supporta, nessun upgrade**
- [~] Fare backup DB Supabase → **N/A** (piano Free non espone backup; rollback via DNS comunque possibile)
- [~] Avvisare clienti → **N/A** (deciso 7/6, non serve)
- [x] Switch DNS: `app.oneflux.it` → Vercel (Next.js) — CNAME aggiunto su Aruba (8/6)
- [~] Creare `old.oneflux.it` → Railway (Streamlit, fallback) → **N/A** (Streamlit eliminato, deciso dismettere subito)
- [x] Servizio Streamlit eliminato da Railway `ingenious-fascination` (8/6)
- [x] Homepage redirect a `/login` — pagina "in costruzione" rimossa (8/6)
- [ ] Monitorare per almeno 7 giorni

### Fase 11 — Spegnimento Streamlit (parzialmente anticipata l'8/6)

- [x] Eliminare il servizio Streamlit dal progetto Railway `ingenious-fascination` (8/6 — worker FastAPI e queue-worker restano)
- [x] Eliminare l'app doppione su Streamlit Community Cloud `oneflux.streamlit.app` (8/6 — account Streamlit lasciato vuoto come fallback 30gg)
- [x] Rimuovere `nuovo.oneflux.it` dal DNS Aruba + da Vercel (8/6)
- [x] Aggiornare link reset/onboarding e CORS worker da `nuovo` a `app.oneflux.it` (8/6)
- [~] `old.oneflux.it` → **N/A** (deciso di non creare fallback, Streamlit dismesso subito)
- [ ] Eliminare il progetto Railway `exemplary-creation` (orfano, vuoto) — dopo 30gg
- [ ] **Sicurezza**: rigenerare `service_role_key` Supabase + `OPENAI_API_KEY` (erano esposte su Streamlit Cloud per mesi) e aggiornarle sul worker Railway

---

## Checklist pre-switch (dal MASTER §16)

- [x] Tutte le sezioni funzionanti e testate su `nuovo.oneflux.it`
- [x] Reset password funzionante lato Next.js (Brevo in produzione)
- [x] Privacy & Cookie Policy + Termini di Servizio pubblicati (`/privacy`, `/termini`)
- [x] Consenso privacy esplicito raccolto all'onboarding con prova reale
- [x] Aggiornare data/versione informativa al cut-over + allineare lista responsabili
- [ ] Backup DB confermato
- [~] Clienti avvisati con almeno 1 settimana di anticipo — **N/A** (non serve, deciso 05/06)
- [ ] Rollback plan: `old.oneflux.it` → Streamlit pronto

---

## Note importanti

- **Database condiviso**: nessuna migrazione dati. Streamlit e Next.js puntano già allo stesso Supabase. Un dato inserito su uno è visibile sull'altro in tempo reale.
- **Worker FastAPI**: resta su Railway anche dopo lo switch. Non si tocca.
- **Rollback**: se emergono problemi gravi post-switch, basta rimettere il DNS di `app.oneflux.it` su Railway (Streamlit) — i dati sono integri perché il DB è condiviso.
- **`www.oneflux.it`**: non usarlo per l'app. Tenerlo libero per la landing page pubblica futura (presentazione ONEFLUX ai potenziali clienti RECOMA).
