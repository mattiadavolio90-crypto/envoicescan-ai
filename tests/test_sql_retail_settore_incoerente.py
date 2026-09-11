"""`v_categorie_settore_incoerenti`: il monitor della Fase 5, provato su un'anomalia
VERA e non solo sul caso pulito (migration 20260911170000).

Eseguito su un Postgres vero (tests/conftest_sql.py): una view si prova
ESEGUENDOLA, perche' un test che legge il testo della migration resterebbe verde
su una query che non seleziona niente.

Il monitor deve fare due cose opposte, e sono due tipi di errore diversi:

  - TACERE sui cambi legittimi. Sullo storico dei clienti veri il 42,3% dei cambi
    e' 'Da Classificare' → categoria reale e il 55,7% e' reale → reale: se il
    monitor li segnalasse, l'alert scatterebbe ogni giorno e verrebbe ignorato
    entro una settimana. Un monitor ignorato non esiste.
  - GRIDARE quando una riga di un RISTORANTE finisce in ARTICOLO DI VENDITA, la
    categoria che esiste solo per i negozi. E' il danno peggiore che il retail
    puo' fare ai clienti attuali, ed e' silenzioso.

«Un monitor che non ha mai visto rosso non si sa se funziona»: qui il rosso si
COSTRUISCE, riga per riga.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.sql

UTENTE = "cccccccc-3333-4333-8333-333333333333"
SEDE = "dddddddd-4444-4444-8444-444444444444"


def _semina_sede(db_sql, tipo: str = "ristorazione"):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'settore@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, tipo_attivita) "
            "VALUES (%s, %s, 'Sede Prova', '09876543210', %s)",
            (SEDE, UTENTE, tipo),
        )


def _registra_cambio(db_sql, old: str, new: str, sede=SEDE, tabella: str = "fatture"):
    """Scrive UNA riga nel registro, come farebbe il trigger su un UPDATE vero."""
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.category_change_log "
            "(table_name, target_id, user_id, ristorante_id, descrizione, "
            " old_categoria, new_categoria, source) "
            "VALUES (%s, '1', %s, %s, 'RIGA DI PROVA', %s, %s, 'db_trigger')",
            (tabella, UTENTE, sede, old, new),
        )


def _incoerenze(sql):
    return sql(
        "SELECT tipo_incoerenza, old_categoria, new_categoria, tipo_attivita "
        "FROM public.v_categorie_settore_incoerenti ORDER BY tipo_incoerenza"
    )


# ── Il rosso: l'anomalia che questa fase esiste per intercettare ─────────────

def test_una_riga_di_un_ristorante_in_articolo_di_vendita_e_incoerente(db_sql, sql):
    """IL CASO. Se questo test diventa verde per la ragione sbagliata (view che
    non seleziona niente), il monitor tace proprio quando serve."""
    _semina_sede(db_sql, tipo="ristorazione")
    _registra_cambio(db_sql, "CARNE", "ARTICOLO DI VENDITA")

    righe = _incoerenze(sql)

    assert len(righe) == 1, f"l'anomalia non e' stata vista: {righe}"
    assert righe[0][0] == "ristorazione_con_categoria_retail"
    assert righe[0][2] == "ARTICOLO DI VENDITA"
    assert righe[0][3] == "ristorazione"


def test_vede_l_anomalia_anche_da_da_classificare(db_sql, sql):
    """Una riga mai classificata che finisce in ARTICOLO DI VENDITA su un
    ristorante e' comunque sbagliata: il filtro e' sulla categoria d'ARRIVO, non
    sulla provenienza. Se qualcuno restringesse la view a `old <> 'Da
    Classificare'` per ridurre il rumore, perderebbe proprio il caso piu'
    probabile — una fattura nuova classificata col prompt sbagliato."""
    _semina_sede(db_sql, tipo="ristorazione")
    _registra_cambio(db_sql, "Da Classificare", "ARTICOLO DI VENDITA")

    righe = _incoerenze(sql)
    assert len(righe) == 1
    assert righe[0][0] == "ristorazione_con_categoria_retail"


def test_la_classe_speculare_negozio_con_categoria_food(db_sql, sql):
    """Un negozio che riceve CARNE: la Fase 1 lo esclude gia' in uscita dalla
    classificazione, quindi se arriva qui qualcosa ha aggirato il gate."""
    _semina_sede(db_sql, tipo="retail")
    _registra_cambio(db_sql, "Da Classificare", "CARNE")

    righe = _incoerenze(sql)
    assert len(righe) == 1
    assert righe[0][0] == "retail_con_categoria_food"
    assert righe[0][3] == "retail"


def test_la_view_regge_anche_senza_la_colonna_tipo_attivita(db_sql, sql):
    """Il caso che il harness NON copre da solo, e che il reviewer ha segnalato.

    `conftest_sql` applica ogni migration con prefisso >= alla data dello
    snapshot, quindi `20260910163000_add_tipo_attivita` e' SEMPRE gia' applicata
    qui: il caso «colonna assente» non lo esercita nessun test. Ma sul DB vivo,
    oggi, la colonna NON c'e' — le migration del branch si applicano solo al
    deploy — e se questa view non fosse creabile prima, l'ordine fra le due
    migration diventerebbe un vincolo da ricordare a memoria.

    Qui la colonna si toglie e si ri-crea la view: deve restare creabile, e ogni
    sede deve essere letta come 'ristorazione' (il default della migration).
    Tutto dentro la transazione del test, che viene annullata.
    """
    _semina_sede(db_sql, tipo="ristorazione")
    _registra_cambio(db_sql, "CARNE", "ARTICOLO DI VENDITA")

    corpo = (
        (RADICE / "supabase" / "migrations"
         / "20260911170000_v_categorie_settore_incoerenti.sql")
        .read_text(encoding="utf-8")
        .replace("BEGIN;", "").replace("COMMIT;", "")
    )
    with db_sql.cursor() as cur:
        cur.execute("DROP VIEW public.v_categorie_settore_incoerenti")
        cur.execute("ALTER TABLE public.ristoranti DROP COLUMN tipo_attivita")
        cur.execute(corpo)

    righe = _incoerenze(sql)
    assert len(righe) == 1, "senza la colonna la view smette di vedere l'anomalia"
    assert righe[0][3] == "ristorazione", "senza la colonna la sede va letta come ristorazione"


def test_la_view_e_creata_con_security_invoker(scalare):
    """COMPORTAMENTALE, non un grep sul sorgente.

    Il presidio gemello in test_retail_monitor_settore_endpoint.py cerca il
    letterale nel file, e la seconda lettura del reviewer ha misurato il suo
    punto cieco: commentando la riga `ALTER VIEW`, la view nasce SENZA l'opzione
    e quel test resta verde, perche' il letterale sopravvive nel commento.
    Qui si legge `pg_class.reloptions` sulla view davvero creata dall'harness.

    Cosa protegge: senza `security_invoker`, una view eredita SECURITY DEFINER
    dal ruolo che la crea e bypassa le RLS di chi la interroga — la ragione per
    cui 14 view sono state chiuse nell'audit anti-hacker del 20/6.
    """
    opzioni = scalare(
        "SELECT reloptions FROM pg_class "
        "WHERE relname = 'v_categorie_settore_incoerenti' AND relkind = 'v'"
    )
    assert opzioni is not None, "la view non dichiara nessuna opzione: security_invoker assente"
    assert "security_invoker=true" in opzioni, opzioni


# ── Il silenzio: tutto cio' che NON deve far scattare l'alert ────────────────

@pytest.mark.parametrize(
    "old,new",
    [
        ("Da Classificare", "CARNE"),          # 42,3% dello storico: lavoro normale
        ("SERVIZI E CONSULENZE", "UTENZE E LOCALI"),  # 55,7%: reale → reale
        ("CARNE", "Da Classificare"),          # 2,0%: torna in coda
        ("BEVANDE", "ACQUA"),                  # la coppia piu' frequente sui dati veri
    ],
)
def test_i_cambi_legittimi_di_un_ristorante_non_fanno_rumore(db_sql, sql, old, new):
    _semina_sede(db_sql, tipo="ristorazione")
    _registra_cambio(db_sql, old, new)

    assert _incoerenze(sql) == [], f"falso positivo su {old} → {new}: l'alert diventerebbe rumore"


def test_un_negozio_in_articolo_di_vendita_e_il_caso_giusto(db_sql, sql):
    """La stessa categoria che su un ristorante e' un'anomalia, su un negozio e'
    esattamente cio' che deve succedere. E' la prova che il discriminante e' il
    SETTORE e non la categoria da sola."""
    _semina_sede(db_sql, tipo="retail")
    _registra_cambio(db_sql, "Da Classificare", "ARTICOLO DI VENDITA")

    assert _incoerenze(sql) == []


def test_i_cambi_sulla_memoria_non_sono_cambi_sulle_fatture(db_sql, sql):
    """`category_change_log` registra anche `prodotti_utente` (113 righe sul live):
    la memoria delle correzioni non e' una riga di fattura e non muove nessun MOL.
    Senza il filtro su table_name il monitor conterebbe due cose diverse insieme."""
    _semina_sede(db_sql, tipo="ristorazione")
    _registra_cambio(db_sql, "CARNE", "ARTICOLO DI VENDITA", tabella="prodotti_utente")

    assert _incoerenze(sql) == []


def test_una_sede_di_un_altro_account_non_si_confonde(db_sql, sql):
    """Il join e' su ristorante_id: una riga di registro senza sede (ristorante_id
    NULL, come le 113 di prodotti_utente sul live) non deve agganciarsi a una
    sede a caso."""
    _semina_sede(db_sql, tipo="ristorazione")
    _registra_cambio(db_sql, "CARNE", "ARTICOLO DI VENDITA", sede=None)

    assert _incoerenze(sql) == []
