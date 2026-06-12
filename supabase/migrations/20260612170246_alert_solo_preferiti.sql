-- Toggle configuratore assistente: avvisi prezzi (briefing + notifiche) limitati
-- ai soli prodotti PREFERITI del ristorante (stella in pagina Prezzi) + i custom
-- tag. Default false = comportamento attuale invariato (AI-first: prodotti che
-- pesano sull'80% della spesa food via Pareto + tag). Si attiva solo se il
-- cliente lo sceglie. Fallback: se attivo ma senza preferiti -> solo i tag,
-- nessun avviso prodotto (NO ritorno al Pareto).

ALTER TABLE assistant_preferences
    ADD COLUMN IF NOT EXISTS alert_prezzi_solo_preferiti boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN assistant_preferences.alert_prezzi_solo_preferiti IS
    'Se true, gli avvisi prezzi si limitano ai prodotti preferiti (prezzi_preferiti) + tag. Default false = Pareto + tag.';
