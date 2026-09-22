"""Raggruppamento dei segnali di catena — `lib/catena-segnali.ts::raggruppaSegnali`.

Perche' qui e non in `apps/web/`: aggiungere un runner di test a `apps/web/`
farebbe scattare `deploy-vercel.yml` (`paths: apps/web/**`) a ogni merge di un
test. Il modulo TS vero viene importato da node via `tests/helpers_ts.py`.

Cosa protegge: la card "Da vedere nella catena" emette un segnale per PUNTO
VENDITA. Il 21/09/2026, su un gruppo da 5 PV, mostrava 13 righe di cui 5
identiche parola per parola ("Mancano le fatture costo e il costo del personale
— vai a completare nel punto vendita"), una per sede. Ripetere lo stesso avviso
cinque volte non aggiunge niente e seppellisce i segnali che invece sono
diversi fra loro.

La trappola del raggruppamento e' il bottone "Vedi PV": e' una DESTINAZIONE, e
cinque PV hanno cinque pagine diverse. Comprimere a una riga con un solo id
manderebbe l'utente su un PV arbitrario, commutando la sede attiva (cookie +
preferenza, effetto persistente) — lo stesso incidente che il commento di
`card-segnali.tsx` documenta per i segnali senza ristorante_id. Per questo si
tengono TUTTI i PV e il bottone si rende solo quando ce n'e' uno.
"""

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-segnali"


def _seg(tipo, pv_nome, rid=None, testo="Mancano le fatture costo", severity="warning", cta="/dashboard"):
    return {
        "tipo": tipo,
        "severity": severity,
        "ristorante_id": rid if rid is not None else f"id-{pv_nome}",
        "pv_nome": pv_nome,
        "testo": testo,
        "cta_page": cta,
    }


def _raggruppa(segnali):
    return esegui_ts(
        MODULO,
        "emit(m.raggruppaSegnali(input));",
        argomento=segnali,
        richiede=["raggruppaSegnali"],
    )


def test_stesso_testo_su_piu_pv_diventa_una_riga_sola():
    """Il caso vero del 21/09: 5 PV, stesso avviso, 5 righe identiche."""
    nomi = ["LAND DEI SAPORI", "MARIANO COMENSE", "PADERNO DUGNANO", "SAN GIULIANO", "VILLA GUARDIA"]
    out = _raggruppa([_seg("dati_mancanti", n) for n in nomi])
    assert len(out) == 1, out
    assert [p["pv_nome"] for p in out[0]["pv"]] == nomi


def test_il_gruppo_tiene_tutti_i_pv_con_la_loro_destinazione():
    """Il bottone porta a una pagina PER PV: perdere gli id manderebbe
    l'utente su un punto vendita arbitrario."""
    out = _raggruppa([
        _seg("dati_mancanti", "Alfa", cta="/dashboard"),
        _seg("dati_mancanti", "Beta", cta="/margini"),
    ])
    assert [(p["ristorante_id"], p["cta_page"]) for p in out[0]["pv"]] == [
        ("id-Alfa", "/dashboard"),
        ("id-Beta", "/margini"),
    ]


def test_testi_diversi_restano_righe_diverse():
    """Si raggruppa per testo IDENTICO: due avvisi che dicono cose diverse
    sono due informazioni, non una ripetuta."""
    out = _raggruppa([
        _seg("dati_mancanti", "Alfa", testo="Mancano le fatture costo"),
        _seg("dati_mancanti", "Beta", testo="Mancano il fatturato e le fatture costo"),
    ])
    assert len(out) == 2
    assert [len(g["pv"]) for g in out] == [1, 1]


def test_stesso_testo_ma_tipo_diverso_non_si_fonde():
    """L'icona dipende dal tipo: fondere due tipi darebbe una riga con
    l'icona di uno dei due, scelta a caso."""
    out = _raggruppa([
        _seg("dati_mancanti", "Alfa", testo="Stesso testo"),
        _seg("ricavi_mancanti", "Beta", testo="Stesso testo"),
    ])
    assert [g["tipo"] for g in out] == ["dati_mancanti", "ricavi_mancanti"]


def test_i_segnali_senza_ristorante_id_non_si_raggruppano():
    """L'avviso "non e' stato possibile controllare" non e' una destinazione
    e non si somma a niente: due errori restano due righe."""
    out = _raggruppa([
        _seg("dati_mancanti", "Catena", rid="", testo="Non è stato possibile controllare"),
        _seg("dati_mancanti", "Catena", rid="", testo="Non è stato possibile controllare"),
    ])
    assert len(out) == 2, out


