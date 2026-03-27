# ============================================
# OH YEAH! — Dockerfile produzione
# Python 3.12 slim + Streamlit
# ============================================

FROM python:3.12-slim AS base

# Metadati immagine
LABEL maintainer="OH YEAH! Hub" \
      description="OH YEAH! SaaS — Food Cost Intelligence" \
      version="1.0"

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
RUN pip install --no-cache-dir -r requirements-lock.txt

# Rimuovi build tools dopo installazione (immagine più leggera)
RUN apt-get purge -y build-essential && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# --- Copia codice applicativo ---
COPY . .

# Copia entrypoint e rendi eseguibile
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Crea directory per secrets runtime (non versionata)
RUN mkdir -p /app/.streamlit && \
    chown -R ohyeah:ohyeah /app

# Passa a utente non-root
USER ohyeah

# Streamlit default port
EXPOSE 8501

# Healthcheck per orchestratori (Railway, ECS, K8s)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
