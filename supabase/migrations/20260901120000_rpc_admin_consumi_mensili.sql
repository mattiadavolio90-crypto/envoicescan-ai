-- Consumi mensili per SEDE, per il tab Admin "Consumi & Piani".
--
-- Due RPC affiancate (fatture e AI) piu' l'indice che mancava su created_at.
--
-- Perche' `created_at` e non `data_documento`: qui si misura il CONSUMO DEL
-- SERVIZIO, cioe' quando la fattura e' entrata in ONEFLUX. Le due basi divergono
-- in modo massiccio -- a luglio 2026 sono stati caricati 1.097 documenti, di cui
-- solo 55 erano fatture di luglio (il resto arretrato fino a gennaio). Un conteggio
-- per data_documento renderebbe la soglia di piano aggirabile caricando arretrati.
-- Il contatore che il CLIENTE vede in Impostazioni (services/routers/account.py)
-- usa invece data_documento e resta com'e': misura un'altra cosa.
--
-- Perche' `distinct ... file_origine`: una fattura ha N righe in fatture_documenti.
-- Senza distinct si conterebbero le righe e il numero risulterebbe gonfiato.

create or replace function admin_consumi_mensili(p_dal date)
returns table (
  ristorante_id uuid,
  mese text,
  manuali bigint,
  sdi bigint,
  tot bigint
)
language sql
stable
security definer
set search_path = public
as $$
  with doc as (
    select distinct
           fd.ristorante_id,
           fd.file_origine,
           date_trunc('month', fd.created_at)::date as mese,
           fd.source_origin
    from fatture_documenti fd
    where fd.deleted_at is null
      and fd.created_at >= p_dal
  )
  select d.ristorante_id,
         to_char(d.mese, 'YYYY-MM') as mese,
         count(*) filter (where d.source_origin = 'manual')::bigint        as manuali,
         count(*) filter (where d.source_origin = 'invoicetronic')::bigint as sdi,
         count(*)::bigint                                                  as tot
  from doc d
  group by d.ristorante_id, d.mese
  order by d.mese desc;
$$;

revoke all on function admin_consumi_mensili(date) from public, anon, authenticated;


-- Richieste AI per sede/mese. Una richiesta e' un BATCH, non una fattura (48
-- richieste hanno coperto 214 fatture ad agosto 2026): e' un dato di consumo e
-- costo, non confrontabile con la soglia fatture del piano.

create or replace function admin_ai_mensile(p_dal date)
returns table (
  ristorante_id uuid,
  mese text,
  categorization bigint,
  chat bigint,
  richieste bigint,
  token bigint,
  costo numeric
)
language sql
stable
security definer
set search_path = public
as $$
  select e.ristorante_id,
         to_char(date_trunc('month', e.created_at), 'YYYY-MM') as mese,
         count(*) filter (where e.operation_type = 'categorization')::bigint as categorization,
         count(*) filter (where e.operation_type = 'chat')::bigint           as chat,
         count(*)::bigint                                                    as richieste,
         coalesce(sum(e.total_tokens), 0)::bigint                            as token,
         coalesce(sum(e.total_cost), 0)::numeric                             as costo
  from ai_usage_events e
  where e.created_at >= p_dal
  group by e.ristorante_id, date_trunc('month', e.created_at)
  order by mese desc;
$$;

revoke all on function admin_ai_mensile(date) from public, anon, authenticated;


-- fatture_documenti non aveva alcun indice su created_at (quelli esistenti sono
-- tutti su user_id/ristorante_id + scadenza/pagata/piva/fornitore). Senza questo
-- le due RPC fanno seq scan a ogni apertura del tab.
create index if not exists idx_fatture_documenti_rist_created
  on fatture_documenti (ristorante_id, created_at)
  where deleted_at is null;
