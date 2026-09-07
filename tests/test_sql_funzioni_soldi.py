"""Le funzioni SQL che calcolano i soldi, eseguite davvero.

Perche' esiste
==============
Sei funzioni del database producono i numeri che il cliente legge — il MOL, i
margini di sede, lo scadenziario — e decidono quali fatture il worker elabora.
Fino al 07/09/2026 nessun test ne eseguiva una riga: la suite mocka il DB, e
quel che si rompe qui si rompe in silenzio, sui dati veri, senza niente di rosso.

    riparto_quote_mensili              riscrive mol, primo_margine, costi_fb_totali
    sposta_fattura_a_sede              sposta righe fra sedi
    sync_margini_mensili_from_ricavi   trigger: aggrega i ricavi del mese
    scadenziario_fatture_aggregate     aggrega le scadenze (un difetto qui ha reso
                                       invisibili 4,4 M di scadenze nel 2026)
    costi_automatici_mensili           i costi che entrano nel MOL
    claim_batch_for_processing         il worker prende in carico le fatture

Come sono scritti
=================
Si seminano righe vere, si chiama la funzione, si guarda cosa torna. Mai
asserire sul TESTO del corpo con `pg_get_functiondef`: un mutante che cambia il
comportamento lascia il testo intatto e sopravviverebbe — misurato il 07/09.

Si asseriscono le COMPONENTI, non l'aggregato. Due errori opposti che si
compensano lasciano la somma giusta e il test verde.

Ogni test gira in una transazione annullata: l'ordine non conta, non serve
pulire, e le righe di un test non si vedono dagli altri.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.sql

UTENTE = "11111111-1111-4111-8111-111111111111"
SEDE = "22222222-2222-4222-8222-222222222222"
SEDE_B = "33333333-3333-4333-8333-333333333333"


def _semina_utente_e_sedi(db_sql, sedi=(SEDE,), attivo=True):
    """Un utente e una o piu' sedi. Il minimo per avere righe referenziabili."""
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'prova@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        for numero, sede in enumerate(sedi, start=1):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
                "partita_iva, attivo) VALUES (%s, %s, %s, %s, %s)",
                (sede, UTENTE, f"Sede {numero}", f"0123456789{numero}", attivo),
            )
    return UTENTE


def _riga_fattura(db_sql, *, sede=SEDE, file="prova.xml", numero_riga=1,
                  categoria="CARNE", totale=Decimal("100.00"),
                  data_documento="2026-03-10", data_competenza=None,
                  ripartita=False, fiducia=None, deleted=False, utente=UTENTE):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
            "numero_riga, data_documento, data_competenza, fornitore, descrizione, "
            "categoria, quantita, prezzo_unitario, totale_riga, "
            "ripartita_su_gruppo, categoria_fiducia, deleted_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'Fornitore', 'riga', %s, 1, %s, %s, "
            "%s, %s, %s) RETURNING id",
            (utente, sede, file, numero_riga, data_documento, data_competenza,
             categoria, totale, totale, ripartita, fiducia,
             "2026-01-01" if deleted else None),
        )
        return cur.fetchone()[0]


def _margini(sql, sede=SEDE, anno=2026, mese=3):
    """La riga di margini_mensili di una sede/mese, come dizionario."""
    colonne = ("quote_riparto_fb", "quote_riparto_spese", "costi_fb_totali",
               "fatturato_netto", "primo_margine", "mol", "fatturato_iva10",
               "fatturato_iva22", "altri_ricavi_noiva", "coperti")
    righe = sql(
        f"SELECT {', '.join(colonne)} FROM public.margini_mensili "
        "WHERE ristorante_id = %s AND anno = %s AND mese = %s",
        sede, anno, mese,
    )
    if not righe:
        return None
    return dict(zip(colonne, righe[0]))


# ---------------------------------------------------------------------------
# costi_automatici_mensili — i costi che entrano nel MOL
#
# Tocca le regole di dominio #1 (`Da Classificare` non entra nei margini) e #2
# (`NOTE E DICITURE` solo a importo zero). Firma:
#   (p_user_id, p_ristorante_id, p_anno, p_cat_food[], p_cat_spese[],
#    p_escludi_da_verificare DEFAULT false) -> TABLE(mese, food, spese)
# ---------------------------------------------------------------------------

CAT_SPESE = ["UTENZE", "AFFITTO"]
CAT_FOOD = ["CARNE", "PESCE"]


def _costi(sql, *, anno=2026, escludi_da_verificare=None, sede=SEDE):
    if escludi_da_verificare is None:
        return sql(
            "SELECT mese, food, spese FROM public.costi_automatici_mensili("
            "%s, %s, %s, %s, %s) ORDER BY mese",
            UTENTE, sede, anno, CAT_FOOD, CAT_SPESE,
        )
    return sql(
        "SELECT mese, food, spese FROM public.costi_automatici_mensili("
        "%s, %s, %s, %s, %s, %s) ORDER BY mese",
        UTENTE, sede, anno, CAT_FOOD, CAT_SPESE, escludi_da_verificare,
    )


