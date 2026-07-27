-- RPC: peso % di ogni categoria sul totale acquisti F&B, per PUNTO VENDITA.
--
-- Serve al segnale di catena "prezzi_sopra" (rinominato di fatto in "peso
-- categoria"), che prima confrontava il PREZZO MEDIO UNITARIO fra PV. Quel
-- confronto era rumore: unità di misura e formati confezione diversi fra
-- fornitori producevano scarti del +300% su categorie eterogenee, mentre sugli
-- stessi dati la composizione della spesa era identica al decimo di punto
-- (SUSHILAND apr-giu 2026: Pesce 53,6%-56,7% sui 4 PV).
--
-- Il peso sul totale è invece confrontabile per costruzione: è una quota, non
-- un prezzo, quindi non dipende da come il fornitore fattura la merce.
--
-- Denominatore = solo categorie Food & Beverage: le spese generali (utenze,
-- manutenzione, materiale di consumo, servizi) sono escluse perché un PV con
-- l'affitto più caro falserebbe il peso di TUTTE le categorie cibo.
--
-- Coerente col resto dell'app:
--   - data di riferimento = COALESCE(data_competenza, data_documento)
--   - filtri: deleted_at IS NULL, categoria <> 'Da Classificare', totale_riga > 0

CREATE OR REPLACE FUNCTION gruppo_peso_categoria(
    p_ristorante_ids uuid[],
    p_data_da date,
    p_data_a date
)
RETURNS TABLE (ristorante_id uuid, categoria text, spesa numeric, peso_perc numeric)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    WITH righe AS (
        SELECT
            f.ristorante_id AS rid,
            f.categoria AS cat,
            SUM(f.totale_riga) AS tot
        FROM fatture f
        WHERE f.ristorante_id = ANY(p_ristorante_ids)
          AND f.deleted_at IS NULL
          AND f.categoria <> 'Da Classificare'
          AND f.totale_riga > 0
          AND UPPER(f.categoria) NOT IN (
                'SERVIZI E CONSULENZE',
                'UTENZE E LOCALI',
                'MANUTENZIONE E ATTREZZATURE',
                'MATERIALE DI CONSUMO'
          )
          AND f.categoria NOT LIKE '%NOTE E DICITURE%'
          AND COALESCE(f.data_competenza, f.data_documento) IS NOT NULL
          AND COALESCE(f.data_competenza, f.data_documento) >= p_data_da
          AND COALESCE(f.data_competenza, f.data_documento) <= p_data_a
        GROUP BY 1, 2
    ),
    tot_pv AS (
        SELECT rid, SUM(tot) AS tot_fb FROM righe GROUP BY 1
    )
    SELECT
        r.rid AS ristorante_id,
        r.cat AS categoria,
        r.tot AS spesa,
        (100.0 * r.tot / t.tot_fb)::numeric AS peso_perc
    FROM righe r
    JOIN tot_pv t ON t.rid = r.rid
    WHERE t.tot_fb > 0;
$$;

REVOKE ALL ON FUNCTION gruppo_peso_categoria(uuid[], date, date) FROM public, anon, authenticated;
