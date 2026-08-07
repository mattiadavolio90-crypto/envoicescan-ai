"""Test audit §1 `services/routers/ricavi.py` (7/8/2026).

Tre invarianti che prima di questa passata nessun test difendeva. `ricavi.py` e'
il DENOMINATORE del MOL: un errore qui sposta il margine esattamente come lo
spostava la whitelist FOOD delle RPC in `margini.py` (fix del 6/8).

  1) COERENZA FONTI in `coperti-analisi`. Un mese in modalita' 'mensile' prende i
     ricavi dall'override (`ricavi_modalita_mensile`), non dai giornalieri. I
     giornalieri eventualmente rimasti a DB per quel mese sono dati orfani: se
     entrano nei widget (giorno top/fiacco, media per giorno-settimana) la stessa
     response mostra due verita' diverse per lo stesso mese.
     Sul DB live al 7/8 il caso e' latente solo perche' le uniche righe
     interessate (2 di TIME CAFE) hanno `coperti = NULL` e vengono scartate dal
     filtro `coperti > 0`: basta un import con i coperti valorizzati per
     accenderlo. Il test lo blocca prima.

  2) INVALIDAZIONE CACHE KPI Home su OGNI scrittura di ricavi. Il trigger
     `sync_margini_mensili_from_ricavi` riscrive `margini_mensili` a ogni
     INSERT/UPDATE/DELETE sui giornalieri, e la card "I tuoi conti" legge da li'
     con una cache TTL 120s. Prima del fix 4 percorsi di scrittura su 5
     invalidavano solo il briefing: il cliente caricava i ricavi e la Home
     restava indietro fino a 2 minuti, ricaricare la pagina non serviva (cache
     per-ristorante, non per-sessione).

  3) PAGINAZIONE. Nessuna delle select su `ricavi_giornalieri` usava `.range()`:
     oltre 1000 righe PostgREST tronca in SILENZIO. Oggi il cliente con piu'
     storico ha 218 righe, quindi e' un rischio latente — ma il troncamento muto
     e' esattamente la classe di difetto che `utils/supabase_paging.py` esiste
     per impedire.

I fake builder qui sotto FILTRANO DAVVERO (date e `range()`): se qualcuno
rimuove il filtro nel codice, il test diventa rosso. Un fake che ignora i filtri
renderebbe questi test vacui — il difetto documentato in
`tests/test_eccezioni_moduli_mockati.py`.
"""
import os
from datetime import date

import pytest

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

from services.routers import ricavi as R  # noqa: E402

RID = "rid-test"
USER = {"id": "user-test"}


class _FakeQuery:
    """Builder che applica per davvero i filtri usati da ricavi.py.

    `range()` affetta la lista come PostgREST (estremi INCLUSIVI), cosi' la
    paginazione viene esercitata invece di essere solo dichiarata.
    """

    def __init__(self, rows, recorder=None, table=""):
        self._rows = list(rows)
        self._rec = recorder
        self._table = table
        self._range = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, col, val):
        if col == "ristorante_id":
            self._rows = [r for r in self._rows if r.get("ristorante_id", RID) == val]
        elif col == "modalita":
            self._rows = [r for r in self._rows if r.get("modalita") == val]
        return self

    def in_(self, col, vals):
        if col == "anno":
            self._rows = [r for r in self._rows if r.get("anno") in vals]
        elif col == "data":
            vs = {str(v) for v in vals}
            self._rows = [r for r in self._rows if str(r.get("data")) in vs]
        return self

    def gte(self, col, val):
        if col == "data":
            self._rows = [r for r in self._rows if str(r.get("data")) >= str(val)]
        return self

    def lte(self, col, val):
        if col == "data":
            self._rows = [r for r in self._rows if str(r.get("data")) <= str(val)]
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def upsert(self, payload, **_k):
        rows = payload if isinstance(payload, list) else [payload]
        if self._rec is not None:
            self._rec.setdefault("upsert", []).extend(rows)
        self._rows = rows
        return self

    def delete(self):
        if self._rec is not None:
            self._rec["delete"] = True
        self._rows = []
        return self

    def execute(self):
        rows = self._rows
        if self._range is not None:
            s, e = self._range
            rows = rows[s:e + 1]
        return type("R", (), {"data": rows, "count": len(rows)})()


