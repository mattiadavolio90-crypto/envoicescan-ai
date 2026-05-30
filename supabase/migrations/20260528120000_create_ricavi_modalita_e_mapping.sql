-- Modalità ricavi per mese: giornaliero (default) o mensile aggregato
-- Quando modalita = 'mensile', i campi fatturato_* contengono il totale mensile
-- e i dati giornalieri vengono ignorati nel calcolo dei margini.
create table if not exists ricavi_modalita_mensile (
    id          uuid primary key default gen_random_uuid(),
    ristorante_id uuid not null references ristoranti(id) on delete cascade,
    anno        int not null check (anno >= 2020 and anno <= 2100),
    mese        int not null check (mese >= 1 and mese <= 12),
    modalita    text not null default 'giornaliero' check (modalita in ('giornaliero', 'mensile')),
    fatturato_iva10   numeric(12,4) not null default 0,
    fatturato_iva22   numeric(12,4) not null default 0,
    altri_ricavi_noiva numeric(12,4) not null default 0,
    updated_at  timestamptz not null default now(),
    unique (ristorante_id, anno, mese)
);

-- Mapping ragione sociale (stringa dal gestionale) → ristorante ONEFLUX
-- Gestito lato admin; usato dal parser Passbi v1 per catene multi-ristorante
create table if not exists ricavi_ragione_sociale_map (
    id                  uuid primary key default gen_random_uuid(),
    ragione_sociale_norm text not null,  -- lowercase, trimmed
    ristorante_id        uuid not null references ristoranti(id) on delete cascade,
    gestionale          text not null default 'passbi_v1',
    created_at          timestamptz not null default now(),
    unique (ragione_sociale_norm, gestionale)
);

-- Indici
create index if not exists idx_ricavi_modalita_mensile_ristorante_anno_mese
    on ricavi_modalita_mensile (ristorante_id, anno, mese);

create index if not exists idx_ricavi_ragione_sociale_map_norm
    on ricavi_ragione_sociale_map (ragione_sociale_norm, gestionale);

-- RLS: accesso solo con service_role_key (come resto del progetto)
alter table ricavi_modalita_mensile enable row level security;
alter table ricavi_ragione_sociale_map enable row level security;

-- Nessuna policy pubblica: solo service_role bypassa RLS
