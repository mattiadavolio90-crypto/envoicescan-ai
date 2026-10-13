-- Memoria degli allarmi Telegram dell'admin (riordino del 13/10/2026).
--
-- Prima ogni controllo (uptime ogni 15', latenza ogni 10') rimandava lo stesso
-- messaggio a ogni giro finche' il problema durava, e nessuno diceva quando era
-- finito. Qui ogni allarme ha una chiave e uno stato: chi controlla chiama
-- admin_allarme_segnala dicendo SOLO se il problema c'e' adesso, e la funzione
-- decide se scrivere su Telegram.
--
-- La tabella sta nel DB e non nella memoria di un processo perche' i controlli
-- urgenti girano su GitHub Actions (fuori dai server che sorvegliano: un server
-- spento non puo' avvisare di essere spento), un run per volta e senza stato.
create table if not exists admin_allarmi (
  chiave          text primary key,
  gravita         text not null check (gravita in ('critico', 'oggi')),
  aperto_at       timestamptz,
  ultimo_invio_at timestamptz,
  risolto_at      timestamptz,
  occorrenze      integer not null default 0,
  testo           text,
  link            text,
  updated_at      timestamptz not null default now()
);

alter table admin_allarmi enable row level security;
revoke all on table admin_allarmi from public, anon, authenticated;

-- Ritorna l'azione da fare:
--   'invia'   problema nuovo (o riaperto dopo essere rientrato)
--   'ripeti'  critico ancora aperto, ultimo messaggio piu' vecchio di p_ripeti
--   'zitto'   problema gia' segnalato, niente di nuovo da dire
--   'risolto' il problema c'era e non c'e' piu': si manda il ✅
--   'niente'  nessun problema, prima ne' adesso
-- Un 'oggi' non si ripete mai: lo si dice una volta per apertura.
create or replace function admin_allarme_segnala(
  p_chiave   text,
  p_gravita  text,
  p_problema boolean,
  p_testo    text default null,
  p_link     text default null,
  p_ripeti   interval default interval '6 hours'
) returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  r admin_allarmi%rowtype;
begin
  if p_gravita not in ('critico', 'oggi') then
    raise exception 'gravita non valida: %', p_gravita;
  end if;

  insert into admin_allarmi (chiave, gravita)
  values (p_chiave, p_gravita)
  on conflict (chiave) do nothing;

  select * into r from admin_allarmi where chiave = p_chiave for update;

  if not p_problema then
    if r.aperto_at is null then
      return 'niente';
    end if;
    update admin_allarmi
       set aperto_at = null, risolto_at = now(), updated_at = now()
     where chiave = p_chiave;
    return 'risolto';
  end if;

  if r.aperto_at is null then
    update admin_allarmi
       set gravita = p_gravita, aperto_at = now(), ultimo_invio_at = now(),
           risolto_at = null, occorrenze = 1, testo = p_testo, link = p_link,
           updated_at = now()
     where chiave = p_chiave;
    return 'invia';
  end if;

  if p_gravita = 'critico' and r.ultimo_invio_at < now() - p_ripeti then
    update admin_allarmi
       set occorrenze = r.occorrenze + 1, ultimo_invio_at = now(),
           testo = p_testo, link = p_link, updated_at = now()
     where chiave = p_chiave;
    return 'ripeti';
  end if;

  update admin_allarmi
     set occorrenze = r.occorrenze + 1, testo = p_testo, link = p_link, updated_at = now()
   where chiave = p_chiave;
  return 'zitto';
end;
$$;

revoke all on function admin_allarme_segnala(text, text, boolean, text, text, interval)
  from public, anon, authenticated;
