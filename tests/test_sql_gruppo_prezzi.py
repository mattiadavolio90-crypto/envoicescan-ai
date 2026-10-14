"""Prezzi di catena: la RPC `gruppo_prezzi_catena` eseguita su un Postgres vero.

Perche' esiste
==============
La scheda «Prezzi» di Analisi catena non carica le righe di fattura: le riceve
aggregate dalla RPC e ci applica `_deriva_variazione`, la stessa funzione
dell'Osservatorio del PV. Se la RPC filtra o ordina diversamente da pandas, la
stessa sede mostra variazioni diverse nelle due pagine, e nessun test con un DB
finto se ne accorge.

Come misura
===========
1. Equivalenza: fatture casuali su due sedi, con tutto cio' che i filtri devono
   scartare (spese generali, note di credito anche a prezzo positivo — TD04 e
   «nc»: `tipo_documento` e' varchar(4) —, prezzi a
   zero, righe cancellate o escluse dai conti, fuori periodo, descrizioni con
   spazi e maiuscole diverse). Per ogni sede le variazioni della catena devono
   coincidere con `_calcola_variazioni_prezzi_sync` sulle righe di quella sede.
   Dal 14/10/2026 un acquisto e' una fattura: il seme ha righe ripetute nella
   stessa fattura, due fatture nello stesso giorno, unita' di misura diverse e
   lo stesso nome di file nelle due sedi, e le due strade devono scegliere la
   stessa fattura come ultima (spareggio data/file/unita').
2. Due sedi con prezzi diversi ma stabili: zero variazioni, un divario. E' il
   caso che separa «calcolo per sede» da «serie mescolata».
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.sql

UTENTE = "11111111-1111-4111-8111-111111111111"
SEDE1 = "22222222-2222-4222-8222-222222222221"
SEDE2 = "22222222-2222-4222-8222-222222222222"
NOMI = {SEDE1: "Centro", SEDE2: "Mare"}
DA, A = "2026-01-01", "2026-12-31"

def _semina_sedi(sql):
    sql(
        "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
        "VALUES (%s, 'catena@oneflux.test', 'x', 'Catena')",
        UTENTE,
    )
    for sede, nome in NOMI.items():
        sql(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
            "VALUES (%s, %s, %s, '01234567891', true)",
            sede, UTENTE, nome,
        )


_NUMERO_RIGA = iter(range(1, 10**6))


def _riga(sql, sede, giorno, descrizione, fornitore, prezzo, *, categoria="LATTICINI", quantita=1,
          tipo="TD01", file=None, cancellata=False, oscurata=False, unita="PZ", senza_file=False):
    sql(
        "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, data_documento, "
        "fornitore, descrizione, categoria, quantita, prezzo_unitario, totale_riga, tipo_documento, "
        "deleted_at, oscurata, unita_misura) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        UTENTE, sede, "" if senza_file else (file or f"f-{sede[-1]}-{giorno}.xml"), next(_NUMERO_RIGA), giorno, fornitore,
        descrizione, categoria,
        quantita, prezzo, prezzo, tipo, "2026-06-01T00:00:00+00:00" if cancellata else None, oscurata, unita,
    )


def _json(valore):
    """Come lo restituirebbe PostgREST: numeric -> numero, date -> stringa ISO."""
    def conv(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, date):
            return v.isoformat()
        raise TypeError(type(v))
    return json.loads(json.dumps(valore, default=conv))


def _esito(sql, sedi=(SEDE1, SEDE2), escluse=None):
    from config.constants import CATEGORIE_SPESE_GENERALI

    valore = sql(
        "SELECT public.gruppo_prezzi_catena(%s::uuid[], %s, %s, %s)",
        list(sedi), DA, A, escluse if escluse is not None else list(CATEGORIE_SPESE_GENERALI),
    )[0][0]
    # jsonb arriva gia' come dict; il giro in JSON lo rende identico a PostgREST.
    return _json(valore)


def _coppie(sql, sedi=(SEDE1, SEDE2), escluse=None):
    return _esito(sql, sedi, escluse)["coppie"]


def _righe_pv(sql, sede):
    """Le righe che `_load_fatture_for_prezzi` darebbe all'Osservatorio del PV."""
    cols = "descrizione,categoria,fornitore,prezzo_unitario,quantita,totale_riga,data_documento,file_origine,tipo_documento,unita_misura"
    righe = sql(
        f"SELECT {cols} FROM public.fatture WHERE ristorante_id = %s AND deleted_at IS NULL "
        "AND NOT oscurata AND data_documento BETWEEN %s AND %s ORDER BY data_documento, id",
        sede, DA, A,
    )
    return _json([dict(zip(cols.split(","), r)) for r in righe])


# `n_fattura` = il file dell'ultimo acquisto: senza, il test non si accorgerebbe
# se le due strade scegliessero come «ultima» una fattura diversa.
_CAMPI = ("prodotto", "categoria", "fornitore", "storico_valori", "media", "penultimo", "ultimo",
          "aumento_perc", "data", "trend", "impatto_stimato", "delta_euro", "n_fattura")


def _confrontabile(v):
    return {k: v[k] for k in _CAMPI}


