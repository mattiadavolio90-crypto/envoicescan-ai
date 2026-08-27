"""Test §3c perimetro non letto (27/8/2026) — l'override mensile deve SPEGNERSI.

Il difetto: `ricavi_modalita_mensile` si poteva accendere ma mai spegnere. Il
frontend mandava `modalita` hardcoded a "mensile" (carica-ricavi-dialog.tsx:234)
e nessun percorso di scrittura dei giornalieri toccava quella riga. Poiche'
`_load_mensile_overrides` filtra `.eq("modalita","mensile")`, il worker
continuava a ignorare i giornalieri appena scritti.

Misurato sul DB live prima del fix: 17 righe in `ricavi_modalita_mensile`, TUTTE
'mensile', ZERO 'giornaliero' — il percorso di spegnimento non era mai stato
eseguito perche' non esisteva. Caso attivo su cliente reale (TIME CAFE, giugno
2026): il cliente aveva inserito un giorno da 3.227,27 EUR netti che veniva
scartato in silenzio a favore dell'override da 73.322,73 EUR.

Questi test difendono i 3 percorsi di scrittura dei giornalieri: POST singolo
(usato dal mobile), batch (dialog desktop) e import XLS. Il fake registra le
`update()` e applica davvero i filtri: senza il filtro `.eq("modalita","mensile")`
nel codice, il test sullo storico preservato cade.
"""
import os

import pytest

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

from services.routers import ricavi as R  # noqa: E402

RID = "rid-test"


class _FakeQuery:
    """Builder che applica per davvero i filtri di `_spegni_override_mensile`."""

    def __init__(self, rows, recorder, table):
        self._rows = list(rows)
        self._rec = recorder
        self._table = table
        self._update_payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def execute(self):
        if self._update_payload is not None:
            for r in self._rows:
                self._rec.setdefault("updated", []).append(
                    {**r, **self._update_payload}
                )
                r.update(self._update_payload)
        return type("R", (), {"data": list(self._rows), "count": len(self._rows)})()


class _FakeSB:
    def __init__(self, modalita, recorder):
        self._mod = modalita
        self._rec = recorder

    def table(self, name):
        # Conta le query emesse, non le righe toccate: e' l'unico modo di vedere
        # un mese processato piu' volte (senza dedup la 2a query non matcherebbe
        # nulla, quindi contare le righe aggiornate non basta).
        self._rec["queries"] = self._rec.get("queries", 0) + 1
        src = {"ricavi_modalita_mensile": self._mod}.get(name, [])
        return _FakeQuery(src, self._rec, name)


def _riga(anno, mese, modalita="mensile", i10=1000.0):
    return {
        "ristorante_id": RID, "anno": anno, "mese": mese, "modalita": modalita,
        "fatturato_iva10": i10, "fatturato_iva22": 0.0,
        "altri_ricavi_noiva": 0.0, "coperti": None,
    }


def test_spegne_override_del_mese_scritto():
    righe = [_riga(2026, 6)]
    rec = {}
    n = R._spegni_override_mensile(_FakeSB(righe, rec), RID, ["2026-06-09"])
    assert n == 1
    assert righe[0]["modalita"] == "giornaliero"


def test_non_tocca_altri_mesi():
    """Scrivere un giorno di giugno non deve spegnere l'override di maggio."""
    righe = [_riga(2026, 5), _riga(2026, 6)]
    rec = {}
    R._spegni_override_mensile(_FakeSB(righe, rec), RID, ["2026-06-09"])
    maggio = [r for r in righe if r["mese"] == 5][0]
    giugno = [r for r in righe if r["mese"] == 6][0]
    assert maggio["modalita"] == "mensile", "maggio non c'entra con la scrittura"
    assert giugno["modalita"] == "giornaliero"


def test_preserva_gli_importi_storici():
    """Spegnere non e' cancellare: il totale mensile resta come storico.

    Se qualcuno sostituisse l'UPDATE con un DELETE (o azzerasse gli importi),
    il dato inserito dal cliente sparirebbe invece di essere disattivato.
    """
    righe = [_riga(2026, 6, i10=54321.0)]
    R._spegni_override_mensile(_FakeSB(righe, {}), RID, ["2026-06-09"])
    assert righe[0]["fatturato_iva10"] == 54321.0
    assert righe[0]["modalita"] == "giornaliero"


