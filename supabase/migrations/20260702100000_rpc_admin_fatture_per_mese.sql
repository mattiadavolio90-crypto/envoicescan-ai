-- RPC per il breakdown mensile delle fatture nell'Admin Overview.
-- Sostituisce il full-load lato Python (admin.py scaricava fino a 50.000 righe
-- `data_documento` e faceva il GROUP BY per mese in memoria, tenendo occupato un
-- thread del worker per secondi). Qui il conteggio raggruppato per mese lo fa il
-- DB e torna ~12 righe. Fondamentale per non saturare il threadpool sotto carico.
--
-- p_dal: data di partenza (inclusa). Conta i documenti attivi (deleted_at IS NULL).

create or replace function admin_fatture_per_mese(p_dal date)
returns table (mese text, n bigint)
language sql
stable
security definer
set search_path = public
as $$
  select to_char(fd.data_documento, 'YYYY-MM') as mese, count(*)::bigint as n
  from fatture_documenti fd
  where fd.data_documento >= p_dal
    and fd.deleted_at is null
  group by to_char(fd.data_documento, 'YYYY-MM')
  order by mese;
$$;

revoke all on function admin_fatture_per_mese(date) from public, anon, authenticated;
