"""Le formule del tag di gruppo, che finiscono in uno `style` o in un `className`.

`lib/catena-tag.ts` e' l'estrazione di 12 espressioni che stavano dentro
`(app)/catena/gruppo-tag-section.tsx`, 721 righe fra hook e JSX. Finche' erano
li' nessun test poteva raggiungerle: `helpers_ts.py` non monta React e
`apps/web/` non ha un runner proprio (ce l'avesse, `deploy-vercel.yml` scatta su
`apps/web/**` e ogni test farebbe partire un deploy di produzione).

**Cosa questi test provano, e cosa no.** Provano che le funzioni estratte
calcolino quello che calcolavano nel .tsx. NON provano che il componente le
chiami con gli argomenti giusti: il rendering resta non testato. E' un buco
dichiarato, non taciuto — la mitigazione applicata e' che l'estrazione e' stata
verificata sul diff (solo import e chiamate) e, per le due regex di slug, contro
l'espressione originale di HEAD su 236 input avversi.

**Perche' le fixture hanno valori negativi.** Il 1/9 il reviewer ha trovato che
fixture di soli positivi non distinguono `0` da `-Infinity`: perdono entrambi
contro tutto. Qui il negativo non e' un caso di scuola — `spesa` arriva netta
delle note di credito (`routers/gruppo.py:2233` lo dice), quindi un tag con un
reso piu' grande degli acquisti ha spesa negativa sul serio.

**Perche' gli assert sono assoluti.** Sempre il 1/9: asserire che due output
combacino fra loro non prova che siano giusti (un path SVG sbagliato in modo
coerente passa). Su nomi di file e intestazioni Excel si asserisce la stringa
intera, non "contiene".
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/catena-tag"
RICHIEDE = [
    "estremiPrezzo", "classePrezzo", "larghezzaBarra", "altezzaBarraTrend",
    "massimoSpesa", "analisiVuota", "soloUnPvConSpesa", "tuttiSelezionati",
    "slugPeriodo", "nomeFileExport", "righeExportPv", "righeExportFornitori",
]

# Le classi si leggono dal modulo: riscriverle qui significherebbe che un test
# verde non dice piu' niente sul colore che il cliente vede davvero.
MIN_CLS, MAX_CLS = esegui_ts(
    MODULO, "emit([m.CLASSE_PREZZO_MIN, m.CLASSE_PREZZO_MAX]);", richiede=RICHIEDE
)


def _ts(espr, arg=None):
    return esegui_ts(MODULO, espr, argomento=arg, richiede=RICHIEDE)


def _pv(*prezzi):
    return [{"prezzo_medio": p} for p in prezzi]


# ─── estremiPrezzo: la soglia dei 2 valori ──────────────────────────────────

def test_estremi_con_due_prezzi():
    assert _ts("emit(m.estremiPrezzo(input))", _pv(3, 7)) == {"minPrezzo": 3, "maxPrezzo": 7}


def test_estremi_un_solo_prezzo_non_confronta():
    """Con un PV solo non esiste un 'migliore': l'evidenza sarebbe rumore."""
    assert _ts("emit(m.estremiPrezzo(input))", _pv(3)) == {"minPrezzo": None, "maxPrezzo": None}


def test_estremi_i_null_si_scartano_prima_di_contare():
    """3 PV di cui 2 senza prezzo NON superano la soglia: conta chi ha il dato."""
    assert _ts("emit(m.estremiPrezzo(input))", _pv(5, None, None)) == {
        "minPrezzo": None, "maxPrezzo": None
    }


def test_estremi_lista_vuota_e_nulla():
    assert _ts("emit(m.estremiPrezzo([]))") == {"minPrezzo": None, "maxPrezzo": None}
    assert _ts("emit(m.estremiPrezzo(null))") == {"minPrezzo": None, "maxPrezzo": None}
    assert _ts("emit(m.estremiPrezzo(undefined))") == {"minPrezzo": None, "maxPrezzo": None}


