"""Le funzioni SQL che calcolano i numeri visti dal cliente in pagina.

Perche' questo file esiste
==========================
Sul DB live vivono 75 funzioni `public`. I test SQL esistenti ne ESEGUONO 12 per
nome (piu' i trigger): tutte le altre non sono mai state eseguite da un test.
Delle 52 restanti, 35 sono trigger di orario e job di pulizia che non muovono
numeri. Le 17 che restano sono vive — ogni nome ha almeno un chiamante in
`services/`, `worker/` o `apps/web/src/` — e calcolano o registrano numeri.

Questo file copre le **8 di Livello 1**: quelle i cui numeri finiscono davanti
al cliente. Le 9 di Livello 2 (`admin_*`, `get_ai_costs_*`, `increment_ai_cost`,
`track_ai_usage_event`) sbagliate darebbero un numero storto a chi gestisce il
prodotto, non a chi lo usa: restano scoperte, dichiarate nel verbale.

Attenzione: alcune di queste funzioni AVEVANO gia' dei test Python
(`test_gruppo_tag_note_credito.py`, `test_gruppo_spesa_pivot_quote.py`,
`test_gruppo_completezza_override.py`, `test_da_classificare_sql_allineato.py`).
Nessuno di quelli ESEGUE la funzione: mockano il client Supabase, o leggono il
FILE della migration. Difendono cose vere, ma un errore dentro il corpo SQL
passerebbe intatto sotto tutti quanti.

Come si prova una funzione qui
==============================
- Si seminano righe vere (soft-deleted comprese) e si asserisce sul NUMERO.
- Mai asserire sul testo del corpo (`pg_get_functiondef`): un mutante che
  cambia il comportamento lascia il testo intatto e sopravvive.
- Mai su un aggregato solo: la somma resta giusta se due componenti sbagliate
  si annullano. Si asseriscono le parti.
- Prima dell'assert vero, si verifica che la semina sia avvenuta: un test che
  non trova righe passa senza provare niente.

Le 8 funzioni e la loro firma sul live (verificata su `pg_proc` l'08/09/2026):
  articoli_da_fatture(uuid, uuid, text[])            -> descrizione, prezzo, um, data
  gruppo_spesa_pivot(uuid[], text, date, date, bool) -> ristorante_id, dim_val, totale
  gruppo_tag_trend(uuid[], text[], date, date)       -> anno, mese, spesa
  gruppo_tag_fornitori(uuid[], text[], date, date)   -> fornitore, spesa, n_righe
  gruppo_tag_descrizioni(uuid[], text, int, bool)    -> descrizione, key, n, spesa
  gruppo_salute_componenti(uuid[], timestamptz, int, int)
  chat_top_categoria_fornitore(uuid, uuid, int, int) -> tipo, voce, spesa
  chat_usage_check_and_log(uuid, uuid, int, bool)    -> integer
"""
from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.sql

UTENTE = "44444444-4444-4444-8444-444444444444"
SEDE = "55555555-5555-4555-8555-555555555555"
SEDE_B = "66666666-6666-4666-8666-666666666666"

DA_CLASSIFICARE = "Da Classificare"


def _semina_utente_e_sedi(db_sql, sedi=(SEDE,)):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'pagina@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        for numero, sede in enumerate(sedi, start=1):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
                "partita_iva, attivo) VALUES (%s, %s, %s, %s, true)",
                (sede, UTENTE, f"Sede {numero}", f"9876543210{numero}"),
            )
    return UTENTE


def _riga(db_sql, *, sede=SEDE, descrizione="SALMONE 5-6", fornitore="ADC SRL",
          categoria="PESCE", totale=Decimal("100.00"), prezzo=None,
          data_documento="2026-03-10", data_competenza=None, deleted=False,
          needs_review=False, fiducia=None, unita_misura="KG",
          numero_riga=None, file="prova.xml", utente=UTENTE, created_at=None):
    """Una riga di `fatture`. I default descrivono il caso normale: riga viva,
    classificata, dentro il periodo. Ogni test cambia solo cio' che prova."""
    _riga.contatore = getattr(_riga, "contatore", 0) + 1
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
            "numero_riga, data_documento, data_competenza, fornitore, descrizione, "
            "categoria, quantita, prezzo_unitario, totale_riga, unita_misura, "
            "needs_review, categoria_fiducia, deleted_at, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, "
            "COALESCE(%s, now())) RETURNING id",
            (utente, sede, file,
             numero_riga if numero_riga is not None else _riga.contatore,
             data_documento, data_competenza, fornitore, descrizione, categoria,
             totale if prezzo is None else prezzo, totale, unita_misura,
             needs_review, fiducia,
             "2026-01-01" if deleted else None, created_at),
        )
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# gruppo_spesa_pivot — il pivot di spesa del gruppo (sede x categoria/fornitore)
#
# Alimenta la pagina Catena. Filtra `Da Classificare` (regola di dominio #1),
# il soft delete, e `totale_riga > 0`: le note di credito NON entrano.
# ---------------------------------------------------------------------------

