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
   Le date sono distinte dentro ogni sede: a parita' di giorno pandas non
   garantisce quale riga sia l'ultima, la RPC si'.
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
          tipo="TD01", file=None, cancellata=False, oscurata=False):
    sql(
        "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, data_documento, "
        "fornitore, descrizione, categoria, quantita, prezzo_unitario, totale_riga, tipo_documento, "
        "deleted_at, oscurata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        UTENTE, sede, file or f"f-{sede[-1]}-{giorno}.xml", next(_NUMERO_RIGA), giorno, fornitore,
        descrizione, categoria,
        quantita, prezzo, prezzo, tipo, "2026-06-01T00:00:00+00:00" if cancellata else None, oscurata,
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
    cols = "descrizione,categoria,fornitore,prezzo_unitario,quantita,totale_riga,data_documento,file_origine,tipo_documento"
    righe = sql(
        f"SELECT {cols} FROM public.fatture WHERE ristorante_id = %s AND deleted_at IS NULL "
        "AND NOT oscurata AND data_documento BETWEEN %s AND %s ORDER BY data_documento",
        sede, DA, A,
    )
    return _json([dict(zip(cols.split(","), r)) for r in righe])


_CAMPI = ("prodotto", "categoria", "fornitore", "storico_valori", "media", "penultimo", "ultimo",
          "aumento_perc", "data", "trend", "impatto_stimato", "delta_euro")


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
    for sede in (SEDE1, SEDE2):
        giorni = rnd.sample(range(0, 360), 220)
        for i, g in enumerate(sorted(giorni)):
            giorno = (date(2026, 1, 1) + timedelta(days=g)).isoformat()
            caso = rnd.random()
            _riga(
                sql, sede, giorno, rnd.choice(prodotti), rnd.choice(fornitori),
                rnd.choice([Decimal("0"), Decimal(f"{rnd.uniform(1, 30):.2f}"), Decimal(f"{rnd.uniform(1, 30):.2f}")]),
                categoria=rnd.choice(["LATTICINI", "FRUTTA", "BEVANDE", "UTENZE E LOCALI", "MATERIALE DI CONSUMO"]),
                quantita=rnd.choice([None, 1, Decimal("2.5"), 10]),
                tipo=rnd.choice(["TD01", "TD01", "TD01", "TD04", "nc", None]),
                file=f"f-{sede[-1]}-{i % 40}.xml",
                cancellata=caso < 0.05,
                oscurata=0.05 <= caso < 0.10,
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
