"""Test del filtro peso (Pareto) degli alert prezzi — services.price_impact_service.

Difetto reale (cliente TIME CAFE, 10/06/2026): nel briefing Home compariva
"il prodotto piu' pesante e' LIMONI TRATTATI, +26.1%". I LIMONI TRATTATI sono
pero' il 283esimo prodotto su 478 per spesa (25 € in 90 giorni): un marginale
che la regola "solo i prodotti che pesano davvero" voleva tenere FUORI.

Due bug sovrapposti:
  1. `_prodotti_pareto` filtrava sulla colonna "Prodotto", che il DataFrame
     grezzo NON ha (ha "Descrizione"; "Prodotto" nasce solo in calcola_alert).
     La guardia scattava sempre -> set() vuoto -> filtro peso disattivato.
  2. il briefing, su timeout del motore live, lasciava in lista la notifica
     price_alert legacy da upload (nessun filtro peso) -> i marginali passavano.

Questi test blindano il bug #1 a livello di motore: dato un caso con un pilastro
(CAFFE') e un marginale che rincara molto in % (LIMONI), solo il pilastro deve
restare negli alert prezzi.
"""
from datetime import date, timedelta

import pandas as pd

from services.price_impact_service import (
    _pareto_key,
    _prodotti_pareto,
    _alert_prodotti,
    _pref_match_key,
    _SOGLIA_PERC_DEFAULT,
)


def _riga(descr, fornitore, data, prezzo, qta, categoria="CAFFE E THE", file="f"):
    return {
        "Descrizione": descr,
        "Fornitore": fornitore,
        "DataDocumento": data,
        "PrezzoUnitario": prezzo,
        "Quantita": qta,
        "TotaleRiga": prezzo * qta,
        "Categoria": categoria,
        "FileOrigine": file,
        "NumeroDocumento": file,
    }


def _df_caffe_e_limoni():
    """Pilastro CAFFE' (spesa enorme) + marginale LIMONI (spesa minima).

    Entrambi rincarano sopra la soglia 5%. CAFFE' deve restare, LIMONI no:
    e' il senso del filtro peso.
    """
    oggi = date.today()
    g = lambda d: (oggi - timedelta(days=d)).isoformat()
    righe = []
    # CAFFE': pilastro. 2 acquisti, prezzo +5.6%, quantita' enorme -> peso enorme.
    righe.append(_riga("CAFFE'CELLINI CORALLI 1000", "CELLINI", g(40), 9.00, 500))
    righe.append(_riga("CAFFE'CELLINI CORALLI 1000", "CELLINI", g(5), 9.50, 500))
    # LIMONI TRATTATI: marginale. +26%, ma quantita' irrisoria -> peso irrisorio.
    righe.append(_riga("LIMONI TRATTATI", "ORTOFRUTTA", g(40), 1.00, 2, categoria="FRUTTA"))
    righe.append(_riga("LIMONI TRATTATI", "ORTOFRUTTA", g(5), 1.26, 2, categoria="FRUTTA"))
    return pd.DataFrame(righe)


def test_pareto_usa_descrizione_non_prodotto_inesistente():
    """Il df grezzo non ha 'Prodotto': il Pareto deve lavorare su 'Descrizione'.

    Prima del fix la guardia '"Prodotto" not in df.columns' era sempre vera e
    _prodotti_pareto tornava sempre vuoto. Ora deve popolarsi.
    """
    df = _df_caffe_e_limoni()
    assert "Prodotto" not in df.columns  # presupposto del bug
    pareto = _prodotti_pareto(df)
    assert pareto, "il filtro Pareto non deve essere vuoto su un df valido"


def test_pilastro_dentro_marginale_fuori_dal_pareto():
    """CAFFE' (pilastro) in fascia Pareto, LIMONI (marginale) fuori."""
    df = _df_caffe_e_limoni()
    pareto = _prodotti_pareto(df)
    assert _pareto_key("CAFFE'CELLINI CORALLI 1000") in pareto
    assert _pareto_key("LIMONI TRATTATI") not in pareto


def test_alert_prodotti_esclude_i_marginali_rincarati():
    """Il marginale che rincara tanto in % NON deve diventare un alert.

    Questo e' il caso esatto della foto: LIMONI +26% ma irrilevante per peso.
    """
    df = _df_caffe_e_limoni()
    pareto = _prodotti_pareto(df)
    alerts = _alert_prodotti(df, soglia_perc_cliente=_SOGLIA_PERC_DEFAULT, prodotti_pareto=pareto)
    nomi = {a["nome"].upper() for a in alerts}
    assert not any("LIMONI" in n for n in nomi), f"LIMONI non deve comparire: {nomi}"
    assert any("CAFFE" in n for n in nomi), f"CAFFE' (pilastro rincarato) deve comparire: {nomi}"


