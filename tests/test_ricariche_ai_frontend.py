"""La scheda «Ricarica AI» dell'admin (fase J): lettura della risposta e righe."""
from __future__ import annotations

import re
from pathlib import Path

from tests.helpers_ts import esegui_ts

MODULO = "lib/ricariche-ai"
FUNZIONI = ["leggiRicariche", "testoResiduo", "rigaRicarica"]
_WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"

R1 = {"id": "r1", "crediti": 300, "nota": "bonifico", "creata_da": "m", "created_at": "2026-10-10T09:00:00Z"}


def _f(fn, arg):
    return esegui_ts(MODULO, f"emit(m.{fn}(input));", argomento=arg, richiede=FUNZIONI)


def test_una_risposta_ben_fatta_si_legge():
    d = {"ricariche": [R1], "residuo": 297, "crediti_boost": 300}
    assert _f("leggiRicariche", d) == d


def test_una_risposta_d_errore_non_si_legge():
    for d in (None, {"detail": "Cliente non trovato"}, {"ricariche": [], "residuo": "x", "crediti_boost": 300},
              {"ricariche": None, "residuo": 0, "crediti_boost": 300}, {"ricariche": [], "residuo": 0}):
        assert _f("leggiRicariche", d) is None, d


def test_ricarica_registrata_col_residuo_illeggibile():
    d = {"ricariche": [], "residuo": None, "crediti_boost": 300}
    assert _f("leggiRicariche", d) == d, "una ricarica registrata non va letta come errore"
    assert _f("testoResiduo", d).startswith("Ricarica registrata.")


def test_il_residuo_si_dice_coi_punti():
    assert _f("testoResiduo", {"ricariche": [R1], "residuo": 1200, "crediti_boost": 300}) == \
        "Ricarica AI da spendere: 1.200 crediti"
    assert _f("testoResiduo", {"ricariche": [], "residuo": 0, "crediti_boost": 300}) == \
        "Nessuna ricarica AI attivata."


def test_la_data_e_quella_di_roma():
    """All'1:30 del 10/10 a Roma l'UTC dice ancora 9/10."""
    assert _f("rigaRicarica", {**R1, "created_at": "2026-10-09T23:30:00Z", "nota": None}) == \
        "10/10/2026 · 300 crediti"


def test_la_riga_della_ricarica():
    assert _f("rigaRicarica", R1) == "10/10/2026 · 300 crediti · bonifico"
    assert _f("rigaRicarica", {**R1, "nota": None}) == "10/10/2026 · 300 crediti"


def _n(rel):
    t = (_WEB / rel).read_text(encoding="utf-8")
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    t = re.sub(r"(?m)^\s*//.*$", "", t)
    return re.sub(r"\s+", "", t)


def test_la_scheda_del_cliente_ha_la_ricarica_fra_le_azioni():
    n = _n("app/(app)/admin/clienti/[id]/cliente-dettaglio-client.tsx")
    assert "<RicaricheAiClienteclienteId={c.id}/></CardContent>" in n


def test_la_scheda_chiede_conferma_prima_di_scrivere():
    n = _n("app/(app)/admin/clienti/[id]/ricariche-ai.tsx")
    # il bottone apre il dialogo; solo «Aggiungi N crediti» del dialogo scrive
    assert "onClick={()=>setAperto(true)}" in n
    assert "<ButtononClick={conferma}disabled={invio}>" in n
    assert n.count('method:"POST"') == 1
    assert "constletto=res.ok?leggiRicariche(d):null;" in n


def test_il_proxy_inoltra_solo_get_e_post_alla_rotta_del_cliente():
    n = _n("app/api/admin/clienti/[id]/ricariche-ai/route.ts")
    assert "${WORKER_URL}/api/admin/clienti/${encodeURIComponent(id)}/ricariche-ai" in n
    assert "exportasyncfunctionGET(" in n and "exportasyncfunctionPOST(" in n
    assert "PATCH" not in n and "DELETE" not in n
