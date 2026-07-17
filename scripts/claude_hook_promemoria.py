"""
Hook PostToolUse per Claude Code: promemoria contestuali sulle trappole ONEFLUX.

Il problema che risolve: le trappole stanno in CLAUDE.md, che Claude legge a
inizio sessione. Ma una regola letta un'ora prima si dimentica a metà lavoro —
e proprio quelle trappole (cache del briefing non invalidata, /m non allineato)
non rompono niente in modo visibile: il cliente vede semplicemente la cosa
sbagliata.

Questo hook non legge: parla **nel momento** in cui il file viene toccato.

Riceve su stdin il JSON dell'evento, stampa su stdout il promemoria (che finisce
nel contesto di Claude) ed esce sempre con 0: un hook che blocca il lavoro per
un promemoria e' un hook che verrà disattivato.

Configurato in .claude/settings.json come hook PostToolUse su Edit|Write.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# (regex sul percorso, promemoria). Il primo match vince per file.
# Ogni voce nasce da un errore realmente accaduto — non da "buone pratiche".
REGOLE: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"daily_briefing_service\.py$|price_impact_service\.py$"),
        "Hai modificato la logica del briefing.\n"
        "  -> BUMPA `_BRIEFING_CODE_VERSION` in services/daily_briefing_service.py,\n"
        "    altrimenti lo snapshot in cache resta valido e il cliente continua a\n"
        "    vedere il testo pre-deploy.\n"
        "  -> Se hai cambiato una soglia, aggiorna la tabella leve di LOGICA_BRIEFING.md\n"
        "    (un test la verifica: _MAX_CARD deve coincidere).",
    ),
    (
        re.compile(r"services[/\\]routers[/\\]\w+\.py$"),
        "Router del worker modificato.\n"
        "  -> MAI `__getattr__` per gli helper: ha gia' rotto 9 router in produzione\n"
        "    (PEP 562 non risolve i global lookup interni). Usa wrapper espliciti.\n"
        "  -> Se hai toccato le firme degli endpoint: python scripts/export_openapi.py",
    ),
    (
        re.compile(r"fastapi_worker\.py$"),
        "Worker modificato.\n"
        "  -> Se hai cambiato un endpoint: python scripts/export_openapi.py\n"
        "    (il workflow openapi-drift.yml fallisce se lo schema diverge).",
    ),
    (
        re.compile(r"apps[/\\]web[/\\]src[/\\]app[/\\]\(app\)[/\\]"),
        "Hai modificato una pagina desktop.\n"
        "  -> `/m` (apps/web/src/app/m/) e' un frontend SEPARATO, non responsive:\n"
        "    se la modifica riguarda anche il mobile, va allineata a mano.",
    ),
    (
        re.compile(r"ai_service\.py$|invoice_service\.py$"),
        "Hai toccato categorizzazione/parsing.\n"
        "  -> Una riga non riconosciuta resta 'Da Classificare' ed esce dai margini.\n"
        "    NIENTE fallback in 'SERVIZI E CONSULENZE' (CLAUDE.md regola 1).\n"
        "  -> 'NOTE E DICITURE' solo su righe con importo 0 (regola 2).\n"
        "  -> Guardia attiva: tests/test_regole_dominio_guardia.py",
    ),
    (
        re.compile(r"db_service\.py$|upload_handler\.py$|auth_service\.py$"),
        "Query sui dati cliente modificate.\n"
        "  -> SELECT su `fatture`/`prodotti`: usa filter_active() (CLAUDE.md regola 5).\n"
        "    Senza, il cliente vede anche le righe nel cestino — e' gia' successo.\n"
        "  -> I filtri user_id/ristorante_id SONO la sicurezza multi-tenant:\n"
        "    service_role_key bypassa RLS, auth.uid() e' sempre NULL.",
    ),
    (
        re.compile(r"supabase[/\\]functions[/\\]"),
        "Edge Function modificata.\n"
        "  -> Test: deno test --allow-env --allow-net supabase/functions/**/*_test.ts\n"
        "  -> Il deploy NON e' automatico col push:\n"
        "    supabase functions deploy <nome> --project-ref vthikmfpywilukizputn",
    ),
    (
        re.compile(r"^migrations[/\\].*\.sql$"),
        "ATTENZIONE: la cartella `migrations/` e' CONGELATA (storica, 001-082).\n"
        "  -> Le migration nuove vanno SOLO in supabase/migrations/ con nome\n"
        "     timestamp AAAAMMGGHHMMSS_nome.sql (formato Supabase CLI).",
    ),
]


def _stampa(testo: str) -> None:
    """La console Windows di default e' cp1252: un'emoji la fa esplodere con
    UnicodeEncodeError, e l'hook morirebbe in silenzio al primo uso. Qui si
    scrive solo ASCII e si degrada invece di sollevare.
    """
    try:
        sys.stdout.write(testo + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(testo.encode("ascii", "replace").decode("ascii") + "\n")


def _percorso_dal_payload(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    return str(tool_input.get("file_path") or "")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    percorso = _percorso_dal_payload(payload)
    if not percorso:
        return 0

    try:
        relativo = str(Path(percorso).resolve().relative_to(Path.cwd().resolve()))
    except (ValueError, OSError):
        relativo = percorso

    normalizzato = relativo.replace("\\", "/")

    for regola, promemoria in REGOLE:
        if regola.search(normalizzato) or regola.search(relativo):
            _stampa(f"[ONEFLUX] Promemoria - {normalizzato}\n{promemoria}")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