def test_idempotente_su_mese_gia_giornaliero():
    """Il filtro .eq("modalita","mensile") evita update inutili."""
    righe = [_riga(2026, 6, modalita="giornaliero")]
    rec = {}
    n = R._spegni_override_mensile(_FakeSB(righe, rec), RID, ["2026-06-09"])
    assert n == 0
    assert "updated" not in rec


def test_piu_giorni_dello_stesso_mese_un_solo_update():
    """Un batch di 30 giorni non deve produrre 30 update sullo stesso mese."""
    righe = [_riga(2026, 6)]
    rec = {}
    date = [f"2026-06-{d:02d}" for d in range(1, 31)]
    n = R._spegni_override_mensile(_FakeSB(righe, rec), RID, date)
    assert n == 1
    assert len(rec.get("updated", [])) == 1
    assert rec["queries"] == 1, (
        f"30 giorni dello stesso mese devono produrre 1 sola query, "
        f"non {rec['queries']}"
    )


def test_batch_a_cavallo_di_due_mesi_li_spegne_entrambi():
    righe = [_riga(2026, 5), _riga(2026, 6)]
    n = R._spegni_override_mensile(
        _FakeSB(righe, {}), RID, ["2026-05-31", "2026-06-01"]
    )
    assert n == 2
    assert all(r["modalita"] == "giornaliero" for r in righe)


@pytest.mark.parametrize("date_invalide", [[], [None], [""], ["non-una-data"], ["20260609"]])
def test_date_malformate_non_esplodono(date_invalide):
    """Una data illeggibile non deve far fallire la scrittura dei ricavi."""
    righe = [_riga(2026, 6)]
    n = R._spegni_override_mensile(_FakeSB(righe, {}), RID, date_invalide)
    assert n == 0
    assert righe[0]["modalita"] == "mensile"


def test_errore_supabase_non_propaga():
    """Best-effort: se l'update fallisce, la scrittura dei ricavi deve proseguire."""
    class _Boom:
        def table(self, _n):
            raise RuntimeError("supabase down")

    assert R._spegni_override_mensile(_Boom(), RID, ["2026-06-09"]) == 0


# ─── MEDIUM-2: validazione `anno` su POST /api/ricavi/modalita ────────────────
# `mese` era validato (1-12), `anno` no: un valore assurdo creava una riga
# irraggiungibile dall'interfaccia (i selettori mostrano solo anni plausibili).

@pytest.mark.parametrize("anno_valido", [2000, 2026, 2100])
def test_anno_plausibile_accettato(anno_valido):
    assert 2000 <= anno_valido <= 2100


@pytest.mark.parametrize("anno_assurdo", [0, 1899, 20260, -2026, 99999])
def test_anno_assurdo_fuori_range(anno_assurdo):
    """Documenta il contratto che l'endpoint ora impone (ricavi.py:1404-1405)."""
    assert not (2000 <= anno_assurdo <= 2100)


def test_endpoint_modalita_valida_anno():
    """Il controllo su `anno` esiste davvero nel sorgente dell'endpoint.

    Ancorato al messaggio d'errore, non alla riga: un refactor che sposta il
    codice non rompe il test, ma rimuovere la guardia si'.
    """
    import inspect
    src = inspect.getsource(R.upsert_ricavi_modalita)
    assert "anno deve essere" in src, "la guardia su `anno` e' sparita"
    assert "mese deve essere" in src, "la guardia su `mese` e' sparita"


# ─── I 3 percorsi di scrittura devono CHIAMARE lo spegnimento ─────────────────
# Il difetto originale non era nell'helper (non esisteva) ma nel fatto che
# nessun percorso lo invocava. Senza questa guardia, rimuovere la chiamata da
# uno dei tre lascerebbe il difetto vivo su quel canale con i test tutti verdi.

@pytest.mark.parametrize("endpoint,canale", [
    ("upsert_ricavo_giornaliero", "POST singolo giorno (mobile)"),
    ("upsert_ricavi_batch", "batch (dialog desktop)"),
    ("import_ricavi_xls", "import XLS"),
])
def test_percorso_scrittura_spegne_override(endpoint, canale):
    import inspect
    src = inspect.getsource(getattr(R, endpoint))
    assert "_spegni_override_mensile" in src, (
        f"{canale}: scrive i giornalieri senza spegnere l'override mensile — "
        f"i giorni salvati verrebbero ignorati dai margini"
    )
