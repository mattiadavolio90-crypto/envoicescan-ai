"""La palette della Salute e' UNA (lib/salute-tint), e regge in entrambi i temi.

Fino al 9/9/2026 la Home PV e la catena avevano ciascuna la propria copia: quella
del PV era senza varianti dark sul testo (emerald-600 su fondo scuro). Dal
18/09/2026 la palette usa i token (`positivo`/`incerto`/`negativo`), che portano
i due temi da soli: il difetto da cercare non e' piu' il `dark:` mancante ma la
classe di palette cruda, che ha un valore solo. Il test non puo' vedere i .tsx
che la importano; puo' vedere che la fonte unica esiste, che ha i quattro colori
del contratto, e che nessuna classe e' cruda.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/salute-tint"
RICHIEDE = ("tintUsaSoloToken",)


def _tint():
    return esegui_ts(MODULO, "emit(m.SALUTE_TINT)", richiede=RICHIEDE)


def test_i_quattro_colori_del_contratto_ci_sono_tutti():
    """verde/giallo/rosso sono il tipo `Salute.colore` del PV; grigio e' il
    "non lo so" della catena (Fase 2). Una chiave assente e' un crash a render."""
    assert set(_tint().keys()) == {"verde", "giallo", "rosso", "grigio"}


@pytest.mark.parametrize("colore", ["verde", "giallo", "rosso", "grigio"])
def test_ogni_colore_ha_le_chiavi_che_le_due_viste_usano(colore):
    chiavi = set(_tint()[colore].keys())
    assert {"ring", "text", "badge", "card", "orb1", "orb2", "dot", "label"} <= chiavi


@pytest.mark.parametrize("colore", ["verde", "giallo", "rosso", "grigio"])
def test_nessuna_classe_di_palette_cruda(colore):
    """Il difetto della copia PV era `text-emerald-600` senza `dark:`; coi token
    la stessa classe e' un difetto anche col `dark:`, perche' scavalca il tema.
    Misurato dal modulo stesso, cosi' chi la aggiunge ha il rosso subito."""
    assert esegui_ts(MODULO, "emit(m.tintUsaSoloToken(m.SALUTE_TINT[input]))",
                     colore, richiede=RICHIEDE) is True


@pytest.mark.parametrize("chiave,cruda", [
    ("text", "text-emerald-600 dark:text-emerald-400"),
    ("badge", "bg-amber-50 text-incerto"),
    ("card", "bg-gradient-to-br from-sky-500/10 to-background"),
    ("dot", "bg-rose-500"),
])
def test_la_guardia_vede_davvero_una_classe_cruda(chiave, cruda):
    """Controprova sulla FUNZIONE vera, non su una regex ricopiata nel test: una
    palette con una classe cruda in qualunque chiave deve essere bocciata, e
    anche se ha la variante `dark:` (il vecchio criterio l'avrebbe promossa)."""
    out = esegui_ts(
        MODULO,
        "emit(m.tintUsaSoloToken({...m.SALUTE_TINT.verde, [input.chiave]: input.cruda}))",
        {"chiave": chiave, "cruda": cruda},
        richiede=RICHIEDE,
    )
    assert out is False