def _pivot(sql, *, sedi=(SEDE,), dimensione="categoria", da="2026-01-01",
           a="2026-12-31", escludi=None):
    if escludi is None:
        return sql(
            "SELECT ristorante_id, dim_val, totale FROM public.gruppo_spesa_pivot("
            "%s, %s, %s, %s) ORDER BY dim_val",
            list(sedi), dimensione, da, a,
        )
    return sql(
        "SELECT ristorante_id, dim_val, totale FROM public.gruppo_spesa_pivot("
        "%s, %s, %s, %s, %s) ORDER BY dim_val",
        list(sedi), dimensione, da, a, escludi,
    )


def test_pivot_somma_per_categoria_e_separa_le_sedi(db_sql, sql):
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga(db_sql, sede=SEDE, categoria="PESCE", totale=Decimal("100.00"))
    _riga(db_sql, sede=SEDE, categoria="PESCE", totale=Decimal("50.00"))
    _riga(db_sql, sede=SEDE, categoria="CARNE", totale=Decimal("30.00"))
    _riga(db_sql, sede=SEDE_B, categoria="PESCE", totale=Decimal("7.00"))

    righe = _pivot(sql, sedi=(SEDE, SEDE_B))
    assert righe, "nessuna riga seminata: il test non prova nulla"
    # Le COMPONENTI, non il totale: due errori opposti lascerebbero la somma giusta.
    per_chiave = {(str(r[0]), r[1]): r[2] for r in righe}
    assert per_chiave[(SEDE, "PESCE")] == Decimal("150.00")
    assert per_chiave[(SEDE, "CARNE")] == Decimal("30.00")
    assert per_chiave[(SEDE_B, "PESCE")] == Decimal("7.00")


def test_pivot_esclude_da_classificare(db_sql, sql):
    """Regola di dominio #1: le righe non classificate non entrano nei margini."""
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, categoria="PESCE", totale=Decimal("100.00"))
    _riga(db_sql, categoria=DA_CLASSIFICARE, totale=Decimal("999.00"))

    valori = {r[1]: r[2] for r in _pivot(sql)}
    assert valori.get("PESCE") == Decimal("100.00")
    assert DA_CLASSIFICARE not in valori, "una riga Da Classificare e' entrata nel pivot"


def test_pivot_esclude_le_righe_cancellate(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, categoria="PESCE", totale=Decimal("100.00"))
    _riga(db_sql, categoria="PESCE", totale=Decimal("500.00"), deleted=True)

    valori = {r[1]: r[2] for r in _pivot(sql)}
    assert valori["PESCE"] == Decimal("100.00"), "una riga soft-deleted e' entrata"


def test_pivot_ignora_le_note_di_credito(db_sql, sql):
    """`totale_riga > 0` e' nel corpo: una nota di credito NON scala la spesa.

    Non e' un bug per definizione — sul percorso catena i tag hanno il
    comportamento opposto (vedi gruppo_tag_*) — ma e' una divergenza reale fra
    due numeri della stessa pagina, e finche' resta va documentata da un test
    che la misura, non dedotta dal codice.
    """
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, categoria="PESCE", totale=Decimal("100.00"))
    _riga(db_sql, categoria="PESCE", totale=Decimal("-30.00"))

    valori = {r[1]: r[2] for r in _pivot(sql)}
    assert valori["PESCE"] == Decimal("100.00")