def test_costi_separa_food_da_spese_generali(db_sql, sql):
    """Le due componenti vanno asserite separatamente, non la loro somma.

    Un errore che spostasse 50 euro da food a spese lascerebbe il totale
    invariato: e' esattamente il caso che la somma non vede.
    """
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"))
    _riga_fattura(db_sql, numero_riga=2, categoria="UTENZE", totale=Decimal("30.00"))

    assert _costi(sql) == [(3, Decimal("100.00"), Decimal("30.00"))]


def test_costi_esclude_da_classificare(db_sql, sql):
    """Regola di dominio #1: una riga non classificata non entra nei margini.

    Se entrasse, il MOL sarebbe calcolato su una categoria inventata.
    """
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"))
    _riga_fattura(db_sql, numero_riga=2, categoria="Da Classificare", totale=Decimal("999.00"))

    mese, food, spese = _costi(sql)[0]
    assert food == Decimal("100.00"), "la riga Da Classificare e' entrata nei costi F&B"
    assert spese == Decimal("0")


def test_costi_esclude_note_e_diciture(db_sql, sql):
    """Regola di dominio #2: le NOTE non sono un costo.

    Mutante SOPRAVVISSUTO, e va spiegato invece che nascosto. Togliendo
    `AND base.categoria <> '📝 NOTE E DICITURE'` dalla funzione questo test
    resta verde. Non perche' sia debole: perche' il CHECK
    `fatture_note_diciture_solo_importo_zero_chk` impedisce a una NOTA con
    importo diverso da zero di esistere (provato: `CheckViolation`). Una NOTA
    vale sempre 0, quindi sommarla o escluderla da' lo stesso numero.

    L'esclusione nella funzione e' dunque una seconda cintura dietro un vincolo
    che gia' tiene — ridondante finche' il CHECK resta. Va lasciata: se un
    giorno il CHECK venisse allentato, e' l'unica cosa che terrebbe le diciture
    fuori dal MOL.

    Cio' che questo test presidia davvero e' il vincolo stesso: se sparisse,
    l'assert sulla riga seminata a importo zero non basterebbe piu' e la copia
    di sicurezza andrebbe provata in altro modo.
    """
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"))
    _riga_fattura(db_sql, numero_riga=2, categoria="\U0001f4dd NOTE E DICITURE",
                  totale=Decimal("0.00"))

    righe = sql(
        "SELECT count(*) FROM public.fatture "
        "WHERE categoria = %s AND ristorante_id = %s",
        "\U0001f4dd NOTE E DICITURE", SEDE,
    )
    assert righe[0][0] == 1, "la riga NOTE non e' stata seminata: il test non prova nulla"
    assert _costi(sql) == [(3, Decimal("100.00"), Decimal("0"))]


def test_costi_una_categoria_sconosciuta_finisce_in_food(db_sql, sql):
    """`p_cat_food` e' dichiarato ma mai usato: food e' un catch-all.

    Non e' un difetto da correggere qui, ma un comportamento da fissare: chi
    domani trasformasse food in una lista chiusa farebbe sparire dal MOL ogni
    categoria nuova, in silenzio.
    """
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CATEGORIA MAI VISTA",
                  totale=Decimal("70.00"))

    assert _costi(sql) == [(3, Decimal("70.00"), Decimal("0"))]


def test_costi_la_competenza_ha_precedenza_sulla_data_documento(db_sql, sql):
    """Una fattura di marzo con competenza gennaio pesa su gennaio."""
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"),
                  data_documento="2026-03-10", data_competenza="2026-01-31")

    assert _costi(sql) == [(1, Decimal("100.00"), Decimal("0"))]


def test_costi_esclude_le_righe_gia_ripartite_sul_gruppo(db_sql, sql):
    """Anti-doppio-conteggio: cio' che il riparto ha gia' distribuito non si somma.

    Senza questo filtro il costo entrerebbe due volte nel MOL — una qui e una
    come quota di riparto.
    """
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"))
    _riga_fattura(db_sql, numero_riga=2, categoria="CARNE", totale=Decimal("500.00"),
                  ripartita=True)

    assert _costi(sql) == [(3, Decimal("100.00"), Decimal("0"))]


def test_costi_esclude_il_cestino(db_sql, sql):
    """Regola di dominio #5: `deleted_at IS NULL`."""
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"))
    _riga_fattura(db_sql, numero_riga=2, categoria="CARNE", totale=Decimal("400.00"),
                  deleted=True)

    assert _costi(sql) == [(3, Decimal("100.00"), Decimal("0"))]


