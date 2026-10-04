"""Fase C1 del piano consulente: il personale ha TRE voci che si sommano.

`margini_mensili.costo_dipendenti` (lordo), `costo_personale_extra` (ore extra)
e la nuova `costo_personale_chiamata` (chiamata). Il totale personale e' la
somma delle tre OVUNQUE: MOL, personale_perc, «personale inserito», catena.

Ogni lettore ha il suo caso con la SOLA chiamata > 0 (lordo 0, extra 0): un
lettore che la dimentica vede un mese senza personale e un MOL piu' alto del
vero. Dove la lettura passa da una select a colonne esplicite, il finto client
restituisce SOLO le colonne chieste: un mock generoso che regala la colonna
anche quando la select non la nomina lascerebbe verde il bug.
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.margini as margini
from services.routers import gruppo
from services.routers.gruppo import _aggrega_sedi_mensili

LORDO, EXTRA, CHIAMATA = 1000.0, 200.0, 37.0


class _Query:
    """Query PostgREST finta: filtra per eq/in_/lte/gte e PROIETTA sulle
    colonne della select. Registra ogni stringa passata a .select()."""

    def __init__(self, righe, log):
        self._righe = [dict(r) for r in righe]
        self._log = log
        self._cols = None

    def select(self, cols="*", **_kw):
        self._log.append(cols)
        self._cols = None if cols.strip() == "*" else [c.strip() for c in cols.split(",")]
        return self

    def eq(self, campo, valore):
        self._righe = [r for r in self._righe if campo not in r or r[campo] == valore]
        return self

    def in_(self, campo, valori):
        self._righe = [r for r in self._righe if campo not in r or r[campo] in valori]
        return self

    def lte(self, campo, valore):
        self._righe = [r for r in self._righe if campo not in r or r[campo] <= valore]
        return self

    def gte(self, campo, valore):
        self._righe = [r for r in self._righe if campo not in r or r[campo] >= valore]
        return self

    def __getattr__(self, _nome):
        return lambda *a, **k: self

    def execute(self):
        if self._cols is None:
            dati = self._righe
        else:
            dati = [{c: r[c] for c in self._cols if c in r} for r in self._righe]
        return SimpleNamespace(data=dati, count=len(dati))


class _SB:
    """Client finto: margini_mensili restituisce le righe date, il resto vuoto."""

    def __init__(self, righe_mm):
        self.righe_mm = righe_mm
        self.select_mm = []
        self.upserts = []
        rpc_res = MagicMock()
        rpc_res.execute.return_value = SimpleNamespace(data=[], count=0)
        self.rpc = MagicMock(return_value=rpc_res)

    def table(self, nome):
        if nome == "margini_mensili":
            q = _Query(self.righe_mm, self.select_mm)
            sb = self

            def _upsert(records, **_kw):
                sb.upserts.extend(records)
                return q
            q.upsert = _upsert
            return q
        return _Query([], [])


def _mm(rid="a", anno=2026, mese=6, lordo=0.0, extra=0.0, chiamata=0.0, **kw):
    riga = {
        "ristorante_id": rid, "anno": anno, "mese": mese,
        "fatturato_netto": 0, "fatturato_iva10": 11_000.0, "fatturato_iva22": 0,
        "altri_ricavi_noiva": 0, "altri_costi_fb": 0, "altri_costi_spese": 0,
        "quote_riparto_fb": 0, "quote_riparto_spese": 0,
        "costo_dipendenti": lordo, "costo_personale_extra": extra,
        "costo_personale_chiamata": chiamata, "coperti": 0,
    }
    riga.update(kw)
    return riga


# ── _aggrega_sedi_mensili: il punto unico della catena ──────────────────────

def _aggrega(**kw):
    return _aggrega_sedi_mensili(
        ids=["a"], righe_mm=[_mm(**kw)],
        costi_auto={"a": ({6: 4_000.0}, {})}, overrides={}, mesi=[6],
    )["a"]


def test_aggrega_sedi_solo_chiamata_entra_nel_personale_e_nel_mol():
    a = _aggrega(chiamata=CHIAMATA)
    assert a["pers"] == CHIAMATA
    assert round(a["mol"], 2) == round(10_000 - 4_000 - CHIAMATA, 2)


def test_aggrega_sedi_somma_le_tre_voci():
    a = _aggrega(lordo=LORDO, extra=EXTRA, chiamata=CHIAMATA)
    assert a["pers"] == LORDO + EXTRA + CHIAMATA == 1237.0
    assert round(a["mol"], 2) == round(10_000 - 4_000 - 1237.0, 2)


def test_aggrega_sedi_chiamata_assente_o_null_vale_zero():
    riga = _mm(lordo=LORDO)
    riga.pop("costo_personale_chiamata")
    out = _aggrega_sedi_mensili(["a"], [riga], {"a": ({}, {})}, {}, [6])["a"]
    assert out["pers"] == LORDO
    assert _aggrega(lordo=LORDO, chiamata=None)["pers"] == LORDO


# ── gruppo_overview e gruppo_margini_coperti: select esplicite ──────────────

def _patch_endpoint(sb):
    return [
        patch.object(gruppo, "_resolve_gruppo",
                     return_value=(sb, "u1", [{"id": "a"}], "Gruppo", {"a": "PV a"}, ["a"])),
        patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)),
        patch.object(gruppo, "_completezza_dati_pv", return_value={}),
        patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": 4_000.0}),
        patch.object(gruppo, "_overrides_mese_sede", return_value={}),
        patch.object(gruppo, "_calcola_segnali", return_value=[]),
        patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
              return_value={"a": ({6: 4_000.0}, {})}),
    ]


def _con(patches, fn):
    for p in patches:
        p.start()
    try:
        return fn()
    finally:
        for p in patches:
            p.stop()


def _select_mm_con_chiamata(sb):
    return [s for s in sb.select_mm if "costo_personale_chiamata" in s]


def test_overview_solo_chiamata_entra_nel_costo_personale_e_nel_mol():
    sb = _SB([_mm(chiamata=CHIAMATA)])
    resp = _con(_patch_endpoint(sb), lambda: gruppo.gruppo_overview(authorization="Bearer t"))
    assert _select_mm_con_chiamata(sb), sb.select_mm
    assert resp.kpi.costo_personale == CHIAMATA
    assert resp.kpi.mol == round(10_000 - 4_000 - CHIAMATA, 2)


def test_overview_somma_le_tre_voci():
    sb = _SB([_mm(lordo=LORDO, extra=EXTRA, chiamata=CHIAMATA)])
    resp = _con(_patch_endpoint(sb), lambda: gruppo.gruppo_overview(authorization="Bearer t"))
    assert resp.kpi.costo_personale == 1237.0
    assert resp.kpi.mol == round(10_000 - 4_000 - 1237.0, 2)


def test_margini_coperti_solo_chiamata_abbassa_il_margine():
    sb = _SB([_mm(chiamata=CHIAMATA, coperti=100)])
    resp = _con(_patch_endpoint(sb),
                lambda: gruppo.gruppo_margini_coperti(mese=None, authorization="Bearer t"))
    assert _select_mm_con_chiamata(sb), sb.select_mm
    riga = resp.righe[0]
    # (10.000 − 4.000 − 37) / 10.000 = 59,63 %; senza la chiamata sarebbe 60,0.
    assert riga.margine_perc == 59.6
    assert resp.gruppo.margine_perc == 59.6
    assert riga.coperti == 100


# ── _calcola_segnali: margine_calo con la sola chiamata ─────────────────────

_OGGI = date.today()
_ANNO = _OGGI.year if _OGGI.month >= 4 else _OGGI.year - 1
if _OGGI.year == _ANNO:
    _MESI = tuple(range(_OGGI.month - 3, _OGGI.month + 1))
else:
    _MESI = (9, 10, 11, 12)

_SEGNALI_SPENTI = {"dati_mancanti", "ricavi_mancanti", "prezzi_sopra",
                   "andamento_incasso", "food_cost_alto"}


def _segnali_margine_calo(sb, costi_fb):
    with patch.object(gruppo, "_completezza_dati_pv", return_value={}), \
         patch.object(gruppo, "_costi_mese_per_sede", return_value={}), \
         patch.object(gruppo, "_overrides_mese_sede", return_value={}), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               side_effect=lambda uid, rids, a: {"a": (costi_fb, {})} if a == _ANNO else {}):
        out = gruppo._calcola_segnali(
            sb, ["a"], {"a": "PV a"}, segnali_off=_SEGNALI_SPENTI, user_id="u1",
        )
    return [s for s in out if s["tipo"] == "margine_calo"]


def test_segnale_margine_calo_vede_la_sede_con_la_sola_chiamata():
    """Il segnale salta i mesi senza personale (pers <= 0): una sede che paga
    solo a chiamata, se la colonna non si legge, non ha MAI un mese confrontabile."""
    sb = _SB([_mm(anno=_ANNO, mese=m, chiamata=CHIAMATA) for m in _MESI])
    costi_fb = {m: 5_900.0 for m in _MESI[:3]}
    costi_fb[_MESI[3]] = 8_700.0
    seg = _segnali_margine_calo(sb, costi_fb)
    assert _select_mm_con_chiamata(sb), sb.select_mm
    assert len(seg) == 1, seg
    # (10.000 − 8.700 − 37) = 12,63 %; media (10.000 − 5.900 − 37) = 40,63 %.
    assert seg[0]["testo"].startswith("Margine al 13%, era 41%"), seg[0]["testo"]


def test_versione_segnali_bumpata_per_la_chiamata():
    assert gruppo._SEGNALI_CODE_VERSION >= 4


# ── Router Margini ──────────────────────────────────────────────────────────

def _patch_margini(sb):
    return patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=sb),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
        _invalidate_home_kpi_cache=MagicMock(),
    )


def _analisi(righe):
    sb = _SB([dict(r, ristorante_id="rist-1", anno=2026) for r in righe])
    mesi = sorted({r["mese"] for r in righe})
    with _patch_margini(sb), \
         patch("services.settore_service.settore_utente", return_value="ristorazione"), \
         patch.object(margini, "_calcola_costi_auto_per_periodo",
                      MagicMock(return_value={(2026, m): (4_000.0, 0.0) for m in mesi})), \
         patch.object(margini, "_load_mensile_overrides", MagicMock(return_value={})):
        return margini.get_margini_analisi(
            f"2026-{mesi[0]:02d}-01", f"2026-{mesi[-1]:02d}-28", authorization="Bearer x")


def test_analisi_mese_con_la_sola_chiamata():
    resp = _analisi([_mm(mese=3, chiamata=CHIAMATA)])
    mese = resp.mesi[0]
    assert (mese.costo_dipendenti, mese.costo_personale_extra, mese.costo_personale_chiamata) \
        == (0.0, 0.0, CHIAMATA)
    assert mese.costi_personale == CHIAMATA
    assert mese.mol == round(10_000 - 4_000 - CHIAMATA, 2)
    assert resp.totali.costo_personale_chiamata == CHIAMATA
    assert resp.totali.costi_personale == CHIAMATA
    assert resp.personale_perc == round(CHIAMATA / 10_000 * 100, 2)


def test_analisi_somma_le_tre_voci_su_piu_mesi():
    resp = _analisi([
        _mm(mese=3, lordo=LORDO, extra=EXTRA, chiamata=CHIAMATA),
        _mm(mese=4, chiamata=13.0),
    ])
    marzo, aprile = resp.mesi
    assert marzo.costi_personale == 1237.0
    assert aprile.costi_personale == 13.0
    t = resp.totali
    assert (t.costo_dipendenti, t.costo_personale_extra, t.costo_personale_chiamata) \
        == (LORDO, EXTRA, 50.0)
    assert t.costi_personale == 1250.0
    assert t.mol == round(20_000 - 8_000 - 1250.0, 2)


def test_get_margini_legge_la_chiamata_dalla_select():
    sb = _SB([_mm(rid="rist-1", mese=3, chiamata=CHIAMATA)])
    with _patch_margini(sb), \
         patch("services.margine_service.calcola_costi_automatici_per_anno_sql",
               MagicMock(return_value=({}, {}))):
        resp = margini.get_margini(anno=2026, authorization="Bearer x")
    assert _select_mm_con_chiamata(sb), sb.select_mm
    marzo = next(m for m in resp.mesi if m.mese == 3)
    assert (marzo.costo_dipendenti, marzo.costo_personale_extra, marzo.costo_personale_chiamata) \
        == (0.0, 0.0, CHIAMATA)


def _salva(**voci):
    sb = _SB([])
    body = margini.SalvaMarginiRequest(anno=2026, mesi=[margini.MarginiMeseData(
        mese=3, fatturato_iva10=11_000.0, costi_fb_auto=4_000.0, **voci,
    )])
    with _patch_margini(sb), \
         patch("services.daily_briefing_service.invalidate_today_briefing", MagicMock()):
        margini.save_margini(body, authorization="Bearer x")
    assert len(sb.upserts) == 1
    return sb.upserts[0]


def test_save_margini_con_la_sola_chiamata():
    rec = _salva(costo_personale_chiamata=CHIAMATA)
    assert rec["costo_personale_chiamata"] == CHIAMATA
    assert rec["costo_dipendenti"] == 0.0 and rec["costo_personale_extra"] == 0.0
    assert rec["mol"] == round(10_000 - 4_000 - CHIAMATA, 2)
    assert rec["personale_perc"] == round(CHIAMATA / 10_000 * 100, 2)


def test_save_margini_somma_le_tre_voci():
    rec = _salva(costo_dipendenti=LORDO, costo_personale_extra=EXTRA,
                 costo_personale_chiamata=CHIAMATA)
    assert (rec["costo_dipendenti"], rec["costo_personale_extra"], rec["costo_personale_chiamata"]) \
        == (LORDO, EXTRA, CHIAMATA)
    assert rec["mol"] == round(10_000 - 4_000 - 1237.0, 2)
    assert rec["personale_perc"] == round(1237.0 / 10_000 * 100, 2)


# ── Cella editabile: la chiamata si scrive come le sorelle ──────────────────

def test_cella_accetta_costo_personale_chiamata():
    """Caso esplicito, oltre al parametrizzato sulla whitelist: il parametrizzato
    itera la whitelist stessa e non si accorgerebbe se la chiamata ne uscisse."""
    q = MagicMock()
    for m in ("select", "eq", "limit", "update", "insert"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=[{"id": "r1"}])
    client = MagicMock()
    client.table.return_value = q
    body = margini.MarginiCellaRequest(anno=2026, mese=3, field="costo_personale_chiamata",
                                       value=CHIAMATA)
    with _patch_margini(client), \
         patch("services.daily_briefing_service.invalidate_today_briefing", MagicMock()):
        resp = margini.update_margini_cella(body, authorization="Bearer x")
    assert (resp.field, resp.value) == ("costo_personale_chiamata", CHIAMATA)
    payload = q.update.call_args.args[0]
    assert payload["costo_personale_chiamata"] == CHIAMATA


@pytest.mark.parametrize("campo", ["costo_dipendenti", "costo_personale_extra",
                                   "costo_personale_chiamata"])
def test_le_tre_voci_del_personale_sono_editabili(campo):
    assert campo in margini._CELL_FIELDS_EDITABILI
