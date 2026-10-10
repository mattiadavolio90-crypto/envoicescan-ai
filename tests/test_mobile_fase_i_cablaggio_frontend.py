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