def test_costi_il_flag_da_verificare_filtra_solo_se_acceso(db_sql, sql):
    """Le due direzioni: con il flag la riga incerta esce, senza resta."""
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", totale=Decimal("100.00"),
                  fiducia="certa")
    _riga_fattura(db_sql, numero_riga=2, categoria="CARNE", totale=Decimal("60.00"),
                  fiducia="da_verificare")

    assert _costi(sql, escludi_da_verificare=False) == [(3, Decimal("160.00"), Decimal("0"))]
    assert _costi(sql, escludi_da_verificare=True) == [(3, Decimal("100.00"), Decimal("0"))]


def test_costi_ritorna_solo_i_mesi_con_righe(db_sql, sql):
    """Nessuno zero spurio: un mese senza fatture non compare affatto.

    Conta perche' a valle un mese a zero e un mese assente non sono la stessa
    cosa: uno dice "nessun costo", l'altro "nessun dato".
    """
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, categoria="CARNE", data_documento="2026-01-15")
    _riga_fattura(db_sql, numero_riga=2, categoria="CARNE", data_documento="2026-05-20")

    assert [r[0] for r in _costi(sql)] == [1, 5]


# ---------------------------------------------------------------------------
# claim_batch_for_processing — il worker prende in carico le fatture
#
# Un difetto qui significa fatture elaborate due volte, o mai. Firma:
#   (p_worker_id text, p_batch_size int DEFAULT 10) -> SETOF fatture_queue
#
# `fatture_queue.id` non ha un default (la sequence esiste ma non e' collegata):
# negli INSERT va passato esplicito, o e' NotNullViolation. Misurato.
# Lasciando user_id e ristorante_id NULL il CHECK di consistenza tenant e'
# soddisfatto senza dover creare utente e sede.
# ---------------------------------------------------------------------------


def _riga_coda(db_sql, *, id_, status="pending", attempt=0, max_attempts=8,
               next_retry="now()", locked_at="NULL", locked_by=None):
    """`next_retry` e `locked_at` sono espressioni SQL, non valori.

    Servono relative a `now()` — la funzione confronta con l'ora corrente, e un
    timestamp fisso renderebbe il test giusto solo il giorno in cui e' scritto.
    """
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, "
            "attempt_count, max_attempts, next_retry_at, locked_at, locked_by) "
            f"VALUES (%s, %s, '12345678901', %s, %s, %s, {next_retry}, {locked_at}, %s)",
            (id_, f"evento-{id_}", status, attempt, max_attempts, locked_by),
        )


def _claim(sql, worker="worker-1", dimensione=None):
    if dimensione is None:
        return sql("SELECT id, status, attempt_count, locked_by "
                   "FROM public.claim_batch_for_processing(%s) ORDER BY id", worker)
    return sql("SELECT id, status, attempt_count, locked_by "
               "FROM public.claim_batch_for_processing(%s, %s) ORDER BY id",
               worker, dimensione)


def test_claim_prende_in_carico_e_marca_chi_ha_preso(db_sql, sql):
    _riga_coda(db_sql, id_=1)
    preso = _claim(sql)

    assert [(r[0], r[1], r[3]) for r in preso] == [(1, "processing", "worker-1")]
    assert sql("SELECT status, locked_by FROM public.fatture_queue WHERE id = 1") == \
        [("processing", "worker-1")], "lo stato non e' stato scritto sulla riga"


def test_claim_prende_anche_i_falliti_da_ritentare(db_sql, sql):
    """`failed` non e' terminale: e' un tentativo da rifare."""
    _riga_coda(db_sql, id_=1, status="pending")
    _riga_coda(db_sql, id_=2, status="failed", attempt=1)

    assert [r[0] for r in _claim(sql)] == [1, 2]


def test_claim_incrementa_il_contatore_dei_tentativi(db_sql, sql):
    """Senza l'incremento una fattura che fallisce sempre gira all'infinito."""
    _riga_coda(db_sql, id_=1, attempt=3)

    assert _claim(sql)[0][2] == 4


def test_claim_si_ferma_al_tetto_dei_tentativi(db_sql, sql):
    """A `attempt_count >= max_attempts` la riga non va piu' ripresa."""
    _riga_coda(db_sql, id_=1, attempt=8, max_attempts=8, status="failed")
    _riga_coda(db_sql, id_=2, attempt=7, max_attempts=8, status="failed")

    assert [r[0] for r in _claim(sql)] == [2], "una riga oltre il tetto e' stata ripresa"


def test_claim_rispetta_l_attesa_prima_del_ritento(db_sql, sql):
    """`next_retry_at` nel futuro significa: non ancora."""
    _riga_coda(db_sql, id_=1, next_retry="now() + INTERVAL '1 hour'")
    _riga_coda(db_sql, id_=2, next_retry="now() - INTERVAL '1 minute'")

    assert [r[0] for r in _claim(sql)] == [2]


