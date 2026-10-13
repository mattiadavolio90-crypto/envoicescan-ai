"""Admin → Clienti, vista Mappa (lib/admin-mappa.ts): stato di ogni nodo,
propagazione verso la radice, canali, link e filtro «Solo con problemi»."""
from __future__ import annotations

from tests.helpers_ts import esegui_ts

MODULO = "lib/admin-mappa"
FUNZIONI = ["raggruppaMotivi", "costruisciMappa", "soloProblemi", "apertiAllInizio", "idConFigli", "vistaDaUrl", "peggiore"]

# 13/10/2026 12:00 UTC
ADESSO = 1791892800000

SUSHI = {"id": "u1", "email": "s@x.it", "nome_ristorante": "Land", "nome_gruppo": "SUSHILAND", "attivo": True,
         "n_sotto_utenti": 0, "sedi": [
             {"id": "r1", "nome_ristorante": "Villa Guardia", "piano": "pro", "sdi_attivo": True,
              "ultimo_caricamento_at": "2026-08-27T10:00:00Z", "ricavi_collegati": True, "commercialista_attivo": False},
             {"id": "r2", "nome_ristorante": "Paderno", "piano": "pro", "sdi_attivo": False,
              "ultimo_caricamento_at": "2026-10-12T10:00:00Z", "ricavi_collegati": False, "commercialista_attivo": False},
         ]}
CASATI = {"id": "u2", "email": "c@x.it", "nome_ristorante": "CASATI 14", "nome_gruppo": None, "attivo": True,
          "n_sotto_utenti": 2, "sedi": [
              {"id": "r3", "nome_ristorante": "CASATI 14", "piano": None, "sdi_attivo": False,
               "ultimo_caricamento_at": "2026-10-08T10:00:00Z", "ricavi_collegati": None, "commercialista_attivo": True}]}
SPENTO = {"id": "u3", "email": "x@x.it", "nome_ristorante": "Chiuso", "nome_gruppo": None, "attivo": False,
          "n_sotto_utenti": None, "sedi": []}


def _v(chiave, gravita, titolo, cliente_id=None, ristorante_id=None):
    return {"chiave": chiave, "gravita": gravita, "titolo": titolo, "dettaglio": None, "da": None,
            "cliente_id": cliente_id, "cliente": None, "ristorante_id": ristorante_id, "link": None, "azione": None}


VOCI = [
    _v("sdi:r1", "oggi", "SDI attivo ma nessuna fattura da 47 giorni", "u1", "r1"),
    _v("ricavi:r1", "critico", "Ricavi fermi da 4 giorni", "u1", "r1"),
    _v("fattura:9", "oggi", "Fattura da assegnare a una sede", "u1"),
    _v("categorie", "oggi", "216 descrizioni da classificare"),
]


def _mappa(clienti=(SUSHI, CASATI, SPENTO), voci=VOCI):
    return esegui_ts(MODULO, f"emit(m.costruisciMappa(input.c, input.v, {ADESSO}));",
                     argomento={"c": list(clienti), "v": list(voci)}, richiede=FUNZIONI)


def _nodo(n, id_):
    if n["id"] == id_:
        return n
    for f in n["figli"]:
        trovato = _nodo(f, id_)
        if trovato:
            return trovato
    return None


def test_lo_stato_peggiore_risale_fino_alla_radice():
    m = _mappa()
    assert _nodo(m, "r1")["stato"] == "critico"
    assert _nodo(m, "u1")["stato"] == "critico"
    assert m["stato"] == "critico"
    assert _nodo(m, "r2")["stato"] == "ok"


def test_canali_della_sede():
    m = _mappa()
    sdi, ricavi, comm = _nodo(m, "r1")["figli"]
    assert (sdi["nome"], sdi["stato"]) == ("SDI attivo", "oggi")
    assert (ricavi["nome"], ricavi["stato"]) == ("Ricavi dalla cassa", "critico")
    assert (comm["nome"], comm["stato"]) == ("Commercialista spento", "spento")
    assert sdi["link"] == "/admin/clienti/u1?tab=sedi" and comm["link"] == "/admin/clienti/u1?tab=invii"
    assert [f["nome"] for f in _nodo(m, "r2")["figli"]] == ["SDI spento", "Ricavi a mano", "Commercialista spento"]


def test_un_canale_non_letto_e_non_so_non_spento():
    m = _mappa()
    _sdi, ricavi, comm = _nodo(m, "r3")["figli"]
    assert (ricavi["nome"], ricavi["stato"]) == ("Ricavi: non letto", "ignoto")
    assert (comm["nome"], comm["stato"]) == ("Invio al commercialista", "ok")
    assert _nodo(m, "u3:utenti")["stato"] == "ignoto"


def test_utenti_sotto_il_cliente():
    m = _mappa()
    assert _nodo(m, "u1:utenti")["nome"] == "Solo il titolare"
    assert _nodo(m, "u2:utenti")["nome"] == "2 sotto-utenti"
    assert _nodo(m, "u2:utenti")["link"] == "/admin/clienti/u2?tab=account"