def test_la_catena_da_per_ogni_sede_le_variazioni_dell_osservatorio(sql):
    from services.routers.gruppo import _variazioni_catena
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync

    _semina_sedi(sql)
    rnd = random.Random(20261011)
    # Le due forme con «ORDER n (m)» devono finire nella serie di «Salmone 5-6»
    # in entrambe le strade (SQL e pandas): e' la regola 3 di utils/voci_prezzo.py.
    prodotti = ["Mozzarella", "MOZZARELLA ", " mozzarella", "Limone", "Salmone 5-6", "Coca BIB 33cl",
                "Salmone 5-6 ORDER 2012258 (1007082)", "SALMONE 5-6 order 2012995(1007786)"]
    fornitori = ["Partesa", "PARTESA ", "Mefon", "ADC"]
    # Un acquisto = una fattura (`una_riga_per_documento` e la CTE `documenti`):
    # il seme deve contenere i casi in cui le due strade possono divergere —
    # lo stesso prodotto su piu' righe della stessa fattura a prezzi e quantita'
    # diverse, due fatture nello stesso giorno (spareggio sul nome del file),
    # unita' di misura diverse nella stessa fattura (non si fondono), lo stesso
    # nome di file nelle due sedi. Un file ha una sola data, come sul live.
    unita = ["PZ", "PZ", " pz", "KG", "CT"]
    for sede in (SEDE1, SEDE2):
        giorni = rnd.sample(range(0, 360), 140)
        for i, g in enumerate(sorted(giorni)):
            giorno = (date(2026, 1, 1) + timedelta(days=g)).isoformat()
            file_del_giorno = [f"F-{g}.xml"] if rnd.random() < 0.5 else [f"f-{sede[-1]}-{g}.xml"]
            if rnd.random() < 0.25:
                file_del_giorno.append(f"G-{sede[-1]}-{g}.xml")
            for file in file_del_giorno:
                prodotto, fornitore = rnd.choice(prodotti), rnd.choice(fornitori)
                for _ in range(rnd.choice([1, 1, 2, 3])):
                    caso = rnd.random()
                    _riga(
                        sql, sede, giorno, prodotto, fornitore,
                        rnd.choice([Decimal("0"), Decimal(f"{rnd.uniform(1, 30):.2f}"), Decimal(f"{rnd.uniform(1, 30):.2f}")]),
                        categoria=rnd.choice(["LATTICINI", "FRUTTA", "BEVANDE", "UTENZE E LOCALI", "MATERIALE DI CONSUMO"]),
                        quantita=rnd.choice([None, 1, Decimal("2.5"), 10]),
                        tipo=rnd.choice(["TD01", "TD01", "TD01", "TD04", "nc", None]),
                        file=file,
                        cancellata=caso < 0.05,
                        oscurata=0.05 <= caso < 0.10,
                        unita=rnd.choice(unita),
                    )
        # Fuori periodo: non deve entrare in nessuna delle due strade.
        _riga(sql, sede, "2025-12-31", "Limone", "Mefon", Decimal("99.00"))

    coppie = _coppie(sql)
    assert coppie, "la RPC non ha restituito nulla: il confronto non misurerebbe niente"

    for soglia in (0.0, 5.0, 15.0):
        catena = _variazioni_catena(coppie, NOMI, soglia)
        for sede in (SEDE1, SEDE2):
            attese = _calcola_variazioni_prezzi_sync(_righe_pv(sql, sede), soglia)
            ottenute = [v for v in catena if v["ristorante_id"] == sede]
            assert len(attese) > 3, "troppe poche variazioni per un confronto che dica qualcosa"
            chiave = lambda v: (v["prodotto"], v["fornitore"])  # noqa: E731
            a = sorted(map(_confrontabile, attese), key=chiave)
            o = sorted(map(_confrontabile, ottenute), key=chiave)
            assert [chiave(v) for v in o] == [chiave(v) for v in a]
            for va, vo in zip(a, o):
                for campo in _CAMPI:
                    if isinstance(va[campo], float):
                        assert vo[campo] == pytest.approx(va[campo], abs=0.011), (campo, va, vo)
                    elif campo == "storico_valori":
                        assert vo[campo] == pytest.approx(va[campo]), (campo, va, vo)
                    else:
                        assert vo[campo] == va[campo], (campo, va, vo)


def test_due_sedi_con_prezzi_diversi_e_stabili_non_sono_un_rincaro(sql):
    from services.routers.gruppo import _calcola_divari_catena, _variazioni_catena

    _semina_sedi(sql)
    for mese in range(3, 9):
        _riga(sql, SEDE1, f"2026-{mese:02d}-10", "BIB COCA COLA", "PARTESA", Decimal("15.80"), quantita=4)
        _riga(sql, SEDE2, f"2026-{mese:02d}-12", "BIB COCA COLA", "PARTESA", Decimal("17.58"), quantita=3)

    coppie = _coppie(sql)
    assert _variazioni_catena(coppie, NOMI, 5.0) == []
    divari = _calcola_divari_catena(coppie, NOMI, 5.0)
    assert len(divari) == 1
    d = divari[0]
    assert (d["prezzo_min"], d["prezzo_max"]) == (15.80, 17.58)
    assert d["divario_perc"] == pytest.approx(11.27, abs=0.01)
    caro = d["per_pv"][0]
    assert caro["nome_pv"] == "Mare"
    # 6 acquisti da 3 pezzi pagati 1,78 in piu' del Centro.
    assert caro["extra_stimato"] == pytest.approx(1.78 * 18, abs=0.01)
    assert d["per_pv"][1]["extra_stimato"] == 0


def test_la_sede_che_non_compra_da_mesi_esce_dal_confronto(sql):
    from services.routers.gruppo import _calcola_divari_catena

    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-09-20", "LIMONE", "MEFON", Decimal("32.00"))
    _riga(sql, SEDE2, "2026-07-01", "LIMONE", "MEFON", Decimal("17.00"))
    assert _calcola_divari_catena(_coppie(sql), NOMI, 5.0, finestra_giorni=60) == []
    assert len(_calcola_divari_catena(_coppie(sql), NOMI, 5.0, finestra_giorni=90)) == 1