def test_claim_non_ruba_il_lavoro_di_un_altro_worker(db_sql, sql):
    """Un lock fresco e' di chi lo ha preso: rubarlo = elaborare due volte."""
    _riga_coda(db_sql, id_=1, status="processing", locked_at="now()", locked_by="worker-2")

    assert _claim(sql, worker="worker-1") == []


def test_claim_recupera_i_lock_scaduti(db_sql, sql):
    """Un worker morto non deve bloccare la fattura per sempre.

    La soglia e' 10 minuti: si prova su entrambi i lati, o il test passerebbe
    anche se qualcuno la spostasse a un'ora.
    """
    _riga_coda(db_sql, id_=1, status="failed", locked_at="now() - INTERVAL '11 minutes'",
               locked_by="worker-morto")
    _riga_coda(db_sql, id_=2, status="failed", locked_at="now() - INTERVAL '9 minutes'",
               locked_by="worker-vivo")

    assert [r[0] for r in _claim(sql)] == [1]


def test_claim_rispetta_la_dimensione_del_lotto(db_sql, sql):
    for identificativo in (1, 2, 3):
        _riga_coda(db_sql, id_=identificativo)

    assert len(_claim(sql, dimensione=2)) == 2


def test_claim_serve_prima_chi_aspetta_da_piu_tempo(db_sql, sql):
    """Ordine per `next_retry_at`: senza, una fattura puo' restare in coda per sempre."""
    _riga_coda(db_sql, id_=1, next_retry="now() - INTERVAL '1 minute'")
    _riga_coda(db_sql, id_=2, next_retry="now() - INTERVAL '1 hour'")

    assert [r[0] for r in sql(
        "SELECT id FROM public.claim_batch_for_processing('worker-1', 1)")] == [2]


@pytest.mark.parametrize("worker, dimensione, atteso", [
    ("", 10, "p_worker_id"),
    ("   ", 10, "p_worker_id"),
    ("worker-1", 0, "p_batch_size"),
    ("worker-1", 101, "p_batch_size"),
])
def test_claim_rifiuta_i_parametri_assurdi(db_sql, sql, worker, dimensione, atteso):
    """Si ferma invece di fare un lotto vuoto o svuotare la coda in un colpo."""
    import psycopg

    with pytest.raises(psycopg.errors.RaiseException, match=atteso):
        sql("SELECT * FROM public.claim_batch_for_processing(%s, %s)", worker, dimensione)
    db_sql.rollback()


# ---------------------------------------------------------------------------
# sync_margini_mensili_from_ricavi — trigger, non RPC
#
# Scatta AFTER INSERT OR UPDATE OR DELETE su ogni riga di ricavi_giornalieri,
# aggrega il mese e riscrive margini_mensili. Si prova scrivendo ricavi veri e
# leggendo i margini: non c'e' nulla da "chiamare".
# ---------------------------------------------------------------------------


def _ricavo(db_sql, *, data, iva10=Decimal("0"), iva22=Decimal("0"),
            altri=Decimal("0"), coperti=None, sede=SEDE):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, "
            "fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, coperti) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (UTENTE, sede, data, iva10, iva22, altri, coperti),
        )
        return cur.fetchone()[0]


def test_ricavi_il_trigger_aggrega_il_mese(db_sql, sql):
    """Due giorni nello stesso mese fanno una riga sola di margini.

    Le componenti si asseriscono una per una: `fatturato_netto` da solo
    resterebbe giusto anche scambiando l'aliquota fra i due imponibili.
    """
    _semina_utente_e_sedi(db_sql)
    _ricavo(db_sql, data="2026-03-01", iva10=Decimal("110.00"), coperti=10)
    _ricavo(db_sql, data="2026-03-02", iva22=Decimal("122.00"), coperti=5)

    margini = _margini(sql)
    assert margini["fatturato_iva10"] == Decimal("110.00")
    assert margini["fatturato_iva22"] == Decimal("122.00")
    assert margini["coperti"] == 15
    # 110/1.10 + 122/1.22 = 100 + 100
    assert margini["fatturato_netto"] == Decimal("200.00")


def test_ricavi_giorni_di_mesi_diversi_non_si_mescolano(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _ricavo(db_sql, data="2026-03-31", iva10=Decimal("110.00"))
    _ricavo(db_sql, data="2026-04-01", iva10=Decimal("220.00"))

    assert _margini(sql, mese=3)["fatturato_iva10"] == Decimal("110.00")
    assert _margini(sql, mese=4)["fatturato_iva10"] == Decimal("220.00")


def test_ricavi_la_modifica_di_un_giorno_ricalcola_il_mese(db_sql, sql):
    """Un UPDATE che non ri-aggregasse lascerebbe il mese fermo al valore vecchio."""
    _semina_utente_e_sedi(db_sql)
    identificativo = _ricavo(db_sql, data="2026-03-01", iva10=Decimal("110.00"))

    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.ricavi_giornalieri SET fatturato_iva10 = %s "
                    "WHERE id = %s", (Decimal("220.00"), identificativo))

    assert _margini(sql)["fatturato_iva10"] == Decimal("220.00")


