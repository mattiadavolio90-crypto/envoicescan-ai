"""F-DRIFT: ricomporre le quote per sede non deve creare centesimi (audit 2026-08).

`esplodi_quote_per_categoria(forza=True)` somma le porzioni per-categoria di ogni
sede per poi rispezzarle. Quella somma fa RIEMERGERE i mezzi centesimi che
l'esplosione precedente aveva diviso: due sedi al 50% di 2,95 tornano 1,475
ciascuna, che arrotondato dà 1,48 + 1,48 = 2,96 contro un header di 2,95.

Il ramo che pareggia le quote-sede esisteva già, ma girava SOLO sotto
`riallinea_al_netto` — cioè quando header e righe divergono. Su questi costi
coincidevano, quindi non pareggiava nessuno: 19 costi su 156 sul DB live, tutti
con l'updated_at del batch di ri-esplosione del 27/8/2026.

Perché non è cosmetico: `riparto_quote_mensili` somma le quote dentro
`margini_mensili`, quindi il centesimo non resta in questa tabella — entra nel
MOL che il cliente legge.

La funzione gira DAVVERO (fake client, nessun mock sulla logica), come in
test_riparto_riesplosione_forzata.py.
"""
from types import SimpleNamespace

import pytest

from services.riparto_service import esplodi_quote_per_categoria


class _Query:
    def __init__(self, client, table):
        self._c = client
        self._t = table

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def delete(self, *a, **k): return self
    def insert(self, *a, **k): return self

    def execute(self):
        if self._t == "fatture":
            return SimpleNamespace(data=self._c.righe)
        if self._t == "riparto_costi_catena_quote":
            return SimpleNamespace(data=self._c.quote)
        if self._t == "riparto_costi_catena":
            return SimpleNamespace(data=[self._c.padre] if self._c.padre else [])
        return SimpleNamespace(data=[])


class _FakeSB:
    def __init__(self, righe, quote, padre):
        self.righe = righe
        self.quote = quote
        self.padre = padre
        self.rpc_calls = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(data=params.get("p_riparto_id"))
        )


def _scenario(importo: float, categoria: str = "UTENZE E LOCALI"):
    """Due sedi al 50%, una categoria, righe che pareggiano già l'header.

    Quest'ultimo dettaglio è ciò che disinnesca `riallinea_al_netto` ed è la
    condizione in cui i 19 costi reali si trovavano.
    """
    meta = importo / 2
    return _FakeSB(
        righe=[{"categoria": categoria, "totale_riga": importo}],
        quote=[
            {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0,
             "quota_importo": round(meta, 2), "categoria": categoria},
            {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0,
             "quota_importo": round(meta, 2), "categoria": categoria},
        ],
        padre={"tipo": "generale", "regola": "equa", "importo_totale": importo},
    )


def _quote_scritte(sb):
    assert sb.rpc_calls, "nessuna RPC chiamata: la funzione non ha riscritto le quote"
    nome, params = sb.rpc_calls[-1]
    assert nome == "sostituisci_quote_riparto"
    return params["p_quote"], params["p_importo_totale"]


# Gli 11 importi reali con drift misurati sul DB live il 28/8/2026.
IMPORTI_REALI = [2.95, 8.61, 9.67, 12.33, 16.57, 18.03, 20.49, 24.91, 38.59, 39.07, 40.03]


@pytest.mark.parametrize("importo", IMPORTI_REALI)
def test_le_quote_pareggiano_lheader(importo):
    sb = _scenario(importo)
    assert esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)

    quote, header = _quote_scritte(sb)
    somma = round(sum(q["quota_importo"] for q in quote), 2)
    assert somma == pytest.approx(round(header, 2), abs=1e-9), (
        f"header {header}, quote {[q['quota_importo'] for q in quote]} = {somma}: "
        f"lo scarto di {round(somma - header, 2)} entrerebbe nel MOL"
    )


@pytest.mark.parametrize("importo", IMPORTI_REALI)
def test_le_quote_non_sono_simmetriche_su_centesimi_dispari(importo):
    """Il sintomo osservabile: su un importo con centesimi dispari due sedi al 50%
    NON possono avere la stessa quota. Trovarle identiche significa che nessuno ha
    pareggiato — è esattamente la firma dei 19 costi trovati sul DB."""
    sb = _scenario(importo)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, _ = _quote_scritte(sb)
    importi = sorted(q["quota_importo"] for q in quote)
    assert importi[0] != importi[-1], (
        f"{importo}: entrambe le sedi a {importi[0]} — nessuno ha assorbito il mezzo centesimo"
    )


def test_importo_pari_resta_diviso_a_meta():
    """Il fix non deve sbilanciare ciò che era già in equilibrio."""
    sb = _scenario(100.00)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, _ = _quote_scritte(sb)
    assert sorted(q["quota_importo"] for q in quote) == [50.0, 50.0]


