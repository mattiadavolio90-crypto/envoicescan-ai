-- Mapping email mittente gestionale → ristorante ONEFLUX
-- Gestito lato admin; il sender è fisso per gestionale (es. "export@passbi.it")
create table if not exists ricavi_email_sender_map (
    id            uuid primary key default gen_random_uuid(),
    email_sender  text not null,
    ristorante_id uuid not null references ristoranti(id) on delete cascade,
    gestionale    text not null default 'passbi_v1',
    attivo        boolean not null default true,
    created_at    timestamptz not null default now(),
    unique (email_sender)
);

create index if not exists idx_ricavi_email_sender_map_sender
    on ricavi_email_sender_map (email_sender);

-- Coda email in ingresso con allegati XLS ricavi
-- Alimentata dalla Edge Function ricavi-email-webhook (Brevo Inbound)
-- Consumata dal worker email_queue_processor.py
create table if not exists ricavi_email_queue (
    id               uuid primary key default gen_random_uuid(),
    idempotency_key  text not null,    -- hash(sender+subject+attachment_name+ora_arrotondata_1h)
    email_sender     text not null,
    email_subject    text,
    attachment_name  text,
    storage_path     text,             -- path in bucket "ricavi-xls"
    ristorante_id    uuid references ristoranti(id),
    user_id          uuid,
    status           text not null default 'pending'
        check (status in ('pending', 'processing', 'done', 'failed', 'dead', 'unknown_sender')),
    attempt_count    int not null default 0,
    max_attempts     int not null default 5,
    next_retry_at    timestamptz not null default now(),
    locked_at        timestamptz,
    locked_by        text,
    last_error       text,
    imported_rows    int,
    created_at       timestamptz not null default now(),
    processed_at     timestamptz,
    unique (idempotency_key)
);

create index if not exists idx_ricavi_email_queue_status_retry
    on ricavi_email_queue (status, next_retry_at)
    where status in ('pending', 'failed');

-- RLS: accesso solo service_role (nessuna policy pubblica)
alter table ricavi_email_sender_map enable row level security;
alter table ricavi_email_queue enable row level security;