def test_ricavi_cancellare_l_ultimo_giorno_azzera_invece_di_sparire(db_sql, sql):
    """La riga di margini resta, a zero.

    Comportamento non ovvio e da fissare: a valle "mese a zero" e "mese assente"
    non sono la stessa cosa, e qui il mese resta presente.
    """
    _semina_utente_e_sedi(db_sql)
    identificativo = _ricavo(db_sql, data="2026-03-01", iva10=Decimal("110.00"))

    with db_sql.cursor() as cur:
        cur.execute("DELETE FROM public.ricavi_giornalieri WHERE id = %s", (identificativo,))

    margini = _margini(sql)
    assert margini is not None, "la riga di margini e' sparita invece di azzerarsi"
    assert margini["fatturato_iva10"] == Decimal("0")
    assert margini["fatturato_netto"] == Decimal("0")


def test_ricavi_senza_coperti_il_totale_resta_ignoto_non_zero(db_sql, sql):
    """`SUM(coperti)` non e' COALESCEd: nessun dato -> NULL, non 0.

    Distinzione che conta: uno zero direbbe "nessun cliente", il NULL dice "non
    lo sappiamo". Un COALESCE aggiunto qui trasformerebbe l'ignoto in una
    misura, e il coperto medio ne uscirebbe falsato.
    """
    _semina_utente_e_sedi(db_sql)
    _ricavo(db_sql, data="2026-03-01", iva10=Decimal("110.00"), coperti=None)

    assert _margini(sql)["coperti"] is None


def test_ricavi_di_sedi_diverse_restano_separati(db_sql, sql):
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _ricavo(db_sql, data="2026-03-01", iva10=Decimal("110.00"), sede=SEDE)
    _ricavo(db_sql, data="2026-03-01", iva10=Decimal("330.00"), sede=SEDE_B)

    assert _margini(sql, sede=SEDE)["fatturato_iva10"] == Decimal("110.00")
    assert _margini(sql, sede=SEDE_B)["fatturato_iva10"] == Decimal("330.00")


# ---------------------------------------------------------------------------
# sposta_fattura_a_sede — sbagliarla significa fatture nella sede sbagliata
#
# (p_user_id, p_file_origine, p_ristorante_id) -> int (righe spostate)
# Sposta sia `fatture` sia `fatture_documenti`, con una guardia sulle collisioni.
# ---------------------------------------------------------------------------


def _documento(db_sql, *, file="prova.xml", sede=SEDE):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.fatture_documenti (user_id, ristorante_id, file_origine) "
            "VALUES (%s, %s, %s)", (UTENTE, sede, file),
        )


def _sposta(sql, *, file="prova.xml", sede=SEDE_B, utente=UTENTE):
    return sql("SELECT public.sposta_fattura_a_sede(%s, %s, %s)", utente, file, sede)[0][0]


def test_sposta_porta_le_righe_nella_sede_indicata(db_sql, sql):
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)
    _riga_fattura(db_sql, numero_riga=2, sede=SEDE)

    assert _sposta(sql) == 2
    assert sql("SELECT count(*) FROM public.fatture WHERE ristorante_id = %s",
               SEDE_B)[0][0] == 2
    assert sql("SELECT count(*) FROM public.fatture WHERE ristorante_id = %s",
               SEDE)[0][0] == 0


def test_sposta_porta_anche_il_documento_non_solo_le_righe(db_sql, sql):
    """Spostare le righe e lasciare il documento indietro spezza lo scadenziario.

    E' il caso che il conteggio di ritorno non vede: guarda solo `fatture`.
    """
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)
    _documento(db_sql, sede=SEDE)

    _sposta(sql)

    assert sql("SELECT ristorante_id::text FROM public.fatture_documenti "
               "WHERE file_origine = 'prova.xml'")[0][0] == SEDE_B


def test_sposta_si_ferma_se_il_file_e_gia_nella_destinazione(db_sql, sql):
    """Collisione: proseguire creerebbe due copie della stessa fattura in una sede."""
    import psycopg

    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)
    _riga_fattura(db_sql, numero_riga=2, sede=SEDE_B)

    with pytest.raises(psycopg.errors.RaiseException,
                       match="collisione_file_in_sede_destinazione"):
        _sposta(sql)
    db_sql.rollback()