def test_stesso_rincaro_in_due_sedi_e_un_rincaro_opposto(sql):
    from services.routers.gruppo import _variazioni_catena

    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-01", "SALMONE", "ADC", Decimal("6.00"))
    _riga(sql, SEDE1, "2026-04-01", "SALMONE", "ADC", Decimal("7.00"))
    _riga(sql, SEDE2, "2026-03-02", "SALMONE", "ADC", Decimal("6.10"))
    _riga(sql, SEDE2, "2026-04-02", "SALMONE", "ADC", Decimal("7.10"))
    _riga(sql, SEDE1, "2026-03-03", "LIMONE", "MEFON", Decimal("20.00"))
    _riga(sql, SEDE1, "2026-04-03", "LIMONE", "MEFON", Decimal("24.00"))
    _riga(sql, SEDE2, "2026-03-04", "LIMONE", "MEFON", Decimal("20.00"))
    _riga(sql, SEDE2, "2026-04-04", "LIMONE", "MEFON", Decimal("16.00"))

    per = {(v["prodotto"], v["nome_pv"]): v for v in _variazioni_catena(_coppie(sql), NOMI, 5.0)}
    assert per[("SALMONE", "Centro")]["n_pv_stesso_verso"] == 2
    assert per[("SALMONE", "Mare")]["n_pv_stesso_verso"] == 2
    assert per[("LIMONE", "Centro")]["n_pv_stesso_verso"] == 1
    assert per[("LIMONE", "Mare")]["n_pv_stesso_verso"] == 1
    assert {v["n_pv_confrontabili"] for v in per.values()} == {2}


def test_categoria_esclusa_e_nota_di_credito_restano_fuori(sql):
    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-01", "ACQUEDOTTO", "COMO ACQUA", Decimal("1357.61"), categoria="UTENZE E LOCALI")
    _riga(sql, SEDE1, "2026-03-02", "RESO", "PARTESA", Decimal("10.00"), tipo="TD04")
    _riga(sql, SEDE1, "2026-03-03", "STORNO", "PARTESA", Decimal("10.00"), tipo="nc")
    _riga(sql, SEDE1, "2026-03-04", "PANE", "FORNO", Decimal("2.00"))
    _riga(sql, SEDE1, "2026-03-05", "PANE", "FORNO", Decimal("2.10"))
    # Le cauzioni escono qualunque sia la categoria: su OFFSIDE stanno in VARIE BAR.
    _riga(sql, SEDE1, "2026-03-06", "ADDEBITO CAUZIONI", "PARTESA", Decimal("150.54"), categoria="VARIE BAR")
    _riga(sql, SEDE1, "2026-03-07", "ADDEBITO CAUZIONI", "PARTESA", Decimal("0.10"), categoria="VARIE BAR")
    assert [c["desc_key"] for c in _coppie(sql, escluse=["UTENZE E LOCALI"])] == ["PANE"]


def test_restano_fuori_solo_le_coppie_che_non_servono_a_nessuna_vista(sql):
    """Un solo acquisto in una sola sede: niente variazione e niente confronto,
    quindi fuori dal valore restituito. Un solo acquisto per sede ma in due sedi
    resta (e' un divario). Il conteggio degli acquisti li vede tutti."""
    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-01", "UNA VOLTA", "F", Decimal("1.00"))
    _riga(sql, SEDE1, "2026-03-02", "IN DUE SEDI", "F", Decimal("1.00"))
    _riga(sql, SEDE2, "2026-03-03", "IN DUE SEDI", "F", Decimal("1.20"))
    _riga(sql, SEDE2, "2026-03-04", "DUE VOLTE", "F", Decimal("1.00"))
    _riga(sql, SEDE2, "2026-03-05", "DUE VOLTE", "F", Decimal("1.10"))
    esito = _esito(sql, escluse=[])
    assert esito["acquisti"] == 5
    assert sorted((c["desc_key"], c["ristorante_id"][-1]) for c in esito["coppie"]) == [
        ("DUE VOLTE", "2"), ("IN DUE SEDI", "1"), ("IN DUE SEDI", "2"),
    ]


def test_senza_acquisti_il_valore_e_vuoto_non_nullo(sql):
    _semina_sedi(sql)
    assert _esito(sql) == {"acquisti": 0, "coppie": []}


def test_lo_storico_si_apre_anche_col_fornitore_troncato(db_sql, sql):
    """La variazione porta il fornitore troncato a 30 caratteri e il client lo
    rimanda per aprire lo storico: col confronto esatto la riga si apriva vuota
    per 54 fornitori su 319 (11/10/2026). Un nome corto resta un confronto
    esatto: «ADC» non deve tirarsi dietro «ADC ITALIA»."""
    from services.routers.prezzi import _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    lungo = "DINGFENG IMPORTEXPORT S.R.L. UNIPERSONALE"
    _riga(sql, SEDE1, "2026-03-01", "SNACK", lungo, Decimal("0.90"))
    _riga(sql, SEDE1, "2026-04-01", "SNACK", lungo, Decimal("1.10"))
    _riga(sql, SEDE1, "2026-03-02", "SNACK", "ADC", Decimal("2.00"))
    _riga(sql, SEDE1, "2026-03-03", "SNACK", "ADC ITALIA", Decimal("9.00"))
    sb = ClientSQL(db_sql)

    troncato = _storico_prodotto_sede(sb, SEDE1, "SNACK", lungo[:30])
    assert [p.prezzo_unitario for p in troncato.punti] == [0.90, 1.10]
    corto = _storico_prodotto_sede(sb, SEDE1, "SNACK", "ADC")
    assert [p.prezzo_unitario for p in corto.punti] == [2.00]

    # Il taglio a 30 cade su uno spazio: il nome troncato finisce con " ".
    spazio = "GRUPPO CIMBALI SERVICE S.R.L. UNIPERSONALE"
    assert spazio[:30].endswith(" ")
    _riga(sql, SEDE1, "2026-05-01", "CAFFE", spazio, Decimal("12.00"))
    assert [p.prezzo_unitario for p in _storico_prodotto_sede(sb, SEDE1, "CAFFE", spazio[:30]).punti] == [12.00]