def test_estremi_con_prezzo_negativo():
    """Un prezzo negativo e' anomalo ma non impossibile: va nel minimo, non ignorato."""
    assert _ts("emit(m.estremiPrezzo(input))", _pv(-1, 5, 12)) == {"minPrezzo": -1, "maxPrezzo": 12}


def test_estremi_prezzi_tutti_uguali():
    assert _ts("emit(m.estremiPrezzo(input))", _pv(4, 4, 4)) == {"minPrezzo": 4, "maxPrezzo": 4}


# ─── classePrezzo ───────────────────────────────────────────────────────────

def test_classe_prezzo_minimo_e_verde():
    assert _ts("emit(m.classePrezzo(3, 3, 7))") == MIN_CLS


def test_classe_prezzo_massimo_e_rosso():
    assert _ts("emit(m.classePrezzo(7, 3, 7))") == MAX_CLS


def test_classe_prezzo_intermedio_e_muto():
    assert _ts("emit(m.classePrezzo(5, 3, 7))") == ""


def test_classe_prezzo_null_e_muto():
    """Il trattino '—' non si colora: senza la guardia, null === null sarebbe true."""
    assert _ts("emit(m.classePrezzo(null, null, null))") == ""


@pytest.mark.parametrize("prezzo", [12.5, 0, -3])
def test_classe_prezzo_muta_quando_gli_estremi_non_esistono(prezzo):
    """Sotto la soglia dei 2 valori gli estremi sono `null` e NIENTE si colora.

    Non e' un caso di scuola: e' il tag con un solo PV, il piu' comune. E qui
    l'uguaglianza stretta non e' intercambiabile con un confronto relazionale —
    in JS `null` si coerce a 0 con `>=` e `<=` ma non con `===`, quindi
    `prezzo >= null` sarebbe vero per ogni prezzo positivo e colorerebbe di rosso
    tutti i PV di un tag che oggi non ne colora nessuno.

    Trovato da due mutanti sopravvissuti (`=== min` -> `<= min`, `=== max` ->
    `>= max`): non erano equivalenze, era questa fixture che mancava.
    """
    assert _ts(f"emit(m.classePrezzo({prezzo}, null, null))") == ""


def test_fotografa_prezzi_uniformi_prendono_entrambe_le_classi():
    """ANOMALIA: con min === max ogni PV e' insieme il piu' caro e il piu' economico.

    `cellTone` (catena-confronti.ts) ha la guardia `v !== ex.worst` per questo
    caso; qui non c'e' mai stata. A schermo tailwind-merge tiene l'ultima, quindi
    un gruppo a prezzo uniforme si mostra tutto "caro". Fotografato, non corretto:
    e' un cambio di cio' che si vede, e vuole la sua finestra di deploy.
    """
    assert _ts("emit(m.classePrezzo(5, 5, 5))") == f"{MIN_CLS} {MAX_CLS}"


def test_classe_prezzo_include_la_variante_dark():
    """Assert assoluto: 'contiene emerald' sopravviverebbe alla perdita di dark:."""
    assert "dark:" in MIN_CLS and "dark:" in MAX_CLS


# ─── larghezzaBarra / altezzaBarraTrend ─────────────────────────────────────

@pytest.mark.parametrize("v,mx,atteso", [
    (30, 100, "30%"),
    (100, 100, "100%"),
    (0, 100, "0%"),
    (1, 3, "33.33333333333333%"),
])
def test_larghezza_barra(v, mx, atteso):
    assert _ts(f"emit(m.larghezzaBarra({v}, {mx}))") == atteso


@pytest.mark.parametrize("mx", [0, -100])
def test_larghezza_barra_max_non_positivo(mx):
    """La guardia e' `> 0`, non `!== 0`: un massimo negativo non deve dividere."""
    assert _ts(f"emit(m.larghezzaBarra(30, {mx}))") == "0%"