def test_sposta_verso_la_stessa_sede_non_fa_nulla_e_non_e_una_collisione(db_sql, sql):
    """Zero righe toccate, nessun errore: l'operazione e' gia' nello stato voluto."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE,))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)

    assert _sposta(sql, sede=SEDE) == 0


def test_sposta_ignora_le_righe_nel_cestino(db_sql, sql):
    """Regola di dominio #5: una fattura cestinata non si sposta."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)
    _riga_fattura(db_sql, numero_riga=2, sede=SEDE, deleted=True)

    assert _sposta(sql) == 1
    assert sql("SELECT ristorante_id::text FROM public.fatture "
               "WHERE numero_riga = 2")[0][0] == SEDE


def test_sposta_rifiuta_una_sede_inesistente(db_sql, sql):
    import psycopg

    _semina_utente_e_sedi(db_sql, sedi=(SEDE,))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)

    with pytest.raises(psycopg.errors.RaiseException, match="inesistente"):
        _sposta(sql, sede="44444444-4444-4444-8444-444444444444")
    db_sql.rollback()


def test_sposta_rifiuta_una_sede_di_un_altro_utente(db_sql, sql):
    """Senza questa guardia si sposterebbero fatture nel database di un altro cliente."""
    import psycopg

    altro = "55555555-5555-4555-8555-555555555555"
    _semina_utente_e_sedi(db_sql, sedi=(SEDE,))
    with db_sql.cursor() as cur:
        cur.execute("INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
                    "VALUES (%s, 'altro@oneflux.test', 'x', 'Altro')", (altro,))
        cur.execute("INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva) "
                    "VALUES (%s, %s, 'Sede altrui', '09999999999')", (SEDE_B, altro))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)

    with pytest.raises(psycopg.errors.RaiseException, match="non appartiene"):
        _sposta(sql)
    db_sql.rollback()


def test_sposta_rifiuta_una_sede_disattivata(db_sql, sql):
    import psycopg

    _semina_utente_e_sedi(db_sql, sedi=(SEDE,))
    with db_sql.cursor() as cur:
        cur.execute("INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
                    "partita_iva, attivo) VALUES (%s, %s, 'Sede chiusa', '08888888888', false)",
                    (SEDE_B, UTENTE))
    _riga_fattura(db_sql, numero_riga=1, sede=SEDE)

    with pytest.raises(psycopg.errors.RaiseException, match="non attivo"):
        _sposta(sql)
    db_sql.rollback()


# ---------------------------------------------------------------------------
# scadenziario_fatture_aggregate — nel 2026 un difetto qui ha reso invisibili
# 4,4 M di scadenze.
#
# (p_user_id, p_ristorante_ids uuid[]) -> TABLE(file_origine, ristorante_id,
#   fornitore, tipo_documento, totale_documento, data_documento, created_at)
#
# Ha una guardia: senza il ruolo `service_role` risponde `Accesso negato`. Il
# ruolo si assume impostando il GUC che `auth.role()` legge.
# ---------------------------------------------------------------------------


def _come_service_role(db_sql):
    with db_sql.cursor() as cur:
        cur.execute("SET LOCAL request.jwt.claim.role = 'service_role'")


def _scadenziario(sql, sedi=(SEDE,)):
    return sql(
        "SELECT file_origine, totale_documento, fornitore, tipo_documento "
        "FROM public.scadenziario_fatture_aggregate(%s, %s) ORDER BY file_origine",
        UTENTE, list(sedi),
    )


def test_scadenziario_nega_a_chi_non_e_service_role(db_sql, sql):
    """Prima cosa da provare: la guardia c'e' e nega davvero.

    Senza, la funzione (SECURITY DEFINER) restituirebbe le fatture di chiunque a
    chi passa un id altrui.
    """
    import psycopg

    _semina_utente_e_sedi(db_sql)
    with pytest.raises(psycopg.errors.RaiseException, match="Accesso negato"):
        _scadenziario(sql)
    db_sql.rollback()


def test_scadenziario_somma_le_righe_di_un_documento(db_sql, sql):
    """Il totale del documento e' la somma delle sue righe, non la prima riga."""
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, totale=Decimal("30.00"))
    _riga_fattura(db_sql, numero_riga=2, totale=Decimal("70.50"))
    _come_service_role(db_sql)

    assert _scadenziario(sql) == [("prova.xml", Decimal("100.50"), "Fornitore", "TD01")]


def test_scadenziario_tiene_separati_i_documenti(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, file="a.xml", numero_riga=1, totale=Decimal("10.00"))
    _riga_fattura(db_sql, file="b.xml", numero_riga=1, totale=Decimal("20.00"))
    _come_service_role(db_sql)

    assert [(r[0], r[1]) for r in _scadenziario(sql)] == \
        [("a.xml", Decimal("10.00")), ("b.xml", Decimal("20.00"))]


def test_scadenziario_lo_stesso_file_in_due_sedi_resta_diviso(db_sql, sql):
    """Sommarli darebbe a ogni sede la scadenza dell'altra."""
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga_fattura(db_sql, sede=SEDE, numero_riga=1, totale=Decimal("10.00"))
    _riga_fattura(db_sql, sede=SEDE_B, numero_riga=1, totale=Decimal("20.00"))
    _come_service_role(db_sql)

    assert sorted(r[1] for r in _scadenziario(sql, sedi=(SEDE, SEDE_B))) == \
        [Decimal("10.00"), Decimal("20.00")]