def test_pareto_key_normalizza_suffisso_e_troncamento():
    """La chiave di match ignora case, suffisso stagionale e tronca a 50 char.

    Garantisce che il prodotto di calcola_alert ('(Descrizione+nota)[:50]')
    combaci con la Descrizione piena del df grezzo, altrimenti il filtro peso
    fallirebbe in modo silenzioso su nomi lunghi o stagionali.
    """
    base = "prosciutto crudo parma s/o legato addobbo speciale extra lungo"
    # display di calcola_alert: case originale + suffisso + troncato a 50
    display = (base.upper() + " ⚠️ >6m")[:50]
    assert _pareto_key(base) == _pareto_key(display)
    assert len(_pareto_key(base)) <= 50


# ── Modalita' "solo preferiti" (Fase 2): il filtro Pareto e' sostituito dalla
#    lista dei prodotti preferiti del cliente (coppia prodotto+fornitore). ──

def _pref_key_da_riga(descr, fornitore):
    """Chiave preferito come la salverebbe prezzi_preferiti, normalizzata per il
    match in _alert_prodotti (stesso troncamento a 50 di _pref_match_key)."""
    return _pref_match_key(descr, fornitore)


def test_solo_preferiti_tiene_solo_il_preferito():
    """Con solo_preferiti, entra SOLO il prodotto a preferito, non il Pareto.

    LIMONI (marginale) e' preferito -> deve comparire anche se il Pareto lo
    escluderebbe. CAFFE' (pilastro) NON e' preferito -> non deve comparire.
    Verifica che il filtro Pareto sia davvero sostituito, non aggiunto.
    """
    df = _df_caffe_e_limoni()
    preferiti = {_pref_key_da_riga("LIMONI TRATTATI", "ORTOFRUTTA")}
    alerts = _alert_prodotti(
        df, soglia_perc_cliente=_SOGLIA_PERC_DEFAULT,
        prodotti_pareto=set(), preferiti_keys=preferiti,
    )
    nomi = {a["nome"].upper() for a in alerts}
    assert any("LIMONI" in n for n in nomi), f"LIMONI (preferito) deve comparire: {nomi}"
    assert not any("CAFFE" in n for n in nomi), f"CAFFE' (non preferito) NON deve comparire: {nomi}"


def test_solo_preferiti_senza_preferiti_nessun_prodotto():
    """solo_preferiti attivo ma lista vuota -> nessun alert prodotto.

    Decisione Mattia: restano solo i tag, niente fallback al Pareto.
    """
    df = _df_caffe_e_limoni()
    alerts = _alert_prodotti(
        df, soglia_perc_cliente=_SOGLIA_PERC_DEFAULT,
        prodotti_pareto=set(), preferiti_keys=set(),
    )
    assert alerts == [], f"senza preferiti non deve esserci alcun alert prodotto: {alerts}"


def test_solo_preferiti_match_su_coppia_prodotto_fornitore():
    """Il preferito combacia solo se ANCHE il fornitore corrisponde."""
    df = _df_caffe_e_limoni()
    # Preferito con fornitore diverso da quello reale del CAFFE' (CELLINI).
    preferiti = {_pref_key_da_riga("CAFFE'CELLINI CORALLI 1000", "ALTRO FORNITORE")}
    alerts = _alert_prodotti(
        df, soglia_perc_cliente=_SOGLIA_PERC_DEFAULT,
        prodotti_pareto=set(), preferiti_keys=preferiti,
    )
    assert alerts == [], f"fornitore diverso non deve combaciare: {alerts}"


def test_pareto_invariato_quando_solo_preferiti_off():
    """Regressione: senza preferiti_keys (None) il comportamento e' il Pareto."""
    df = _df_caffe_e_limoni()
    pareto = _prodotti_pareto(df)
    alerts = _alert_prodotti(df, soglia_perc_cliente=_SOGLIA_PERC_DEFAULT, prodotti_pareto=pareto)
    nomi = {a["nome"].upper() for a in alerts}
    assert any("CAFFE" in n for n in nomi)
    assert not any("LIMONI" in n for n in nomi)
