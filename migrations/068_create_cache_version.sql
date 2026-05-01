-- Migration 068: Cache version table per invalidazione cross-process della memoria classificazione.
--
-- Contesto:
-- L'app Streamlit mantiene una cache in-memory (process-scoped) di prodotti_utente,
-- prodotti_master e classificazioni_manuali. In deploy multi-worker (Streamlit + worker)
-- ogni processo ha la sua cache → un INSERT/UPDATE/DELETE eseguito da un processo non
-- invalida la cache degli altri.
--
-- Soluzione: una piccola tabella con UNA riga per chiave; ogni scrittura sulle tabelle
-- memoria bumpa la `version`. Il client legge `version` con TTL ~30s; se diversa
-- dall'ultima vista, ricarica la cache locale.

create table if not exists public.cache_version (
    key text primary key,
    version bigint not null default 1,
    updated_at timestamptz not null default now()
);

insert into public.cache_version(key, version)
values ('memoria_classificazione', 1)
on conflict (key) do nothing;

-- ---------- Funzione bump (SECURITY DEFINER per scrivere bypassando RLS) ----------
create or replace function public.fn_bump_cache_version()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    update public.cache_version
        set version = version + 1,
            updated_at = now()
    where key = 'memoria_classificazione';
    return null;
end;
$$;

revoke all on function public.fn_bump_cache_version() from public, anon, authenticated;
grant execute on function public.fn_bump_cache_version() to service_role;

-- ---------- Trigger su prodotti_utente / prodotti_master / classificazioni_manuali ----------
drop trigger if exists trg_bump_cache_pu on public.prodotti_utente;
create trigger trg_bump_cache_pu
after insert or update or delete on public.prodotti_utente
for each statement execute function public.fn_bump_cache_version();

drop trigger if exists trg_bump_cache_pm on public.prodotti_master;
create trigger trg_bump_cache_pm
after insert or update or delete on public.prodotti_master
for each statement execute function public.fn_bump_cache_version();

drop trigger if exists trg_bump_cache_cm on public.classificazioni_manuali;
create trigger trg_bump_cache_cm
after insert or update or delete on public.classificazioni_manuali
for each statement execute function public.fn_bump_cache_version();

-- ---------- RLS / GRANTS ----------
alter table public.cache_version enable row level security;

drop policy if exists "cache_version_read" on public.cache_version;
create policy "cache_version_read"
    on public.cache_version
    for select
    to authenticated, anon, service_role
    using (true);

-- Solo il service_role (back-end app) può scrivere; i trigger usano la funzione SECURITY DEFINER.
revoke insert, update, delete on public.cache_version from public, anon, authenticated;
grant select on public.cache_version to public, anon, authenticated, service_role;
grant insert, update on public.cache_version to service_role;
