#!/bin/bash
set -e

# ════════════════════════════════════════════════════════════════════════════
# ONEFLUX — Docker Entrypoint (FastAPI worker + queue-worker)
# ════════════════════════════════════════════════════════════════════════════
# Streamlit e' stato eliminato (switch 8/6 → Next.js su Vercel). Su Railway girano
# DUE servizi, entrambi da questa stessa immagine, distinti dal COMANDO:
#
#   worker        → python -m services.fastapi_worker   (API /health /api/*)
#   queue-worker  → python worker/run.py                (ingest coda fatture)
#
# Railway passa il comando come override del servizio: arriva qui come "$@" e
# viene eseguito. Se nessun comando e' passato, FALLIAMO esplicito invece di
# avviare un default (storicamente era `streamlit run app.py`, ora morto): un
# default sbagliato darebbe un deploy "verde" che serve l'app sbagliata.
#
# Contratto env (validato fail-closed sotto): le chiavi che servono SEMPRE.
# WORKER_SECRET_KEY e INVOICETRONIC_WEBHOOK_SECRET sono richieste dal solo
# servizio API (gate route) e validate dentro l'app, non qui.
# ════════════════════════════════════════════════════════════════════════════

# Railway inietta $PORT; l'app FastAPI legge WORKER_PORT. Allineiamo i due cosi'
# l'API ascolta sulla porta che Railway instrada, senza dover settare WORKER_PORT
# a mano sul dashboard (causa storica di non-riproducibilita').
if [ -n "$PORT" ] && [ -z "$WORKER_PORT" ]; then
    export WORKER_PORT="$PORT"
fi

# Validazione variabili obbligatorie (comuni a entrambi i servizi).
: "${SUPABASE_URL:?FATAL: SUPABASE_URL non impostata}"
: "${SUPABASE_SERVICE_ROLE_KEY:?FATAL: SUPABASE_SERVICE_ROLE_KEY non impostata - serve la service_role key che bypassa RLS}"
: "${OPENAI_API_KEY:?FATAL: OPENAI_API_KEY non impostata}"

if [ "$#" -eq 0 ]; then
    echo "FATAL: nessun comando passato all'entrypoint." >&2
    echo "       Imposta lo Start Command del servizio Railway, es.:" >&2
    echo "         worker:       python -m services.fastapi_worker" >&2
    echo "         queue-worker: python worker/run.py" >&2
    exit 1
fi

echo "🚀 Avvio: $*"
exec "$@"
