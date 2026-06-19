"""Test guardia: il briefing CATENA non dice "tutto sotto controllo" se mancano dati.

Difetto osservato (Gruppo SUSHILAND, 18/06): il briefing apriva "Nessuna
segnalazione aperta: tutto sotto controllo" mentre 3 PV su 4 erano senza dati di
costo (salute 25) e la salute del gruppo era 42 (rossa) — due frasi che si
contraddicono. Inoltre trattava i PV senza costi come performance reali
("più indietro VILLA GUARDIA 0%"), perché 'dati_incompleti' guardava solo il
fatturato, non i costi.

Fix: la completezza si misura sulla SALUTE per-PV (che rileva i costi mancanti).
"""
from services.routers.gruppo import _build_briefing, RankingPV, SalutePV


def _rank(rid, nome, margine, incompleti=False):
    return RankingPV(
        ristorante_id=rid, nome=nome, margine_perc=margine,
        fatturato=1000.0, colore="verde", dati_incompleti=incompleti,
    )


def _sal(rid, nome, indice):
    colore = "verde" if indice >= 80 else ("giallo" if indice >= 50 else "rosso")
    return SalutePV(ristorante_id=rid, nome=nome, indice=indice, colore=colore)


def test_sushiland_tre_pv_senza_costi():
    # 1 PV sano (LAND 94, margine 57), 3 con costi mancanti (salute 25).
    ranking = [
        _rank("land", "LAND DEI SAPORI SRL", 57.0),
        _rank("villa", "SUSHILAND VILLA GUARDIA SRL", 0.0),
        _rank("sang", "SUSHILAND SAN GIULIANO M. SRL", 0.0),
        _rank("mar", "SUSHILAND MARIANO COMENSE SRL", 0.0),
    ]
    salute_pv = [
        _sal("land", "LAND DEI SAPORI SRL", 94),
        _sal("villa", "SUSHILAND VILLA GUARDIA SRL", 25),
        _sal("sang", "SUSHILAND SAN GIULIANO M. SRL", 25),
        _sal("mar", "SUSHILAND MARIANO COMENSE SRL", 25),
    ]
    out = _build_briefing(
        "SUSHILAND", ranking, salute_indice=42, salute_colore="rosso",
        n_segnali=0, sev_max="warning", salute_pv=salute_pv,
    )
    testo = out.narrativa
    # MAI "tutto sotto controllo" con salute rossa.
    assert "tutto sotto controllo" not in testo.lower()
    # Solo il PV sano entra nel confronto margini (gli altri hanno margine finto).
    assert "LAND DEI SAPORI SRL" in testo and "57%" in testo
    assert "VILLA GUARDIA" not in testo
    # Segnala le 3 sedi da completare e la salute bassa.
    assert "3 punti vendita" in testo
    assert "da completare" in testo
    assert "42" in testo


def test_tutto_sano_dice_tutto_in_ordine():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
    )
    assert "tutto in ordine" in out.narrativa.lower()


def test_salute_rossa_mai_sotto_controllo_anche_senza_segnali():
    # Il guard chiave: n_segnali=0 NON basta per "tutto sotto controllo" se la
    # salute è rossa.
    ranking = [_rank("a", "PV A", 10.0)]
    salute_pv = [_sal("a", "PV A", 30)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=30, salute_colore="rosso",
        n_segnali=0, sev_max="warning", salute_pv=salute_pv,
    )
    assert "tutto sotto controllo" not in out.narrativa.lower()
    assert "salute del gruppo è bassa" in out.narrativa.lower()


def test_segnali_aperti_mostra_conteggio():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=2, sev_max="warning", salute_pv=salute_pv,
    )
    assert "2 cose da vedere" in out.narrativa
    assert "tutto sotto controllo" not in out.narrativa.lower()


def test_completezza_per_presenza_dati_non_salute():
    # Decisione 19/06: la completezza si misura per PRESENZA di dati (incompleti_ids),
    # non per % salute. Qui le salute sono alte (>=50) ma B e' in incompleti_ids ->
    # B NON entra nel confronto e viene contato tra i da-completare.
    ranking = [_rank("a", "PV A", 40.0), _rank("b", "PV B", 30.0)]
    salute_pv = [_sal("a", "PV A", 85), _sal("b", "PV B", 80)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=82, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        incompleti_ids={"b"},
    )
    # Un solo PV affidabile: niente confronto "va meglio/peggio".
    assert "Va meglio" not in out.narrativa
    assert "1 punto vendita" in out.narrativa and "da completare" in out.narrativa
    # Con una sede incompleta non si dice "tutto sotto controllo".
    assert "tutto sotto controllo" not in out.narrativa.lower()
