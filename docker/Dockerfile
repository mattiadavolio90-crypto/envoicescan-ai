# ============================================
# ONEFLUX — Dockerfile produzione
# Python 3.12 slim — FastAPI worker + queue-worker
# (Streamlit eliminato: il frontend e' Next.js su Vercel)
# ============================================

FROM python:3.12-slim AS base

# Metadati immagine
LABEL maintainer="ONEFLUX" \
      description="ONEFLUX — worker API + queue-worker (FastAPI)" \
      version="2.0"

# Evita prompt interattivi e .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dipendenze di sistema per argon2-cffi, Pillow, lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libjpeg62-turbo-dev \
        libxml2-dev \
        libxslt1-dev \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Utente non-root per sicurezza
RUN groupadd -r ohyeah && useradd -r -g ohyeah -m -s /bin/bash ohyeah

WORKDIR /app

# --- Layer cache: dipendenze prima del codice ---
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt 'python-dotenv>=1.0.0'

# Rimuovi build tools dopo installazione (immagine più leggera)
RUN apt-get purge -y build-essential && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# --- Copia codice applicativo ---
COPY . .

# Copia entrypoint e rendi eseguibile
COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

RUN chown -R ohyeah:ohyeah /app

# Passa a utente non-root
USER ohyeah

# Porta API FastAPI (servizio "worker"). Il "queue-worker" non espone HTTP.
# Railway instrada su $PORT; l'entrypoint allinea WORKER_PORT=$PORT.
EXPOSE 8000

# Healthcheck per compose/orchestratori: valido per il servizio API. Per il
# queue-worker (no HTTP) l'healthcheck va disabilitato lato servizio.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f "http://localhost:${WORKER_PORT:-8000}/health" || exit 1

# Il comando concreto e' fornito dal servizio (Railway Start Command / compose
# `command:`). L'entrypoint lo esegue; senza comando fallisce esplicito.
ENTRYPOINT ["/docker-entrypoint.sh"]