def test_pivot_usa_data_competenza_quando_c_e(db_sql, sql):
    """`COALESCE(data_competenza, data_documento)`: la competenza vince."""
    _semina_utente_e_sedi(db_sql)
    # documento a marzo, competenza a gennaio: dentro una finestra di gennaio
    _riga(db_sql, categoria="PESCE", totale=Decimal("100.00"),
          data_documento="2026-03-10", data_competenza="2026-01-15")
    _riga(db_sql, categoria="CARNE", totale=Decimal("40.00"),
          data_documento="2026-03-10")

    valori = {r[1]: r[2] for r in _pivot(sql, da="2026-01-01", a="2026-01-31")}
    assert valori.get("PESCE") == Decimal("100.00"), "la data_competenza non ha vinto"
    assert "CARNE" not in valori, "una riga fuori finestra e' entrata"


def test_pivot_per_fornitore_raggruppa_sull_altra_dimensione(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, fornitore="ADC SRL", totale=Decimal("100.00"))
    _riga(db_sql, fornitore="ITTICA SPA", totale=Decimal("25.00"))

    valori = {r[1]: r[2] for r in _pivot(sql, dimensione="fornitore")}
    assert valori == {"ADC SRL": Decimal("100.00"), "ITTICA SPA": Decimal("25.00")}


def test_pivot_fornitore_vuoto_diventa_nd(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, fornitore="", totale=Decimal("12.00"))

    valori = {r[1]: r[2] for r in _pivot(sql, dimensione="fornitore")}
    assert valori == {"N/D": Decimal("12.00")}


def test_pivot_flag_da_verificare_esclude_solo_se_acceso(db_sql, sql):
    """Il flag e' SPENTO in produzione (ESCLUDI_DA_VERIFICARE_DAI_MARGINI=False,
    `config/constants.py`), quindi il ramo vivo e' il default: entrambi provati."""
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, categoria="PESCE", totale=Decimal("100.00"))
    _riga(db_sql, categoria="PESCE", totale=Decimal("60.00"), fiducia="da_verificare")

    spento = {r[1]: r[2] for r in _pivot(sql, escludi=False)}
    acceso = {r[1]: r[2] for r in _pivot(sql, escludi=True)}
    assert spento["PESCE"] == Decimal("160.00")
    assert acceso["PESCE"] == Decimal("100.00")


# ---------------------------------------------------------------------------
# gruppo_tag_descrizioni / gruppo_tag_fornitori / gruppo_tag_trend
#
# Le tre RPC della pagina Tag di catena. La chiave di raggruppamento e'
# `upper(regexp_replace(btrim(descrizione), '\\s+', ' ', 'g'))`: due scritture
# della stessa cosa con spazi diversi devono cadere insieme.
# ---------------------------------------------------------------------------

def _descrizioni(sql, *, sedi=(SEDE,), q=None, limite=500, escludi=None):
    if escludi is None:
        return sql(
            "SELECT descrizione, descrizione_key, n, spesa "
            "FROM public.gruppo_tag_descrizioni(%s, %s, %s) ORDER BY descrizione_key",
            list(sedi), q, limite,
        )
    return sql(
        "SELECT descrizione, descrizione_key, n, spesa "
        "FROM public.gruppo_tag_descrizioni(%s, %s, %s, %s) ORDER BY descrizione_key",
        list(sedi), q, limite, escludi,
    )


def _fornitori(sql, chiavi, *, sedi=(SEDE,), da="2026-01-01", a="2026-12-31"):
    return sql(
        "SELECT fornitore, spesa, n_righe FROM public.gruppo_tag_fornitori("
        "%s, %s, %s, %s) ORDER BY fornitore",
        list(sedi), list(chiavi), da, a,
    )


def _trend(sql, chiavi, *, sedi=(SEDE,), da="2026-01-01", a="2026-12-31"):
    return sql(
        "SELECT anno, mese, spesa FROM public.gruppo_tag_trend(%s, %s, %s, %s)",
        list(sedi), list(chiavi), da, a,
    )


def test_descrizioni_normalizza_spazi_e_maiuscole_nella_chiave(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="Salmone  5-6", totale=Decimal("10.00"))
    _riga(db_sql, descrizione="  salmone 5-6  ", totale=Decimal("15.00"))

    righe = _descrizioni(sql)
    assert len(righe) == 1, f"le due scritture non sono cadute insieme: {righe}"
    _, chiave, n, spesa = righe[0]
    assert chiave == "SALMONE 5-6"
    assert n == 2
    assert spesa == Decimal("25.00")