class _FakeSB:
    def __init__(self, giornalieri=None, margini=None, modalita=None, recorder=None):
        self._g = giornalieri or []
        self._m = margini or []
        self._mod = modalita or []
        self._rec = recorder if recorder is not None else {}

    def table(self, name):
        src = {
            "ricavi_giornalieri": self._g,
            "margini_mensili": self._m,
            "ricavi_modalita_mensile": self._mod,
        }.get(name, [])
        return _FakeQuery(src, recorder=self._rec, table=name)


def _gio(d, coperti=None, i10=0.0, i22=0.0, altri=0.0):
    return {
        "id": f"g-{d}", "data": d, "coperti": coperti,
        "fatturato_iva10": i10, "fatturato_iva22": i22,
        "altri_ricavi_noiva": altri, "source": "manuale",
        "ristorante_id": RID,
    }


def _mod_mensile(anno, mese, i10=0.0, i22=0.0, altri=0.0, coperti=None):
    return {
        "anno": anno, "mese": mese, "modalita": "mensile",
        "fatturato_iva10": i10, "fatturato_iva22": i22,
        "altri_ricavi_noiva": altri, "coperti": coperti,
        "ristorante_id": RID,
    }


@pytest.fixture
def patch_ctx(monkeypatch):
    """Sostituisce i soli agganci esterni: auth, client, resolver, costi F&B.

    NON mocka la logica sotto test: le query passano dai fake builder sopra, che
    filtrano davvero.
    """
    calls = {"kpi": [], "briefing": []}

    # La funzione REALE, catturata prima del patch: l'override mensile è la logica
    # sotto test, va eseguita davvero. Mockiamo solo i costi F&B (fuori perimetro)
    # e l'invalidazione cache (che vogliamo osservare).
    import services.fastapi_worker as fw_mod
    overrides_reali = fw_mod._load_mensile_overrides

    class _FW:
        _load_mensile_overrides = staticmethod(overrides_reali)

        @staticmethod
        def _calcola_costi_auto_per_periodo(sb, rid, mesi):
            return {}

        @staticmethod
        def _invalidate_home_kpi_cache(rid):
            calls["kpi"].append(rid)

    monkeypatch.setattr(R, "_fw", lambda: _FW())
    monkeypatch.setattr(R, "_resolve_user_from_token", lambda *a, **k: USER)
    monkeypatch.setattr(R, "_resolve_ristorante_id", lambda *a, **k: RID)

    import services.daily_briefing_service as dbs
    monkeypatch.setattr(
        dbs, "invalidate_today_briefing",
        lambda uid, rid, sb: calls["briefing"].append(rid),
    )
    return calls


# ─────────────────────────── 1) Coerenza delle fonti ───────────────────────────

def test_mese_mensile_esclude_i_giornalieri_orfani(patch_ctx, monkeypatch):
    """Il mese e' in modalita' 'mensile': i suoi giornalieri NON entrano nei widget.

    Se questo test diventa rosso, `coperti-analisi` sta di nuovo mescolando due
    fonti: totali dall'override e giorno top/media-dow da righe che l'override ha
    gia' sostituito.
    """
    sb = _FakeSB(
        giornalieri=[
            # Giugno = mese in modalita' mensile -> orfani, da ignorare.
            _gio("2026-06-10", coperti=900, i10=50000.0),
            _gio("2026-06-11", coperti=800, i10=40000.0),
            # Luglio = mese normale -> deve restare.
            _gio("2026-07-05", coperti=40, i10=1000.0),
            _gio("2026-07-06", coperti=60, i10=1500.0),
        ],
        margini=[{"anno": 2026, "mese": 7, "fatturato_iva10": 2500.0,
                  "fatturato_iva22": 0.0, "altri_ricavi_noiva": 0.0,
                  "coperti": 100, "ristorante_id": RID}],
        modalita=[_mod_mensile(2026, 6, i10=80655.0, coperti=1700)],
    )
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    out = R.get_coperti_analisi(data_da="2026-06-01", data_a="2026-07-31")

    giorni = {g.data for g in out.giorni}
    assert giorni == {"2026-07-05", "2026-07-06"}, (
        "i giornalieri di un mese in modalita' mensile sono rientrati nei widget"
    )
    # Il giorno top deve venire da luglio, non dalle righe orfane da 900 coperti.
    assert out.kpi.giorno_top is not None
    assert out.kpi.giorno_top.coperti == 60
    assert out.kpi.coperti_medi_giorno == 50.0


