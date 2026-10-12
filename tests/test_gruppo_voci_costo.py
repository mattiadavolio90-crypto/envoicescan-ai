"""«Voci di costo» della scheda Margini di catena (12/10/2026).

Per ogni punto vendita, `gruppo_margini_coperti` da' le incidenze sul fatturato
netto di F&B, spese generali e personale, con lo stesso periodo e la stessa
formula del margine (decisione di Mattia: un solo calcolo). Con i dati completi
le quattro voci fanno 100.

La sede «incompleta» mostra comunque F&B e spese, che vengono dalle fatture;
personale e margine no, come la tabella di sopra. Si prova l'endpoint vero con
il finto client di `test_personale_chiamata_gruppo_margini`, che proietta sulle
colonne della select.
"""
from unittest.mock import patch

from services.routers import gruppo
from tests.test_personale_chiamata_gruppo_margini import _SB, _con, _mm

# Netto 10.000 (11.000 con IVA al 10%), F&B 4.000 dalle fatture.
FB = 4_000.0


def _patches(sb, ids, completezza=None, fb=None):
    nomi = {rid: f"PV {rid}" for rid in ids}
    fb = fb or {rid: FB for rid in ids}
    return [
        patch.object(gruppo, "_resolve_gruppo",
                     return_value=(sb, "u1", [{"id": r} for r in ids], "Gruppo", nomi, ids)),
        patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)),
        patch.object(gruppo, "_completezza_dati_pv", return_value=completezza or {}),
        patch.object(gruppo, "_costi_mese_per_sede", return_value=dict(fb)),
        patch.object(gruppo, "_overrides_mese_sede", return_value={}),
        patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
              return_value={rid: ({6: v}, {}) for rid, v in fb.items()}),
    ]


def _margini(righe_mm, ids=("a",), **kw):
    sb = _SB(righe_mm)
    return _con(_patches(sb, list(ids), **kw),
                lambda: gruppo.gruppo_margini_coperti(mese=None, authorization="Bearer t"))


def _voci(r):
    return (r.food_cost_perc, r.spese_generali_perc, r.personale_perc, r.margine_perc)


def test_sede_completa_le_quattro_voci_fanno_cento():
    resp = _margini([_mm(lordo=2_000.0, altri_costi_spese=1_500.0)])
    riga = resp.righe[0]
    assert _voci(riga) == (40.0, 15.0, 20.0, 25.0)
    assert sum(_voci(riga)) == 100.0


def test_il_personale_somma_le_tre_voci_come_il_margine():
    resp = _margini([_mm(lordo=1_000.0, extra=600.0, chiamata=400.0, altri_costi_spese=1_500.0)])
    assert resp.righe[0].personale_perc == 20.0


def test_sede_incompleta_tiene_fb_e_spese_e_perde_personale_e_margine():
    """Il personale c'e' nei mesi passati ma manca nell'ultimo: la sede e'
    «incompleta» e il suo personale annuo e' sottostimato. Si mostra cio' che
    viene dalle fatture, non una percentuale che sembra buona perche' mancano dati."""
    resp = _margini(
        [_mm(lordo=2_000.0, altri_costi_spese=1_500.0)],
        completezza={"a": ["il costo del personale"]},
    )
    riga = resp.righe[0]
    assert riga.dati_incompleti is True
    assert _voci(riga) == (40.0, 15.0, None, None)


def test_senza_fatturato_nessuna_voce():
    resp = _margini([_mm(lordo=2_000.0, altri_costi_spese=1_500.0, fatturato_iva10=0.0)])
    assert _voci(resp.righe[0]) == (None, None, None, None)


def test_spese_e_personale_a_zero_sono_un_dato_che_manca():
    """Come il F&B: un «0%» sarebbe colorato «migliore della catena»."""
    resp = _margini([_mm(lordo=0.0, altri_costi_spese=0.0)])
    riga = resp.righe[0]
    assert riga.spese_generali_perc is None
    assert riga.personale_perc is None
    assert riga.food_cost_perc == 40.0


