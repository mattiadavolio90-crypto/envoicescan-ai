"""Le liste di categorie F&B ricopiate dentro il SQL restano allineate a Python.

Il perimetro
============
`config/constants.py` dichiara le 25 categorie Food & Beverage e le 4 di spese
generali. Quelle stesse liste sono RICOPIATE, a mano, dentro tre funzioni del
database (misurato il 7/9/2026 leggendo i corpi dal DB live):

  * `_riparto_categoria_is_fb`  — decide se una quota di riparto pesa sul F&B o
    sulle spese: e' l'unica cosa che separa i due addendi del MOL;
  * `gruppo_spreco_fb_categorie` — filtra le righe del cruscotto sprechi;
  * `gruppo_peso_categoria` — esclude le spese generali dal peso categorie.

Oggi le tre copie coincidono con Python. Nessun test lo verificava: aggiungere
una categoria in `constants.py` e dimenticare il DB avrebbe spostato dei costi
dal F&B alle spese generali (o viceversa) senza rompere nulla di visibile — il
MOL totale resta identico, cambiano le sue componenti, ed e' esattamente la
classe di errore che un aggregato nasconde.

Questi test ESEGUONO le funzioni su un Postgres vero (vedi
tests/conftest_sql.py): non leggono il testo delle migration, che sopravvive a
qualunque mutazione del corpo. Anche le due aggregazioni si provano chiamandole
su righe seminate, non ispezionandone il sorgente: un assert sul testo passa
anche se un filtro nuovo esclude una categoria lasciando la lista intatta.
"""
from __future__ import annotations

import pytest

from config.constants import (
    CATEGORIE_FOOD_BEVERAGE,
    CATEGORIE_SPESE_GENERALI,
)

pytestmark = pytest.mark.sql


@pytest.mark.parametrize("categoria", CATEGORIE_FOOD_BEVERAGE)
def test_riparto_riconosce_ogni_categoria_fb(scalare, categoria):
    """Ogni categoria F&B di Python pesa sul F&B anche nel riparto."""
    assert scalare("SELECT public._riparto_categoria_is_fb(%s)", categoria) is True, (
        f"{categoria!r} e' F&B in config/constants.py ma _riparto_categoria_is_fb "
        "la classifica come spesa generale: le sue quote finirebbero nel secchio "
        "sbagliato del MOL"
    )


@pytest.mark.parametrize("categoria", CATEGORIE_SPESE_GENERALI)
def test_riparto_non_scambia_le_spese_per_fb(scalare, categoria):
    """E nessuna categoria di spesa generale viene contata come F&B."""
    assert scalare("SELECT public._riparto_categoria_is_fb(%s)", categoria) is False, (
        f"{categoria!r} e' una spesa generale ma il riparto la conta nel F&B: "
        "gonfia i costi F&B e sgonfia le spese, a MOL invariato"
    )


def test_riparto_non_conosce_categorie_che_python_non_ha(sql):
    """Nessuna categoria in piu' nella copia SQL: il confronto va in due direzioni.

    Verificare solo che le 29 di Python siano classificate bene lascerebbe
    passare una 30esima riga rimasta nel SQL dopo una rinomina — che
    classificherebbe come F&B una categoria che l'app non usa piu'.
    """
    note = set(CATEGORIE_FOOD_BEVERAGE)
    righe = sql(
        "SELECT c FROM unnest(%s::text[]) AS c WHERE public._riparto_categoria_is_fb(c)",
        sorted(note),
    )
    riconosciute = {r[0] for r in righe}
    assert riconosciute == note, (
        "la lista F&B dentro _riparto_categoria_is_fb non coincide con "
        f"CATEGORIE_FOOD_BEVERAGE: solo in SQL {sorted(riconosciute - note)}, "
        f"solo in Python {sorted(note - riconosciute)}"
    )


def test_riparto_e_insensibile_a_spazi_e_maiuscole(scalare):
    """Il corpo fa upper(btrim(...)): e' un comportamento, non un dettaglio.

    Le categorie arrivano da `fatture.categoria`, scritta anche da script e
    dall'AI: se la normalizzazione sparisse, '  carne ' smetterebbe di pesare
    sul F&B senza che nulla segnali l'errore.
    """
    assert scalare("SELECT public._riparto_categoria_is_fb(%s)", "  carne ") is True