def test_descrizioni_esclude_da_classificare_e_cancellate(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("10.00"))
    _riga(db_sql, descrizione="TONNO", categoria=DA_CLASSIFICARE, totale=Decimal("99.00"))
    _riga(db_sql, descrizione="BRANZINO", totale=Decimal("99.00"), deleted=True)

    chiavi = {r[1] for r in _descrizioni(sql)}
    assert chiavi == {"SALMONE 5-6"}


def test_descrizioni_filtra_su_q_e_rispetta_il_limite(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("10.00"))
    _riga(db_sql, descrizione="TONNO PINNA GIALLA", totale=Decimal("20.00"))

    assert {r[1] for r in _descrizioni(sql, q="salmo")} == {"SALMONE 5-6"}
    assert {r[1] for r in _descrizioni(sql, q="  ")} == {"SALMONE 5-6", "TONNO PINNA GIALLA"}
    # ordine per spesa DESC: col limite 1 resta il TONNO, che spende di piu'
    assert [r[1] for r in _descrizioni(sql, limite=1)] == ["TONNO PINNA GIALLA"]


def test_fornitori_ripartisce_la_spesa_del_tag(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", fornitore="ADC SRL", totale=Decimal("100.00"))
    _riga(db_sql, descrizione="SALMONE 5-6", fornitore="ADC SRL", totale=Decimal("20.00"))
    _riga(db_sql, descrizione="SALMONE 5-6", fornitore="ITTICA SPA", totale=Decimal("30.00"))
    _riga(db_sql, descrizione="TONNO", fornitore="ADC SRL", totale=Decimal("500.00"))

    righe = _fornitori(sql, ["SALMONE 5-6"])
    assert righe, "nessuna riga: il test non prova nulla"
    per_fornitore = {r[0]: (r[1], r[2]) for r in righe}
    assert per_fornitore["ADC SRL"] == (Decimal("120.00"), 2)
    assert per_fornitore["ITTICA SPA"] == (Decimal("30.00"), 1)
    assert "TONNO" not in str(per_fornitore)


def test_fornitori_scala_le_note_di_credito(db_sql, sql):
    """Guardia del 27/8: queste RPC calcolano SPESA, non prezzo — una nota di
    credito deve ABBASSARE il totale. Il test la esegue davvero: quello
    esistente (`test_gruppo_tag_note_credito.py`) legge il file di migration."""
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", fornitore="ADC SRL", totale=Decimal("100.00"))
    _riga(db_sql, descrizione="SALMONE 5-6", fornitore="ADC SRL", totale=Decimal("-30.00"))

    per_fornitore = {r[0]: r[1] for r in _fornitori(sql, ["SALMONE 5-6"])}
    assert per_fornitore["ADC SRL"] == Decimal("70.00"), "la nota di credito non e' stata scalata"


def test_fornitori_vuoto_diventa_lineetta(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", fornitore="   ", totale=Decimal("10.00"))

    assert [r[0] for r in _fornitori(sql, ["SALMONE 5-6"])] == ["—"]


def test_trend_raggruppa_per_anno_e_mese(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("10.00"), data_documento="2026-01-05")
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("15.00"), data_documento="2026-01-20")
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("40.00"), data_documento="2026-02-03")

    righe = _trend(sql, ["SALMONE 5-6"])
    assert {(r[0], r[1]): r[2] for r in righe} == {
        (2026, 1): Decimal("25.00"),
        (2026, 2): Decimal("40.00"),
    }


def test_trend_scala_le_note_di_credito(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("100.00"), data_documento="2026-01-05")
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("-30.00"), data_documento="2026-01-06")

    assert [r[2] for r in _trend(sql, ["SALMONE 5-6"])] == [Decimal("70.00")]


def test_trend_e_fornitori_escludono_le_cancellate(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("10.00"), data_documento="2026-01-05")
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("900.00"),
          data_documento="2026-01-05", deleted=True)

    assert [r[2] for r in _trend(sql, ["SALMONE 5-6"])] == [Decimal("10.00")]
    assert [r[1] for r in _fornitori(sql, ["SALMONE 5-6"])] == [Decimal("10.00")]


