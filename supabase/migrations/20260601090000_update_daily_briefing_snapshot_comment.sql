-- Aggiorna la documentazione della colonna snapshot dopo l'introduzione di
-- azioni[] e tutto_ok per la Home AI. Nessuna modifica di schema: snapshot e'
-- jsonb schemaless, i nuovi campi non richiedono migration strutturale.

COMMENT ON COLUMN daily_briefing_state.snapshot IS
    'JSON del briefing Home AI: {bullets: [str], azioni: [{id, topic_key, severity, testo, cta_label, cta_page}], tutto_ok: bool, narrative: str (template o AI), generated_at: ISO, notif_count: int, notif_fingerprint: str, severity_max: str}';
