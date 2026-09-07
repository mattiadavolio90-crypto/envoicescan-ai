-- Elimina sei funzioni raggiungibili ma non usate, misurate il 07/09/2026.
--
-- Quattro non hanno alcun chiamante in services/, worker/, utils/, scripts/,
-- tools/, supabase/functions/ e apps/web/. Le altre due sono un caso diverso e
-- vanno lette con attenzione: `get_distinct_files` E' VIVA e ha due chiamanti
-- in produzione (services/db_service.py, services/upload_handler.py). Di essa
-- si eliminano due varianti su tre, lasciando quella che i chiamanti usano.
--
-- La prima e' la legacy `(text)`, per due difetti misurati:
--
--   1. Non ha guardia di autorizzazione e non filtra `deleted_at`, quindi
--      conterebbe anche le fatture nel cestino (regola di dominio #5).
--   2. E' rotta comunque: ha `SET search_path TO ''` ma referenzia `fatture`
--      senza qualificarla, quindi se venisse scelta risponderebbe
--      `relation "fatture" does not exist`. Verificato eseguendola.
--
-- Insieme a lei se ne elimina una seconda, `get_distinct_files(uuid)`. E' un
-- wrapper di una riga che chiama `get_distinct_files(p_user_id, NULL::uuid)`,
-- cioe' esattamente cio' che la 2-arg fa gia' da sola grazie al suo
-- `DEFAULT NULL`. Non aggiunge nulla, e la sua esistenza e' proprio cio' che
-- rende ambigua la chiamata a un argomento:
--
--      get_distinct_files(p_user_id => <uuid>)
--      ERROR: function public.get_distinct_files(p_user_id => uuid) is not unique
--
-- Misurato sul DB live il 07/09/2026. E' l'errore PGRST203 che i due chiamanti
-- incontrano quando manca la sede: in `elimina_tutte_fatture` viene ingoiato
-- (`logger.warning`) e il codice prosegue con un conteggio parziale, cioe'
-- dichiara all'utente MENO fatture di quante ne sta cancellando.
--
-- Nota per chi legge: togliere la sola variante `(text)` NON basta. Le due
-- rimaste sarebbero ambigue fra loro, perche' il `DEFAULT NULL` rende la 2-arg
-- chiamabile con un argomento solo. Verificato eseguendo, non deducendo.
--
-- Resta quindi UNA sola variante, l'implementazione completa, che non va
-- toccata e che soddisfa entrambi i chiamanti (con e senza sede):
--   get_distinct_files(p_user_id uuid, p_ristorante_id uuid DEFAULT NULL)
--   -> guardia auth.role()/auth.uid(), verifica proprieta' della sede,
--      filtro `deleted_at IS NULL`.
--
-- La firma va sempre esplicitata: il solo nome non distingue le varianti.

DROP FUNCTION IF EXISTS public.get_distinct_files(p_user_id text);
DROP FUNCTION IF EXISTS public.get_distinct_files(p_user_id uuid);

DROP FUNCTION IF EXISTS public.gruppo_prezzi_categoria(
    p_ristorante_ids uuid[], p_data_da date, p_data_a date, p_escludi_da_verificare boolean);

DROP FUNCTION IF EXISTS public.swap_ricette_order(ricetta_id_1 uuid, ricetta_id_2 uuid);

DROP FUNCTION IF EXISTS public.create_ristorante_for_user(
    p_user_id uuid, p_nome text, p_piva character varying, p_ragione_sociale text);

DROP FUNCTION IF EXISTS public.conta_ristoranti_utente(p_user_id uuid);
