-- FIX upload bloccato (errore 42P10) — sostituisce l'indice UNIQUE PARZIALE con uno PIENO.
--
-- Problema: uq_fatture_dedup_active era UNIQUE ... WHERE deleted_at IS NULL.
-- PostgREST/supabase-py .upsert(on_conflict=...) NON puo' usare un indice unico parziale
-- come arbitro di ON CONFLICT: genera "INSERT ... ON CONFLICT (cols) DO UPDATE" senza
-- la clausola WHERE del predicato, e Postgres rigetta con:
--   42P10 "there is no unique or exclusion constraint matching the ON CONFLICT specification".
-- Risultato: dal 03/06 salva_fattura_processata() falliva su OGNI riga -> nessuna fattura caricata.
--
-- Soluzione: indice UNIQUE non-parziale sulle stesse 4 colonne. PostgREST lo usa direttamente.
-- Verificato pre-migration: 0 collisioni su (user_id, ristorante_id, file_origine, numero_riga)
-- sull'INTERA tabella (incluse le righe cestinate), quindi la creazione non puo' fallire.
--
-- Effetto sul cestino: ora una riga cestinata e una attiva con la stessa quaterna NON possono
-- coesistere. Il re-upload di un file cestinato fa DO UPDATE sulla riga esistente; il codice
-- applicativo imposta deleted_at=NULL nel record di upsert, quindi la riga torna ATTIVA
-- (semantica coerente: ricaricare un file lo ripristina).

DROP INDEX IF EXISTS public.uq_fatture_dedup_active;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fatture_dedup
ON public.fatture (user_id, ristorante_id, file_origine, numero_riga);
