"""Le ore extra sono un sottoinsieme del turno, anche nelle somme del frontend.

**Il difetto, misurato il 5/9/2026.** Il modello e' stato invertito quel giorno:
le extra erano additive (09-17 con 2 extra = 10 ore), ora sono comprese nel
turno (= 8 ore di cui 2 di straordinario). Il clamp `min(extra, ore)` era stato
messo nel worker, in `margini.py`, in `workspace.py`, nel costo del singolo
turno e su /m — ma **non** nell'aggregazione per persona del tab Personale
desktop, che e' proprio la card dei totali che il cliente guarda.

Misurato eseguendo le due versioni: un turno da 8 ore con `ore_extra = 10`
(errore di battitura plausibile) mostrava **10 ore e 100 €** invece di 8 e 80 —
il **25% in piu'** sul monte ore e sul costo, in silenzio.

E' la terza volta che lo stesso fix parziale lascia indietro un consumatore: il
04/09 erano l'export Excel e /m, trovati dal code-reviewer. Per questo la regola
ora vive in un solo modulo (`lib/ore-turno.ts`) che desktop e mobile importano,
invece che in cinque copie di `Math.min`.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/ore-turno"
RICHIEDE = ["ripartisciOre"]


def _ripartisci(ore, extra):
    return esegui_ts(
        MODULO,
        "emit(m.ripartisciOre(input.ore, input.extra))",
        {"ore": ore, "extra": extra},
        richiede=RICHIEDE,
    )


def test_le_extra_sono_comprese_nel_turno_non_aggiunte():
    """Il caso nominale: 09-17 con 2 extra = 8 ore, di cui 2 di straordinario."""
    r = _ripartisci(8.0, 2.0)
    assert r["ordinarie"] == 6.0
    assert r["extra"] == 2.0
    assert r["ordinarie"] + r["extra"] == 8.0, "il totale deve restare le ore del turno"


def test_extra_oltre_le_ore_non_gonfia_il_monte_ore():
    """Il difetto misurato: 8 ore con 10 extra davano 10 ore, non 8."""
    r = _ripartisci(8.0, 10.0)
    assert r["extra"] == 8.0, "lo straordinario non puo' eccedere le ore lavorate"
    assert r["ordinarie"] == 0.0, "l'ordinario non deve mai andare negativo"
    assert r["ordinarie"] + r["extra"] == 8.0


def test_extra_pari_alle_ore_azzera_l_ordinario_senza_negativi():
    r = _ripartisci(6.0, 6.0)
    assert r["ordinarie"] == 0.0
    assert r["extra"] == 6.0


def test_senza_extra_tutto_e_ordinario():
    for assente in (None, 0):
        r = _ripartisci(7.5, assente)
        assert r["ordinarie"] == 7.5, f"con extra={assente!r}"
        assert r["extra"] == 0


def test_valori_negativi_non_producono_ore_negative():
    """Un dato sporco a DB non deve diventare un monte ore negativo."""
    r = _ripartisci(8.0, -3.0)
    assert r["extra"] == 0
    assert r["ordinarie"] == 8.0

    r = _ripartisci(-2.0, 1.0)
    assert r["ordinarie"] == 0
    assert r["extra"] == 0


def test_i_decimali_non_si_accumulano():
    """Senza arrotondamento 8.7 - 0.3 vale 8.399999999999999 in floating point.

    Non e' pedanteria: quel valore risale fino al monte ore mostrato in card.
    Il caso va scelto misurando (`node -e`), non a intuito: 7.7 - 0.3 fa 7.4
    esatto e passerebbe anche senza arrotondamento.
    """
    r = _ripartisci(8.7, 0.3)
    assert r["ordinarie"] == 8.4, r["ordinarie"]


# ── l'aggregazione per persona ───────────────────────────────────────────────
# Questi test esistono per una lezione precisa: i test sopra provano
# `ripartisciOre` in ISOLAMENTO, e il code-reviewer ha mostrato che restavano
# tutti verdi rimettendo `t.ore_extra ?? 0` senza clamp nel chiamante. La
# libreria era giusta e il consumatore no — che e' esattamente il difetto
# ripetuto tre volte. Per questo l'aggregazione e' stata spostata in `lib/`:
# non per eleganza, ma perche' li' il presidio puo' eseguirla davvero.

RICHIEDE_AGG = ["ripartisciOre", "aggregaPerPersona"]


def _aggrega(turni, ore_per_turno):
    """Chiama aggregaPerPersona col vero TypeScript.

    `ore` viaggia dentro ogni turno perche' le callback non attraversano il
    ponte JSON: il modulo le riceve come funzioni costruite di la'.
    """
    return esegui_ts(
        MODULO,
        "emit(m.aggregaPerPersona(input.turni, (t) => t.dipendente_id, (t) => t.ore))",
        {"turni": [dict(t, ore=o) for t, o in zip(turni, ore_per_turno)]},
        richiede=RICHIEDE_AGG,
    )


def _turno(**over):
    t = {"dipendente_id": "mario", "tipo_giorno": "turno", "mensile": False,
         "ore_extra": None, "costo_orario": None, "costo_orario_extra": None}
    t.update(over)
    return t


def test_aggregazione_extra_oltre_le_ore_non_gonfia_il_totale():
    """Il difetto vero, al punto d'uso: 8 ore con 10 extra restano 8 ore.

    ⚠️ Si asseriscono le COMPONENTI, non la somma. Una prima stesura controllava
    `oreStd + oreExt == 8.0` e `costoTot == 80.0`, e il code-reviewer ha
    mostrato che il mutante ci passava: senza clamp escono `oreStd = -2` e
    `oreExt = 10`, che sommano a 8, e `-20 + 100` che fa 80. **Gli errori si
    compensano esattamente nel totale.** Il cliente avrebbe visto in card -2h
    ordinarie e -20 EUR, con il totale giusto e un test verde.
    """
    r = _aggrega([_turno(ore_extra=10, costo_orario=10)], [8.0])
    assert r["oreStd"]["mario"] == 0.0, "ordinarie negative: manca il clamp nel chiamante"
    assert r["oreExt"]["mario"] == 8.0, "straordinario oltre le ore del turno"
    assert r["costoStd"]["mario"] == 0.0
    assert r["costoExt"]["mario"] == 80.0
    assert r["costoTot"]["mario"] == 80.0


def test_aggregazione_somma_piu_turni_della_stessa_persona():
    r = _aggrega(
        [_turno(ore_extra=2, costo_orario=10), _turno(ore_extra=1, costo_orario=10)],
        [8.0, 6.0],
    )
    assert r["oreStd"]["mario"] == 11.0     # (8-2) + (6-1)
    assert r["oreExt"]["mario"] == 3.0
    assert r["costoTot"]["mario"] == 140.0  # 14 ore x 10


def test_aggregazione_tariffa_extra_maggiorata():
    r = _aggrega([_turno(ore_extra=2, costo_orario=10, costo_orario_extra=15)], [8.0])
    assert r["costoStd"]["mario"] == 60.0
    assert r["costoExt"]["mario"] == 30.0
    assert r["costoTot"]["mario"] == 90.0


def test_aggregazione_extra_eccedenti_con_tariffa_maggiorata():
    """Le due dimensioni incrociate anche qui, non solo su costoTurnoGiornaliero.

    Stessa lacuna trovata nella funzione gemella: un test con extra eccedenti e
    uno con tariffa maggiorata, mai insieme. Qui le componenti sono gia'
    asserite (quindi il mutante muore comunque), ma il caso incrociato e' quello
    che vale in euro: 120 e non 130.
    """
    r = _aggrega([_turno(ore_extra=10, costo_orario=10, costo_orario_extra=15)], [8.0])
    assert r["oreStd"]["mario"] == 0.0
    assert r["oreExt"]["mario"] == 8.0
    assert r["costoStd"]["mario"] == 0.0
    assert r["costoExt"]["mario"] == 120.0
    assert r["costoTot"]["mario"] == 120.0


def test_aggregazione_riposi_e_assenze_restano_fuori():
    """Contarli diluirebbe la media oraria mostrata in card."""
    for tipo in ("riposo", "ferie", "malattia"):
        r = _aggrega([_turno(tipo_giorno=tipo, costo_orario=10)], [8.0])
        assert r["oreStd"] == {}, tipo
        assert r["costoTot"] == {}, tipo


def test_aggregazione_turno_senza_tariffa_conta_le_ore_ma_non_il_costo():
    """Senza costo_orario non si inventa un costo: e' il caso dei 107 turni reali."""
    r = _aggrega([_turno(costo_orario=None)], [8.0])
    assert r["oreStd"]["mario"] == 8.0
    assert r["costoTot"] == {}