def test_scadenziario_esclude_il_cestino(db_sql, sql):
    """Una scadenza cestinata non si paga: era il difetto costato 4,4 M di visibilita'."""
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, numero_riga=1, totale=Decimal("10.00"))
    _riga_fattura(db_sql, numero_riga=2, totale=Decimal("999.00"), deleted=True)
    _come_service_role(db_sql)

    assert _scadenziario(sql)[0][1] == Decimal("10.00")


def test_scadenziario_ignora_le_sedi_non_richieste(db_sql, sql):
    _semina_utente_e_sedi(db_sql, sedi=(SEDE, SEDE_B))
    _riga_fattura(db_sql, sede=SEDE, file="a.xml", numero_riga=1, totale=Decimal("10.00"))
    _riga_fattura(db_sql, sede=SEDE_B, file="b.xml", numero_riga=1, totale=Decimal("20.00"))
    _come_service_role(db_sql)

    assert [r[0] for r in _scadenziario(sql, sedi=(SEDE,))] == ["a.xml"]


def test_scadenziario_salta_i_documenti_senza_nome_file(db_sql, sql):
    """Un file vuoto o di soli spazi non e' un documento: raggrupparlo creerebbe
    una scadenza fantasma che somma righe di fatture diverse."""
    _semina_utente_e_sedi(db_sql)
    _riga_fattura(db_sql, file="   ", numero_riga=1, totale=Decimal("50.00"))
    _riga_fattura(db_sql, file="vero.xml", numero_riga=2, totale=Decimal("10.00"))
    _come_service_role(db_sql)

    assert [r[0] for r in _scadenziario(sql)] == ["vero.xml"]


# ---------------------------------------------------------------------------
# riparto_quote_mensili — riscrive mol, primo_margine, costi_fb_totali e
# fatturato_netto in margini_mensili.
#
# (p_user_id, p_anno, p_mese) -> int (sedi toccate)
#
# Separa i costi F&B dalle spese generali: se sbaglia la separazione il MOL
# TOTALE resta giusto e le componenti no. Per questo si asserisce sulle singole
# voci, mai sul solo MOL.
# ---------------------------------------------------------------------------


def _riparto(db_sql, *, descrizione="Costo catena", importo=Decimal("100.00"),
             tipo="generale", anno=2026, mese=3, file="riparto.xml"):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.riparto_costi_catena (user_id, descrizione, "
            "importo_totale, tipo, anno, mese, file_origine) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (UTENTE, descrizione, importo, tipo, anno, mese, file),
        )
        return cur.fetchone()[0]


def _quota(db_sql, riparto_id, *, sede=SEDE, perc=Decimal("100.000"),
           importo=Decimal("100.00"), categoria=None):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.riparto_costi_catena_quote (riparto_id, "
            "ristorante_id, quota_perc, quota_importo, categoria) "
            "VALUES (%s, %s, %s, %s, %s)",
            (riparto_id, sede, perc, importo, categoria),
        )


def _imposta_margini(db_sql, *, sede=SEDE, anno=2026, mese=3, **valori):
    colonne = ", ".join(valori)
    segnaposto = ", ".join(["%s"] * len(valori))
    with db_sql.cursor() as cur:
        cur.execute(
            f"INSERT INTO public.margini_mensili (user_id, ristorante_id, anno, "
            f"mese, {colonne}) VALUES (%s, %s, %s, %s, {segnaposto})",
            (UTENTE, sede, anno, mese, *valori.values()),
        )


def test_riparto_una_quota_generale_va_nelle_spese_non_nel_food(db_sql, sql):
    """La separazione e' il punto: un errore qui lascia il MOL giusto e le
    componenti sbagliate, che e' il modo peggiore di sbagliare."""
    _semina_utente_e_sedi(db_sql)
    riparto = _riparto(db_sql, tipo="generale")
    _quota(db_sql, riparto, importo=Decimal("100.00"))

    assert sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)[0][0] == 1

    margini = _margini(sql)
    assert margini["quote_riparto_spese"] == Decimal("100.00")
    assert margini["quote_riparto_fb"] == Decimal("0.00")


def test_riparto_una_quota_fb_va_nel_food_non_nelle_spese(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    riparto = _riparto(db_sql, tipo="fb")
    _quota(db_sql, riparto, importo=Decimal("100.00"))

    sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)

    margini = _margini(sql)
    assert margini["quote_riparto_fb"] == Decimal("100.00")
    assert margini["quote_riparto_spese"] == Decimal("0.00")