def test_fotografa_larghezza_barra_negativa():
    """ANOMALIA: spesa netta di note di credito puo' essere negativa -> '-30%'.

    Il browser tratta una larghezza negativa come 0: la barra sparisce e non si
    distingue da una spesa nulla.
    """
    assert _ts("emit(m.larghezzaBarra(-30, 100))") == "-30%"


def test_altezza_trend_ha_il_pavimento_a_quattro():
    """Un mese quasi a zero resta visibile come colonnina invece di sparire."""
    assert _ts("emit(m.altezzaBarraTrend(0, 100))") == "4%"
    assert _ts("emit(m.altezzaBarraTrend(1, 100))") == "4%"


def test_altezza_trend_sopra_il_pavimento():
    assert _ts("emit(m.altezzaBarraTrend(30, 100))") == "30%"


def test_fotografa_trend_negativo_appare_positivo():
    """ANOMALIA: Math.max(4, -30) = 4. Un mese in perdita si disegna come una
    barra positiva bassa, indistinguibile da un mese di spesa minima."""
    assert _ts("emit(m.altezzaBarraTrend(-30, 100))") == "4%"


def test_le_due_barre_divergono_di_proposito():
    """La divergenza e' dichiarata: unificarle cambierebbe i pixel di una delle due."""
    assert _ts("emit([m.larghezzaBarra(0, 100), m.altezzaBarraTrend(0, 100)])") == ["0%", "4%"]


# ─── massimoSpesa ───────────────────────────────────────────────────────────

def test_massimo_spesa_positive():
    assert _ts("emit(m.massimoSpesa(input))", [{"spesa": 10}, {"spesa": 40}, {"spesa": 25}]) == 40


def test_massimo_spesa_lista_vuota_non_e_meno_infinito():
    """Senza lo 0 iniziale uscirebbe -Infinity, che in uno style diventa '-Infinity%'."""
    assert _ts("emit(m.massimoSpesa([]))") == 0


def test_massimo_spesa_tutte_negative_e_zero():
    """Il pavimento a 0 restituisce un valore che NON e' nella lista.

    Con fixture di soli positivi questo comportamento e' invisibile: e' il caso
    che il mutante `Math.max(...)` senza lo 0 supererebbe indisturbato.
    """
    assert _ts("emit(m.massimoSpesa(input))", [{"spesa": -100}, {"spesa": -50}]) == 0


def test_massimo_spesa_mista():
    assert _ts("emit(m.massimoSpesa(input))", [{"spesa": -100}, {"spesa": 7}]) == 7


# ─── analisiVuota / soloUnPvConSpesa ────────────────────────────────────────

def test_analisi_vuota_senza_dati():
    assert _ts("emit(m.analisiVuota(null))") is True
    assert _ts("emit(m.analisiVuota(undefined))") is True


def test_analisi_vuota_tutti_a_zero():
    assert _ts("emit(m.analisiVuota({per_pv: input}))", [{"spesa": 0}, {"spesa": 0}]) is True


def test_analisi_non_vuota_se_uno_ha_spesa():
    assert _ts("emit(m.analisiVuota({per_pv: input}))", [{"spesa": 0}, {"spesa": 5}]) is False


def test_analisi_non_vuota_con_sole_note_di_credito():
    """Spesa negativa NON e' vuoto: c'e' qualcosa da mostrare.

    E' il motivo per cui `=== 0` non va riscritto in `<= 0`. Serve una fixture
    negativa per vederlo.
    """
    assert _ts("emit(m.analisiVuota({per_pv: input}))", [{"spesa": -40}]) is False


def test_analisi_vuota_per_pv_vuoto():
    """`every` su lista vuota e' true: nessun PV = niente da mostrare."""
    assert _ts("emit(m.analisiVuota({per_pv: []}))") is True


def test_solo_un_pv_con_spesa():
    assert _ts("emit(m.soloUnPvConSpesa(input))", [{"spesa": 10}, {"spesa": 0}]) is True


def test_solo_un_pv_ma_e_l_unico():
    """Con un PV solo l'hint 'aggiungi le altre sedi' non ha senso: length > 1."""
    assert _ts("emit(m.soloUnPvConSpesa(input))", [{"spesa": 10}]) is False