def test_nota_di_credito_pareggia_col_segno_giusto():
    """Header negativo (TD04): le quote restano negative e sommano all'header.
    I CHECK sul segno sono stati rimossi il 27/8 (20260827214500) proprio per
    questo: il pareggio non deve reintrodurre un vincolo di positività."""
    sb = _scenario(-2.95)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, header = _quote_scritte(sb)

    assert all(q["quota_importo"] <= 0 for q in quote), "una nota di credito ha prodotto quote positive"
    somma = round(sum(q["quota_importo"] for q in quote), 2)
    assert somma == pytest.approx(round(header, 2), abs=1e-9)


def test_tre_sedi_pareggiano():
    """Il pareggio non è una proprietà del caso a due sedi."""
    importo = 10.00
    sb = _FakeSB(
        righe=[{"categoria": "UTENZE E LOCALI", "totale_riga": importo}],
        quote=[
            {"id": f"q{i}", "ristorante_id": f"sede-{i}", "quota_perc": 33.333,
             "quota_importo": 3.33, "categoria": "UTENZE E LOCALI"}
            for i in range(3)
        ],
        padre={"tipo": "generale", "regola": "equa", "importo_totale": importo},
    )
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, header = _quote_scritte(sb)
    assert round(sum(q["quota_importo"] for q in quote), 2) == pytest.approx(round(header, 2), abs=1e-9)


def test_piu_categorie_pareggiano_comunque():
    """Con più categorie per sede il pareggio deve valere sul TOTALE, non per
    categoria: è il caso che generava 2 dei 19 drift reali."""
    importo = 32.73
    sb = _FakeSB(
        righe=[
            {"categoria": "UTENZE E LOCALI", "totale_riga": 30.91},
            {"categoria": "MATERIALE DI CONSUMO", "totale_riga": 1.82},
        ],
        quote=[
            {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 15.45, "categoria": "UTENZE E LOCALI"},
            {"id": "q2", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 0.91, "categoria": "MATERIALE DI CONSUMO"},
            {"id": "q3", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 15.45, "categoria": "UTENZE E LOCALI"},
            {"id": "q4", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 0.91, "categoria": "MATERIALE DI CONSUMO"},
        ],
        padre={"tipo": "generale", "regola": "equa", "importo_totale": importo},
    )
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, header = _quote_scritte(sb)
    assert round(sum(q["quota_importo"] for q in quote), 2) == pytest.approx(round(header, 2), abs=1e-9)


def test_il_riallineamento_al_netto_resta_intatto():
    """Il ramo storico (header lordo ≠ righe nette) non deve essere stato
    scalfito: continua a riportare le quote al netto reale."""
    sb = _FakeSB(
        righe=[{"categoria": "UTENZE E LOCALI", "totale_riga": 100.00}],
        quote=[
            {"id": "q1", "ristorante_id": "sede-a", "quota_perc": 50.0, "quota_importo": 61.0, "categoria": None},
            {"id": "q2", "ristorante_id": "sede-b", "quota_perc": 50.0, "quota_importo": 61.0, "categoria": None},
        ],
        # `origine="fattura"` e' la condizione del riallineamento: senza, l'header
        # resta quello inserito a mano e non c'e' nessun netto da cui ripartire.
        padre={"tipo": "generale", "regola": "equa", "importo_totale": 122.00,
               "origine": "fattura"},
    )
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, header = _quote_scritte(sb)
    assert round(header, 2) == 100.00, "il netto reale non ha sostituito il lordo"
    assert round(sum(q["quota_importo"] for q in quote), 2) == pytest.approx(100.00, abs=1e-9)


def test_lo_scarto_va_sullultima_sede_come_ovunque():
    """Quale sede assorbe il centesimo non cambia il pareggio — ma la convenzione
    sì. `_quote_equa`, `_quote_percentuali`, `_spezza_importo_per_pesi` e il ramo
    `riallinea_al_netto` fanno tutti assorbire all'ULTIMO elemento in ordine. Se
    qui cambiasse, due percorsi darebbero risultati diversi sullo stesso costo e
    il confronto fra due esecuzioni diventerebbe rumore.
    """
    sb = _scenario(2.95)
    esplodi_quote_per_categoria(sb, "user-1", "riparto-1", "f.xml", forza=True)
    quote, _ = _quote_scritte(sb)

    per_sede = {q["ristorante_id"]: q["quota_importo"] for q in quote}
    ultima = sorted(per_sede)[-1]
    assert per_sede[ultima] == 1.47, (
        f"lo scarto non e' finito sull'ultima sede in ordine: {per_sede}"
    )
    assert per_sede[sorted(per_sede)[0]] == 1.48
