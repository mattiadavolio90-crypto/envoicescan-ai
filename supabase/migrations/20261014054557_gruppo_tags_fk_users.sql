-- Tag di catena: i tag e i loro prodotti seguono l'account quando viene cancellato.
--
-- `gruppo_tags.user_id` e `gruppo_tag_prodotti.user_id` (20260617230000) sono
-- nati senza FK verso `users`. Le due strade di cancellazione di un account
-- (`POST /api/account/elimina` del cliente e la cancellazione dall'admin)
-- contano sul CASCADE da `users`: i nomi dei tag di catena e le descrizioni dei
-- loro prodotti, dati scritti dal cliente, restavano nel DB. Trovato il
-- 13/10/2026 nell'analisi delle inerenze delle Fasi C1-C2; sul live 0 righe
-- orfane, 1 account con tag di catena.
--
-- Da allora `gruppo_tag_cartelle` ha gia' la FK con CASCADE e `gruppo_tags`
-- la FK composta verso le cartelle con SET NULL (cartella_id): cancellando
-- l'account le cartelle spariscono e i tag perdono la cartella un istante
-- prima di sparire a loro volta. Nessun conflitto fra i due vincoli.
--
-- Idempotente. Va applicata al live PRIMA del push, come le altre di oggi.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'gruppo_tags_user_id_fkey'
          AND conrelid = 'public.gruppo_tags'::regclass
    ) THEN
        ALTER TABLE public.gruppo_tags
            ADD CONSTRAINT gruppo_tags_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'gruppo_tag_prodotti_user_id_fkey'
          AND conrelid = 'public.gruppo_tag_prodotti'::regclass
    ) THEN
        ALTER TABLE public.gruppo_tag_prodotti
            ADD CONSTRAINT gruppo_tag_prodotti_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
    END IF;
END
$$;

-- Ogni lettura del worker filtra `gruppo_tag_prodotti` per user_id, e il
-- CASCADE lo cerca: finora c'era solo l'indice su tag_id.
CREATE INDEX IF NOT EXISTS idx_gruppo_tag_prodotti_user
    ON public.gruppo_tag_prodotti (user_id);

COMMENT ON COLUMN public.gruppo_tags.user_id IS
    'Account del tag di catena. FK verso users con CASCADE: cancellato l''account, '
    'spariscono tag e prodotti del tag (GDPR art. 17).';
