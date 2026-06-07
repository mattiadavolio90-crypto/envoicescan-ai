-- Multi-token: sessioni multiple per utente (1 utente -> N dispositivi).
-- Sostituisce il modello a token singolo su users.session_token, che faceva si'
-- che un secondo login sloggasse silenziosamente il primo dispositivo (cookie orfano -> 401).
--
-- Strategia additiva: questa tabella affianca users.session_token. La validazione
-- (verifica_sessione_da_cookie) cerca prima qui, poi fa fallback alla vecchia colonna,
-- cosi' le sessioni create prima del deploy non si rompono. users.session_token resta
-- in DB (deprecata) e verra' rimossa quando tutte le sessioni legacy saranno scadute.
--
-- Nota indice: idx_sessioni_token_active e' UNIQUE PARZIALE (WHERE revoked_at IS NULL).
-- E' usato SOLO per lookup applicative, MAI come arbitro di un upsert PostgREST
-- (che non supporta indici parziali e darebbe errore 42P10).

CREATE TABLE IF NOT EXISTS public.sessioni (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  token         text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  user_agent    text,
  ip            text,
  source        text NOT NULL DEFAULT 'login',   -- 'login' | 'impersonation'
  revoked_at    timestamptz
);

-- Un token attivo e' unico; i token revocati possono ripetersi senza vincolo.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessioni_token_active
  ON public.sessioni (token) WHERE revoked_at IS NULL;

-- Lookup sessioni attive di un utente, ordinate per ultima attivita' (evict + cap 5).
CREATE INDEX IF NOT EXISTS idx_sessioni_user_active
  ON public.sessioni (user_id, last_seen_at DESC) WHERE revoked_at IS NULL;