def test_la_stella_di_catena_e_quella_del_pv_della_riga(sql):
    from services.routers.gruppo import _variazioni_catena

    _semina_sedi(sql)
    for sede in (SEDE1, SEDE2):
        _riga(sql, sede, "2026-03-01", "SALMONE", "ADC", Decimal("6.00"))
        _riga(sql, sede, "2026-04-01", "SALMONE", "ADC", Decimal("7.00"))
    per = {v["nome_pv"]: v for v in _variazioni_catena(_coppie(sql), NOMI, 5.0, {SEDE1: {"SALMONE|ADC"}})}
    assert (per["Centro"]["preferito"], per["Mare"]["preferito"]) == (True, False)


def test_un_cambio_di_confezione_non_e_lo_stesso_rincaro_di_un_altra_sede(sql):
    from services.routers.gruppo import _calcola_divari_catena, _variazioni_catena

    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-01", "BEVANDA", "PARTESA", Decimal("1.00"))
    _riga(sql, SEDE1, "2026-04-01", "BEVANDA", "PARTESA", Decimal("14.00"))
    _riga(sql, SEDE2, "2026-03-02", "BEVANDA", "PARTESA", Decimal("1.00"))
    _riga(sql, SEDE2, "2026-04-02", "BEVANDA", "PARTESA", Decimal("1.20"))
    per = {v["nome_pv"]: v for v in _variazioni_catena(_coppie(sql), NOMI, 5.0)}
    assert per["Centro"]["da_controllare"] is True and per["Mare"]["da_controllare"] is False
    # Senza l'esclusione il +1300% del Centro farebbe dire «in 2 PV su 2».
    assert per["Mare"]["n_pv_stesso_verso"] == 1
    divari = _calcola_divari_catena(_coppie(sql), NOMI, 5.0)
    assert [d["da_controllare"] for d in divari] == [True]


def test_togliere_la_stella_toglie_anche_quella_salvata_troncata(db_sql, sql):
    from services.routers.prezzi import _salva_preferito, _togli_preferito
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    sb = ClientSQL(db_sql)
    desc = "PRODOTTO CON UNA DESCRIZIONE MOLTO LUNGA CHE SUPERA I SESSANTA CARATTERI DI SICURO"
    forn = "DINGFENG IMPORTEXPORT S.R.L. UNIPERSONALE"
    # La forma salvata fino all'11/10/2026, dal nome a video.
    _salva_preferito(sb, SEDE1, UTENTE, desc[:60], forn[:30])
    _salva_preferito(sb, SEDE1, UTENTE, desc, forn)
    _salva_preferito(sb, SEDE2, UTENTE, desc, forn)
    conta = "SELECT ristorante_id::text, count(*) FROM public.prezzi_preferiti GROUP BY 1 ORDER BY 1"
    assert sql(conta) == [(SEDE1, 2), (SEDE2, 1)]
    _togli_preferito(sb, SEDE1, desc, forn)
    assert sql(conta) == [(SEDE2, 1)], "la stella dell'altra sede non si tocca"


def test_la_stella_di_un_altro_cliente_non_si_tocca_dalla_catena(db_sql, sql, monkeypatch):
    """La rotta riceve `ristorante_id` dal client. Il test d'isolamento generale
    non vedeva il DELETE senza controllo: nella sua seed l'altro cliente non ha
    stelle, quindi cancellare «niente» non lascia tracce (mutazione del
    12/10/2026). Qui l'altra sede ha una stella, e deve restare."""
    from fastapi import HTTPException
    from services.routers import gruppo as G
    from services.routers.prezzi import _salva_preferito
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    sb = ClientSQL(db_sql)
    _salva_preferito(sb, SEDE2, UTENTE, "SALMONE", "ADC")
    # Il gruppo di chi chiama ha la sola SEDE1: SEDE2 e' di un altro.
    monkeypatch.setattr(G, "_resolve_gruppo", lambda auth: (sb, UTENTE, [], "G", {SEDE1: "Centro"}, [SEDE1]))

    with pytest.raises(HTTPException) as e:
        G.gruppo_prezzi_preferito_togli(SEDE2, "SALMONE", "ADC", authorization="x")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        G.gruppo_prezzi_preferito_aggiungi(
            G.PreferitoCatenaRequest(ristorante_id=SEDE2, prodotto="LIMONE"), authorization="x",
        )
    assert sql("SELECT descrizione_key FROM public.prezzi_preferiti WHERE ristorante_id = %s", SEDE2) == [("SALMONE",)]


def test_le_stelle_lette_per_la_home_combaciano_con_gli_avvisi(db_sql, sql):
    """La Home legge le stelle con `_carica_preferiti_keys` e le confronta col
    fornitore che `calcola_alert` tronca a 20: le due chiavi devono uscire uguali
    per un fornitore dal nome lungo (10 stelle su 19 sul live)."""
    import pandas as pd
    from services.db_service import calcola_alert
    from services.price_impact_service import _carica_preferiti_keys, _pref_match_key
    from services.routers.prezzi import _salva_preferito
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    forn = "LA GE' GE' PESCA DI GAVAZZI SANTO & C. S.R.L"
    _salva_preferito(ClientSQL(db_sql), SEDE1, UTENTE, "SALMONE NORVEGIA", forn)
    stelle = _carica_preferiti_keys(SEDE1, ClientSQL(db_sql))
    righe = [{"Descrizione": "SALMONE NORVEGIA", "Fornitore": forn, "DataDocumento": d, "PrezzoUnitario": p,
              "Categoria": "PESCE", "FileOrigine": f"{d}.xml", "Quantita": 2.0}
             for d, p in (("2026-03-01", 10.0), ("2026-04-01", 12.0))]
    r = calcola_alert(pd.DataFrame(righe), 5.0).iloc[0]
    assert stelle == {_pref_match_key(r["Prodotto"], r["Fornitore"])}