def test_aggregazione_riga_mensile_usa_il_lordo_non_la_tariffa():
    """Dalla busta paga il costo e' un dato, non un ricalcolo."""
    r = _aggrega(
        [_turno(mensile=True, lordo_mensile=2000, importo_extra=300, ore_extra=20)],
        [160.0],
    )
    assert r["costoStd"]["mario"] == 1700.0
    assert r["costoExt"]["mario"] == 300.0
    assert r["costoTot"]["mario"] == 2000.0
    assert r["oreExt"]["mario"] == 20.0


def test_aggregazione_tiene_separate_le_persone():
    r = _aggrega(
        [_turno(dipendente_id="mario", costo_orario=10),
         _turno(dipendente_id="lucia", costo_orario=20)],
        [8.0, 4.0],
    )
    assert r["costoTot"]["mario"] == 80.0
    assert r["costoTot"]["lucia"] == 80.0
    assert r["oreStd"]["lucia"] == 4.0


# ── il costo del singolo turno ───────────────────────────────────────────────
# Stessa formula in tre punti (tab desktop, /m, riepilogo mensile) e uno era
# rimasto indietro. Ora e' una sola funzione, provata qui.

RICHIEDE_COSTO = ["ripartisciOre", "costoTurnoGiornaliero"]


def _costo(ore, extra, co, coExt=None):
    return esegui_ts(
        MODULO,
        "emit(m.costoTurnoGiornaliero(input.ore, input.extra, input.co, input.coExt))",
        {"ore": ore, "extra": extra, "co": co, "coExt": coExt},
        richiede=RICHIEDE_COSTO,
    )


