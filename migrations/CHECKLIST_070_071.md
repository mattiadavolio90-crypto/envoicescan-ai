MIGRATION 070 - Checklist Verifica
==================================

Migration 070 implementa la tabella fornitori_pagamenti_config con tutti i vincoli.

☑ CREATE FUNCTION fn_bump_cache_version_fornitori_config() PRIMA del trigger
   ✅ Linea 103-113

☑ Unique index parziale WHERE piva_fornitore IS NOT NULL
   ✅ idx_frn_pag_cfg_piva_unique (linea 49-52)

☑ Unique index parziale WHERE piva_fornitore IS NULL AND fornitore_norm IS NOT NULL
   ✅ idx_frn_pag_cfg_norm_unique (linea 54-57)

☑ CHECK giorni_pagamento BETWEEN 0 AND 365
   ✅ Linea 34

☑ CHECK data_riferimento IN ('data_documento','fine_mese','fine_mese_successivo')
   ✅ Linea 37-38

☑ CHECK constraint almeno uno tra piva e norm valorizzato
   ✅ Linea 45 - (piva_fornitore IS NOT NULL OR fornitore_norm IS NOT NULL)

☑ RLS abilitata, nessuna policy user-facing
   ✅ Linea 61-67

☑ created_at e updated_at con DEFAULT now()
   ✅ Linea 41-42

☑ Trigger bump cache_version su INSERT/UPDATE/DELETE
   ✅ trg_bump_cache_frn_cfg (linea 120-123)

---

MIGRATION 071 - Checklist Verifica
==================================

Migration 071 implementa il backfill di fatture_documenti con strategia batch.

☑ CREATE INDEX CONCURRENTLY presente
   ✅ Linea 27-30

☑ Loop batch da 1000 con COMMIT intermedi (PL/pgSQL DO block)
   ✅ Linea 36-129

☑ ON CONFLICT DO NOTHING per idempotenza
   ✅ Linea 94

☑ segno_compensazione derivato da tipo_documento (TD04 → -1, altri → 1)
   ✅ Linea 78-82 (CASE WHEN ... = 'TD04' THEN -1 ELSE 1)

☑ scadenza_source = 'none' per tutti i record storici
   ✅ Linea 84 ('none'::TEXT)

☑ pagata = false per tutti i record storici
   ✅ Linea 86 (FALSE::BOOLEAN)

☑ source_origin = 'manual' per tutti i record storici
   ✅ Linea 88 ('manual'::TEXT)

☑ VACUUM ANALYZE alla fine
   ✅ Linea 135

☑ DROP INDEX idx_fatture_backfill alla fine
   ✅ Linea 137

☑ Query di verifica finale inclusa nel file
   ✅ Linea 141-150 (COMMENT con istruzioni verifica manuale)

---

STRATEGIA BATCH BREAKDOWN (071)
===============================

1. CREATE INDEX CONCURRENTLY idx_fatture_backfill
   - Indice temporaneo su (user_id, ristorante_id, file_origine) WHERE deleted_at IS NULL
   - CONCURRENTLY evita lock table

2. DO $$ ... END $$; (PL/pgSQL batch loop)
   - Raccogliamo ARRAY di file_origine distinti (ordinati)
   - Loop con v_offset += 1000
   - Per ogni batch: INSERT INTO fatture_documenti (SELECT aggregato FROM fatture...)
   - ON CONFLICT (user_id, ristorante_id, file_origine) DO NOTHING
   - RAISE NOTICE per tracking progresso

3. Aggregazione dati header (per GROUP BY user_id, ristorante_id, file_origine):
   - fornitore, piva_cessionario, numero_documento → prima riga non-NULL
   - data_documento, data_competenza, tipo_documento → prima riga
   - totale_documento, totale_imponibile, totale_iva → prima riga
   - segno_compensazione: -1 se TD04, else 1
   - scadenza_xml, giorni_termini_xml → NULL (no parse storico)
   - scadenza_effettiva → NULL (da calcolare con regole in futuro)
   - scadenza_source → 'none'
   - pagata → FALSE
   - source_origin → 'manual'

