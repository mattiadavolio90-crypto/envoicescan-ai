#!/bin/bash
set -e

# ============================================
# OH YEAH! — Docker Entrypoint
# Genera secrets.toml dalle variabili d'ambiente
# ============================================

SECRETS_FILE="/app/.streamlit/secrets.toml"

echo "🔧 Generazione secrets.toml da variabili d'ambiente..."

# Crea secrets.toml solo se non è già montato dall'esterno
if [ ! -f "$SECRETS_FILE" ] || [ "${REGENERATE_SECRETS:-0}" = "1" ]; then

    cat > "$SECRETS_FILE" <<EOF
# Auto-generato da docker-entrypoint.sh — NON versionare
OPENAI_API_KEY = "${OPENAI_API_KEY}"

[supabase]
url = "${SUPABASE_URL}"
key = "${SUPABASE_KEY}"

[brevo]
api_key = "${BREVO_API_KEY}"
sender_email = "${BREVO_SENDER_EMAIL:-noreply@ohyeahhub.it}"
sender_name = "${BREVO_SENDER_NAME:-OH YEAH! Hub}"
reply_to_email = "${BREVO_REPLY_TO_EMAIL:-info@ohyeahhub.it}"
reply_to_name = "${BREVO_REPLY_TO_NAME:-OH YEAH! Hub}"
bcc_email = "${BREVO_BCC_EMAIL:-}"
EOF

    echo "✅ secrets.toml generato con successo"
else
    echo "ℹ️  secrets.toml già presente (montato esternamente), skip generazione"
fi

# Se sono stati passati argomenti (es. da docker-compose command:), esegui quelli.
# Altrimenti avvia Streamlit (comportamento default).
if [ "$#" -gt 0 ]; then
    echo "🚀 Avvio: $*"
    exec "$@"
else
    echo "🚀 Avvio Streamlit..."
    exec streamlit run app.py \
        --server.port=8501 \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --browser.gatherUsageStats=false
fi