def test_motivi_del_cliente_e_della_radice():
    m = _mappa()
    u1 = _nodo(m, "u1")
    assert u1["motivi"][0] == "Fattura da assegnare a una sede"
    assert "Villa Guardia: Ricavi fermi da 4 giorni" in u1["motivi"]
    # la voce SDI c'e', quindi non si aggiunge anche «nessuna fattura da N giorni»
    assert not any("Nessuna fattura da" in x for x in u1["motivi"])
    assert m["motivi"] == ["216 descrizioni da classificare"]


def test_sede_ferma_senza_voce_sdi():
    sede = {**SUSHI["sedi"][1], "ultimo_caricamento_at": "2026-10-01T10:00:00Z"}
    m = _mappa(clienti=[{**SUSHI, "sedi": [sede]}], voci=[])
    assert _nodo(m, "r2")["stato"] == "oggi"
    assert _nodo(m, "r2")["motivi"] == ["Paderno: Nessuna fattura da 12 giorni"]


def test_cliente_disattivo_e_grigio_e_dato_non_letto_non_e_fermo():
    m = _mappa()
    assert _nodo(m, "u3")["stato"] == "spento" and _nodo(m, "u3")["sub"] == "disattivo"
    incompleto = {**SUSHI, "salute_incompleta": True}
    m2 = _mappa(clienti=[incompleto], voci=[])
    assert _nodo(m2, "r1")["stato"] == "ok"
    assert _nodo(m2, "r1")["sub"] == "Pro · —"


def test_link_e_sottotitoli():
    m = _mappa()
    assert m["link"] == "/admin" and _nodo(m, "u1")["link"] == "/admin/clienti/u1"
    assert _nodo(m, "r1")["link"] == "/admin/clienti/u1?tab=sedi"
    assert _nodo(m, "u1")["sub"] == "catena · 2 sedi" and _nodo(m, "u2")["sub"] == "punto vendita"
    assert _nodo(m, "r2")["sub"] == "Pro · ieri"


def test_solo_problemi_aperti_e_espandi_tutto():
    m = _mappa()
    filtrata = esegui_ts(MODULO, f"emit(m.soloProblemi(m.costruisciMappa(input.c, input.v, {ADESSO})));",
                         argomento={"c": [SUSHI, CASATI, SPENTO], "v": VOCI}, richiede=FUNZIONI)
    assert [f["id"] for f in filtrata["figli"]] == ["u1"]
    assert [f["id"] for f in filtrata["figli"][0]["figli"]] == ["r1"]
    aperti = esegui_ts(MODULO, f"emit(m.apertiAllInizio(m.costruisciMappa(input.c, input.v, {ADESSO})));",
                       argomento={"c": [SUSHI, CASATI, SPENTO], "v": VOCI}, richiede=FUNZIONI)
    assert aperti == ["oneflux", "u1"]  # CASATI e' a posto, il disattivo e' grigio
    tutti = esegui_ts(MODULO, f"emit(m.idConFigli(m.costruisciMappa(input.c, input.v, {ADESSO})));",
                      argomento={"c": [SUSHI, CASATI, SPENTO], "v": VOCI}, richiede=FUNZIONI)
    assert set(tutti) == {"oneflux", "u1", "u2", "u3", "r1", "r2", "r3"}
    assert m["sub"] == "3 clienti"


def test_vista_dall_url():
    assert esegui_ts(MODULO, "emit(m.vistaDaUrl(input));", argomento="mappa", richiede=FUNZIONI) == "mappa"
    assert esegui_ts(MODULO, "emit(m.vistaDaUrl(input));", argomento="altro", richiede=FUNZIONI) == "lista"
    assert esegui_ts(MODULO, "emit(m.vistaDaUrl(input));", argomento=None, richiede=FUNZIONI) == "lista"


def test_ferma_dal_settimo_giorno():
    def stato(quando):
        sede = {**SUSHI["sedi"][1], "ultimo_caricamento_at": quando}
        return _nodo(_mappa(clienti=[{**SUSHI, "sedi": [sede]}], voci=[]), "r2")["stato"]
    assert stato("2026-10-06T12:00:00Z") == "oggi"
    assert stato("2026-10-06T13:00:00Z") == "ok"


def test_la_voce_di_un_cliente_che_non_e_in_lista_sta_sulla_radice():
    m = _mappa(voci=[_v("x", "critico", "Fattura di un cliente sparito", "zzz")])
    assert m["motivi"] == ["Fattura di un cliente sparito"] and m["stato"] == "critico"


def test_motivi_uguali_si_raggruppano():
    voci = [_v(f"fattura:{i}", "oggi", "Fattura da assegnare a una sede", "u2") for i in range(5)]
    assert _nodo(_mappa(voci=voci), "u2")["motivi"][0] == "Fattura da assegnare a una sede (5)"
    assert esegui_ts(MODULO, "emit(m.raggruppaMotivi(input));", argomento=["a", "b", "a"], richiede=FUNZIONI) == ["a (2)", "b"]


def test_si_aprono_i_clienti_con_qualcosa_da_fare_non_solo_gli_urgenti():
    voci = [_v("fattura:1", "oggi", "Fattura da assegnare a una sede", "u2")]
    aperti = esegui_ts(MODULO, f"emit(m.apertiAllInizio(m.costruisciMappa(input.c, input.v, {ADESSO})));",
                       argomento={"c": [CASATI, SPENTO], "v": voci}, richiede=FUNZIONI)
    assert aperti == ["oneflux", "u2"]
