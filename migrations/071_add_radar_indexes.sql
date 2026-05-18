-- Indice per Radar duplicati su fatture_documenti
CREATE INDEX IF NOT EXISTS idx_fatture_documenti_radar
ON fatture_documenti (
    user_id,
    ristorante_id,
    piva_fornitore,
    data_documento,
    totale_documento
)
WHERE deleted_at IS NULL;

-- Indice per storico importi per fornitore
CREATE INDEX IF NOT EXISTS idx_fatture_documenti_piva_data
ON fatture_documenti (
    user_id,
    ristorante_id,
    piva_fornitore,
    data_documento DESC
)
WHERE deleted_at IS NULL AND piva_fornitore IS NOT NULL;
