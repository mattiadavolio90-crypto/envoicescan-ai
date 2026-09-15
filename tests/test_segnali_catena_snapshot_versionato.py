"""La cache giornaliera dei segnali catena non deve sopravvivere a un deploy.

Difetto trovato nell'audit L8 (15/09/2026) e misurato sul DB live: 40 righe su 40
di `gruppo_segnali_state`, dal 28/06 al 15/09 su 3 account, senza alcuna chiave
`code_version` nello snapshot. La cache e' per (user_id, giorno di Roma) e l'unico
svuotamento esistente e' per-account, al salvataggio della config assistente
(`gruppo.py`, `salva_gruppo_assistant_config`). Nessun frontend passa `force=true`
(`card-segnali.tsx`, `mobile-catena.tsx`, `api/gruppo/segnali/route.ts`).

Conseguenza: per un account multi-sede che aveva gia' letto i segnali di oggi, un
deploy che cambiava `_calcola_segnali` o le sue soglie NON si vedeva fino a
mezzanotte di Roma. Il briefing per-sede aveva gia' il presidio giusto
(`_BRIEFING_CODE_VERSION`, `snapshot_is_stale`); questa cache, che ha la stessa
forma, ne era priva — un'asimmetria, non una scelta.

I due lettori sono presidiati entrambi: l'endpoint `gruppo_segnali` e
`_conta_segnali_cache`, che alimenta il conteggio e la severity del briefing di
catena. Se se ne presidiasse uno solo, dopo un deploy la pagina mostrerebbe i
segnali nuovi mentre il briefing continuerebbe a contare quelli vecchi.

I test ESEGUONO il codice vero con un finto client Supabase: nessun assert sul
sorgente, nessun controllo sul decoratore.
"""
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from services.routers import gruppo


# ── Finto client Supabase: minimo per servire la catena select/eq/limit/execute ──

class _Resp:
    def __init__(self, data: List[Dict[str, Any]]):
        self.data = data


class _Query:
    def __init__(self, rows: List[Dict[str, Any]], registro: Dict[str, Any]):
        self._rows = rows
        self._registro = registro

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _Resp(self._rows)

    def upsert(self, payload, **_k):
        self._registro.setdefault("upsert", []).append(payload)
        return self

    def delete(self):
        return self


class _FakeSB:
    """Ritorna le righe preparate per `gruppo_segnali_state`, vuoto per il resto."""

    def __init__(self, snapshot: Optional[Dict[str, Any]]):
        self.registro: Dict[str, Any] = {}
        self._snapshot = snapshot

    def table(self, nome: str):
        if nome == "gruppo_segnali_state" and self._snapshot is not None:
            return _Query([{"snapshot": self._snapshot}], self.registro)
        return _Query([], self.registro)


def _snapshot(code_version: Optional[int], segnali: List[Dict[str, Any]]):
    snap: Dict[str, Any] = {"segnali": segnali, "generated_at": "2026-09-15T08:00:00+00:00"}
    if code_version is not None:
        snap["code_version"] = code_version
    return snap


# Forma REALE del modello Segnale (gruppo.py): tipo, severity, ristorante_id,
# pv_nome, testo, cta_page. Un segnale con campi inventati farebbe alzare
# Segnale(**s) dentro il try del fast-path, e l'except lo ingoierebbe facendo
# ricalcolare: il test passerebbe per la ragione sbagliata.
_SEGNALE = {
    "tipo": "margine_calo",
    "severity": "warning",
    "ristorante_id": "rid-1",
    "pv_nome": "Sede A",
    "testo": "Margine 66%, era 71%",
    "cta_page": "/margini",
}


# ══════════════════════════════════════════════════════════════════════════
# 1. L'helper di versione
# ══════════════════════════════════════════════════════════════════════════

def test_snapshot_della_versione_in_esecuzione_e_corrente():
    assert gruppo._snapshot_versione_corrente(
        {"code_version": gruppo._SEGNALI_CODE_VERSION}
    ) is True


def test_snapshot_di_un_altra_versione_non_e_corrente():
    assert gruppo._snapshot_versione_corrente(
        {"code_version": gruppo._SEGNALI_CODE_VERSION + 1}
    ) is False


def test_snapshot_senza_code_version_non_e_corrente():
    """Le 40 righe misurate in produzione il 15/09/2026 sono esattamente questo
    caso: scritte da un codice anteriore al presidio."""
    assert gruppo._snapshot_versione_corrente({"segnali": [], "generated_at": "x"}) is False


@pytest.mark.parametrize("valore", ["ventiquattro", None, [], {}, object()])
def test_code_version_illeggibile_non_e_corrente(valore):
    """Meglio ricalcolare che servire qualcosa di dubbio: nessuna eccezione esce."""
    assert gruppo._snapshot_versione_corrente({"code_version": valore}) is False


def test_snapshot_assente_non_e_corrente():
    assert gruppo._snapshot_versione_corrente(None) is False
    assert gruppo._snapshot_versione_corrente({}) is False


