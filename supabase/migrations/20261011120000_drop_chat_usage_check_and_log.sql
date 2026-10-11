-- Via la vecchia RPC della chat (11/10/2026, residuo della fase J).
--
-- Dal 10/10/2026 il worker consuma i crediti con `chat_crediti_check_and_log`
-- (migration 20261010135911); `chat_usage_check_and_log` era rimasta solo per il
-- worker VECCHIO nella finestra fra migration e push. Il push e' passato e il
-- codice non la chiama piu' (zero chiamanti in services/, worker/, functions/).
-- Una funzione SECURITY DEFINER che scrive su chat_usage_log e che nessuno usa
-- e' una porta in piu' da sorvegliare: si toglie.
--
-- Contiene un DROP: il connettore MCP la rifiuta, va incollata nell'SQL Editor.
-- Idempotente (IF EXISTS). I test `-m sql` la applicano come le altre.

DROP FUNCTION IF EXISTS public.chat_usage_check_and_log(uuid, uuid, integer, boolean, integer);