def test_riparto_la_categoria_della_quota_batte_il_tipo_del_riparto(db_sql, sql):
    """Con una categoria esplicita decide lei, non `tipo` della testata.

    Qui la testata dice 'generale' ma la categoria e' F&B: la quota deve finire
    nel food. Se prevalesse il tipo, i costi merce di una catena finirebbero
    fra le spese generali e il primo margine sarebbe gonfiato.
    """
    _semina_utente_e_sedi(db_sql)
    riparto = _riparto(db_sql, tipo="generale")
    _quota(db_sql, riparto, importo=Decimal("100.00"), categoria="CARNE")

    sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)

    margini = _margini(sql)
    assert margini["quote_riparto_fb"] == Decimal("100.00")
    assert margini["quote_riparto_spese"] == Decimal("0.00")


def test_riparto_ricalcola_tutte_le_voci_derivate(db_sql, sql):
    """Ogni voce si asserisce da sola: il MOL da solo nasconde due errori opposti.

    Ricavi:  iva10 110 -> 100 netti,  iva22 122 -> 100 netti,  altri 50
             fatturato_netto = 250
    Costi:   food auto 40 + altri food 10 + quota fb 20   = 70
             spese auto 30 + altre spese 5 + quota spese 15 = 50
             personale 20 + extra 10                        = 30
    primo_margine = 250 - 70 = 180
    mol           = 250 - 70 - 50 - 30 = 100
    """
    _semina_utente_e_sedi(db_sql)
    _imposta_margini(
        db_sql,
        fatturato_iva10=Decimal("110.00"), fatturato_iva22=Decimal("122.00"),
        altri_ricavi_noiva=Decimal("50.00"),
        costi_fb_auto=Decimal("40.00"), altri_costi_fb=Decimal("10.00"),
        costi_spese_auto=Decimal("30.00"), altri_costi_spese=Decimal("5.00"),
        costo_dipendenti=Decimal("20.00"), costo_personale_extra=Decimal("10.00"),
    )
    riparto_fb = _riparto(db_sql, tipo="fb", file="fb.xml")
    _quota(db_sql, riparto_fb, importo=Decimal("20.00"))
    riparto_spese = _riparto(db_sql, tipo="generale", file="spese.xml")
    _quota(db_sql, riparto_spese, importo=Decimal("15.00"))

    sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)

    margini = _margini(sql)
    assert margini["fatturato_netto"] == Decimal("250.00")
    assert margini["costi_fb_totali"] == Decimal("70.00")
    assert margini["primo_margine"] == Decimal("180.00")
    assert margini["mol"] == Decimal("100.00")


def test_riparto_azzera_la_sede_uscita_dal_riparto(db_sql, sql):
    """Tolto il riparto, le quote vecchie non devono restare appiccicate.

    Senza questo ramo una sede continuerebbe a portare nel MOL un costo che non
    le e' piu' attribuito — e nessuno se ne accorgerebbe, perche' il numero c'e'.
    """
    _semina_utente_e_sedi(db_sql)
    _imposta_margini(db_sql, quote_riparto_fb=Decimal("80.00"),
                     quote_riparto_spese=Decimal("20.00"))

    assert sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)[0][0] == 1

    margini = _margini(sql)
    assert margini["quote_riparto_fb"] == Decimal("0.00")
    assert margini["quote_riparto_spese"] == Decimal("0.00")


def test_riparto_tocca_solo_il_mese_richiesto(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    riparto = _riparto(db_sql, mese=3, file="marzo.xml")
    _quota(db_sql, riparto, importo=Decimal("100.00"))
    riparto_aprile = _riparto(db_sql, mese=4, file="aprile.xml")
    _quota(db_sql, riparto_aprile, importo=Decimal("300.00"))

    sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)

    assert _margini(sql, mese=3)["quote_riparto_spese"] == Decimal("100.00")
    assert _margini(sql, mese=4) is None, "ha scritto su un mese che non era il suo"


def test_riparto_somma_le_quote_di_piu_riparti_sulla_stessa_sede(db_sql, sql):
    _semina_utente_e_sedi(db_sql)
    primo = _riparto(db_sql, tipo="generale", file="uno.xml")
    _quota(db_sql, primo, importo=Decimal("60.00"))
    secondo = _riparto(db_sql, tipo="generale", file="due.xml")
    _quota(db_sql, secondo, importo=Decimal("40.00"))

    sql("SELECT public.riparto_quote_mensili(%s, 2026, 3)", UTENTE)

    assert _margini(sql)["quote_riparto_spese"] == Decimal("100.00")


def test_riparto_rifiuta_un_utente_nullo(db_sql, sql):
    """Senza la guardia scriverebbe su margini di sedi non identificate."""
    import psycopg

    with pytest.raises(psycopg.errors.RaiseException, match="p_user_id"):
        sql("SELECT public.riparto_quote_mensili(NULL, 2026, 3)")
    db_sql.rollback()
