-- RPC per il conteggio aggregato delle fatture per utente nella lista clienti admin.
-- Sostituisce il full-load lato Python (scaricava tutte le righe e contava in
-- memoria). Conta i documenti attivi (deleted_at IS NULL) raggruppati per user_id.

create or replace function admin_conteggio_fatture(p_user_ids uuid[])
returns table (user_id uuid, n bigint)
language sql
stable
security definer
set search_path = public
as $$
  select fd.user_id, count(*)::bigint as n
  from fatture_documenti fd
  where fd.user_id = any(p_user_ids)
    and fd.deleted_at is null
  group by fd.user_id;
$$;

revoke all on function admin_conteggio_fatture(uuid[]) from public, anon, authenticated;
