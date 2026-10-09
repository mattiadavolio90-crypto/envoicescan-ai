"""Il cablaggio del «Da fare» della Home di catena (`da-fare-catena.tsx`).

Fino al 28/9/2026 questo file presidiava `card-segnali.tsx` («Da vedere nella
catena»), che decideva nel `.tsx` se un errore diventava «Tutto sotto
controllo». La decisione ora sta in `lib/home-da-fare.ts` ed e' provata
eseguendola (`test_home_da_fare_frontend.py`). Qui resta quello che la lib non
puo' vedere, perche' vive nei due componenti:

- che l'errore di rete ARRIVI alla lib (con `errore: false` fisso la lib
  direbbe «caricamento» per sempre, e la regola provata non servirebbe a niente);
- che «Riprova» rilanci davvero il caricamento;
- la guardia anti-race sulle risposte sorpassate (vive su `useRef`);
- che il componente non dica «Tutto in ordine» prima di aver guardato
  l'avviso di errore;
- che un avviso archiviato sparisca solo dopo la risposta del worker (fase G).

**Limite dichiarato:** fotografia del sorgente, come
`test_catena_config_guardia_salva.py` (niente runner npm in `apps/web/`).
"""
import pathlib
import re

import pytest

_WEB = pathlib.Path(__file__).resolve().parents[1] / "apps/web/src"
_CATENA = _WEB / "app/(app)/catena/da-fare-catena.tsx"


@pytest.fixture(scope="module")
def testo() -> str:
    return _CATENA.read_text(encoding="utf-8")


def _normalizza(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_l_errore_di_rete_arriva_alla_lib(testo):
    n = _normalizza(testo)
    assert "segnali:data,errore:loadError,avvisi,erroreAvvisi,nDaCollocare" in n, (
        "`daFareCatena` non riceve piu' gli errori di rete: un fetch fallito "
        "resterebbe «Controllo i punti vendita…» per sempre, o peggio"
    )
    assert "setLoadError(true)" in n, "il ramo catch dei segnali non segna piu' l'errore"
    assert "setErroreAvvisi(true)" in n, "il ramo catch degli avvisi non segna piu' l'errore"


def test_riprova_rilancia_il_caricamento(testo):
    assert re.search(r"onRiprova=\{carica\}", testo), (
        "«Riprova» non richiama piu' `carica`: dopo un errore la Home resta "
        "cieca fino al reload"
    )


def test_la_richiesta_ignora_le_risposte_sorpassate(testo):
    assert "++reqRef.current" in testo
    assert testo.count("my === reqRef.current") == 4, (
        "le guardie anti-race (then/catch di segnali e avvisi) non sono piu' "
        "quattro: una risposta sorpassata puo' sovrascrivere lo stato della "
        "richiesta corrente"
    )


def test_niente_logica_nel_componente(testo):
    """Se qui compare un calcolo, va in `lib/home-da-fare.ts` e si prova li'."""
    for vietato, perche in [
        (r"\.sort\(", "un ordinamento"),
        (r"\.reduce\(", "un aggregato"),
        (r"\.filter\(", "un filtro"),
    ]:
        assert not re.search(vietato, testo), f"da-fare-catena.tsx ora contiene {perche}"


def test_l_avviso_vince_sul_verde(testo):
    """Con zero voci, l'avviso (caricamento/errore, avvisi non letti) deve
    vincere sul verde. La lib non da' mai `verde` insieme a un avviso, ma il
    componente non deve dipendere da quella promessa per non mentire."""
    i_nota = testo.find("if (nota || notaLettura) {")
    i_verde = testo.find("if (verde) return <TuttoInOrdine />;")
    assert i_nota != -1 and i_verde != -1
    assert i_nota < i_verde, "il verde viene controllato prima dell'avviso di errore"


def test_un_avviso_sparisce_solo_se_il_worker_lo_ha_archiviato(testo):
    n = _normalizza(testo)
    assert 'fetch("/api/notifiche/dismiss"' in n
    assert "body:JSON.stringify({id:v.rif})" in n, "si archivierebbe un id che non e' della notifica"
    i_ok = n.find("if(!res.ok)thrownewError();")
    i_arch = n.find("setArchiviati(")
    assert i_ok != -1 and i_arch != -1 and i_ok < i_arch, (
        "l'avviso sparisce prima della risposta: tornerebbe al prossimo caricamento"
    )


# ─── Un elenco solo: gli avvisi delle sedi stanno nel «Da fare» ─────────────

_WIDGET = _WEB / "app/(app)/dashboard/notifiche-widget.tsx"
_SINTESI = _WEB / "app/(app)/catena/sintesi-catena.tsx"


def test_la_home_di_catena_legge_gli_avvisi_del_gruppo(testo):
    assert 'fetch("/api/gruppo/notifiche"' in _normalizza(testo), (
        "il «Da fare» della catena non legge piu' gli avvisi delle sedi"
    )


def test_la_home_di_catena_non_ha_un_secondo_elenco():
    """Fase G (screen 12): «Vedi tutti gli avvisi» ripeteva i fatti del «Da fare»."""
    assert "NotificheWidget" not in _SINTESI.read_text(encoding="utf-8")


def test_il_widget_e_solo_del_punto_vendita():
    n = _normalizza(_WIDGET.read_text(encoding="utf-8"))
    assert 'fetch("/api/notifiche",' in n
    assert "/api/gruppo/notifiche" not in n
    assert 'destinazioneAvviso(n,"sede")' in n
    assert "ctaDi(" not in n


@pytest.mark.parametrize(
    "home",
    ["app/(app)/dashboard/page.tsx", "app/(app)/catena/page.tsx", "app/(app)/catena/sintesi-catena.tsx"],
)
def test_carica_fatture_non_sta_in_home(home):
    """Mattia, 28/9: la Home e' recap e assistenza, «Carica fatture» sta solo in
    Analisi Fatture del punto vendita. Si cerca il componente, non il testo."""
    assert "upload-modal" not in (_WEB / home).read_text(encoding="utf-8")


def test_carica_fatture_resta_in_analisi_fatture():
    """Il gemello: toglierlo dalle Home non deve toglierlo dall'unico posto dove resta."""
    pagina = _normalizza((_WEB / "app/(app)/analisi-fatture/page.tsx").read_text(encoding="utf-8"))
    assert "actions={<UploadModal/>}" in pagina