def test_costo_turno_senza_tariffa_e_zero_non_un_errore():
    """Il caso dei 107 turni reali: costo_orario NULL su tutti."""
    assert _costo(8.0, 2.0, None) == 0


def test_senza_tariffa_standard_non_si_paga_nemmeno_lo_straordinario():
    """costo_orario NULL ma costo_orario_extra valorizzato: totale 0, non 30.

    Il guard `if (costoOrario == null) return 0` sembra ridondante — un mutante
    che lo sostituisce con `costoOrario ?? 0` passa tutti gli altri test, perche'
    moltiplicare per zero da' comunque zero. Ma con la sola tariffa extra
    impostata il fallback inventa **30 EUR** da un turno di cui non conosciamo
    il costo, e quel numero finirebbe nel MOL. Misurato affiancando le due
    versioni, non dedotto: il mutante era sopravvissuto e diceva che mancava
    questo test, non che la riga fosse inutile.
    """
    assert _costo(8.0, 2.0, None, 15.0) == 0


def test_costo_turno_extra_oltre_le_ore_non_gonfia_l_importo():
    """8 ore a 10 EUR restano 80, anche dichiarando 10 ore di straordinario."""
    assert _costo(8.0, 10.0, 10.0) == 80.0


def test_costo_turno_tariffa_extra_si_applica_solo_alle_extra():
    assert _costo(8.0, 2.0, 10.0, 15.0) == 90.0     # 6x10 + 2x15


def test_costo_turno_extra_eccedenti_con_tariffa_maggiorata():
    """Le DUE dimensioni insieme: extra oltre le ore E tariffa extra diversa.

    ⚠️ Il caso che mancava, trovato dal code-reviewer al terzo giro. C'era un
    test con extra eccedenti (ma tariffa unica) e uno con tariffa maggiorata (ma
    extra in-range): **le due dimensioni non si incrociavano mai**, e senza
    clamp il mutante restava verde perche' con una sola tariffa gli errori si
    compensano (-2x10 + 10x10 = 80, come il caso corretto).

    Con tariffe diverse non si compensano piu': 130 EUR invece di 120. E'
    esattamente il caso nominale dello straordinario maggiorato, cioe' il motivo
    per cui il campo esiste.
    """
    assert _costo(8.0, 10.0, 10.0, 15.0) == 120.0   # 0x10 + 8x15, non 8x15+(-2)x10


def test_costo_turno_senza_tariffa_extra_usa_quella_standard():
    assert _costo(8.0, 2.0, 10.0, None) == 80.0


def test_costo_turno_tutto_straordinario():
    assert _costo(6.0, 6.0, 10.0, 20.0) == 120.0