def test_il_numero_d_ordine_nel_nome_non_spezza_la_serie(sql):
    """LA GE' GE' scrive «ORDER 2025916 (1014546)» in ogni consegna: fino al
    13/10/2026 erano 70 nomi per 19 prodotti, mai una variazione. Due direzioni:
    stesse consegne si uniscono, il prodotto diverso (MOWI) resta a parte."""
    from services.routers.gruppo import _variazioni_catena

    _semina_sedi(sql)
    forn = "LA GE' GE' PESCA DI GAVAZZI SANTO & C. S.R.L"
    _riga(sql, SEDE1, "2026-09-01", "SALMONI 5/6 SALMAR ORDER 2012258 (1007082)", forn, Decimal("10.00"), categoria="PESCE")
    _riga(sql, SEDE1, "2026-10-01", "SALMONI 5/6 SALMAR ORDER 2012995 (1007786)", forn, Decimal("12.00"), categoria="PESCE")
    _riga(sql, SEDE1, "2026-09-01", "SALMONI 5/6 MOWI ORDER 20131407 (100638660)", forn, Decimal("10.00"), categoria="PESCE")
    _riga(sql, SEDE1, "2026-10-01", "SALMONI 5/6 MOWI ORDER 20148324 (100703803)", forn, Decimal("10.00"), categoria="PESCE")

    coppie = _coppie(sql, sedi=(SEDE1,))
    assert sorted((c["desc_key"], c["n_acquisti"]) for c in coppie) == [("SALMONI 5/6 MOWI", 2), ("SALMONI 5/6 SALMAR", 2)]
    variazioni = _variazioni_catena(coppie, NOMI, 5.0)
    assert [(v["prodotto"], v["aumento_perc"]) for v in variazioni] == [("SALMONI 5/6 SALMAR", 20.0)]


def test_il_divario_e_lo_storico_mostrano_il_nome_senza_numero_d_ordine(db_sql, sql):
    """Il nome a video del divario viene dalla RPC (descrizione grezza) e va
    ripulito nel worker; lo storico deve prendere TUTTE le consegne del prodotto
    e nessun prodotto che inizia allo stesso modo («AGLIO NERO» non e' «AGLIO»)."""
    from services.routers.gruppo import _calcola_divari_catena
    from services.routers.prezzi import _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    forn = "LA GE' GE' PESCA"
    _riga(sql, SEDE1, "2026-09-01", "AGLIO ORDER 1 (1)", forn, Decimal("1.00"), categoria="VERDURA")
    _riga(sql, SEDE1, "2026-10-01", "AGLIO ORDER 2 (2)", forn, Decimal("2.00"), categoria="VERDURA")
    _riga(sql, SEDE1, "2026-10-01", "AGLIO NERO", forn, Decimal("9.00"), categoria="VERDURA")
    _riga(sql, SEDE2, "2026-10-02", "AGLIO ORDER 3 (3)", forn, Decimal("3.00"), categoria="VERDURA")

    divari = _calcola_divari_catena(_coppie(sql), NOMI, 5.0)
    assert [(d["prodotto"], d["prezzo_min"], d["prezzo_max"]) for d in divari] == [("AGLIO", 2.0, 3.0)]

    storico = _storico_prodotto_sede(ClientSQL(db_sql), SEDE1, "AGLIO", forn)
    assert [p.prezzo_unitario for p in storico.punti] == [1.00, 2.00]
    # Una richiesta vecchia col nome grezzo (ORDER dentro) apre lo stesso storico.
    grezzo = _storico_prodotto_sede(ClientSQL(db_sql), SEDE1, "AGLIO ORDER 9 (9)", forn)
    assert [p.prezzo_unitario for p in grezzo.punti] == [1.00, 2.00]


def test_i_divari_hanno_chiavi_distinte_e_la_stella_di_un_pv_del_confronto(sql):
    """Due provenienze dello stesso pesce hanno lo stesso nome nei primi 60
    caratteri: la scheda le confondeva (chiave React = nome+fornitore) e, al
    cambio di filtro, a video restavano schede della lista precedente. Ora il
    divario porta la sua chiave e il nome intero. La stella vale se UNO dei PV
    del confronto ha stellato il prodotto, e non se l'ha stellato un PV fuori."""
    from services.routers.gruppo import _calcola_divari_catena

    _semina_sedi(sql)
    base = "DENTICE GIBBOSO 1/2 PESCATO DENTEX GIBBOSUS PESCATO FAO 34 ATL. CENTRO ORIENTALE AMI E PALANGARI "
    for origine, (p1, p2) in (("(DE)", ("22.00", "24.00")), ("(EU)", ("24.00", "26.00"))):
        _riga(sql, SEDE1, "2026-07-20", base + origine, "LA GE' GE' PESCA", Decimal(p1), categoria="PESCE")
        _riga(sql, SEDE2, "2026-07-21", base + origine, "LA GE' GE' PESCA", Decimal(p2), categoria="PESCE")

    stelle = {SEDE2: {f"{base}(EU)|LA GE' GE' PESCA"}, "fuori-gruppo": {f"{base}(DE)|LA GE' GE' PESCA"}}
    divari = _calcola_divari_catena(_coppie(sql), NOMI, 5.0, preferiti_per_sede=stelle)
    assert sorted(d["prodotto"][-4:] for d in divari) == ["(DE)", "(EU)"]
    assert len({(d["desc_key"], d["forn_key"]) for d in divari}) == 2
    assert {d["prodotto"][-4:]: d["preferito"] for d in divari} == {"(DE)": False, "(EU)": True}


