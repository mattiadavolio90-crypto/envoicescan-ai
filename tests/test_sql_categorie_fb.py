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
qualunque mutazione del corpo.
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


def test_spreco_fb_usa_le_stesse_categorie_del_riparto(sql):
    """La lista dentro `gruppo_spreco_fb_categorie` e' la terza copia della stessa cosa.

    Non si puo' interrogare la funzione senza dati, quindi si confronta la
    lista che il suo corpo contiene: qui l'oggetto del test E' il testo del
    corpo, perche' il difetto da prevenire e' due liste che divergono. Il
    confronto e' comunque sul DB vero (`pg_get_functiondef`), non sul file di
    migration, che potrebbe non essere quello applicato.
    """
    corpo = sql(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'gruppo_spreco_fb_categorie'"
    )[0][0]
    mancanti = [c for c in CATEGORIE_FOOD_BEVERAGE if f"'{c}'" not in corpo]
    assert not mancanti, (
        f"gruppo_spreco_fb_categorie non elenca {mancanti}: quelle righe "
        "sparirebbero dal cruscotto sprechi senza alcun errore"
    )


def test_peso_categoria_esclude_esattamente_le_spese_generali(sql):
    """`gruppo_peso_categoria` esclude le spese per NOME, con una quarta copia.

    Se una spesa generale non fosse elencata li', entrerebbe nel peso delle
    categorie F&B e ne diluirebbe le percentuali.
    """
    corpo = sql(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'gruppo_peso_categoria'"
    )[0][0]
    mancanti = [c for c in CATEGORIE_SPESE_GENERALI if f"'{c}'" not in corpo]
    assert not mancanti, (
        f"gruppo_peso_categoria non esclude {mancanti}: quelle spese entrano "
        "nel peso delle categorie F&B"
    )
