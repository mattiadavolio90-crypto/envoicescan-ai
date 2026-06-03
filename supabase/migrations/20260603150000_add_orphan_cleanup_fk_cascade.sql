-- Tabelle per-tenant che alla cancellazione account restavano ORFANE (no FK CASCADE,
-- non incluse nel loop di admin_elimina_cliente) -> residui dati cliente (problema GDPR).
-- Fix: pulizia orfani esistenti + FK ON DELETE CASCADE verso users/ristoranti.
--
-- daily_briefing_state NON e' qui: ha user_id/ristorante_id di tipo TEXT (non uuid),
-- la FK non e' applicabile senza conversione di tipo -> gestita via lista applicativa
-- in admin_elimina_cliente. La conversione text->uuid resta come miglioria schema futura.

-- 1) Cleanup righe orfane preesistenti (residuo cancellazione account passata).
--    Verificato: 24 righe in margini_mensili di un user_id non piu' esistente.
DELETE FROM public.margini_mensili t
WHERE t.user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM public.users u WHERE u.id = t.user_id);

-- 2) FK ON DELETE CASCADE su user_id e ristorante_id per le 6 tabelle uuid.
DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'notification_inbox','margini_mensili','fornitori_pagamenti_config',
    'category_change_log','chat_usage_log','email_rate_log'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    -- FK verso users(id)
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = format('fk_%s_user', t) AND conrelid = format('public.%I', t)::regclass
    ) THEN
      EXECUTE format(
        'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE',
        t, format('fk_%s_user', t)
      );
    END IF;
    -- FK verso ristoranti(id)
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint
      WHERE conname = format('fk_%s_rist', t) AND conrelid = format('public.%I', t)::regclass
    ) THEN
      EXECUTE format(
        'ALTER TABLE public.%I ADD CONSTRAINT %I FOREIGN KEY (ristorante_id) REFERENCES public.ristoranti(id) ON DELETE CASCADE',
        t, format('fk_%s_rist', t)
      );
    END IF;
  END LOOP;
END $$;