def test_due_pv_con_spesa_non_e_il_caso():
    assert _ts("emit(m.soloUnPvConSpesa(input))", [{"spesa": 10}, {"spesa": 5}]) is False


def test_solo_un_pv_con_spesa_ignora_i_negativi():
    """`> 0` e non `>= 0`: un PV a spesa negativa non conta come 'ha spesa'."""
    assert _ts("emit(m.soloUnPvConSpesa(input))", [{"spesa": 10}, {"spesa": -3}]) is True


# ─── tuttiSelezionati ───────────────────────────────────────────────────────

_CAND = [{"descrizione_key": "a"}, {"descrizione_key": "b"}]


def test_tutti_selezionati_vero():
    assert _ts("emit(m.tuttiSelezionati(input, new Map([['a',1],['b',1]])))", _CAND) is True


def test_tutti_selezionati_parziale():
    assert _ts("emit(m.tuttiSelezionati(input, new Map([['a',1]])))", _CAND) is False


def test_tutti_selezionati_lista_vuota_e_falso():
    """`every` su vuoto e' true: senza la guardia il pulsante direbbe
    'deseleziona tutti' quando non c'e' niente da deselezionare."""
    assert _ts("emit(m.tuttiSelezionati([], new Map()))") is False


def test_tutti_selezionati_accetta_anche_un_set():
    """Il .tsx passa una Map, ma la funzione chiede solo `.has`."""
    assert _ts("emit(m.tuttiSelezionati(input, new Set(['a','b'])))", _CAND) is True


# ─── slug e nome file ───────────────────────────────────────────────────────

@pytest.mark.parametrize("label,atteso", [
    ("Gennaio 2026", "gennaio-2026"),
    ("", ""),
    (None, ""),
    ("  doppio  spazio  ", "doppio-spazio"),
    ("---", ""),
    ("Q1 2026 (rev)", "q1-2026-rev"),
    ("Café", "caf"),
])
def test_slug_periodo(label, atteso):
    assert _ts("emit(m.slugPeriodo(input))", label) == atteso


def test_nome_file_export_stringa_intera():
    """Assert assoluto: 'contiene lo slug' non proverebbe che il resto sia giusto."""
    assert _ts(
        "emit(m.nomeFileExport(input[0], input[1]))", ["Salmone Rosa", "Gennaio 2026"]
    ) == "tag_salmone-rosa_gennaio-2026.xlsx"


def test_fotografa_trattino_appeso_nel_nome_del_tag():
    """ANOMALIA: lo slug del NOME non ha il replace di coda che ha quello del
    periodo, quindi un tag che finisce per punteggiatura lascia un trattino."""
    assert _ts(
        "emit(m.nomeFileExport(input[0], input[1]))", ["Pesce!", "Gennaio 2026"]
    ) == "tag_pesce-_gennaio-2026.xlsx"


def test_nome_file_senza_periodo():
    assert _ts(
        "emit(m.nomeFileExport(input[0], input[1]))", ["Pesce", None]
    ) == "tag_pesce_.xlsx"


# ─── righe di export ────────────────────────────────────────────────────────

def test_righe_export_pv_chiavi_esatte():
    """Le chiavi sono le intestazioni che il cliente legge in Excel: si asserisce
    l'oggetto intero, accento di 'Quantità' compreso."""
    riga = _ts("emit(m.righeExportPv(input))", [{
        "ristorante_id": "r1", "nome": "Centro", "spesa": 1234.567, "quantita": 12.5,
        "n_righe": 4, "n_fornitori": 2, "incidenza_pct": 33.3, "prezzo_medio": 9.87,
    }])[0]
    assert riga == {
        "Punto vendita": "Centro",
        "Spesa": 1234.57,
        "Incidenza %": "33.3%",
        "Prezzo medio": 9.87,
        "Quantità": 12.5,
        "Righe": 4,
        "Fornitori": 2,
    }


