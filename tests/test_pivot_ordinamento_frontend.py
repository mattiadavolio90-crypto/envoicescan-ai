"""Test dell'ordinamento della pivot di Analisi Fatture (`lib/pivot-ordinamento.ts`).

Eseguono il TypeScript vero via node (`helpers_ts.esegui_ts`): `apps/web/` non
ha un runner proprio per scelta strutturale — `deploy-vercel.yml` si attiva su
`apps/web/**`, quindi un runner li' farebbe deployare la produzione a ogni
merge di test.

Il modulo nasce da un difetto trovato il 22/09/2026 controllando tutti e nove
gli export dell'app: l'ordinamento era uno `useState` dentro `PivotTable`,
mentre il bottone "Esporta Excel" sta nel componente padre e leggeva le righe
non ordinate. Il cliente ordinava per una colonna, esportava, e nel file
trovava un ordine diverso da quello a schermo. Ora la funzione e' una sola e
i test possono vederla.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/pivot-ordinamento"

FUNZIONI = ["ordinaRighePivot", "prossimoSort"]
VALORI = ["SORT_PIVOT_INIZIALE"]


def _esegui(espressione, argomento=None):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=FUNZIONI)


def test_esportazioni_valore_presenti():
    presenti = _esegui("emit(input.map((n) => typeof m[n] !== \"undefined\"));", VALORI)
    assert presenti == [True] * len(VALORI), dict(zip(VALORI, presenti))


def _righe():
    """Tre righe con ordini DIVERSI su ogni chiave: se due chiavi producessero
    lo stesso ordine, un test non distinguerebbe quale delle due e' stata usata."""
    return [
        {"dimensione": "CARNE", "totale": 100.0, "incidenza_pct": 10.0,
         "periodi": {"2026-08": 70.0, "2026-09": 30.0}},
        {"dimensione": "BEVANDE", "totale": 900.0, "incidenza_pct": 90.0,
         "periodi": {"2026-08": 10.0, "2026-09": 890.0}},
        {"dimensione": "ORTOFRUTTA", "totale": 500.0, "incidenza_pct": 50.0,
         "periodi": {"2026-08": 400.0, "2026-09": 100.0}},
    ]


def _ordine(sort):
    return _esegui(
        "emit(m.ordinaRighePivot(input.rows, input.sort).map((r) => r.dimensione));",
        {"rows": _righe(), "sort": sort},
    )


# ─── Il difetto del 22/09/2026: schermo ed export ordinano uguale ───────────

def test_stato_iniziale_e_totale_decrescente():
    """E' l'ordine con cui la tabella si presenta: la voce che pesa di piu' in
    cima. L'export deve partire dallo stesso."""
    iniziale = _esegui("emit(m.SORT_PIVOT_INIZIALE);")
    assert iniziale == {"key": "totale", "dir": "desc"}
    assert _ordine(iniziale) == ["BEVANDE", "ORTOFRUTTA", "CARNE"]


def test_ordina_per_totale_crescente():
    assert _ordine({"key": "totale", "dir": "asc"}) == ["CARNE", "ORTOFRUTTA", "BEVANDE"]


def test_ordina_per_nome():
    assert _ordine({"key": "dimensione", "dir": "asc"}) == [
        "BEVANDE", "CARNE", "ORTOFRUTTA",
    ]


def test_ordina_per_incidenza():
    assert _ordine({"key": "incidenza_pct", "dir": "desc"}) == [
        "BEVANDE", "ORTOFRUTTA", "CARNE",
    ]


def test_ordina_per_una_colonna_di_periodo():
    """Cliccando l'intestazione di un mese si ordina per la spesa di quel mese.
    I due mesi danno ordini diversi apposta: cosi' il test distingue quale
    colonna e' stata davvero usata."""
    assert _ordine({"key": "2026-08", "dir": "desc"}) == [
        "ORTOFRUTTA", "CARNE", "BEVANDE",
    ]
    assert _ordine({"key": "2026-09", "dir": "desc"}) == [
        "BEVANDE", "ORTOFRUTTA", "CARNE",
    ]


def test_senza_ordinamento_resta_l_ordine_del_server():
    """Il terzo stato del ciclo: si torna all'ordine con cui il server ha
    mandato le righe, che nessuna delle due direzioni riproduce."""
    assert _ordine({"key": None, "dir": None}) == ["CARNE", "BEVANDE", "ORTOFRUTTA"]


def test_periodo_assente_da_una_riga_vale_zero():
    """Una categoria che in quel mese non ha speso nulla: `undefined` la
    manderebbe in cima o in fondo a seconda del motore."""
    righe = _righe()
    del righe[0]["periodi"]["2026-08"]
    ordine = _esegui(
        "emit(m.ordinaRighePivot(input.rows, input.sort).map((r) => r.dimensione));",
        {"rows": righe, "sort": {"key": "2026-08", "dir": "asc"}},
    )
    assert ordine == ["CARNE", "BEVANDE", "ORTOFRUTTA"]


def test_nomi_fornitore_con_maiuscole_incoerenti_restano_vicini():
    """Dalle fatture i nomi arrivano con grafie diverse: senza
    `sensitivity: "base"` "Acme" e "ACME" finiscono lontanissimi nell'elenco."""
    righe = [
        {"dimensione": "ACME", "totale": 1.0, "incidenza_pct": 1.0, "periodi": {}},
        {"dimensione": "Bianchi", "totale": 2.0, "incidenza_pct": 2.0, "periodi": {}},
        {"dimensione": "acme srl", "totale": 3.0, "incidenza_pct": 3.0, "periodi": {}},
    ]
    ordine = _esegui(
        "emit(m.ordinaRighePivot(input.rows, input.sort).map((r) => r.dimensione));",
        {"rows": righe, "sort": {"key": "dimensione", "dir": "asc"}},
    )
    assert ordine == ["ACME", "acme srl", "Bianchi"]


def test_non_muta_l_array_ricevuto():
    """Ordinare in posto cambierebbe anche l'array del componente padre: la
    tabella si riordinerebbe da sola a ogni export."""
    prima_dopo = _esegui(
        "const r = input.rows;"
        "m.ordinaRighePivot(r, input.sort);"
        "emit(r.map((x) => x.dimensione));",
        {"rows": _righe(), "sort": {"key": "totale", "dir": "desc"}},
    )
    assert prima_dopo == ["CARNE", "BEVANDE", "ORTOFRUTTA"]


# ─── Il ciclo delle intestazioni ────────────────────────────────────────────

def test_ciclo_sort_su_colonna_nuova_parte_crescente():
    assert _esegui(
        "emit(m.prossimoSort(input, 'totale'));", {"key": "dimensione", "dir": "asc"}
    ) == {"key": "totale", "dir": "asc"}


def test_ciclo_sort_asc_desc_niente_asc():
    """Tre click tornano al punto di partenza, passando per "nessun ordine"."""
    s1 = _esegui("emit(m.prossimoSort(input, 'totale'));", {"key": "totale", "dir": "asc"})
    assert s1 == {"key": "totale", "dir": "desc"}
    s2 = _esegui("emit(m.prossimoSort(input, 'totale'));", s1)
    assert s2 == {"key": None, "dir": None}
    s3 = _esegui("emit(m.prossimoSort(input, 'totale'));", s2)
    assert s3 == {"key": "totale", "dir": "asc"}
