"""Gate "modalità mensile" su GET /api/margini/fatturato-centri-giorni.

Nei mesi in modalità mensile l'override ha la precedenza e le righe giornaliere
rimaste a DB sono orfane (ricavi.py:1055). L'endpoint distribuisce le quote per
centro usando `netto_mese` calcolato da quelle righe: senza il gate, quel
denominatore è falso e le frazioni per centro sono sbagliate.

Il gate vive nell'endpoint e non solo nel client perché la regola deve valere
per ogni consumatore, presente e futuro: la classe di difetto "regola applicata
solo in alcuni dei suoi punti" si è già ripetuta 3 volte nel progetto.

Caso reale che l'ha motivato (misurato 27/8/2026): TIME CAFE maggio 2026 ha
88.606,27 € concentrati su UN giorno orfano in un mese `mensile`.
"""
import services.routers.margini as margini


class _FakeQuery:
    def __init__(self, data, boom=False):
        self._data = data
        self._boom = boom

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        if self._boom:
            raise RuntimeError("connessione persa")

        class _R:
            pass

        r = _R()
        r.data = self._data
        return r


class _FakeSB:
    def __init__(self, data, boom=False):
        self._data = data
        self._boom = boom

    def table(self, _nome):
        return _FakeQuery(self._data, self._boom)


def test_mese_in_modalita_mensile_riconosce_override():
    sb = _FakeSB([{"modalita": "mensile"}])
    assert margini._mese_in_modalita_mensile(sb, "rid", 2026, 5) is True


def test_mese_senza_override_non_e_mensile():
    sb = _FakeSB([])
    assert margini._mese_in_modalita_mensile(sb, "rid", 2026, 7) is False


def test_errore_di_lettura_e_fail_open():
    """Un errore di rete non deve svuotare la pagina: si prosegue coi giornalieri.

    Regressione: il primo giro usava `logger` senza che il modulo lo definisse,
    quindi l'except sollevava NameError e il fail-open diventava un 500.
    """
    sb = _FakeSB(None, boom=True)
    assert margini._mese_in_modalita_mensile(sb, "rid", 2026, 5) is False


def test_il_modulo_espone_un_logger():
    """Guardia diretta sulla causa del difetto sopra."""
    assert hasattr(margini, "logger")
