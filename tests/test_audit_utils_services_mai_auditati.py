"""Presidi della dimensione di audit su utils/ e i moduli services/ mai guardati.

Tre difetti latenti trovati leggendo codice che nessuna passata aveva mai letto:

1. `verifica_integrita_fattura` contava anche le righe cestinate (regola #5).
2. `righe_ripartite_proiettate` leggeva le quote senza paginare: PostgREST
   tronca a 1000 senza dirlo, e il conteggio cresce sedi x categorie x mesi.
3. `calcola_ricetta` saltava le righe non calcolabili, restituendo un foodcost
   piu' basso del vero senza che l'utente lo sapesse.

Ognuno chiama il codice vero: un test che ricalcola la formula sopravvive al
mutante e non prova niente.
"""

import pytest

from services.foodcost_service import RigaFoodcostNonCalcolabile, calcola_ricetta
from services.riparto_service import righe_ripartite_proiettate
from utils.validation import verifica_integrita_fattura


# --------------------------------------------------------------------------
# 1. Soft delete su verifica_integrita_fattura (CLAUDE.md #5)
# --------------------------------------------------------------------------

class _RespCount:
    def __init__(self, count):
        self.count = count
        self.data = []


class _FakeFattureQuery:
    """Query su `fatture` che conta come il DB reale: le righe cestinate
    esistono in tabella e spariscono SOLO se arriva il filtro deleted_at."""

    def __init__(self, sink, vive, cestinate):
        self._sink = sink
        self._vive = vive
        self._cestinate = cestinate
        self._solo_vive = False

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def is_(self, campo, valore):
        if campo == "deleted_at" and valore == "null":
            self._solo_vive = True
            self._sink["filtro_soft_delete"] = True
        return self

    def execute(self):
        return _RespCount(self._vive if self._solo_vive else self._vive + self._cestinate)


class _FakeSB:
    def __init__(self, sink, vive, cestinate):
        self._sink = sink
        self._vive = vive
        self._cestinate = cestinate

    def table(self, nome):
        assert nome == "fatture"
        return _FakeFattureQuery(self._sink, self._vive, self._cestinate)


def test_ramo_legacy_non_conta_le_righe_cestinate():
    """3 righe salvate + 2 cestinate: senza filtro il conteggio dice 5 e
    l'integrita' risulta rotta su una fattura che invece e' a posto."""
    sink = {}
    sb = _FakeSB(sink, vive=3, cestinate=2)

    esito = verifica_integrita_fattura(
        nome_file="F1.xml",
        dati_prodotti=[{}, {}, {}],
        user_id="u1",
        supabase_client=sb,
        righe_db_override=None,
    )

    assert sink.get("filtro_soft_delete") is True, "manca .is_('deleted_at','null')"
    assert esito["righe_db"] == 3
    assert esito["perdite"] == 0
    assert esito["integrita_ok"] is True


def test_override_bypassa_la_query_e_resta_il_percorso_vivo():
    sink = {}
    sb = _FakeSB(sink, vive=3, cestinate=2)

    esito = verifica_integrita_fattura(
        nome_file="F1.xml",
        dati_prodotti=[{}, {}],
        user_id="u1",
        supabase_client=sb,
        righe_db_override=2,
    )

    assert esito["integrita_ok"] is True
    assert "filtro_soft_delete" not in sink


# --------------------------------------------------------------------------
# 2. Paginazione delle quote di riparto
# --------------------------------------------------------------------------

class _QuoteQuery:
    """Tabella quote con il cap PostgREST: senza .range() ritorna al massimo
    _CAP righe, in silenzio. Con .range() serve la finestra chiesta."""

    _CAP = 1000

    def __init__(self, righe, sink):
        self._righe = righe
        self._sink = sink
        self._range = None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def range(self, start, end):
        self._sink["ha_paginato"] = True
        self._range = (start, end)
        return self

    def execute(self):
        if self._range is None:
            return _Resp(self._righe[: self._CAP])
        start, end = self._range
        return _Resp(self._righe[start:end + 1])


class _Resp:
    def __init__(self, data):
        self.data = data


class _VuotaQuery:
    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def execute(self):
        return _Resp([])


class _SBQuote:
    def __init__(self, quote, sink):
        self._quote = quote
        self._sink = sink

    def table(self, nome):
        if nome == "riparto_costi_catena_quote":
            return _QuoteQuery(self._quote, self._sink)
        return _VuotaQuery()


def test_le_quote_oltre_le_mille_non_vengono_troncate_in_silenzio():
    """1.500 quote su 300 riparti: senza paginazione ne leggerebbe 1000 e le
    quote dei riparti oltre il cap sparirebbero dai costi del punto vendita."""
    quote = [
        {"riparto_id": f"r{i // 5}", "quota_perc": 10.0,
         "quota_importo": 1.0, "categoria": "CARNE"}
        for i in range(1500)
    ]
    sink = {}
    sb = _SBQuote(quote, sink)

    righe_ripartite_proiettate(sb, "u1", "pv1", None, None)

    assert sink.get("ha_paginato") is True, "la query quote deve usare .range()"


# --------------------------------------------------------------------------
# 3. Il foodcost non si sottostima in silenzio
# --------------------------------------------------------------------------

def test_riga_non_calcolabile_non_sparisce_dal_totale():
    """La riga rotta valeva 0 e il totale usciva 12.0: un piatto piu' economico
    del vero, con l'errore solo nei log del server."""
    righe = [
        {"tipo": "articolo", "prezzo_unitario": 12.0, "um_db": "KG",
         "quantita": 1.0, "um": "KG", "nome": "MANZO"},
        {"tipo": "articolo", "prezzo_unitario": "non-un-numero", "um_db": "KG",
         "quantita": 1.0, "um": "KG", "nome": "SALSA"},
    ]

    with pytest.raises(RigaFoodcostNonCalcolabile) as exc:
        calcola_ricetta(righe)

    assert "SALSA" in str(exc.value), "l'errore deve dire QUALE riga non torna"


def test_ricetta_valida_resta_calcolata():
    righe = [
        {"tipo": "articolo", "prezzo_unitario": 10.0, "um_db": "KG",
         "quantita": 500, "um": "G", "nome": "MANZO"},
    ]

    assert calcola_ricetta(righe) == pytest.approx(5.0)