def test_l_ordine_del_backend_non_cambia():
    """Il backend ordina per severita' e tipo, e a PARITA' di gravita' quel
    suo ordine resta: il gruppo prende il posto della sua prima occorrenza.

    Dal 22/09/2026 c'e' un'eccezione, coperta piu' sotto: un gruppo PROMOSSO a
    errore risale, perche' il backend aveva ordinato prima che la promozione
    esistesse. Qui sono tutti warning, quindi la regola vale intera."""
    out = _raggruppa([
        _seg("margine_calo", "Alfa", testo="Margine in calo"),
        _seg("dati_mancanti", "Beta", testo="Mancano i costi"),
        _seg("margine_calo", "Gamma", testo="Margine in calo"),
    ])
    assert [g["testo"] for g in out] == ["Margine in calo", "Mancano i costi"]
    assert [p["pv_nome"] for p in out[0]["pv"]] == ["Alfa", "Gamma"]


def test_un_solo_pv_in_errore_alza_la_severita_del_gruppo():
    """Se un PV su cinque e' in errore, la riga non puo' restare un warning:
    la severita' del gruppo e' la piu' alta dei suoi membri."""
    out = _raggruppa([
        _seg("dati_mancanti", "Alfa", severity="warning"),
        _seg("dati_mancanti", "Beta", severity="error"),
        _seg("dati_mancanti", "Gamma", severity="warning"),
    ])
    assert len(out) == 1
    assert out[0]["severity"] == "error"


def test_lista_vuota_resta_vuota():
    """La card distingue "nessun segnale" (spunta verde) da un errore: il
    raggruppamento non puo' inventare una riga."""
    assert _raggruppa([]) == []


@pytest.mark.parametrize("n", [1, 2, 13])
def test_nessun_segnale_si_perde_per_strada(n):
    """Somma di controllo: quanti PV entrano, tanti ne escono."""
    out = _raggruppa([_seg("dati_mancanti", f"PV{i}") for i in range(n)])
    assert sum(len(g["pv"]) for g in out) == n


# ─── Un errore non sta sotto un avviso ──────────────────────────────────────
#
# Il backend ordina per severita' PRIMA che il raggruppamento avvenga, ma la
# severita' del gruppo puo' SALIRE dopo: basta che uno dei PV fusi sia in
# errore. Fino al 22/09/2026 il gruppo restava alla posizione della sua prima
# occorrenza — cioe' un errore poteva finire sotto un warning, nella card che
# serve a dire «guarda prima questo».


def test_il_gruppo_promosso_a_errore_risale():
    """Il warning arriva per primo dal backend; il secondo segnale dello
    stesso gruppo e' un errore e lo promuove. La riga promossa deve salire."""
    out = _raggruppa([
        _seg("avviso_a", "PV1", rid="r1", testo="Solo un avviso", severity="warning"),
        _seg("dati_mancanti", "PV2", rid="r2", testo="Mancano dati", severity="warning"),
        _seg("dati_mancanti", "PV3", rid="r3", testo="Mancano dati", severity="error"),
    ])
    assert [g["severity"] for g in out] == ["error", "warning"]
    assert out[0]["testo"] == "Mancano dati"


def test_a_parita_di_severita_l_ordine_del_backend_resta():
    """Il riordino e' SOLO per gravita': l'ordine per tipo deciso dal backend
    non va rimescolato, o la card cambia disposizione a ogni caricamento.

    Dieci elementi, non tre: con tre, un comparatore instabile a volte non li
    rimescola affatto e il test passa lo stesso — un presidio che uccide il
    mutante 2 volte su 3 non e' un presidio.
    """
    attesi = [f"Avviso {i:02d}" for i in range(10)]
    out = _raggruppa([
        _seg(f"tipo_{i}", f"PV{i}", rid=f"r{i}", testo=t, severity="warning")
        for i, t in enumerate(attesi)
    ])
    assert [g["testo"] for g in out] == attesi


def test_piu_errori_restano_nell_ordine_fra_loro():
    out = _raggruppa([
        _seg("tipo_a", "PV1", rid="r1", testo="Errore uno", severity="error"),
        _seg("tipo_b", "PV2", rid="r2", testo="Avviso", severity="warning"),
        _seg("tipo_c", "PV3", rid="r3", testo="Errore due", severity="error"),
    ])
    assert [g["testo"] for g in out] == ["Errore uno", "Errore due", "Avviso"]


def test_un_errore_gia_in_testa_non_si_muove():
    out = _raggruppa([
        _seg("tipo_a", "PV1", rid="r1", testo="Grave", severity="error"),
        _seg("tipo_b", "PV2", rid="r2", testo="Meno grave", severity="warning"),
    ])
    assert [g["testo"] for g in out] == ["Grave", "Meno grave"]
