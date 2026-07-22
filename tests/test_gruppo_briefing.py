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


def test_segnali_aperti_non_dice_tutto_ok():
    # Con segnali aperti il briefing NON deve dire "tutto in ordine" (le card sotto
    # mostrano già i dettagli); e non ripete più il vecchio rimando-indice "N cose
    # da vedere più sotto" (che duplicava le card).
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=2, sev_max="warning", salute_pv=salute_pv,
    )
    assert "cose da vedere" not in out.narrativa
    assert "tutto in ordine" not in out.narrativa.lower()


def test_fatture_da_collocare_accenno_asciutto_senza_numero():
    # Decisione 22/07 (piano briefing dinamico, Fase 3 estesa alla catena): il
    # numero (365) resta SOLO nella card sotto (n_fatture_da_collocare, campo
    # strutturato); la narrativa può accennare che ce ne sono, senza ripetere
    # il numero né usare l'imperativo "assegnale/dividile" (non azionabile su
    # mobile, dove la coda non esiste).
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_da_collocare=3,
    )
    # Conteggio esposto come campo strutturato (il numero vero, per la card).
    assert out.n_fatture_da_collocare == 3
    # La narrativa accenna ma NON riporta il numero né l'imperativo.
    assert "da collocare" in out.narrativa.lower()
    assert "3 fatture" not in out.narrativa
    assert "assegnale" not in out.narrativa.lower()
    # Con fatture in sospeso non si dice "tutto in ordine".
    assert "tutto in ordine" not in out.narrativa.lower()


def test_nessuna_fattura_da_collocare_campo_a_zero():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_da_collocare=0,
    )
    assert out.n_fatture_da_collocare == 0
    # Senza sospesi né altri problemi, torna il "tutto in ordine".
    assert "tutto in ordine" in out.narrativa.lower()


# ── Fase 3 estesa alla catena (22/07): apertura "fatture arrivate ieri" ──────
# Caso OFFSIDE: P.IVA condivisa fra sedi → le fatture arrivate ieri restano in
# coda 'da_assegnare' finché non le smisti (fatture_ieri_da_assegnare=True).
# Caso SUSHILAND: ogni PV ha la propria P.IVA → le fatture arrivate ieri sono
# GIÀ sui PV (fatture_ieri_da_assegnare=False), il rimando va al singolo PV.
# Stessa formula per entrambi: cambia solo il flag, non il codice — e infatti
# man mano che il routing per indirizzo copre più fornitori OFFSIDE, il peso si
# sposta da 'in coda' a 'già assegnate' senza toccare questa funzione.

def test_fatture_arrivate_ieri_in_coda_rimanda_alla_card():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "OFFSIDE", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_arrivate_ieri=11, fatture_ieri_da_assegnare=True,
    )
    assert "11 fatture" in out.narrativa
    assert "da assegnare a un locale" in out.narrativa
    assert "qui sotto" in out.narrativa


def test_fatture_arrivate_ieri_gia_sui_pv_rimanda_al_pv():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "SUSHILAND", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_arrivate_ieri=14, fatture_ieri_da_assegnare=False,
    )
    assert "14 fatture" in out.narrativa
    assert "punto vendita" in out.narrativa
    assert "da assegnare a un locale" not in out.narrativa


def test_fatture_arrivate_ieri_singolare():
    ranking = [_rank("a", "PV A", 30.0)]
    salute_pv = [_sal("a", "PV A", 90)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=90, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_arrivate_ieri=1, fatture_ieri_da_assegnare=True,
    )
    assert "è arrivata una fattura" in out.narrativa


def test_novita_di_ieri_non_ripete_arretrato_non_ridondante():
    # Se ieri sono arrivate fatture (novità), NON si ripete anche l'accenno
    # all'arretrato generico nella stessa narrativa — sono due concetti diversi
    # (novità vs arretrato) ma il messaggio "da collocare" del blocco arretrato
    # diventerebbe ridondante col dettaglio già dato dal blocco novità.
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "OFFSIDE", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_da_collocare=365, n_fatture_arrivate_ieri=11,
        fatture_ieri_da_assegnare=True,
    )
    assert out.narrativa.count("da collocare") <= 1
    assert "11 fatture" in out.narrativa


def test_senza_novita_ma_con_arretrato_accenna_senza_numero():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "OFFSIDE", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_da_collocare=365, n_fatture_arrivate_ieri=None,
    )
    assert "365" not in out.narrativa
    assert "da collocare" in out.narrativa.lower()


def test_senza_novita_senza_arretrato_silenzio_sul_tema_fatture():
    ranking = [_rank("a", "PV A", 30.0), _rank("b", "PV B", 20.0)]
    salute_pv = [_sal("a", "PV A", 90), _sal("b", "PV B", 85)]
    out = _build_briefing(
        "GRUPPO", ranking, salute_indice=88, salute_colore="verde",
        n_segnali=0, sev_max="info", salute_pv=salute_pv,
        n_fatture_da_collocare=0, n_fatture_arrivate_ieri=None,
    )
    assert "fattur" not in out.narrativa.lower()
    assert "tutto in ordine" in out.narrativa.lower()


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