def test_mese_normale_usa_i_giornalieri(patch_ctx, monkeypatch):
    """Contro-prova: senza override i giornalieri devono entrare tutti.

    Impedisce che il fix precedente venga "risolto" filtrando via tutto.
    """
    sb = _FakeSB(
        giornalieri=[
            _gio("2026-07-05", coperti=40, i10=1000.0),
            _gio("2026-07-06", coperti=60, i10=1500.0),
        ],
        margini=[{"anno": 2026, "mese": 7, "fatturato_iva10": 2500.0,
                  "fatturato_iva22": 0.0, "altri_ricavi_noiva": 0.0,
                  "coperti": 100, "ristorante_id": RID}],
        modalita=[],
    )
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    out = R.get_coperti_analisi(data_da="2026-07-01", data_a="2026-07-31")

    assert {g.data for g in out.giorni} == {"2026-07-05", "2026-07-06"}
    assert out.ha_dati_giornalieri is True


# ────────────────── 2) Invalidazione cache KPI Home su scrittura ──────────────────

def test_upsert_giornaliero_invalida_kpi_home(patch_ctx, monkeypatch):
    sb = _FakeSB(recorder={})
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    body = R.RicavoUpsertRequest(
        data="2026-07-10", fatturato_iva10=100.0, fatturato_iva22=0.0,
        altri_ricavi_noiva=0.0, coperti=10,
    )
    R.upsert_ricavo_giornaliero(body=body)

    assert patch_ctx["kpi"] == [RID], (
        "POST /giornalieri non invalida i KPI Home: la card resta stantia fino al TTL"
    )
    assert patch_ctx["briefing"] == [RID]


def test_delete_giornaliero_invalida_kpi_home(patch_ctx, monkeypatch):
    sb = _FakeSB(giornalieri=[_gio("2026-07-10", coperti=10)], recorder={})
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    R.delete_ricavo_giornaliero(data="2026-07-10")

    assert patch_ctx["kpi"] == [RID], (
        "DELETE /giornalieri non invalida i KPI Home"
    )


def test_batch_invalida_kpi_home(patch_ctx, monkeypatch):
    sb = _FakeSB(recorder={})
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    body = R.RicaviBatchUpsertRequest(
        items=[R.RicavoUpsertRequest(
            data="2026-07-10", fatturato_iva10=100.0, fatturato_iva22=0.0,
            altri_ricavi_noiva=0.0, coperti=10,
        )],
        source="xls",
    )
    R.upsert_ricavi_batch(body=body)

    assert patch_ctx["kpi"] == [RID], (
        "POST /batch non invalida i KPI Home: e' il percorso dell'import XLS"
    )


# ──────────────────────────── 3) Paginazione ────────────────────────────

def test_giornalieri_oltre_mille_righe_non_troncati(patch_ctx, monkeypatch):
    """Oltre 1000 righe PostgREST tronca in silenzio: qui devono tornare tutte."""
    rows = []
    d = date(2024, 1, 1)
    from datetime import timedelta
    for i in range(1200):
        rows.append(_gio(str(d + timedelta(days=i)), coperti=10, i10=100.0))
    sb = _FakeSB(giornalieri=rows)
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    out = R.get_ricavi_giornalieri(data_da="2024-01-01", data_a="2027-12-31")

    assert len(out.items) == 1200, (
        f"troncamento silenzioso: attese 1200 righe, tornate {len(out.items)}"
    )


def test_pre_check_batch_conta_updated_oltre_mille(patch_ctx, monkeypatch):
    """Il pre-check dedup deve vedere TUTTE le date esistenti, non le prime 1000.

    Con il cap le righe oltre la millesima venivano contate come "inserite" pur
    essendo aggiornamenti: il totale mostrato al cliente era sbagliato.
    """
    from datetime import timedelta
    d0 = date(2024, 1, 1)
    esistenti = [_gio(str(d0 + timedelta(days=i)), coperti=5) for i in range(1100)]
    sb = _FakeSB(giornalieri=esistenti, recorder={})
    monkeypatch.setattr(R, "_get_supabase_client", lambda: sb)

    body = R.RicaviBatchUpsertRequest(
        items=[R.RicavoUpsertRequest(
            data=str(d0 + timedelta(days=i)), fatturato_iva10=10.0,
            fatturato_iva22=0.0, altri_ricavi_noiva=0.0, coperti=5,
        ) for i in range(1100)],
        source="xls",
    )
    out = R.upsert_ricavi_batch(body=body)

    assert out.updated == 1100, (
        f"pre-check troncato: {out.updated} updated invece di 1100 "
        f"({out.inserted} contate come nuove)"
    )
    assert out.inserted == 0