def test_le_tre_rpc_del_tag_non_concordano_su_da_classificare(db_sql, sql):
    """Divergenza REALE fra tre numeri della stessa pagina, misurata qui.

    `gruppo_tag_descrizioni` esclude `Da Classificare` (regola di dominio #1),
    ma `gruppo_tag_fornitori` e `gruppo_tag_trend` NO: una descrizione non
    classificata non compare nell'elenco dei tag, ma se il tag esiste per altre
    righe la sua spesa entra nel dettaglio fornitori e nel grafico.

    Il test NON dichiara chi ha ragione — e' una decisione di prodotto, non mia.
    Documenta il comportamento di oggi, cosi' che cambiarlo sia una scelta
    esplicita e non un effetto collaterale.
    """
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("100.00"), data_documento="2026-01-05")
    _riga(db_sql, descrizione="SALMONE 5-6", totale=Decimal("50.00"),
          categoria=DA_CLASSIFICARE, data_documento="2026-01-05")

    elenco = {r[1]: r[3] for r in _descrizioni(sql)}
    assert elenco["SALMONE 5-6"] == Decimal("100.00"), "descrizioni non esclude Da Classificare"

    assert [r[1] for r in _fornitori(sql, ["SALMONE 5-6"])] == [Decimal("150.00")]
    assert [r[2] for r in _trend(sql, ["SALMONE 5-6"])] == [Decimal("150.00")]


# ---------------------------------------------------------------------------
# gruppo_salute_componenti — il semaforo di completezza dati per sede
#
# Alimenta il MOL di gruppo: se una sede risulta "senza fatturato", il MOL della
# catena viene nascosto in pagina. Ritorna una riga PER OGNI sede chiesta
# (LEFT JOIN su unnest), anche per quelle senza dati: e' il punto che un test
# sui soli dati presenti non vedrebbe.
# ---------------------------------------------------------------------------

def _margini_mensili(db_sql, *, sede=SEDE, anno=2026, mese=3, iva10=0, iva22=0,
                     noiva=0, dipendenti=0, extra=0):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, mese, "
            "fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, costo_dipendenti, "
            "costo_personale_extra) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (UTENTE, sede, anno, mese, iva10, iva22, noiva, dipendenti, extra),
        )


def _salute(sql, *, sedi=(SEDE,), inizio="2026-01-01", anno=2026, mese=3):
    return sql(
        "SELECT ristorante_id, n_fatture, n_needs_review, netto, personale "
        "FROM public.gruppo_salute_componenti(%s, %s, %s, %s)",
        list(sedi), inizio, anno, mese,
    )


def test_salute_conta_fatture_e_righe_da_rivedere(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, created_at="2026-02-01")
    _riga(db_sql, created_at="2026-02-01", needs_review=True)
    _riga(db_sql, created_at="2026-02-01", needs_review=True)

    righe = _salute(sql)
    assert len(righe) == 1
    _, n_fatture, n_review, _, _ = righe[0]
    # Le due componenti separate: un errore che le confondesse (n_review == n)
    # passerebbe se ne asserissi una sola.
    assert n_fatture == 3
    assert n_review == 2