def test_il_gruppo_somma_spese_e_personale_di_tutte_le_sedi():
    """b ha il doppio dell'incasso. Gruppo: netto 30.000, F&B 8.000, spese
    1.500 + 4.500 = 6.000, personale 2.000 + 4.000 = 6.000. b e' incompleta: la
    sua riga perde il personale, ma il gruppo lo somma e il client lo marca
    «parziale» (`n_incompleti`), come gia' fa col margine del gruppo."""
    resp = _margini(
        [
            _mm(rid="a", lordo=2_000.0, altri_costi_spese=1_500.0),
            _mm(rid="b", lordo=4_000.0, altri_costi_spese=4_500.0, fatturato_iva10=22_000.0),
        ],
        ids=("a", "b"),
        completezza={"b": ["il costo del personale"]},
    )
    per_id = {r.ristorante_id: r for r in resp.righe}
    assert per_id["b"].personale_perc is None
    assert per_id["b"].spese_generali_perc == 22.5
    g = resp.gruppo
    assert g.spese_generali_perc == 20.0
    assert g.personale_perc == 20.0
    assert g.food_cost_perc == 26.7
    assert resp.n_incompleti == 1


# ── La chat di catena riceve la stessa riserva della pagina ─────────────────
# La riga del gruppo con sedi incomplete e' «parziale» a schermo. Alla chat
# arrivava il numero nudo: su SUSHILAND il personale del gruppo (9,6%, mezzo anno
# senza personale) si sarebbe letto «contenuto» contro la soglia del prompt.

def _chat(dump, args=None):
    import services.fastapi_worker as fw
    from unittest.mock import MagicMock
    g = MagicMock()
    g.gruppo_margini_coperti.return_value.model_dump.return_value = dump
    g.incasso_fuori_norma_per_sede.return_value = {}
    with patch.object(fw, "_gruppo_router_mod", return_value=g):
        return fw._chat_esegui_tool_gruppo("gruppo_margini_coperti", args or {}, "Bearer t")


def _dump(n_incompleti, righe):
    return {"n_incompleti": n_incompleti, "righe": righe,
            "gruppo": {"nome": "Gruppo", "personale_perc": 9.6, "dati_incompleti": False}}


def test_chat_gruppo_parziale_porta_la_nota_nel_dato():
    out = _chat(_dump(1, [
        {"ristorante_id": "a", "dati_incompleti": False},
        {"ristorante_id": "b", "dati_incompleti": True, "spese_generali_perc": 22.5},
    ]))
    assert "parziale" in out["gruppo"]["nota"].lower()
    assert "soglie" in out["gruppo"]["nota"]
    per_id = {r["ristorante_id"]: r for r in out["righe"]}
    assert "incompleti" in per_id["b"]["nota"]
    assert "nota" not in per_id["a"]


def test_chat_gruppo_completo_nessuna_nota():
    out = _chat(_dump(0, [{"ristorante_id": "a", "dati_incompleti": False}]))
    assert "nota" not in out["gruppo"]
    assert "nota" not in out["righe"][0]


def test_chat_la_nota_del_mese_fuori_norma_non_si_perde():
    """Una sede con l'incasso di ferie ha gia' la sua nota: resta quella."""
    import services.fastapi_worker as fw
    from unittest.mock import MagicMock
    g = MagicMock()
    g.gruppo_margini_coperti.return_value.model_dump.return_value = _dump(1, [
        {"ristorante_id": "b", "dati_incompleti": True},
    ])
    g.incasso_fuori_norma_per_sede.return_value = {"b": True}
    with patch.object(fw, "_gruppo_router_mod", return_value=g):
        out = fw._chat_esegui_tool_gruppo("gruppo_margini_coperti", {"mese": 8}, "Bearer t")
    assert out["righe"][0]["nota"] == fw._NOTA_INCASSO_FUORI_NORMA
    assert "parziale" in out["gruppo"]["nota"].lower()
