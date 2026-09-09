"""
Guardia contro il drift fra il codice e i documenti che il cliente legge.

La Privacy Policy e i Termini sono dichiarazioni al pubblico: quando il codice
cambia e il documento resta fermo, il documento non diventa "vecchio", diventa
falso. Ed è la dichiarazione falsa che il Garante contesta, non la lacuna
dichiarata.

Il 09/09/2026 l'audit ne ha trovate tre insieme, tutte con la stessa causa (i
documenti scritti una volta, il codice andato avanti):

  1. l'export GDPR consegnava al cliente una P.IVA del titolare inesistente —
     corretta ovunque il 10/07/2026 tranne lì, perché il test che la presidiava
     (`test_documentazione_onesta`) scorre solo i `.md` e non vedeva il `.py`;
  2. `@vercel/analytics` era montato nel root layout mentre privacy, banner
     cookie e dossier dichiaravano l'assenza di analytics;
  3. i parametri Argon2 dichiarati (p=1) non erano quelli usati (p=4).

Qui si fermano. Ogni test lega un fatto del codice alla frase che lo dichiara,
così cambiare l'uno senza l'altro diventa rosso.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PRIVACY_TSX = ROOT / "apps" / "web" / "src" / "app" / "(legal)" / "privacy" / "page.tsx"
TERMINI_TSX = ROOT / "apps" / "web" / "src" / "app" / "(legal)" / "termini" / "page.tsx"
ROOT_LAYOUT = ROOT / "apps" / "web" / "src" / "app" / "layout.tsx"
WEB_PACKAGE_JSON = ROOT / "apps" / "web" / "package.json"
AUTH_SERVICE = ROOT / "services" / "auth_service.py"
ACCOUNT_ROUTER = ROOT / "services" / "routers" / "account.py"
COMPLIANCE_MD = ROOT / "docs" / "COMPLIANCE_GDPR.md"

PIVA_CORRETTA = "12993240154"
PIVA_ERRATA = "09599210961"


def _leggi(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _senza_commenti_jsx(sorgente: str) -> str:
    """Toglie i commenti /* */ e // così un test non passa per una frase
    che vive in un commento invece che nel testo mostrato all'utente."""
    senza_blocchi = re.sub(r"/\*.*?\*/", "", sorgente, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", senza_blocchi, flags=re.MULTILINE)


# --------------------------------------------------------------------------
# 1. La P.IVA errata non deve rientrare — nel CODICE, non solo nei .md
# --------------------------------------------------------------------------

# File che nominano il titolare verso il cliente. Il primo è quello che l'ha
# fatta sopravvivere due mesi: è il JSON che il cliente scarica esercitando
# l'art. 20, cioè il documento che certifica CHI tratta i suoi dati.
FILE_CON_TITOLARE = [
    ACCOUNT_ROUTER,
    PRIVACY_TSX,
    TERMINI_TSX,
    ROOT / "apps" / "web" / "src" / "app" / "(legal)" / "layout.tsx",
    ROOT / "apps" / "web" / "src" / "lib" / "landing-content.ts",
    ROOT / "apps" / "web" / "src" / "components" / "landing" / "structured-data.tsx",
]


@pytest.mark.parametrize(
    "sorgente",
    [p for p in FILE_CON_TITOLARE if p.exists()],
    ids=lambda p: p.name,
)
def test_piva_errata_non_rientra_nel_codice(sorgente: Path) -> None:
    """La P.IVA storica errata è già ricomparsa 5 volte, l'ultima in un .py
    che il cliente scarica. Il presidio sui .md non bastava."""
    assert PIVA_ERRATA not in _leggi(sorgente), (
        f"{sorgente.name} contiene la P.IVA errata {PIVA_ERRATA}. "
        f"Quella di RECOMASYSTEM Srl è {PIVA_CORRETTA}."
    )


def test_export_gdpr_dichiara_il_titolare_corretto() -> None:
    """L'export art. 20 è il documento in cui il cliente legge chi è il
    titolare: la P.IVA dev'esserci, e dev'essere quella vera."""
    sorgente = _leggi(ACCOUNT_ROUTER)
    match = re.search(r'"titolare_trattamento":\s*"([^"]+)"', sorgente)
    assert match, "L'export GDPR non dichiara più il titolare del trattamento."
    valore = match.group(1)
    assert PIVA_CORRETTA in valore, (
        f"L'export dichiara il titolare come {valore!r}, senza la P.IVA "
        f"corretta {PIVA_CORRETTA}."
    )


# --------------------------------------------------------------------------
# 2. Nessun analytics finché i documenti dichiarano di non averne
# --------------------------------------------------------------------------

# Pacchetti di analytics/tracking. Se uno di questi rientra, i tre documenti
# che dichiarano "nessun analytics" vanno riscritti PRIMA — e va rivisto il
# banner cookie, che oggi non ha Accetta/Rifiuta proprio perché non serve.
PACCHETTI_TRACKING = [
    "@vercel/analytics",
    "@vercel/speed-insights",
    "posthog-js",
    "mixpanel-browser",
    "@amplitude/analytics-browser",
    "react-ga4",
    "@sentry/nextjs",
]


def test_nessun_pacchetto_analytics_nelle_dipendenze() -> None:
    pkg = json.loads(_leggi(WEB_PACKAGE_JSON))
    dichiarate = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    trovati = sorted(set(dichiarate) & set(PACCHETTI_TRACKING))
    assert not trovati, (
        f"Dipendenze di tracking presenti: {trovati}. La privacy policy, il "
        f"banner cookie e docs/COMPLIANCE_GDPR.md dichiarano l'assenza di "
        f"analytics: aggiornali (e valuta un consenso preventivo) prima di "
        f"reintrodurle."
    )


def test_root_layout_non_monta_analytics() -> None:
    """La dipendenza fuori dal package.json non basta: conta cosa il layout
    manda davvero al browser di ogni visitatore."""
    layout = _senza_commenti_jsx(_leggi(ROOT_LAYOUT))
    assert "vercel/analytics" not in layout, (
        "Il root layout importa @vercel/analytics mentre i documenti "
        "dichiarano l'assenza di analytics."
    )
    assert not re.search(r"<Analytics\b", layout), (
        "Il root layout monta <Analytics /> mentre i documenti dichiarano "
        "l'assenza di analytics."
    )


def test_privacy_dichiara_assenza_di_analytics() -> None:
    """L'altro verso dello stesso vincolo: se un domani si vuole l'analytics,
    questo test costringe a togliere prima la dichiarazione dal documento."""
    testo = _senza_commenti_jsx(_leggi(PRIVACY_TSX))
    assert "Cookie analytics o di tracciamento comportamentale" in testo, (
        "La privacy non dichiara più l'assenza di cookie analytics: se è una "
        "scelta voluta, aggiorna anche il banner cookie (serve un consenso "
        "preventivo) e i test qui sopra."
    )


# --------------------------------------------------------------------------
# 3. I parametri di sicurezza dichiarati sono quelli usati
# --------------------------------------------------------------------------

def _parametri_argon2_dal_codice() -> tuple[int, int, int]:
    """Legge m, t, p dalla PasswordHasher reale invece di fidarsi del testo."""
    sorgente = _leggi(AUTH_SERVICE)
    blocco = re.search(
        r"ph\s*=\s*argon2\.PasswordHasher\((.*?)\)", sorgente, flags=re.DOTALL
    )
    assert blocco, "PasswordHasher non trovato in services/auth_service.py"
    corpo = blocco.group(1)

    def _valore(nome: str) -> int:
        m = re.search(rf"{nome}\s*=\s*(\d+)", corpo)
        assert m, f"parametro {nome} non trovato nella PasswordHasher"
        return int(m.group(1))

    return _valore("memory_cost"), _valore("time_cost"), _valore("parallelism")


def test_privacy_dichiara_i_parametri_argon2_reali() -> None:
    """CLAUDE.md §Sicurezza chiede che i parametri restino allineati fra
    codice, test e documentazione: la privacy è l'anello che mancava — ha
    dichiarato p=1 per mesi mentre il codice usava p=4."""
    m, t, p = _parametri_argon2_dal_codice()
    atteso = f"Argon2id (m={m}, t={t}, p={p})"
    testo = _senza_commenti_jsx(_leggi(PRIVACY_TSX))
    assert atteso in testo, (
        f"La privacy policy non dichiara i parametri Argon2 reali. "
        f"Il codice usa {atteso}: aggiorna il testo della pagina."
    )


def test_compliance_gdpr_dichiara_i_parametri_argon2_reali() -> None:
    m, t, p = _parametri_argon2_dal_codice()
    atteso = f"Argon2id (m={m}, t={t}, p={p})"
    assert atteso in _leggi(COMPLIANCE_MD), (
        f"docs/COMPLIANCE_GDPR.md non dichiara i parametri Argon2 reali ({atteso})."
    )


def test_privacy_non_dichiara_conservazione_login_di_15_minuti() -> None:
    """I 15 minuti sono la durata del BLOCCO (_LOCKOUT_MINUTES); la
    conservazione dei tentativi è a 24h. La privacy li confondeva, dichiarando
    una cancellazione più rapida di quella reale."""
    sorgente = _leggi(AUTH_SERVICE)
    assert re.search(r"timedelta\(hours=24\)", sorgente), (
        "Il cleanup di login_attempts non è più a 24 ore: aggiorna la privacy "
        "policy, che dichiara quel valore all'utente."
    )
    testo = _senza_commenti_jsx(_leggi(PRIVACY_TSX))
    assert "conservati per 15 minuti" not in testo, (
        "La privacy dichiara di conservare i tentativi di accesso per 15 "
        "minuti, ma il codice li elimina dopo 24 ore."
    )


# --------------------------------------------------------------------------
# 4. Ogni destinatario di dati personali è dichiarato
# --------------------------------------------------------------------------

# Host esterni raggiunti dal codice → nome che deve comparire nella tabella
# "Destinatari dei Dati" della privacy. Un fornitore che riceve dati personali
# e non è in tabella è una violazione dell'art. 13.1.e.
HOST_DA_DICHIARARE = {
    "api.openai.com": "OpenAI",
    "api.brevo.com": "Brevo",
    "supabase.co": "Supabase",
}


@pytest.mark.parametrize("host,fornitore", sorted(HOST_DA_DICHIARARE.items()))
def test_fornitore_contattato_e_dichiarato(host: str, fornitore: str) -> None:
    testo = _senza_commenti_jsx(_leggi(PRIVACY_TSX))
    assert fornitore in testo, (
        f"Il codice contatta {host} ma {fornitore} non compare fra i "
        f"destinatari dei dati nella privacy policy."
    )


def test_backup_su_github_e_dichiarato() -> None:
    """Il dump `pg_dump` è una copia integrale del DB custodita da un terzo
    negli USA: era documentato solo internamente, non verso il cliente."""
    workflow = ROOT / ".github" / "workflows" / "db_backup.yml"
    if not workflow.exists():
        pytest.skip("nessun workflow di backup: niente da dichiarare")
    testo = _senza_commenti_jsx(_leggi(PRIVACY_TSX))
    assert "GitHub" in testo, (
        "Esiste un workflow di backup del database su GitHub, ma GitHub non è "
        "dichiarato fra i destinatari dei dati nella privacy policy."
    )


def test_telegram_non_riceve_email_in_chiaro() -> None:
    """Telegram (extra-UE) non è un sub-responsabile dichiarato: gli alert non
    devono portargli fuori dati personali. L'email del mittente esce mascherata,
    il valore esatto resta su ricavi_email_queue.email_sender."""
    edge = ROOT / "supabase" / "functions" / "ricavi-email-webhook" / "index.ts"
    sorgente = _senza_commenti_jsx(_leggi(edge))
    alert_con_email = re.findall(r"`Da: \$\{([^}]+)\}`", sorgente)
    assert alert_con_email, "Nessun alert 'Da:' trovato: il test non misura più nulla."
    non_mascherati = [e for e in alert_con_email if "maskEmail" not in e]
    assert not non_mascherati, (
        f"Alert Telegram con email non mascherata: {non_mascherati}. "
        f"Usa maskEmail(), o dichiara Telegram fra i sub-responsabili."
    )
