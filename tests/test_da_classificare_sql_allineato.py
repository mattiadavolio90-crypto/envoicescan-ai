"""La regola «Da Classificare» vale anche nelle RPC SQL (R11).

**Perché questo file esiste.** R6 ha dato una fonte unica al perimetro Python:
`CATEGORIA_NON_CLASSIFICATA` in `config/constants.py`, usata dai 7 punti che
filtrano le righe non classificate fuori dal MOL. Ma la stessa regola di dominio
vive **anche dentro le RPC PostgreSQL**, e una funzione PL/pgSQL non può
importare una costante Python.

**Misurato il 3/09/2026 sul DB di produzione** (`pg_proc`, non i file):
**7 RPC vive** contengono la regola (13 occorrenze su 12 file di migration) — `costi_automatici_mensili`,
`costi_automatici_mensili_gruppo`, `gruppo_peso_categoria`,
`gruppo_prezzi_categoria`, `gruppo_spesa_pivot`, `gruppo_spreco_fb_categorie`,
`gruppo_tag_descrizioni` — tutte con la grafia corretta e lo stesso filtro
`categoria <> 'Da Classificare'`.

**Cosa protegge questo test.** Non può interrogare il DB (la suite mockizza
Supabase), quindi guarda **i file di migration**, che sono ciò che verrà
deployato. Se qualcuno cambia la stringa in Python senza toccarle — o la scrive
con la grafia sbagliata in una migration nuova — le due sponde divergono: il
Python esclude le righe dal MOL e l'SQL no, o viceversa. Due totali diversi
nella stessa pagina, che è il difetto già pagato da questo progetto.

⚠️ **Le migration non si riscrivono**: sono lo storico di ciò che è stato
applicato. Questo test non chiede di modificarle, chiede che una migration
**nuova** usi la stessa stringa.
"""
import pathlib
import re

import pytest

from config.constants import CATEGORIA_NON_CLASSIFICATA

_MIGRATIONS = pathlib.Path(__file__).resolve().parents[1] / "supabase" / "migrations"

# Il filtro di esclusione, in codice eseguibile (non nei commenti `--`).
#
# Cerca SOLO i confronti che nominano questa regola: `categoria <> '...'`
# compare anche per `'📝 NOTE E DICITURE'`, che è un'altra esclusione legittima
# e non c'entra con R11. Il pattern richiede quindi che il valore inizi per
# "Da Cla", così intercetta anche la grafia errata `'Da Clasificare'` — che è
# esattamente il caso che questo test deve far fallire.
_FILTRO = re.compile(r"categoria\s*<>\s*'(Da Cla[^']*)'", re.I)


def _sql_vivo(percorso: pathlib.Path) -> str:
    return "\n".join(
        r for r in percorso.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith("--")
    )


def _file_col_filtro():
    for f in sorted(_MIGRATIONS.glob("*.sql")):
        if _FILTRO.search(_sql_vivo(f)):
            yield f


def test_esistono_migration_col_filtro():
    """Se questo cade, il filtro è sparito dall'SQL: o è stato rimosso davvero
    (e allora le righe non classificate entrano nel MOL), o è stato riscritto in
    una forma che questo test non riconosce più."""
    trovati = list(_file_col_filtro())
    assert len(trovati) >= 12, (
        f"i file di migration col filtro sono {len(trovati)}, attesi almeno 12 "
        "(13 occorrenze: `costi_automatici_catchall_food` ne ha due). "
        "Se sono meno, o il filtro è sparito o ha cambiato forma"
    )


@pytest.mark.parametrize(
    "percorso", list(_file_col_filtro()), ids=lambda p: p.name[:40]
)
def test_ogni_filtro_sql_usa_la_stessa_stringa_del_python(percorso):
    """Le due sponde devono confrontare **lo stesso valore**.

    La variante errata storica `'Da Clasificare'` (una sola "s") è il caso reale
    da cui nasce questo controllo: in SQL non darebbe errore, filtrerebbe
    semplicemente nulla — e le righe non classificate rientrerebbero nel MOL in
    silenzio.
    """
    valori = set(_FILTRO.findall(_sql_vivo(percorso)))
    diversi = valori - {CATEGORIA_NON_CLASSIFICATA}
    assert diversi == set(), (
        f"{percorso.name}: il filtro confronta {diversi}, non "
        f"'{CATEGORIA_NON_CLASSIFICATA}'. Le RPC e il Python escluderebbero "
        "righe diverse dal MOL"
    )


def test_le_sette_rpc_vive_sono_dichiarate():
    """Il conto misurato a DB il 3/9, scritto qui perché non si perda.

    Non è un test sul database (la suite lo mockizza): è il promemoria di quali
    RPC portano la regola, così chi ne aggiunge una sa che deve entrare in lista
    — e chi legge sa che il perimetro SQL esiste.
    """
    attese = {
        "costi_automatici_mensili",
        "costi_automatici_mensili_gruppo",
        "gruppo_peso_categoria",
        "gruppo_prezzi_categoria",
        "gruppo_spesa_pivot",
        "gruppo_spreco_fb_categorie",
        "gruppo_tag_descrizioni",
    }
    testo = "\n".join(_sql_vivo(f) for f in _file_col_filtro())
    mancanti = {r for r in attese if f"FUNCTION public.{r}(" not in testo
                and f"FUNCTION {r}(" not in testo}
    assert mancanti == set(), (
        f"queste RPC portano il filtro a DB ma non si trovano nelle migration "
        f"col filtro: {mancanti}. Se una è stata rinominata, aggiorna la lista"
    )