def test_salute_somma_i_ricavi_e_il_personale_del_mese(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _margini_mensili(db_sql, iva10=1000, iva22=200, noiva=50, dipendenti=300, extra=25)
    _margini_mensili(db_sql, anno=2026, mese=4, iva10=999999)

    _, _, _, netto, personale = _salute(sql, anno=2026, mese=3)[0]
    assert netto == Decimal("1250"), "il netto non e' la somma delle tre voci"
    assert personale == Decimal("325"), "il personale non somma dipendenti + extra"


def test_salute_ritorna_una_riga_anche_per_la_sede_senza_dati(db_sql, sql):
    """Il LEFT JOIN su unnest: una sede muta deve comparire con degli zeri, non
    sparire. Se sparisse, il chiamante non saprebbe distinguere «sede senza
    dati» da «sede non chiesta»."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga(db_sql, sede=SEDE, created_at="2026-02-01")

    per_sede = {str(r[0]): r[1:] for r in _salute(sql, sedi=(SEDE, SEDE_B))}
    assert set(per_sede) == {SEDE, SEDE_B}
    assert per_sede[SEDE_B] == (0, 0, Decimal("0"), Decimal("0"))


def test_salute_esclude_le_cancellate_e_le_fatture_troppo_vecchie(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, created_at="2026-02-01")
    _riga(db_sql, created_at="2026-02-01", deleted=True)
    _riga(db_sql, created_at="2025-06-01")   # prima di p_inizio

    assert _salute(sql, inizio="2026-01-01")[0][1] == 1


# ---------------------------------------------------------------------------
# articoli_da_fatture — gli articoli e i prezzi da cui parte il foodcost
#
# `DISTINCT ON (descrizione)` con `ORDER BY descrizione, data_documento DESC`:
# di ogni articolo resta la riga PIU' RECENTE. E' il prezzo che il cliente
# vede nella scheda ricetta.
# ---------------------------------------------------------------------------

def _articoli(sql, *, utente=UTENTE, sede=SEDE, escluse=("Da Classificare",)):
    return sql(
        "SELECT descrizione, prezzo_unitario, unita_misura, data_documento "
        "FROM public.articoli_da_fatture(%s, %s, %s) ORDER BY descrizione",
        utente, sede, list(escluse),
    )


def test_articoli_tiene_il_prezzo_piu_recente_di_ogni_descrizione(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6", prezzo=Decimal("12.00"),
          totale=Decimal("12.00"), data_documento="2026-01-10")
    _riga(db_sql, descrizione="SALMONE 5-6", prezzo=Decimal("18.50"),
          totale=Decimal("18.50"), data_documento="2026-03-10")
    _riga(db_sql, descrizione="TONNO", prezzo=Decimal("30.00"),
          totale=Decimal("30.00"), data_documento="2026-02-01")

    righe = _articoli(sql)
    assert len(righe) == 2, f"DISTINCT ON non ha compattato: {righe}"
    per_descrizione = {r[0]: r[1] for r in righe}
    assert per_descrizione["SALMONE 5-6"] == Decimal("18.50"), "ha tenuto il prezzo vecchio"
    assert per_descrizione["TONNO"] == Decimal("30.00")


def test_articoli_esclude_le_categorie_chieste_e_le_cancellate(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6")
    _riga(db_sql, descrizione="COMMISSIONI", categoria="SERVIZI E CONSULENZE")
    _riga(db_sql, descrizione="BRANZINO", deleted=True)

    assert {r[0] for r in _articoli(sql, escluse=("SERVIZI E CONSULENZE",))} == {"SALMONE 5-6"}


def test_articoli_scarta_le_descrizioni_vuote(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, descrizione="SALMONE 5-6")
    _riga(db_sql, descrizione="   ")

    assert {r[0] for r in _articoli(sql)} == {"SALMONE 5-6"}


def test_articoli_isola_la_sede_e_l_utente(db_sql, sql):
    """La funzione NON e' SECURITY DEFINER (misurato su pg_proc) e filtra su
    user_id + ristorante_id: e' l'unico isolamento che ha."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga(db_sql, sede=SEDE, descrizione="SALMONE 5-6")
    _riga(db_sql, sede=SEDE_B, descrizione="TONNO ALTRA SEDE")

    assert {r[0] for r in _articoli(sql, sede=SEDE)} == {"SALMONE 5-6"}
    assert {r[0] for r in _articoli(sql, sede=SEDE_B)} == {"TONNO ALTRA SEDE"}


# ---------------------------------------------------------------------------
# chat_top_categoria_fornitore — la risposta della chat a «chi mi costa di piu'»
#
# Finestra mobile su `data_documento >= CURRENT_DATE - p_giorni`: le date dei
# test sono relative a oggi, non fisse, o il test scade.
# ---------------------------------------------------------------------------

def _top(sql, *, utente=UTENTE, sede=SEDE, giorni=90, top=5):
    return sql(
        "SELECT tipo, voce, spesa FROM public.chat_top_categoria_fornitore("
        "%s, %s, %s, %s)", utente, sede, giorni, top,
    )


def _giorni_fa(db_sql, giorni):
    with db_sql.cursor() as cur:
        cur.execute("SELECT (CURRENT_DATE - %s::int)::text", (giorni,))
        return cur.fetchone()[0]


def test_top_classifica_categorie_e_fornitori_separatamente(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    recente = _giorni_fa(db_sql, 5)
    _riga(db_sql, categoria="PESCE", fornitore="ADC SRL",
          totale=Decimal("100.00"), data_documento=recente)
    _riga(db_sql, categoria="CARNE", fornitore="ADC SRL",
          totale=Decimal("40.00"), data_documento=recente)
    _riga(db_sql, categoria="CARNE", fornitore="MACELLO SPA",
          totale=Decimal("10.00"), data_documento=recente)

    righe = _top(sql)
    assert righe, "nessuna riga: il test non prova nulla"
    categorie = {r[1]: r[2] for r in righe if r[0] == "categoria"}
    fornitori = {r[1]: r[2] for r in righe if r[0] == "fornitore"}
    # Le due classifiche sono indipendenti e vanno asserite separatamente: la
    # somma totale sarebbe identica anche se le voci fossero mescolate.
    assert categorie == {"PESCE": Decimal("100.00"), "CARNE": Decimal("50.00")}
    assert fornitori == {"ADC SRL": Decimal("140.00"), "MACELLO SPA": Decimal("10.00")}


def test_top_taglia_fuori_le_righe_oltre_la_finestra(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga(db_sql, categoria="PESCE", totale=Decimal("100.00"),
          data_documento=_giorni_fa(db_sql, 5))
    _riga(db_sql, categoria="CARNE", totale=Decimal("999.00"),
          data_documento=_giorni_fa(db_sql, 200))

    categorie = {r[1]: r[2] for r in _top(sql, giorni=90)}
    assert categorie.get("PESCE") == Decimal("100.00")
    assert "CARNE" not in categorie, "una riga fuori finestra e' entrata"


def test_top_rispetta_il_numero_di_voci_chiesto(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    recente = _giorni_fa(db_sql, 3)
    for indice, categoria in enumerate(("PESCE", "CARNE", "PANE"), start=1):
        _riga(db_sql, categoria=categoria, fornitore=f"F{indice}",
              totale=Decimal(indice * 10), data_documento=recente)

    voci = [r[1] for r in _top(sql, top=2) if r[0] == "categoria"]
    assert voci == ["PANE", "CARNE"], f"non ha tenuto le 2 piu' care: {voci}"


def test_top_esclude_le_cancellate_e_normalizza_il_fornitore_vuoto(db_sql, sql):
    """Il ramo `categoria = ''` -> 'Altro' NON e' raggiungibile dai dati veri: il
    constraint `fatture_categoria_not_empty_chk` (regola di dominio #1) vieta la
    categoria vuota, e il DB rifiuta l'INSERT. Provato: la prima stesura di
    questo test lo seminava e il DB l'ha respinto. Il COALESCE su `categoria`
    nel corpo e' codice difensivo su un caso impossibile, non un comportamento
    da presidiare. Il fornitore vuoto, invece, e' ammesso e capita davvero."""
    _semina_utente_e_sedi(db_sql)
    recente = _giorni_fa(db_sql, 5)
    _riga(db_sql, categoria="PESCE", fornitore="   ",
          totale=Decimal("10.00"), data_documento=recente)
    _riga(db_sql, categoria="PESCE", totale=Decimal("500.00"),
          data_documento=recente, deleted=True)

    righe = _top(sql)
    categorie = {r[1]: r[2] for r in righe if r[0] == "categoria"}
    fornitori = {r[1]: r[2] for r in righe if r[0] == "fornitore"}
    assert categorie == {"PESCE": Decimal("10.00")}, "una riga cancellata e' entrata"
    assert fornitori == {"Sconosciuto": Decimal("10.00")}


def test_top_su_tutte_le_sedi_quando_il_ristorante_e_nullo(db_sql, sql):
    """`p_ristorante_id IS NULL` = tutte le sedi dell'utente: e' il ramo della
    chat di catena."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    recente = _giorni_fa(db_sql, 5)
    _riga(db_sql, sede=SEDE, categoria="PESCE", totale=Decimal("100.00"), data_documento=recente)
    _riga(db_sql, sede=SEDE_B, categoria="PESCE", totale=Decimal("30.00"), data_documento=recente)

    una_sede = {r[1]: r[2] for r in _top(sql, sede=SEDE) if r[0] == "categoria"}
    tutte = {r[1]: r[2] for r in _top(sql, sede=None) if r[0] == "categoria"}
    assert una_sede == {"PESCE": Decimal("100.00")}
    assert tutte == {"PESCE": Decimal("130.00")}


# ---------------------------------------------------------------------------
# chat_usage_check_and_log — il limite giornaliero della chat
#
# Ritorna -1 quando il limite e' esaurito, altrimenti il numero della domanda
# appena consumata (1-based) E REGISTRA la riga: e' un check con effetto
# collaterale, non una lettura.
# ---------------------------------------------------------------------------

def _quota(sql, *, utente=UTENTE, sede=SEDE, limite=3, pool=False):
    return sql(
        "SELECT public.chat_usage_check_and_log(%s, %s, %s, %s)",
        utente, sede, limite, pool,
    )[0][0]


def test_quota_conta_le_domande_e_poi_blocca(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    assert [_quota(sql, limite=3) for _ in range(3)] == [1, 2, 3]
    assert _quota(sql, limite=3) == -1, "la quarta domanda ha superato il limite di 3"


def test_quota_registra_una_riga_per_domanda_consumata(db_sql, sql, scalare):
    """L'effetto collaterale e' il punto: se non scrivesse, il contatore
    ripartirebbe da zero a ogni domanda e il limite non esisterebbe."""
    _semina_utente_e_sedi(db_sql)
    _quota(sql, limite=2)
    _quota(sql, limite=2)
    assert scalare("SELECT count(*) FROM public.chat_usage_log") == 2

    _quota(sql, limite=2)   # rifiutata
    assert scalare("SELECT count(*) FROM public.chat_usage_log") == 2, \
        "una domanda RIFIUTATA ha comunque consumato una riga"


def test_quota_limite_nullo_o_negativo_blocca_subito(db_sql, sql, scalare):
    _semina_utente_e_sedi(db_sql)
    assert _quota(sql, limite=0) == -1
    assert _quota(sql, limite=-5) == -1
    assert scalare("SELECT count(*) FROM public.chat_usage_log") == 0


def test_quota_e_per_sede_ma_il_pool_la_unisce(db_sql, sql):
    """A `p_pool=false` ogni sede ha la sua quota; a true si contano tutte
    insieme sull'utente. E' la differenza fra account singolo e catena."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    assert _quota(sql, sede=SEDE, limite=2) == 1
    assert _quota(sql, sede=SEDE_B, limite=2) == 1, "la seconda sede eredita il conteggio della prima"

    # a pool acceso le due righe gia' scritte contano insieme: la terza sfonda
    assert _quota(sql, sede=SEDE, limite=2, pool=True) == -1


def test_quota_azzera_a_mezzanotte_UTC_non_italiana(db_sql, sql):
    """DIVERGENZA NOTA E NON DECISA (07/09/2026): il taglio e' mezzanotte UTC,
    che in Italia cade all'01:00 (inverno) o alle 02:00 (estate). Un cliente che
    scrive all'00:30 sta ancora consumando la quota del giorno prima.

    Questo test DOCUMENTA il comportamento di oggi, non lo cambia: la decisione
    e' di Mattia. Se un giorno il taglio passera' al fuso italiano, questo test
    va aggiornato consapevolmente — ed e' esattamente il suo scopo.
    """
    _semina_utente_e_sedi(db_sql)
    with db_sql.cursor() as cur:
        # una domanda registrata alle 23:30 UTC di ieri: e' PRIMA del taglio,
        # quindi non deve contare oggi...
        cur.execute(
            "INSERT INTO public.chat_usage_log (user_id, ristorante_id, created_at) "
            "VALUES (%s, %s, date_trunc('day', now() AT TIME ZONE 'UTC') "
            "AT TIME ZONE 'UTC' - interval '30 minutes')",
            (UTENTE, SEDE),
        )
        # ...mentre una alle 00:30 UTC di oggi conta.
        cur.execute(
            "INSERT INTO public.chat_usage_log (user_id, ristorante_id, created_at) "
            "VALUES (%s, %s, date_trunc('day', now() AT TIME ZONE 'UTC') "
            "AT TIME ZONE 'UTC' + interval '30 minutes')",
            (UTENTE, SEDE),
        )

    # limite 2: una sola delle due righe conta, quindi la prossima passa ed e' la 2a
    assert _quota(sql, limite=2) == 2
    assert _quota(sql, limite=2) == -1
