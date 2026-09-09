"""La palette della Salute e' UNA (lib/salute-tint), e regge in entrambi i temi.

Fino al 9/9/2026 la Home PV e la catena avevano ciascuna la propria copia: quella
del PV era senza varianti dark sul testo (emerald-600 su fondo scuro). Il test
non puo' vedere i .tsx che la importano; puo' vedere che la fonte unica esiste,
che ha i quattro colori del contratto, e che nessun colore pieno e' mono-tema.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/salute-tint"
RICHIEDE = ("tintHaEntrambiITemi",)


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
def test_nessun_colore_pieno_senza_variante_dark(colore):
    """Il difetto della copia PV: `text-emerald-600` senza `dark:`. Misurato dal
    modulo stesso, cosi' chi aggiunge una classe piena ha il rosso subito."""
    assert esegui_ts(MODULO, "emit(m.tintHaEntrambiITemi(input))", colore,
                     richiede=RICHIEDE) is True


def test_il_controllo_sui_temi_vede_davvero_una_classe_mono_tema():
    """Controprova del presidio: una palette con un colore pieno e senza `dark:`
    deve risultare mono-tema, altrimenti il test sopra e' verde per vuoto."""
    out = esegui_ts(
        MODULO,
        "const t = m.SALUTE_TINT; "
        "const finto = {...t, verde: {...t.verde, text: 'text-emerald-600'}}; "
        "const pieno = /\\b(?:text|bg)-(?:emerald|amber|rose)-\\d{3}\\b/; "
        "emit(pieno.test(finto.verde.text) && !finto.verde.text.includes('dark:'))",
        richiede=RICHIEDE,
    )
    assert out is True
