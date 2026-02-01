-- ============================================================
-- MIGRAZIONE: Tracking Costi AI per Cliente
-- ============================================================
-- Aggiunge colonne per tracciare costi AI per ristorante
-- Versione: 014
-- Data: 2026-02-01
-- ============================================================

-- Aggiungi colonne tracking AI alla tabella ristoranti
ALTER TABLE ristoranti 
ADD COLUMN IF NOT EXISTS ai_cost_total DECIMAL(10,4) DEFAULT 0,
ADD COLUMN IF NOT EXISTS ai_pdf_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS ai_categorization_count INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS ai_last_usage TIMESTAMP;

-- Commenti per documentazione
COMMENT ON COLUMN ristoranti.ai_cost_total IS 'Costo totale cumulativo AI in USD (PDF + Categorizzazione)';
COMMENT ON COLUMN ristoranti.ai_pdf_count IS 'Numero totale PDF/immagini processati con AI Vision';
COMMENT ON COLUMN ristoranti.ai_categorization_count IS 'Numero totale categorizzazioni AI effettuate';
COMMENT ON COLUMN ristoranti.ai_last_usage IS 'Timestamp ultimo utilizzo AI';

-- Drop funzione esistente increment_ai_cost (vecchia signature)
DROP FUNCTION IF EXISTS increment_ai_cost(UUID, DECIMAL, INT);

-- Funzione RPC per incrementare costo AI
CREATE OR REPLACE FUNCTION increment_ai_cost(
    p_ristorante_id UUID,
    p_cost DECIMAL,
    p_tokens INT DEFAULT 0,
    p_operation_type TEXT DEFAULT 'pdf'
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE ristoranti
    SET 
        ai_cost_total = COALESCE(ai_cost_total, 0) + p_cost,
        ai_pdf_count = CASE 
            WHEN p_operation_type = 'pdf' THEN COALESCE(ai_pdf_count, 0) + 1
            ELSE COALESCE(ai_pdf_count, 0)
        END,
        ai_categorization_count = CASE 
            WHEN p_operation_type = 'categorization' THEN COALESCE(ai_categorization_count, 0) + 1
            ELSE COALESCE(ai_categorization_count, 0)
        END,
        ai_last_usage = NOW()
    WHERE id = p_ristorante_id;
END;
$$;

-- Drop funzione esistente (se presente) per evitare conflitti tipo ritorno
DROP FUNCTION IF EXISTS get_ai_costs_summary();

-- Funzione RPC per ottenere riepilogo costi AI (per admin)
CREATE OR REPLACE FUNCTION get_ai_costs_summary()
RETURNS TABLE (
    ristorante_id UUID,
    nome_ristorante TEXT,
    ragione_sociale TEXT,
    ai_cost_total DECIMAL,
    ai_pdf_count INT,
    ai_categorization_count INT,
    ai_last_usage TIMESTAMP,
    ai_avg_cost_per_operation DECIMAL
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        r.id,
        r.nome_ristorante,
        r.ragione_sociale,
        COALESCE(r.ai_cost_total, 0) as ai_cost_total,
        COALESCE(r.ai_pdf_count, 0) as ai_pdf_count,
        COALESCE(r.ai_categorization_count, 0) as ai_categorization_count,
        r.ai_last_usage,
        CASE 
            WHEN (COALESCE(r.ai_pdf_count, 0) + COALESCE(r.ai_categorization_count, 0)) > 0 
            THEN ROUND(COALESCE(r.ai_cost_total, 0) / (r.ai_pdf_count + r.ai_categorization_count), 4)
            ELSE 0
        END as ai_avg_cost_per_operation
    FROM ristoranti r
    WHERE r.attivo = true
    ORDER BY r.ai_cost_total DESC NULLS LAST;
END;
$$;

-- Grant permessi
GRANT EXECUTE ON FUNCTION increment_ai_cost TO authenticated;
GRANT EXECUTE ON FUNCTION get_ai_costs_summary TO authenticated;
