"""Uscendo, la conversazione con l'assistente non resta nella scheda (audit di ottobre #23).

La chiave per persona (`idPersona`) impedisce alla UI di chi entra dopo di
mostrarla, ma il dato restava in chiaro in sessionStorage fino alla chiusura della
scheda: sul tablet di sala titolare e dipendente si alternano nella stessa.
"""
import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

_STORAGE_FINTO = """
    const dati = new Map(input);
    const storage = {
      get length() { return dati.size; },
      key(i) { return [...dati.keys()][i] ?? null; },
      removeItem(k) { dati.delete(k); },
    };
    m.svuotaConversazioni(storage);
    emit([...dati.keys()].sort());
"""


def test_toglie_le_conversazioni_e_lascia_il_resto():
    restano = esegui_ts("lib/home-chat", _STORAGE_FINTO, [
        ["oneflux:assistente:u-1", "[...]"],
        ["oneflux:assistente:u-1:sala@x.it", "[...]"],
        ["oneflux:assistente:u-2:cucina@x.it", "[...]"],
        ["oneflux:chat-messages", "[...]"],
        ["oneflux:analisi-e-tag:barra", "1"],
        ["oneflux:briefing-seen:2026-10-17", "1"],
        ["altro", "x"],
    ], richiede=["svuotaConversazioni"])
    assert restano == ["altro", "oneflux:analisi-e-tag:barra", "oneflux:briefing-seen:2026-10-17"]


def _senza_commenti(testo):
    testo = re.sub(r"/\*.*?\*/", "", testo, flags=re.S)
    return re.sub(r"(?<![:\"'])//[^\n]*", "", testo)


def test_cablata_nei_due_logout_e_nel_login():
    sidebar = _senza_commenti((WEB / "components/nav/app-sidebar.tsx").read_text(encoding="utf-8"))
    menu_m = _senza_commenti((WEB / "app/(mobile)/m/header-menu.tsx").read_text(encoding="utf-8"))
    login = _senza_commenti((WEB / "app/(auth)/login/page.tsx").read_text(encoding="utf-8"))
    assert re.search(r"async function handleLogout\(\) \{\s*svuotaConversazioniDelBrowser\(\);", sidebar)
    assert re.search(r"async function logout\(\) \{\s*svuotaConversazioniDelBrowser\(\);", menu_m)
    # Sul login arriva anche la sessione scaduta, che non passa dai due pulsanti.
    assert re.search(
        r"export default function LoginPage\(\) \{\s*useEffect\(\(\) => svuotaConversazioniDelBrowser\(\), \[\]\);",
        login,
    )


def test_la_versione_del_browser_usa_sessionstorage():
    chat = _senza_commenti((WEB / "lib/home-chat.ts").read_text(encoding="utf-8"))
    corpo = chat.split("export function svuotaConversazioniDelBrowser(): void {", 1)[1].split("\n}", 1)[0]
    assert "svuotaConversazioni(window.sessionStorage);" in corpo