4. VACUUM ANALYZE public.fatture_documenti;
   - Ricalcola statistiche per query planner

5. DROP INDEX idx_fatture_backfill;

---

MIGRATION 069.5 - Nuova colonna piva_cedente
=============================================

**AGGIUNTA 2026-05-10:** Migration 069.5 introdotta tra 069 e 070 per supportare Step 2 (parser DatiPagamento).

☑ ALTER TABLE fatture ADD COLUMN IF NOT EXISTS piva_cedente TEXT DEFAULT NULL;
   ✅ migrations/069.5_add_piva_cedente_to_fatture.sql

**Scopo:** Salvare P.IVA del cedente (fornitore emittente) a livello di riga per:
- Utilizzo da parte di migration 071 backfill per popolare fatture_documenti.piva_cedente
- Matching con fornitori_pagamenti_config in Step 6 (regole fornitore)

**Per righe storiche:** piva_cedente = NULL, propagato come NULL a fatture_documenti durante backfill.

---

ORDINE MIGRAZIONI AGGIORNATO
=============================

**Nuovo ordine di applicazione:**
```
069 → 069.5 → 070 → 071
```

Sequenza:
1. **069:** CREATE TABLE fatture_documenti (schema + trigger propagazione deleted_at)
2. **069.5:** ALTER TABLE fatture ADD COLUMN piva_cedente (supporto Step 2 parser)
3. **070:** CREATE TABLE fornitori_pagamenti_config (regole fornitore)
4. **071:** Backfill fatture_documenti da fatture (legge piva_cedente da colonna aggiunta in 069.5)

---

CORREZIONE 071 - piva_cedente invece di piva_cessionario
=========================================================

**CORREZIONE 2026-05-10:** Migration 071 linea 85-86 corretta.

**Prima:**
```sql
(ARRAY_AGG(DISTINCT f.piva_cessionario ORDER BY f.piva_cessionario) 
 FILTER (WHERE f.piva_cessionario IS NOT NULL))[1],
```

**Dopo:**
```sql
(ARRAY_AGG(DISTINCT f.piva_cedente ORDER BY f.piva_cedente) 
 FILTER (WHERE f.piva_cedente IS NOT NULL))[1],
```

**Motivo:** La colonna `piva_cedente` è quella che contiene la P.IVA del fornitore emittente (estratta da CedentePrestatore).
La `piva_cessionario` è la P.IVA del destinatario e non è rilevante per questo aggregato.
Migration 069.5 aggiunge la colonna piva_cedente a fatture; migration 071 la legge per popolare fatture_documenti.
   - Pulizia temporaneo

6. Verifica manuale POST-MIGRATION:
   COUNT(*) FROM fatture_documenti WHERE deleted_at IS NULL 
   MUST EQUAL 
   COUNT(DISTINCT file_origine) FROM fatture WHERE deleted_at IS NULL

---

ORDINE APPLICAZIONE PRODUZIONE (Manuale)
==========================================

Passo 1: Applica 069
   - Esegui: psql -h db.supabase.co -d postgres -U postgres -f 069_create_fatture_documenti.sql
   - Verifica: SELECT COUNT(*) FROM fatture_documenti; (deve ritornare 0, tabella esiste)

Passo 2: Applica 070
   - Esegui: psql -h db.supabase.co -d postgres -U postgres -f 070_create_fornitori_pagamenti_config.sql
   - Verifica: SELECT COUNT(*) FROM fornitori_pagamenti_config; (deve ritornare 0, tabella esiste)

Passo 3: Applica 071
   - Esegui: psql -h db.supabase.co -d postgres -U postgres -f 071_backfill_fatture_documenti.sql
   - Verifica: 
     * SELECT COUNT(*) FROM fatture_documenti; (deve > 0 se fatture esistenti)
     * SELECT COUNT(DISTINCT file_origine) FROM fatture WHERE deleted_at IS NULL;
     * I due numeri DEVONO coincidere
   - Se divergono: identificare file_origine missing con query EXCEPT

---

PRONTO PER APPROVAZIONE: 070 e 071
