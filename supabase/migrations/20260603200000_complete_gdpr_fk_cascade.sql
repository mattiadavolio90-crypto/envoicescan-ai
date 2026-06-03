-- Completa la copertura GDPR ON DELETE CASCADE per le tabelle per-tenant rimaste
-- scoperte. La cancellazione account (admin.py Streamlit, admin_elimina_cliente
-- FastAPI) eliminava solo un sottoinsieme di tabelle; le FK CASCADE garantiscono
-- che CANCELLARE la riga in users pulisca automaticamente TUTTI i dati personali,
-- da qualsiasi punto di ingresso, senza liste manuali da mantenere in 3 codebase.
--
-- diario_eventi, inventario_voci, ingredienti_utente, spese_extra, turni_personale:
--   dati operativi personali del ristoratore -> CASCADE (eliminati con l'account).
-- marketplace_leads: contatto commerciale -> SET NULL (si scollega l'identita',
--   il lead resta come dato aggregato anonimo).
--
-- Verificato 2026-06-03: 0 righe orfane in tutte le tabelle prima dell'ALTER.

-- ── CASCADE: dati operativi personali ──────────────────────────────────────
ALTER TABLE public.diario_eventi
  ADD CONSTRAINT diario_eventi_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.inventario_voci
  ADD CONSTRAINT inventario_voci_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.ingredienti_utente
  ADD CONSTRAINT ingredienti_utente_userid_fkey
  FOREIGN KEY (userid) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.spese_extra
  ADD CONSTRAINT spese_extra_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.turni_personale
  ADD CONSTRAINT turni_personale_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ── SET NULL: lead commerciale (mantenuto anonimizzato) ─────────────────────
ALTER TABLE public.marketplace_leads
  ADD CONSTRAINT marketplace_leads_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- ── Indici sulle nuove FK (un DELETE sul padre senza indice sul figlio fa seq scan) ──
CREATE INDEX IF NOT EXISTS idx_diario_eventi_user_id      ON public.diario_eventi(user_id);
CREATE INDEX IF NOT EXISTS idx_inventario_voci_user_id    ON public.inventario_voci(user_id);
CREATE INDEX IF NOT EXISTS idx_ingredienti_utente_userid  ON public.ingredienti_utente(userid);
CREATE INDEX IF NOT EXISTS idx_spese_extra_user_id        ON public.spese_extra(user_id);
CREATE INDEX IF NOT EXISTS idx_turni_personale_user_id    ON public.turni_personale(user_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_leads_user_id  ON public.marketplace_leads(user_id);
