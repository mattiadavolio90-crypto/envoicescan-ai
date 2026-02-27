-- ============================================================
-- MIGRATION 036: Aggiungi ultimo_ristorante_id a users
-- ============================================================
-- Colonna usata da app.py per ricordare l'ultimo ristorante
-- selezionato dall'utente tra una sessione e l'altra.
--
-- Viene scritta da app.py ogni volta che l'utente cambia ristorante:
--   supabase.table('users').update({'ultimo_ristorante_id': ristorante_id})
--             .eq('id', user_id).execute()
--
-- Viene letta all'avvio di sessione per impostare il ristorante
-- di default invece del primo in lista.
-- ============================================================

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS ultimo_ristorante_id UUID REFERENCES public.ristoranti(id) ON DELETE SET NULL;

COMMENT ON COLUMN public.users.ultimo_ristorante_id IS 'Ultimo ristorante selezionato - usato per ripristinare il contesto alla prossima sessione';