def test_la_stella_di_una_sede_fuori_dalla_finestra_non_accende_il_divario(sql):
    """Il preferito del divario e' di un PV DEL CONFRONTO: una sede del gruppo
    che il prodotto l'ha comprato mesi prima esce dal confronto, e la sua stella
    non deve accendere il divario degli altri due."""
    from services.routers.gruppo import _calcola_divari_catena

    _semina_sedi(sql)
    terza = "22222222-2222-4222-8222-222222222223"
    sql("INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, %s, '01234567891', true)", terza, UTENTE, "Lago")
    _riga(sql, SEDE1, "2026-07-20", "LIMONE", "MEFON", Decimal("17.00"), categoria="FRUTTA")
    _riga(sql, SEDE2, "2026-07-21", "LIMONE", "MEFON", Decimal("32.00"), categoria="FRUTTA")
    _riga(sql, terza, "2026-02-01", "LIMONE", "MEFON", Decimal("20.00"), categoria="FRUTTA")
    nomi = {**NOMI, terza: "Lago"}
    coppie = _coppie(sql, sedi=(SEDE1, SEDE2, terza))

    [d] = _calcola_divari_catena(coppie, nomi, 5.0, preferiti_per_sede={terza: {"LIMONE|MEFON"}})
    assert sorted(p["nome_pv"] for p in d["per_pv"]) == ["Centro", "Mare"]
    assert d["preferito"] is False
    [d] = _calcola_divari_catena(coppie, nomi, 5.0, preferiti_per_sede={SEDE2: {"LIMONE|MEFON"}})
    assert d["preferito"] is True


def test_l_anteprima_della_fattura_di_una_sede_del_gruppo(db_sql, sql, monkeypatch):
    """In catena la fattura e' di un'altra sede (l'anteprima del PV legge solo la
    sede della sessione). Righe in ordine, senza le cancellate; una sede fuori
    dal gruppo e' 404 anche se il file esiste."""
    from fastapi import HTTPException
    from services.routers import gruppo as G
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    sb = ClientSQL(db_sql)
    _riga(sql, SEDE1, "2026-07-20", "LIMONE", "MEFON", Decimal("17.00"), file="f-limone.xml")
    _riga(sql, SEDE1, "2026-07-20", "AGLIO", "MEFON", Decimal("4.50"), file="f-limone.xml")
    _riga(sql, SEDE1, "2026-07-20", "CANCELLATA", "MEFON", Decimal("1.00"), file="f-limone.xml", cancellata=True)
    _riga(sql, SEDE2, "2026-07-20", "SEGRETO", "MEFON", Decimal("9.00"), file="f-limone.xml")
    monkeypatch.setattr(G, "_resolve_gruppo", lambda auth: (sb, UTENTE, [], "G", {SEDE1: "Centro"}, [SEDE1]))

    esito = G.gruppo_prezzi_fattura(SEDE1, " f-limone.xml ", authorization="x")
    assert [r["descrizione"] for r in esito["righe"]] == ["LIMONE", "AGLIO"]
    assert esito["count"] == 2
    with pytest.raises(HTTPException) as e:
        G.gruppo_prezzi_fattura(SEDE2, "f-limone.xml", authorization="x")
    assert e.value.status_code == 404


def test_lo_storico_aperto_dalla_riga_ha_gli_stessi_acquisti_della_riga(db_sql, sql):
    """La riga porta le chiavi intere (`desc_key`, `forn_key`) e lo storico deve
    trovare ESATTAMENTE gli acquisti che la lista ha raggruppato. Col solo nome a
    video, tagliato a 60, il worker ripiegava sui primi 30 caratteri e mescolava
    prodotti diversi: 624 nomi lunghi su 1.058 (14/10/2026), soprattutto lotti di
    pesce che differiscono nelle ultime cifre."""
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync, _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    lotto = "BRANZINI 600/800 NIKO GRECIA ALLEVATO DICENTRARCHUS LABRAX ALLEVATE GRECIA (NIKO3103) "
    a, b = lotto + "147", lotto + "148"
    _riga(sql, SEDE1, "2026-03-01", a, "ITTICA NORD SRL", Decimal("10.00"), categoria="PESCE")
    # stesso prodotto: numero d'ordine in testa, fornitore scritto in minuscolo
    _riga(sql, SEDE1, "2026-04-01", "ORDER 41484 (122741) " + a, "ittica nord srl ", Decimal("11.00"), categoria="PESCE")
    _riga(sql, SEDE1, "2026-05-01", a, "ITTICA NORD SRL", Decimal("13.00"), categoria="PESCE")
    # un altro lotto: stessi primi 60 caratteri, prodotto diverso
    _riga(sql, SEDE1, "2026-03-15", b, "ITTICA NORD SRL", Decimal("30.00"), categoria="PESCE")
    _riga(sql, SEDE1, "2026-04-15", b, "ITTICA NORD SRL", Decimal("40.00"), categoria="PESCE")

    riga = next(v for v in _calcola_variazioni_prezzi_sync(_righe_pv(sql, SEDE1), 5.0) if v["storico_valori"][0] == 10.0)
    assert riga["prodotto"] == a[:60] == b[:60], "il caso deve avere i due lotti indistinguibili a video"

    storico = _storico_prodotto_sede(
        ClientSQL(db_sql), SEDE1, riga["prodotto"], riga["fornitore"], DA, A,
        desc_key=riga["desc_key"], forn_key=riga["forn_key"],
    )
    assert [p.prezzo_unitario for p in storico.punti] == riga["storico_valori"] == [10.0, 11.0, 13.0]
    assert storico.prezzo_medio == pytest.approx(riga["media"])


def test_lo_storico_per_chiave_non_si_tira_dietro_un_altro_fornitore(db_sql, sql):
    from services.routers.prezzi import _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-01", "LATTE INTERO", "ADC", Decimal("1.00"))
    _riga(sql, SEDE1, "2026-03-02", "LATTE INTERO", "ADC ITALIA", Decimal("9.00"))
    _riga(sql, SEDE1, "2026-03-03", "LATTE INTERO 1L", "ADC", Decimal("5.00"))

    storico = _storico_prodotto_sede(ClientSQL(db_sql), SEDE1, "LATTE INTERO", "ADC", desc_key="LATTE INTERO", forn_key="ADC")
    assert [p.prezzo_unitario for p in storico.punti] == [1.00]


