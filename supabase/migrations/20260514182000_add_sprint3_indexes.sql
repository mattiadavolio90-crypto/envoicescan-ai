-- Indice per nota credito non usata
-- (query su tipo_documento + piva_cedente + created_at)
CREATE INDEX IF NOT EXISTS idx_fatture_tipo_piva_data
ON fatture (user_id, ristorante_id, tipo_documento,
            piva_cedente, data_documento)
WHERE deleted_at IS NULL AND piva_cedente IS NOT NULL;

-- Indice per sconto_fornitore_scaduto
-- (query su sconto_percentuale + piva_cedente)
CREATE INDEX IF NOT EXISTS idx_fatture_sconto_piva
ON fatture (user_id, ristorante_id, piva_cedente,
            data_documento)
WHERE deleted_at IS NULL AND sconto_percentuale > 0;

-- Indice per fornitore_unico_categoria
CREATE INDEX IF NOT EXISTS idx_fatture_categoria_piva
ON fatture (user_id, ristorante_id, categoria,
            piva_cedente, data_documento)
WHERE deleted_at IS NULL;
