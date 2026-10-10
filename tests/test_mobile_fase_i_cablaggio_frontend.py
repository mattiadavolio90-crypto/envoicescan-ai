"""Fase I (10/10/2026): due allineamenti di `/m` al desktop che non hanno logica
da eseguire — una frase e un componente nel layout.

Guardano la FORMA dei .tsx perche' l'harness non esegue i componenti (limite
dichiarato): uccidono il mutante realistico, cioe' togliere la riga o il banner.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
FRASE = "Scrivi quanto hai pagato, IVA compresa: senza fattura l&apos;IVA è un costo."


def _src(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_il_modulo_spese_del_telefono_dice_iva_compresa_come_il_desktop():
    assert FRASE in _src("app/(app)/workspace/spese-view.tsx")
    assert FRASE in _src("app/(mobile)/m/diario/mobile-spese.tsx")


def test_la_frase_sta_nel_modulo_e_non_nella_lista():
    """Prima del campo Descrizione, dentro il Dialog: nella lista delle spese non
    avrebbe senso."""
    m = _src("app/(mobile)/m/diario/mobile-spese.tsx")
    assert m.index("Nuova spesa") < m.index(FRASE) < m.index("Descrizione *")


def test_il_layout_del_telefono_ha_l_uscita_dall_impersonazione():
    assert "<ImpersonaBanner inFlusso />" in _src("app/(mobile)/m/layout.tsx")


def test_il_banner_del_telefono_non_e_a_posizione_fissa():
    """A posizione fissa coprirebbe l'intestazione con il menu: sul telefono scorre
    con la pagina. Il desktop resta com'era."""
    b = _src("components/admin/impersona-banner.tsx")
    m = re.search(r'inFlusso\s*\?\s*"([^"]*)"\s*:\s*"([^"]*)"', b)
    assert m, "la scelta della classe per inFlusso non c'e' piu'"
    in_flusso, desktop = m.groups()
    assert "fixed" not in in_flusso
    assert "fixed" in desktop
    assert "<ImpersonaBanner />" in _src("app/(app)/layout.tsx")


def test_la_chat_del_telefono_in_catena_parla_del_gruppo_con_la_regola_della_home():
    """In catena la chat di /m e' quella del gruppo: vista catena, pool AI e
    interruttore di gruppo come la Home di catena (chatCatenaAttiva), non la
    config della sede (con la chat di catena spenta il cliente avrebbe visto la chat
    e ricevuto un 403 a ogni domanda)."""
    p = _src("app/(mobile)/m/chat/page.tsx")
    assert "vista={inChain ? vistaCatena() : vistaSede(utente?.sede_attiva_id)}" in p
    assert "chatCatenaAttiva(gruppo)" in p
    assert "(inChain ? gruppo?.limite_giorno : config?.chat_limite_giorno) ?? 0" in p
    assert "(inChain ? gruppo?.domande_oggi : config?.chat_domande_oggi) ?? 0" in p


def test_la_catena_del_telefono_ha_il_da_fare_per_sede_e_non_il_verde_sopra_la_coda():
    m = _src("app/(mobile)/m/briefing/mobile-catena.tsx")
    assert "<DaFareCatena" in m and "senzaVerde={!!msgDaCollocare}" in m and "nDaCollocare={null}" in m
    d = _src("app/(app)/catena/da-fare-catena.tsx")
    assert "if (verde) return senzaVerde ? null : <TuttoInOrdine />;" in d
    # La Home desktop non lo passa: il suo verde resta quello di sempre.
    assert "senzaVerde" not in _src("app/(app)/catena/sintesi-catena.tsx")


def test_la_chat_del_telefono_scorre_per_numero_di_messaggi_non_per_elenco():
    """`c.voci` e' un array nuovo a ogni render: come dipendenza faceva scorrere la
    pagina a ogni tasto digitato."""
    m = _src("app/(mobile)/m/chat/mobile-chat.tsx")
    assert "}, [nVoci, c.attesa]);" in m
    assert "[c.voci" not in m


def test_la_tab_assistente_di_m_in_catena_segue_la_chat_di_gruppo():
    """Stessa regola di /m/chat: altrimenti la tab compare e rimanda indietro (chat
    di gruppo spenta) o manca con la chat accesa."""
    m = _src("app/(mobile)/m/layout.tsx")
    assert "? chatCatenaAttiva(await fetchGruppoChatConfig())" in m
    assert ": (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;" in m


def test_dopo_il_caricamento_il_link_alla_coda_c_e_solo_con_la_scheda_accesa():
    u = _src("app/(app)/analisi-fatture/upload-modal.tsx")
    assert "export function UploadModal({ codaAccesa = true }: { codaAccesa?: boolean })" in u
    assert "{codaAccesa && (\n                <Link\n                  href={LINK_CODA_GRUPPO}" in u
    p = _src("app/(app)/analisi-fatture/page.tsx")
    assert '<UploadModal codaAccesa={schedaCatenaAccesa(user?.pagine_abilitate, "collocare")} />' in p