def test_righe_export_pv_prezzo_zero_resta_zero():
    """`?? "—"` e non `|| "—"`: un prezzo di 0 e' un dato, non un dato mancante.

    Raggiungibile con dati veri: `routers/gruppo.py:2250` calcola
    `round(spesa_pv / qta, 2)` quando la quantita' e' positiva, e su un articolo
    in omaggio (o una riga netta di nota di credito) il risultato e' 0.0. Con
    `||` il cliente leggerebbe "—" ("prezzo non disponibile") al posto di 0
    ("gratis"), che sono due informazioni diverse.

    Lacuna trovata dal code-reviewer: avevo dichiarato equivalente il `??` di
    `estremiPrezzo` — vero li', dove il parametro e' una lista — e non avevo
    controllato questo, dove il tipo e' `number | null` e lo 0 esiste davvero.
    """
    riga = _ts("emit(m.righeExportPv(input))", [{
        "ristorante_id": "r1", "nome": "Centro", "spesa": 0, "quantita": 5,
        "n_righe": 1, "n_fornitori": 1, "incidenza_pct": 0, "prezzo_medio": 0,
    }])[0]
    assert riga["Prezzo medio"] == 0


def test_righe_export_pv_prezzo_assente_e_trattino():
    riga = _ts("emit(m.righeExportPv(input))", [{
        "ristorante_id": "r1", "nome": "Centro", "spesa": 10, "quantita": 0,
        "n_righe": 1, "n_fornitori": 1, "incidenza_pct": 100, "prezzo_medio": None,
    }])[0]
    assert riga["Prezzo medio"] == "—"


def _spesa_esportata(spesa):
    return _ts("emit(m.righeExportPv(input))", [{
        "ristorante_id": "r1", "nome": "C", "spesa": spesa, "quantita": 1,
        "n_righe": 1, "n_fornitori": 1, "incidenza_pct": 0, "prezzo_medio": None,
    }])[0]["Spesa"]


def test_righe_export_pv_arrotonda_a_due_decimali():
    assert _spesa_esportata(1234.567) == 1234.57
    assert _spesa_esportata(40.005) == 40.01


def test_fotografa_arrotondamento_asimmetrico_sui_negativi():
    """ANOMALIA: `Math.round` in JS arrotonda i .5 verso +infinito, non lontano
    da zero. Quindi +40.005 -> 40.01 ma -40.005 -> -40.01 solo perche' il .5 cade
    dalla parte giusta: su -40.015 il verso e' l'altro (-40.01, non -40.02).

    Su una nota di credito l'export puo' quindi differire di un centesimo dal
    valore che la stessa cifra avrebbe col segno opposto. Un centesimo su un
    export non e' un incidente; e' la classe di errore che conta, e va detta.
    """
    assert _spesa_esportata(-40.005) == -40.01
    assert _spesa_esportata(-40.015) == -40.01
    assert _spesa_esportata(40.015) == 40.02


def test_fotografa_meno_zero_nell_export():
    """Un importo che arrotonda a zero da sotto resta `-0` in JS. JSON lo
    serializza come 0, ma il foglio Excel riceve il -0 vero."""
    assert _ts("emit(Object.is(m.righeExportPv(input)[0].Spesa, -0))", [{
        "ristorante_id": "r1", "nome": "C", "spesa": -0.001, "quantita": 1,
        "n_righe": 1, "n_fornitori": 1, "incidenza_pct": 0, "prezzo_medio": None,
    }]) is True


def test_righe_export_fornitori_chiavi_esatte():
    riga = _ts("emit(m.righeExportFornitori(input))", [
        {"nome": "Ittica SRL", "spesa": 99.999, "incidenza_pct": 50, "n_righe": 3}
    ])[0]
    assert riga == {
        "Fornitore": "Ittica SRL",
        "Spesa": 100,
        "Incidenza %": "50%",
        "Righe": 3,
    }


def test_righe_export_liste_vuote():
    assert _ts("emit([m.righeExportPv([]), m.righeExportFornitori([])])") == [[], []]
