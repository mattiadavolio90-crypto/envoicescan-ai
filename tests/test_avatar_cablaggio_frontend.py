"""L'avatar della Home e' collegato dove Mattia l'ha voluto (fase L, 15/10/2026).

La logica (modi, voce, frasi, benvenuto) e' eseguita in `test_avatar_flusso_frontend.py`;
qui si guarda che le tre Home la usino: senza `onStato` il flusso non saprebbe mai che
«Ascolta» sta leggendo, senza il benvenuto il saluto dopo il login sparirebbe in silenzio.
Si legge il sorgente senza commenti, cosi' un `onStato` citato in un commento non basta.
"""
import re
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parent.parent / "apps/web/src"
_RIQUADRO = _WEB / "components/home/riquadro-assistente.tsx"
_M_PV = _WEB / "app/(mobile)/m/briefing/mobile-briefing.tsx"
_M_CATENA = _WEB / "app/(mobile)/m/briefing/mobile-catena.tsx"
_ASCOLTA = _WEB / "components/ascolta-button.tsx"


def _n(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"\{/\*.*?\*/\}", "", t, flags=re.S)
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    return re.sub(r"\s+", "", t)


@pytest.mark.parametrize("file", [_RIQUADRO, _M_PV, _M_CATENA], ids=lambda p: p.name)
def test_ascolta_avvisa_l_avatar(file):
    t = _n(file)
    blocchi = re.findall(r"<AscoltaButton[^>]*?/>", t)
    assert blocchi, f"{file.name}: nessun AscoltaButton"
    assert all("onStato={suStato}" in b for b in blocchi), f"{file.name}: un AscoltaButton non avvisa l'avatar"


@pytest.mark.parametrize("file", [_RIQUADRO, _M_PV, _M_CATENA], ids=lambda p: p.name)
def test_ogni_home_ha_il_flusso_e_il_benvenuto(file):
    t = _n(file)
    assert "<AvatarFlussomodo={modo}" in t, f"{file.name}: manca il flusso"
    assert "<BenvenutoAssistente" in t, f"{file.name}: manca il benvenuto"


def test_da_computer_colonna_e_fascia_sotto_lo_schermo_largo():
    t = _n(_RIQUADRO)
    assert 'variante="colonna"' in t and 'variante="fascia"' in t


def test_il_modo_arriva_da_ascolta_attesa_e_chat():
    t = _n(_RIQUADRO)
    assert "modoAvatar({parla,pensa:inCorso!==null,ascolta})" in t
    assert "onFocusCapture=" in t and "onBlurCapture={()=>setAscolta(false)}" in t


def test_ascolta_dice_quando_smette_anche_se_sparisce():
    """Se il pulsante si smonta mentre legge (cambio pagina), l'avatar non deve restare a parlare."""
    t = _n(_ASCOLTA)
    assert 'onStatoRef.current?.("idle",null);' in t


def test_ascolta_avvisa_quando_passa_alla_voce_di_sistema():
    """Se l'audio cade mentre suona lo stato resta «playing»: senza questa chiamata l'avatar
    seguirebbe ancora l'audio morto e la frase evidenziata si fermerebbe."""
    t = _n(_ASCOLTA)
    corpo = t[t.index("functionfallbackWebSpeech()"):t.index("asyncfunctionplay()")]
    assert 'setStato("playing");onStatoRef.current?.("playing",null);' in corpo


def test_da_computer_la_conversazione_scorre_dentro_il_riquadro():
    t = _n(_RIQUADRO)
    assert "<ConversazioneAltezzaFissa.Providervalue={true}>" in t
    pannello = _n(_WEB / "components/home/pannello-conversazione.tsx")
    assert 'altezzaFissa&&"lg:max-h-nonelg:min-h-0lg:flex-1"' in pannello


@pytest.mark.parametrize(
    "file",
    [_RIQUADRO, _WEB / "components/home/use-modo-avatar.ts"],
    ids=lambda p: p.name,
)
def test_l_avatar_non_rompe_il_demo_tour(file):
    """Il riquadro del briefing gira anche nel Demo Tour pubblico (/demo), che non ha
    AssistenteProvider: `useAssistente()` li' lancia e la demo va in crash al primo passo
    (trovato dal revisore il 15/10, prima del push). Si usa la versione opzionale."""
    t = _n(file)
    assert "useAssistenteOpzionale()" in t
    assert "useAssistente()" not in t


def test_il_benvenuto_non_parte_nel_demo_tour():
    """La demo non ha AssistenteProvider: senza questo controllo il benvenuto coprirebbe la barra
    del tour e consumerebbe quello del giorno a chi apre la demo dallo stesso browser."""
    t = _n(_WEB / "components/home/benvenuto-assistente.tsx")
    assert "constnellApp=useAssistenteOpzionale()!==null;" in t
    assert "useEffect(()=>{if(!nellApp)return;" in t