def test_riparto_su_categoria_assente_non_esplode(scalare):
    """NULL e stringa vuota valgono 'non F&B', non un errore.

    `riparto_quote_mensili` chiama questa funzione dentro un FILTER su righe
    che possono avere categoria NULL (quota senza categoria: vale il `tipo`
    dell'header). Se qui sollevasse, il ricalcolo delle quote fallirebbe.
    """
    assert scalare("SELECT public._riparto_categoria_is_fb(NULL)") is False
    assert scalare("SELECT public._riparto_categoria_is_fb('')") is False


def _semina_una_riga_per_categoria(db_sql, categorie):
    """Una fattura per categoria, tutte nella stessa sede e nello stesso mese.

    Serve a chiamare davvero le funzioni di aggregazione: senza righe
    restituiscono l'insieme vuoto e qualunque filtro sembrerebbe corretto.
    """
    utente = "11111111-1111-4111-8111-111111111111"
    sede = "22222222-2222-4222-8222-222222222222"
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'prova@oneflux.test', 'x', 'Prova')",
            (utente,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva) "
            "VALUES (%s, %s, 'Sede di prova', '01234567890')",
            (sede, utente),
        )
        for numero, categoria in enumerate(categorie, start=1):
            cur.execute(
                "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
                "numero_riga, data_documento, fornitore, descrizione, categoria, "
                "quantita, prezzo_unitario, totale_riga) "
                "VALUES (%s, %s, 'prova.xml', %s, DATE '2026-03-10', 'Fornitore', "
                "%s, %s, 1, 100, 100)",
                (utente, sede, numero, f"riga {categoria}", categoria),
            )
    return utente, sede


def test_spreco_fb_ritorna_esattamente_le_categorie_fb(db_sql, sql):
    """`gruppo_spreco_fb_categorie` aggrega le F&B e nient'altro.

    Si chiama la funzione su righe vere invece di leggerne il corpo: un test sul
    TESTO passerebbe anche se qualcuno aggiungesse un filtro che esclude una
    categoria pur lasciando la lista intatta (provato: mutante sopravvissuto).
    """
    tutte = list(CATEGORIE_FOOD_BEVERAGE) + list(CATEGORIE_SPESE_GENERALI)
    _utente, sede = _semina_una_riga_per_categoria(db_sql, tutte)

    righe = sql(
        "SELECT categoria FROM public.gruppo_spreco_fb_categorie("
        "%s::uuid[], DATE '2026-03-01', DATE '2026-03-31')",
        [sede],
    )
    ottenute = {r[0] for r in righe}
    attese = set(CATEGORIE_FOOD_BEVERAGE)
    assert ottenute == attese, (
        "il cruscotto sprechi non aggrega le stesse categorie F&B di Python: "
        f"mancano {sorted(attese - ottenute)}, in piu' {sorted(ottenute - attese)}"
    )


def test_peso_categoria_esclude_le_spese_generali(db_sql, sql):
    """`gruppo_peso_categoria` pesa solo le F&B: le spese generali non diluiscono.

    Se una spesa generale entrasse nel calcolo, le percentuali di tutte le
    categorie F&B scenderebbero senza che nulla segnali l'errore.
    """
    tutte = list(CATEGORIE_FOOD_BEVERAGE) + list(CATEGORIE_SPESE_GENERALI)
    _utente, sede = _semina_una_riga_per_categoria(db_sql, tutte)

    righe = sql(
        "SELECT categoria, peso_perc FROM public.gruppo_peso_categoria("
        "%s::uuid[], DATE '2026-03-01', DATE '2026-03-31')",
        [sede],
    )
    ottenute = {r[0] for r in righe}
    intruse = ottenute & set(CATEGORIE_SPESE_GENERALI)
    assert not intruse, (
        f"{sorted(intruse)} sono spese generali ma pesano fra le categorie F&B: "
        "diluiscono le percentuali di tutte le altre"
    )
    assert ottenute == set(CATEGORIE_FOOD_BEVERAGE), (
        "mancano dal peso categorie: "
        f"{sorted(set(CATEGORIE_FOOD_BEVERAGE) - ottenute)}"
    )
    # Le righe seminate hanno tutte lo stesso importo: i pesi devono sommare a 100.
    totale = sum(float(r[1]) for r in righe)
    assert abs(totale - 100.0) < 0.01, (
        f"i pesi sommano a {totale:.2f} invece di 100: la base del calcolo "
        "include righe che non compaiono nel risultato"
    )
