-- Indice di supporto per la guardia anti-doppione documento (invoice_service.py,
-- _trova_documento_duplicato_per_identita): cerca un documento ATTIVO con la stessa
-- identità naturale (piva_fornitore + numero_documento + data_documento + tipo_documento)
-- ma file_origine diverso, per rilevare lo stesso documento entrato due volte con nomi
-- file diversi (SDI + upload manuale, o stessa fattura con estensione diversa dopo
-- sbustatura P7M: 'X.xml.p7m' vs 'X.xml').
--
-- Non UNIQUE e non constraint: il blocco è applicativo (messaggio comprensibile al
-- cliente), non un errore Postgres 23505. Solo indice per rendere la query rapida.
-- Parziale su deleted_at IS NULL (i documenti cestinati non devono bloccare un
-- ricaricamento legittimo).

CREATE INDEX IF NOT EXISTS idx_fatture_documenti_identita_naturale
ON public.fatture_documenti (user_id, ristorante_id, piva_fornitore, numero_documento, data_documento, tipo_documento)
WHERE deleted_at IS NULL;