def test_lo_storico_per_chiave_ha_le_stesse_esclusioni_della_riga(db_sql, sql):
    """Una nota di credito a prezzo positivo e una riga in spesa generale con lo
    stesso nome non entrano nella riga: non devono entrare nemmeno nel suo storico."""
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync, _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-01", "MOZZARELLA", "ADC", Decimal("5.00"))
    _riga(sql, SEDE1, "2026-04-01", "MOZZARELLA", "ADC", Decimal("6.00"))
    _riga(sql, SEDE1, "2026-04-10", "MOZZARELLA", "ADC", Decimal("2.00"), tipo="TD04")
    _riga(sql, SEDE1, "2026-04-20", "MOZZARELLA", "ADC", Decimal("9.00"), categoria="MANUTENZIONE E ATTREZZATURE")

    riga = _calcola_variazioni_prezzi_sync(_righe_pv(sql, SEDE1), 5.0)[0]
    storico = _storico_prodotto_sede(
        ClientSQL(db_sql), SEDE1, riga["prodotto"], riga["fornitore"], DA, A,
        desc_key=riga["desc_key"], forn_key=riga["forn_key"],
    )
    assert [p.prezzo_unitario for p in storico.punti] == riga["storico_valori"] == [5.0, 6.0]


def test_lo_storico_si_apre_anche_col_numero_d_ordine_incollato(db_sql, sql):
    """«NORVEGIA ORDER 222449/222450» diventa la chiave «NORVEGIA/222450»: la
    parola piu' lunga della chiave non sta nella descrizione grezza (caso reale
    sul live, 14/10/2026)."""
    from services.routers.prezzi import _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL
    from utils.voci_prezzo import chiave_prodotto

    _semina_sedi(sql)
    grezza = "SALMONE NORVEGIA ORDER 222449/222450"
    chiave = chiave_prodotto(grezza)
    assert "NORVEGIA/222450" in chiave and "NORVEGIA/222450" not in grezza
    _riga(sql, SEDE1, "2026-03-01", grezza, "ITTICA", Decimal("10.00"), categoria="PESCE")
    _riga(sql, SEDE1, "2026-04-01", grezza, "ITTICA", Decimal("12.00"), categoria="PESCE")

    storico = _storico_prodotto_sede(ClientSQL(db_sql), SEDE1, chiave, "ITTICA", desc_key=chiave, forn_key="ITTICA")
    assert [p.prezzo_unitario for p in storico.punti] == [10.00, 12.00]


def test_un_acquisto_e_una_fattura_nel_pv_in_catena_e_nello_storico(db_sql, sql):
    """ORTOFRUTTA 2,88 -> 3,83 -> 2,88 tutto nella fattura 39/FA (screenshot di
    Mattia del 14/10/2026): era una variazione dentro la stessa fattura. Ora la
    39/FA e' UN acquisto a prezzo ponderato, uguale nelle tre strade; un'unita'
    diversa nella stessa fattura resta un acquisto a se'."""
    from services.routers.gruppo import _variazioni_catena
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync, _storico_prodotto_sede
    from tests.helpers_supabase_sql import ClientSQL

    _semina_sedi(sql)
    forn = "GIANOLI S.A.S."
    _riga(sql, SEDE1, "2026-03-04", "ORTOFRUTTA", forn, Decimal("2.50"), quantita=2, file="38.xml", categoria="VERDURE")
    _riga(sql, SEDE1, "2026-04-04", "ORTOFRUTTA", forn, Decimal("2.88"), quantita=2, file="39.xml", categoria="VERDURE")
    _riga(sql, SEDE1, "2026-04-04", "ORTOFRUTTA", forn, Decimal("3.83"), quantita=4, file="39.xml", categoria="VERDURE")
    _riga(sql, SEDE1, "2026-04-04", "ORTOFRUTTA", forn, Decimal("2.88"), quantita=2, file="39.xml", categoria="VERDURE")
    _riga(sql, SEDE1, "2026-04-04", "ORTOFRUTTA", forn, Decimal("40.00"), quantita=1, file="39.xml", categoria="VERDURE", unita="CT")
    ponderato = (2.88 * 2 + 3.83 * 4 + 2.88 * 2) / 8

    pv = {v["n_fattura"]: v for v in _calcola_variazioni_prezzi_sync(_righe_pv(sql, SEDE1), 0.0)}
    catena = {v["n_fattura"]: v for v in _variazioni_catena(_coppie(sql), NOMI, 0.0)}
    # Il CT della 39 resta un acquisto a se'. A parita' di data e file lo
    # spareggio e' l'unita' in ordine alfabetico: CT prima di PZ, quindi
    # l'ultimo acquisto e' la 39 in PZ e il penultimo il CT.
    for strada in (pv, catena):
        v = strada["39.xml"]
        assert v["storico_valori"] == pytest.approx([2.50, 40.0, ponderato])
        assert v["penultimo"] == pytest.approx(40.0)
        assert v["ultimo"] == pytest.approx(round(ponderato, 4))
    assert pv["39.xml"]["media"] == pytest.approx(catena["39.xml"]["media"])
    assert pv["39.xml"]["media"] == pytest.approx(round((2.50 + ponderato + 40.0) / 3, 4)), "ogni fattura pesa uguale"

    v = pv["39.xml"]
    storico = _storico_prodotto_sede(
        ClientSQL(db_sql), SEDE1, v["prodotto"], v["fornitore"], DA, A, desc_key=v["desc_key"], forn_key=v["forn_key"],
    )
    assert [p.prezzo_unitario for p in storico.punti] == pytest.approx([2.50, 40.0, round(ponderato, 4)], abs=1e-4)
    assert [p.quantita for p in storico.punti] == [2, 1, 8]
    assert storico.prezzo_medio == pytest.approx(v["media"])


