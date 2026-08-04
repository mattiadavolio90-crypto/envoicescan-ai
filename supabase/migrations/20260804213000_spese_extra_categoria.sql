-- ============================================================
-- MIGRATION: Categoria sulle spese extra (tab Spese)
-- ============================================================
-- Sostituisce la scelta grossolana F&B/Generale con le 29 categorie canoniche
-- gia' usate dall'AI sulle righe fattura (TUTTE_LE_CATEGORIE in config/constants.py).
--
-- Il campo `tipo` NON sparisce: e' il binario contabile che decide in quale cella
-- di margini_mensili finisce il totale mensile (fb -> altri_costi_fb,
-- generale -> altri_costi_spese) e quindi entra nel MOL. Da qui in avanti e'
-- DERIVATO dalla categoria lato router (_tipo_da_categoria in
-- services/routers/workspace.py), mai piu' scelto a mano quando c'e' una categoria.
--
-- NULLABLE e senza backfill, deliberatamente: una spesa 'fb' storica puo' essere
-- CARNE o PESCE e non e' desumibile. Le voci pre-esistenti restano categoria IS NULL,
-- continuano a funzionare perche' `tipo` e' ancora popolato, e contano nel MOL
-- esattamente come prima. Migration puramente additiva: nessun UPDATE su righe
-- esistenti, quindi i totali per tipo non possono muoversi.
--
-- Niente CHECK sulla lista delle categorie: vive gia' in config/constants.py e
-- nella tabella `categorie`, un terzo posto da tenere allineato sarebbe debito.
-- La validazione sta nel router.

ALTER TABLE spese_extra ADD COLUMN IF NOT EXISTS categoria TEXT;

COMMENT ON COLUMN spese_extra.categoria IS 'Categoria canonica (TUTTE_LE_CATEGORIE in config/constants.py). NULL = voce storica senza categoria, mai inventata a posteriori. Il tipo fb/generale e'' derivato da questa colonna lato router.';

CREATE INDEX IF NOT EXISTS idx_spese_extra_categoria
    ON spese_extra (ristorante_id, categoria)
    WHERE categoria IS NOT NULL;
