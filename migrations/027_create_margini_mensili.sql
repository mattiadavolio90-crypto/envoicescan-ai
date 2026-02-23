-- ============================================================
-- MIGRATION 027: Crea tabella margini_mensili
-- ============================================================
-- Tabella per il calcolo del Margine Operativo Lordo (MOL) mensile.
-- Salva input manuali (fatturato, costi extra, personale) e snapshot
-- dei costi automatici calcolati dalle fatture.
-- I costi automatici vengono ricalcolati ad ogni accesso (Opzione B).
-- ============================================================

CREATE TABLE IF NOT EXISTS margini_mensili (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,                  -- FK utente (con underscore, allineato a fatture)
    ristorante_id UUID NOT NULL,            -- FK ristorante (con underscore, allineato a fatture)
    anno INTEGER NOT NULL,
    mese INTEGER NOT NULL CHECK (mese >= 1 AND mese <= 12),
    
    -- INPUT MANUALE (editabili dall'utente)
    fatturato_iva10 NUMERIC(10,2) DEFAULT 0,    -- Fatturato IVA vendita 10%
    fatturato_iva22 NUMERIC(10,2) DEFAULT 0,    -- Fatturato IVA vendita 22%
    altri_costi_fb NUMERIC(10,2) DEFAULT 0,     -- Costi F&B extra (non in fatture)
    altri_costi_spese NUMERIC(10,2) DEFAULT 0,  -- Spese generali extra (non in fatture)
    costo_dipendenti NUMERIC(10,2) DEFAULT 0,   -- Costo personale lordo mensile
    
    -- SNAPSHOT COSTI AUTOMATICI (calcolati da fatture, ricalcolati al load)
    costi_fb_auto NUMERIC(10,2) DEFAULT 0,      -- Da fatture con categorie CATEGORIE_FOOD
    costi_spese_auto NUMERIC(10,2) DEFAULT 0,   -- Da fatture con categorie CATEGORIE_SPESE_GENERALI
    
    -- SNAPSHOT CAMPI CALCOLATI (ricalcolati on-the-fly, salvati per export/storico)
    fatturato_netto NUMERIC(10,2) DEFAULT 0,
    costi_fb_totali NUMERIC(10,2) DEFAULT 0,
    primo_margine NUMERIC(10,2) DEFAULT 0,
    mol NUMERIC(10,2) DEFAULT 0,
    food_cost_perc NUMERIC(5,2) DEFAULT 0,
    spese_perc NUMERIC(5,2) DEFAULT 0,
    personale_perc NUMERIC(5,2) DEFAULT 0,
    mol_perc NUMERIC(5,2) DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Un solo record per ristorante/anno/mese
    UNIQUE(ristorante_id, anno, mese)
);

-- ============================================================
-- INDEXES per performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_margini_ristorante_anno 
    ON margini_mensili(ristorante_id, anno);

CREATE INDEX IF NOT EXISTS idx_margini_user 
    ON margini_mensili(user_id);

CREATE INDEX IF NOT EXISTS idx_margini_anno_mese 
    ON margini_mensili(anno, mese);

-- ============================================================
-- RLS PERMISSIVE (allineato a 024_fix_rls_custom_auth.sql)
-- L'app usa autenticazione custom, sicurezza gestita a livello applicativo.
-- ============================================================
ALTER TABLE margini_mensili ENABLE ROW LEVEL SECURITY;

CREATE POLICY "margini_mensili_select_policy" ON margini_mensili
    FOR SELECT USING (true);

CREATE POLICY "margini_mensili_insert_policy" ON margini_mensili
    FOR INSERT WITH CHECK (true);

CREATE POLICY "margini_mensili_update_policy" ON margini_mensili
    FOR UPDATE USING (true);

CREATE POLICY "margini_mensili_delete_policy" ON margini_mensili
    FOR DELETE USING (true);

-- Grant accesso (coerente con altre tabelle)
GRANT ALL ON margini_mensili TO anon;
GRANT ALL ON margini_mensili TO authenticated;
GRANT ALL ON margini_mensili TO service_role;

-- ============================================================
-- VERIFICA
-- ============================================================
-- SELECT tablename, policyname, cmd, qual, with_check 
-- FROM pg_policies 
-- WHERE tablename = 'margini_mensili';