# ══════════════════════════════════════════════════════════════════════════
# 2. L'endpoint: lo snapshot di un'altra versione non viene servito
# ══════════════════════════════════════════════════════════════════════════

def _chiama_endpoint(snapshot, segnali_ricalcolati):
    """Esegue `gruppo_segnali` vero con la risoluzione gruppo e il calcolo finti."""
    sb = _FakeSB(snapshot)
    with patch.object(
        gruppo, "_resolve_gruppo",
        return_value=(sb, "user-1", [], "Catena Test", {}, ["rid-1", "rid-2"]),
    ), patch.object(
        gruppo, "_get_gruppo_config", return_value=([], [])
    ), patch.object(
        gruppo, "_calcola_segnali", return_value=list(segnali_ricalcolati)
    ) as calcolo:
        resp = gruppo.gruppo_segnali(force=False, authorization="Bearer t")
    return resp, calcolo, sb


def test_snapshot_della_versione_corrente_viene_servito_senza_ricalcolare():
    """Il caso normale: la cache 1x/giorno deve continuare a funzionare."""
    snap = _snapshot(gruppo._SEGNALI_CODE_VERSION, [_SEGNALE])
    resp, calcolo, _ = _chiama_endpoint(snap, [])

    assert calcolo.called is False, "la cache valida non deve far ricalcolare"
    assert len(resp.segnali) == 1
    assert resp.generated_at == "2026-09-15T08:00:00+00:00"


def test_snapshot_di_versione_vecchia_viene_ricalcolato():
    """Il difetto: prima del fix questo snapshot veniva servito tale e quale."""
    vecchio = _snapshot(gruppo._SEGNALI_CODE_VERSION - 1, [_SEGNALE])
    nuovo = dict(_SEGNALE, testo="Margine 60%, era 71% (regola nuova)")
    resp, calcolo, _ = _chiama_endpoint(vecchio, [nuovo])

    assert calcolo.called is True, "snapshot di un altro codice: va ricalcolato"
    assert resp.segnali[0].testo == "Margine 60%, era 71% (regola nuova)"


def test_snapshot_senza_code_version_viene_ricalcolato():
    """Le righe gia' in produzione: al primo deploy si rigenerano da sole."""
    resp, calcolo, _ = _chiama_endpoint(_snapshot(None, [_SEGNALE]), [_SEGNALE])
    assert calcolo.called is True


def test_la_scrittura_registra_la_versione_in_esecuzione():
    """Senza questo, lo snapshot nuovo sarebbe stantio appena scritto."""
    _, _, sb = _chiama_endpoint(_snapshot(None, []), [_SEGNALE])

    upserts = sb.registro.get("upsert") or []
    assert upserts, "lo snapshot ricalcolato va salvato"
    assert upserts[-1]["snapshot"]["code_version"] == gruppo._SEGNALI_CODE_VERSION


# ══════════════════════════════════════════════════════════════════════════
# 3. Il secondo consumatore: il briefing di catena
# ══════════════════════════════════════════════════════════════════════════

def test_conta_segnali_legge_lo_snapshot_della_versione_corrente():
    sb = _FakeSB(_snapshot(gruppo._SEGNALI_CODE_VERSION, [_SEGNALE, dict(_SEGNALE, severity="error")]))
    n, sev = gruppo._conta_segnali_cache(sb, "user-1")
    assert (n, sev) == (2, "error")


def test_conta_segnali_su_versione_vecchia_dice_non_determinabile():
    """None, non 0: `tutto_ok` non deve accendersi su un conteggio che non vale
    piu'. E' lo stesso contratto gia' presidiato da
    tests/test_catena_errore_non_diventa_tutto_ok.py per la cache assente."""
    sb = _FakeSB(_snapshot(gruppo._SEGNALI_CODE_VERSION - 1, [_SEGNALE]))
    n, sev = gruppo._conta_segnali_cache(sb, "user-1")
    assert n is None, "snapshot di un altro codice = non determinabile, non zero"
    assert sev == "info"


def test_conta_segnali_senza_code_version_dice_non_determinabile():
    sb = _FakeSB(_snapshot(None, [_SEGNALE, _SEGNALE, _SEGNALE]))
    n, _ = gruppo._conta_segnali_cache(sb, "user-1")
    assert n is None


# ══════════════════════════════════════════════════════════════════════════
# 4. I due lettori non devono divergere
# ══════════════════════════════════════════════════════════════════════════

def test_i_due_lettori_concordano_sullo_stesso_snapshot_vecchio():
    """Il fix parziale sarebbe: presidiare l'endpoint e dimenticare il briefing.
    Su uno snapshot di versione vecchia l'endpoint deve ricalcolare E il
    conteggio deve dirsi non determinabile — mai la pagina aggiornata col
    briefing fermo ai segnali di ieri."""
    vecchio = _snapshot(gruppo._SEGNALI_CODE_VERSION - 1, [_SEGNALE])

    _, calcolo, _ = _chiama_endpoint(vecchio, [_SEGNALE])
    n, _sev = gruppo._conta_segnali_cache(_FakeSB(vecchio), "user-1")

    assert calcolo.called is True
    assert n is None
