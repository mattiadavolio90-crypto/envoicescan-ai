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
- che il componente comune non dica «Tutto in ordine» prima di aver guardato
  l'avviso di errore.

**Limite dichiarato:** fotografia del sorgente, come
`test_catena_config_guardia_salva.py` (niente runner npm in `apps/web/`).
"""
import pathlib
import re

import pytest

_WEB = pathlib.Path(__file__).resolve().parents[1] / "apps/web/src"
_CATENA = _WEB / "app/(app)/catena/da-fare-catena.tsx"
_COMUNE = _WEB / "components/home/da-fare-oggi.tsx"


@pytest.fixture(scope="module")
def testo() -> str:
    return _CATENA.read_text(encoding="utf-8")


def _normalizza(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_l_errore_di_rete_arriva_alla_lib(testo):
    n = _normalizza(testo)
    assert "daFareCatena({segnali:data,errore:loadError,nDaCollocare})" in n, (
        "`daFareCatena` non riceve piu' `errore: loadError`: un fetch fallito "
        "resterebbe «Controllo i punti vendita…» per sempre, o peggio"
    )
    assert "setLoadError(true)" in n, "il ramo catch non segna piu' l'errore"


def test_riprova_rilancia_il_caricamento(testo):
    assert re.search(r"onRiprova=\{carica\}", testo), (
        "«Riprova» non richiama piu' `carica`: dopo un errore la Home resta "
        "cieca fino al reload"
    )


def test_la_richiesta_ignora_le_risposte_sorpassate(testo):
    assert "++reqRef.current" in testo
    assert testo.count("my === reqRef.current") == 2, (
        "le guardie anti-race (then/catch) non sono piu' due: una risposta "
        "sorpassata puo' sovrascrivere lo stato della richiesta corrente"
    )


def test_niente_logica_nel_componente(testo):
    """Se qui compare un calcolo, va in `lib/home-da-fare.ts` e si prova li'."""
    for vietato, perche in [
        (r"\.sort\(", "un ordinamento"),
        (r"\.reduce\(", "un aggregato"),
        (r"\.filter\(", "un filtro"),
    ]:
        assert not re.search(vietato, testo), f"da-fare-catena.tsx ora contiene {perche}"


def test_il_componente_comune_guarda_l_errore_prima_del_verde():
    """Con zero voci, l'avviso (caricamento/errore) deve vincere sul verde.
    La lib non da' mai `verde` insieme a un avviso, ma il componente non deve
    dipendere da quella promessa per non mentire."""
    t = _COMUNE.read_text(encoding="utf-8")
    i_nota = t.find("if (nota) return nota;")
    i_verde = t.find("if (verde) {")
    assert i_nota != -1 and i_verde != -1
    assert i_nota < i_verde, "il verde viene controllato prima dell'avviso di errore"


# ─── Gli avvisi della Home di catena ────────────────────────────────────────

_WIDGET = _WEB / "app/(app)/dashboard/notifiche-widget.tsx"
_SINTESI = _WEB / "app/(app)/catena/sintesi-catena.tsx"


def test_la_home_di_catena_chiede_gli_avvisi_del_gruppo():
    n = _normalizza(_SINTESI.read_text(encoding="utf-8"))
    assert '<NotificheWidgetambito="gruppo"onVaiSede={(id,pagina)=>vaiAlPV(id,pagina)}/>' in n, (
        "la Home di catena non mostra piu' gli avvisi di gruppo, o il loro "
        "pulsante non cambia sede prima di aprire la pagina"
    )


def test_il_widget_legge_l_endpoint_del_suo_ambito():
    n = _normalizza(_WIDGET.read_text(encoding="utf-8"))
    assert 'fetch(ambito==="gruppo"?"/api/gruppo/notifiche":"/api/notifiche"' in n


def test_il_pulsante_segue_la_destinazione_decisa_in_lib():
    """In catena un <Link> diretto aprirebbe la pagina della sede sbagliata: il
    widget non deve usare `ctaDi` da solo, ma `destinazioneAvviso` con l'ambito."""
    t = _WIDGET.read_text(encoding="utf-8")
    n = _normalizza(t)
    assert "destinazioneAvviso(n,ambito)" in n
    assert "ctaDi(" not in t
    assert "onVaiSede(dest.ristoranteId,dest.href)" in n


def test_carica_fatture_in_catena_segue_la_stessa_regola_del_pv():
    """La regola vive in lib (caricaFattureInHome, provata in
    test_home_kpi_frontend.py); qui che la Home di catena la usi davvero."""
    pagina = _normalizza((_WEB / "app/(app)/catena/page.tsx").read_text(encoding="utf-8"))
    assert "caricaFatture={caricaFattureInHome(pagine)}" in pagina
    assert "{caricaFatture&&<UploadModal/>}" in _normalizza(_SINTESI.read_text(encoding="utf-8"))
