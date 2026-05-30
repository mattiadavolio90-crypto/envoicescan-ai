-- Audit log per ogni decisione dell'AI o dell'admin che tocca la categoria di righe fattura.
-- Permette "Annulla" su un gruppo (batch), osservabilità completa del processo.
create table if not exists ai_review_log (
    id          bigserial primary key,
    created_at  timestamptz not null default now(),
    attore      text not null,               -- 'auto-review' | 'admin:email' | 'streak-auto'
    azione      text not null,               -- 'classifica' | 'auto_review' | 'risolvi_conflitto' | 'annulla'
    descrizione text,                        -- descrizione prodotto (per leggibilità)
    categoria_da text,                       -- categoria precedente (per undo)
    categoria_a  text not null,              -- categoria applicata
    ids_fatture  bigint[] not null default '{}', -- IDs righe fattura toccate
    righe_count  int not null default 0,
    nota         text,                       -- info extra (bucket, conflitto, ecc.)
    annullato_at timestamptz,               -- NULL = attivo; NOT NULL = annullato
    annullato_da text
);

create index if not exists ai_review_log_created_at_idx on ai_review_log (created_at desc);
create index if not exists ai_review_log_attore_idx on ai_review_log (attore);
create index if not exists ai_review_log_annullato_idx on ai_review_log (annullato_at) where annullato_at is null;