def test_i_casi_limite_della_fusione_sono_uguali_nel_pv_e_in_catena(sql):
    """I casi che il seme casuale non garantisce, ognuno uguale nelle due strade:
    un calo di esattamente il 5% su una riga per fattura (prima il float di
    pandas lo portava a 4,99999% e spariva dal PV), due fatture nello stesso
    giorno (spareggio sul nome del file), righe senza file (acquisti a se'),
    quantita' a zero (media semplice)."""
    from services.routers.gruppo import _variazioni_catena
    from services.routers.prezzi import _calcola_variazioni_prezzi_sync

    _semina_sedi(sql)
    _riga(sql, SEDE1, "2026-03-06", "PASTO DI GRANO", "H.D. ITALIA", Decimal("1.80"), quantita=40, file="a.xml")
    _riga(sql, SEDE1, "2026-04-10", "PASTO DI GRANO", "H.D. ITALIA", Decimal("1.71"), quantita=40, file="b.xml")
    # stesso giorno: «B.xml» viene prima di «a.xml» (codepoint), l'ultimo e' a.xml
    _riga(sql, SEDE1, "2026-05-01", "LATTE", "ADC", Decimal("1.00"), file="z.xml")
    _riga(sql, SEDE1, "2026-05-02", "LATTE", "ADC", Decimal("2.00"), file="a.xml")
    _riga(sql, SEDE1, "2026-05-02", "LATTE", "ADC", Decimal("3.00"), file="B.xml")
    # senza file: due righe, due acquisti
    _riga(sql, SEDE1, "2026-05-03", "PANE", "ADC", Decimal("1.00"), senza_file=True)
    _riga(sql, SEDE1, "2026-05-03", "PANE", "ADC", Decimal("1.50"), senza_file=True)
    # quantita' a zero: media semplice (4,00)
    _riga(sql, SEDE1, "2026-05-04", "OLIO", "ADC", Decimal("2.00"), file="o1.xml")
    _riga(sql, SEDE1, "2026-05-05", "OLIO", "ADC", Decimal("3.00"), quantita=0, file="o2.xml")
    _riga(sql, SEDE1, "2026-05-05", "OLIO", "ADC", Decimal("5.00"), quantita=0, file="o2.xml")
    # decimali periodici: (2,88x2 + 3,83x4) / 6 = 3,51333... -> 6 decimali in tutte e due
    _riga(sql, SEDE1, "2026-05-06", "BURRO", "ADC", Decimal("1.00"), file="u1.xml")
    _riga(sql, SEDE1, "2026-05-07", "BURRO", "ADC", Decimal("2.88"), quantita=2, file="u2.xml")
    _riga(sql, SEDE1, "2026-05-07", "BURRO", "ADC", Decimal("3.83"), quantita=4, file="u2.xml")
    # uno storno nella stessa fattura: pesano solo le quantita' positive
    _riga(sql, SEDE1, "2026-05-08", "ACETO", "ADC", Decimal("2.00"), file="c1.xml")
    _riga(sql, SEDE1, "2026-05-09", "ACETO", "ADC", Decimal("1.00"), quantita=3, file="c2.xml")
    _riga(sql, SEDE1, "2026-05-09", "ACETO", "ADC", Decimal("5.00"), quantita=-2, file="c2.xml")

    pv = {v["prodotto"]: v for v in _calcola_variazioni_prezzi_sync(_righe_pv(sql, SEDE1), 5.0)}
    catena = {v["prodotto"]: v for v in _variazioni_catena(_coppie(sql), NOMI, 5.0)}
    assert set(pv) == set(catena) == {"PASTO DI GRANO", "LATTE", "PANE", "OLIO", "BURRO", "ACETO"}
    # Uguali al bit, non solo a meno di una tolleranza: e' l'arrotondamento a 6
    # decimali dalle due parti a renderlo possibile.
    for prodotto in pv:
        assert pv[prodotto]["storico_valori"] == catena[prodotto]["storico_valori"], prodotto
    for strada in (pv, catena):
        assert strada["BURRO"]["storico_valori"] == [1.0, round((2.88 * 2 + 3.83 * 4) / 6, 6)]
        assert strada["ACETO"]["storico_valori"] == [2.0, 1.0]
    for strada in (pv, catena):
        assert strada["PASTO DI GRANO"]["aumento_perc"] == -5.0
        assert strada["LATTE"]["storico_valori"] == [1.0, 3.0, 2.0]
        assert strada["LATTE"]["n_fattura"] == "a.xml"
        assert strada["PANE"]["storico_valori"] == [1.0, 1.5]
        assert strada["OLIO"]["storico_valori"] == [2.0, 4.0]


def test_la_rpc_ordina_il_testo_per_codepoint_come_pandas():
    """Il Postgres dei test nasce con LANG=C.UTF-8, quindi l'ordine del testo e'
    gia' quello dei codepoint e togliere `COLLATE "C"` non farebbe fallire
    nessun test eseguito; il live e' en_US.UTF-8, dove «G-1» e «f-1» si
    scambiano. Presidio sul TESTO della migration (unico possibile qui): lo
    spareggio, la categoria e i nomi devono dichiarare la collation."""
    from pathlib import Path

    testo = sorted((Path(__file__).resolve().parents[1] / "supabase/migrations").glob("*_gruppo_prezzi_catena*.sql"))[-1].read_text()
    corpo = testo.split("AS $function$")[1]
    for frammento in (
        'd.file_key COLLATE "C" DESC',
        'd.unita_key COLLATE "C" DESC',
        'max(r.categoria COLLATE "C")',
        'mode() WITHIN GROUP (ORDER BY r.descrizione COLLATE "C")',
        'mode() WITHIN GROUP (ORDER BY r.fornitore COLLATE "C")',
    ):
        assert frammento in corpo, frammento
