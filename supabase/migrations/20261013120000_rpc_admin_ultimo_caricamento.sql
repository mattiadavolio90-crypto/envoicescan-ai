-- Ultimo caricamento per sede, per la lista clienti dell'admin.
--
-- Il pannello deve dire a colpo d'occhio chi ha smesso di mandare fatture: il
-- totale storico (admin_conteggio_fatture) non lo dice. Una riga per sede
-- richiesta, anche senza documenti (ultimo = NULL): la UI distingue «mai» da
-- «da N giorni». Il max sfrutta idx_fatture_documenti_rist_created.
create or replace function admin_ultimo_caricamento(p_ristorante_ids uuid[])
returns table(ristorante_id uuid, ultimo timestamptz)
language sql
stable
security definer
set search_path = public
as $$
  select r.id,
         (select max(fd.created_at)
            from fatture_documenti fd
           where fd.ristorante_id = r.id
             and fd.deleted_at is null)
  from unnest(p_ristorante_ids) as r(id);
$$;

revoke all on function admin_ultimo_caricamento(uuid[]) from public, anon, authenticated;
