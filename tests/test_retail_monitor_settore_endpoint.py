"""GET /api/admin/retail/categorie-incoerenti — il monitor della Fase 5 retail.

Provato NEL PUNTO CHE LO CHIAMA e non solo nel corpo. E' la lezione che la Fase 4
ha pagato quattro volte (tests/test_wiring_settore_endpoint.py): provare la
funzione non prova che qualcuno la usi. Qui il consumatore vero non e' nemmeno
Python — e' `curl` dentro .github/workflows/retail_settore_check.yml — quindi la
rotta si esercita via HTTP con TestClient, e la forma della response si asserisce
come la legge `jq`: `.totale`, `.ristorazione_con_categoria_retail | length`,
`.retail_con_categoria_food | length`. Se un domani qualcuno rinominasse una di
quelle chiavi, l'endpoint resterebbe verde da Python e il workflow leggerebbe
`null` in silenzio — che e' il modo in cui un monitor muore senza che nessuno se
ne accorga.

La query SQL che alimenta l'endpoint e' provata a parte, su un Postgres vero, in
tests/test_sql_retail_settore_incoerente.py: qui si prova il wiring, li' il
segnale.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.routers.admin as admin

RADICE = Path(__file__).resolve().parents[1]
WORKFLOW = RADICE / ".github" / "workflows" / "retail_settore_check.yml"
VIEW_SQL = RADICE / "supabase" / "migrations" / "20260911170000_v_categorie_settore_incoerenti.sql"

ROTTA = "/api/admin/retail/categorie-incoerenti"


def _riga(tipo="ristorazione_con_categoria_retail", **extra):
    base = {
        "log_id": 1,
        "changed_at": "2026-09-11T10:00:00+00:00",
        "user_id": "11111111-1111-4111-8111-111111111111",
        "ristorante_id": "22222222-2222-4222-8222-222222222222",
        "nome_ristorante": "TRATTORIA",
        "tipo_attivita": "ristorazione",
        "tipo_incoerenza": tipo,
        "descrizione": "RIGA",
        "old_categoria": "CARNE",
        "new_categoria": "ARTICOLO DI VENDITA",
        "file_origine": "IT123.xml",
        "numero_riga": 3,
        "actor_email": None,
        "source": "db_trigger",
        "batch_id": None,
    }
    base.update(extra)
    return base


class _Query:
    def __init__(self, righe):
        self._righe = righe
        self.filtri = {}

    def select(self, *a, **k):
        return self

    def gte(self, campo, valore):
        self.filtri["gte"] = (campo, valore)
        return self

    def order(self, campo, desc=False):
        self.filtri["order"] = (campo, desc)
        return self

    def execute(self):
        return SimpleNamespace(data=self._righe)


class _FakeSB:
    def __init__(self, righe):
        self.righe = righe
        self.tabelle = []
        self.ultima_query = None

    def table(self, nome):
        self.tabelle.append(nome)
        self.ultima_query = _Query(self.righe)
        return self.ultima_query


def _patch(righe):
    sb = _FakeSB(righe)
    return sb, patch.object(admin, "get_supabase_client", MagicMock(return_value=sb))


# ── Il corpo ────────────────────────────────────────────────────────────────

def test_nessuna_incoerenza_totale_zero():
    """Il caso normale, ed e' quello che deve valere quasi sempre: l'alert tace."""
    sb, p = _patch([])
    with p:
        out = admin.retail_categorie_incoerenti()
    assert out["totale"] == 0
    assert out["ristorazione_con_categoria_retail"] == []
    assert out["retail_con_categoria_food"] == []


def test_legge_la_view_e_non_la_tabella_del_registro():
    """Se leggesse category_change_log direttamente si porterebbe dietro la logica
    del settore in Python, dove nessun test SQL la coprirebbe."""
    sb, p = _patch([])
    with p:
        admin.retail_categorie_incoerenti()
    assert sb.tabelle == ["v_categorie_settore_incoerenti"]


def test_le_due_classi_restano_separate():
    """Mai sommate in un unico numero: sono due danni opposti (un ristorante che
    riceve una categoria da negozio, un negozio che ne riceve una food)."""
    sb, p = _patch([
        _riga(),
        _riga(tipo="retail_con_categoria_food", tipo_attivita="retail",
              new_categoria="CARNE", old_categoria="Da Classificare"),
    ])
    with p:
        out = admin.retail_categorie_incoerenti()
    assert out["totale"] == 2
    assert len(out["ristorazione_con_categoria_retail"]) == 1
    assert len(out["retail_con_categoria_food"]) == 1


def test_un_tipo_sconosciuto_non_finisce_nel_secchio_sbagliato():
    """Senza `altro`, un tipo aggiunto alla view domani cadrebbe in una delle due
    classi e l'alert direbbe una cosa per un'altra."""
    sb, p = _patch([_riga(tipo="classe_nuova_di_domani")])
    with p:
        out = admin.retail_categorie_incoerenti()
    assert out["totale"] == 1
    assert out["ristorazione_con_categoria_retail"] == []
    assert out["retail_con_categoria_food"] == []
    assert out["altro"][0]["tipo_incoerenza"] == "classe_nuova_di_domani"


def test_la_finestra_e_24h_e_filtra_per_changed_at():
    sb, p = _patch([])
    with p:
        out = admin.retail_categorie_incoerenti()
    assert out["finestra_ore"] == 24
    assert sb.ultima_query.filtri["gte"][0] == "changed_at"


@pytest.mark.parametrize("richiesto,atteso", [(1, 1), (48, 48), (0, 1), (-5, 1), (99999, 720)])
def test_la_finestra_resta_dentro_i_limiti(richiesto, atteso):
    """Un `ore` fuori scala non deve diventare una scansione completa del registro."""
    sb, p = _patch([])
    with p:
        out = admin.retail_categorie_incoerenti(ore=richiesto)
    assert out["finestra_ore"] == atteso


# ── Il CALL SITE: la rotta HTTP, che e' cio' che il workflow chiama ─────────

CHIAVE = "chiave-di-prova"


def _client(monkeypatch):
    """Client HTTP con la stessa credenziale del workflow: X-Worker-Key.

    `WORKER_SECRET_KEY` e' una costante di modulo letta all'import, quindi si
    sostituisce sul modulo e non via os.environ (che a import gia' avvenuto non
    cambierebbe niente e lascerebbe il test verde per la ragione sbagliata).
    """
    from fastapi.testclient import TestClient
    import services.fastapi_worker as fw

    monkeypatch.setattr(fw, "WORKER_SECRET_KEY", CHIAVE)
    monkeypatch.setattr(fw, "WORKER_DEV_MODE", False)
    client = TestClient(fw.app, raise_server_exceptions=False)
    client.headers.update({"X-Worker-Key": CHIAVE})
    return client


def test_senza_la_worker_key_la_rotta_risponde_401(monkeypatch):
    """Il monitor espone i dati di TUTTI gli account: la chiave macchina e' l'unica
    cosa che lo separa da chiunque passi."""
    client = _client(monkeypatch)
    client.headers.pop("X-Worker-Key")
    assert client.get(ROTTA).status_code == 401


def test_la_rotta_e_montata_ed_e_raggiungibile(monkeypatch):
    """Il presidio che la Fase 4 non aveva: la funzione puo' essere perfetta e non
    essere montata su nessun path."""
    sb, p = _patch([])
    with p:
        risposta = _client(monkeypatch).get(ROTTA)
    assert risposta.status_code == 200, risposta.text


def test_la_response_ha_le_chiavi_che_il_workflow_legge_con_jq(monkeypatch):
    """Le tre chiavi sono un contratto con retail_settore_check.yml. Rinominarne
    una lascerebbe l'endpoint verde e il workflow cieco (jq ritorna null, il
    confronto `!= '0'` fallirebbe e l'alert non partirebbe mai)."""
    sb, p = _patch([_riga()])
    with p:
        corpo = _client(monkeypatch).get(ROTTA).json()
    assert corpo["totale"] == 1
    assert isinstance(corpo["ristorazione_con_categoria_retail"], list)
    assert isinstance(corpo["retail_con_categoria_food"], list)


def test_la_rotta_accetta_il_parametro_ore_come_lo_passa_il_workflow(monkeypatch):
    sb, p = _patch([])
    with p:
        corpo = _client(monkeypatch).get(f"{ROTTA}?ore=24").json()
    assert corpo["finestra_ore"] == 24


# ── Il workflow e la view: i due artefatti che nessun import esegue ─────────

def test_il_workflow_chiama_esattamente_questa_rotta():
    """Un monitor che interroga un path sbagliato riceve 404 e, per come e'
    scritto lo step, si limita a loggare un errore: tacerebbe per sempre.

    Si guarda la riga del `curl`, NON il file intero: il path compare anche nel
    commento in testa, e un `ROTTA in testo` resterebbe verde con la chiamata
    puntata altrove. E' un mutante che e' davvero sopravvissuto alla prima
    stesura di questo presidio.
    """
    righe = WORKFLOW.read_text(encoding="utf-8").splitlines()
    invocazioni = [r for r in righe if "${WORKER_URL}" in r]
    assert len(invocazioni) == 1, f"attesa una sola chiamata al worker: {invocazioni}"
    chiamata = invocazioni[0]
    assert f'"${{WORKER_URL}}{ROTTA}?ore=24"' in chiamata, chiamata
    assert "X-Worker-Key" in WORKFLOW.read_text(encoding="utf-8")


def test_il_workflow_alza_l_alert_solo_quando_il_totale_non_e_zero():
    """Il rumore uccide un monitor: se l'alert partisse sempre, verrebbe ignorato
    entro una settimana e a quel punto non esisterebbe piu'."""
    testo = WORKFLOW.read_text(encoding="utf-8")
    assert "if: steps.check.outputs.totale != '0'" in testo


def test_la_lista_food_della_view_e_quella_delle_costanti():
    """La view ripete in SQL la lista di CATEGORIE_FOOD_BEVERAGE. Se le due
    divergono, la classe 2 smette di vedere proprio le categorie aggiunte dopo —
    in silenzio, perche' nessuna query fallisce."""
    from config.constants import CATEGORIE_FOOD_BEVERAGE

    blocco = VIEW_SQL.read_text(encoding="utf-8").split("l.new_categoria IN (")[1].split(");")[0]
    nella_view = set(re.findall(r"'([^']+)'", blocco))
    assert nella_view == set(CATEGORIE_FOOD_BEVERAGE)


def test_la_rotta_resta_protetta_anche_senza_la_guardia_del_router():
    """La guardia PER-ROTTA, isolata dalla rete del router.

    Il reviewer della Fase 5 ha notato che `test_senza_la_worker_key...` resta
    verde anche togliendo il `Depends` dalla rotta, perche' l'APIRouter ne ha
    gia' uno: quel test misura la difesa del router, non quella aggiunta. Qui si
    prova lo scenario ESATTO per cui la guardia per-rotta esiste — qualcuno che
    domani rimuove il `dependencies` dall'APIRouter — leggendo le dependency
    dichiarate sulla rotta stessa.
    """
    import services.fastapi_worker as fw
    from fastapi.routing import APIRoute

    rotte = [r for r in fw.app.routes
             if isinstance(r, APIRoute) and r.path == ROTTA]
    assert len(rotte) == 1, f"rotta non montata una volta sola: {rotte}"

    # FastAPI fonde le due dichiarazioni in una lista sola e indistinguibile, per
    # cui «c'e' _verify_worker_key» resterebbe vero anche con una sola delle due:
    # si contano. Due = router + rotta; una sola = una delle due e' sparita.
    guardie = [d for d in rotte[0].dependencies
               if getattr(getattr(d, "dependency", None), "__name__", "") == "_verify_worker_key"]
    assert len(guardie) == 2, (
        "attese DUE guardie (quella del router e quella della rotta): con una "
        "sola, togliere il `dependencies` dall'APIRouter lascerebbe la rotta "
        f"scoperta. Viste: {len(guardie)}"
    )


def test_la_categoria_retail_della_view_e_quella_delle_costanti():
    """Come per la lista food: la view ripete in SQL il letterale
    'ARTICOLO DI VENDITA'. Se la costante venisse rinominata e la view no, la
    classe 1 — quella per cui esiste tutta la fase — smetterebbe di vedere
    qualsiasi cosa, in silenzio e senza che nessuna query fallisca."""
    from config.constants import CATEGORIA_ARTICOLO_DI_VENDITA

    testo = VIEW_SQL.read_text(encoding="utf-8")
    assert f"l.new_categoria = '{CATEGORIA_ARTICOLO_DI_VENDITA}'" in testo


def test_la_view_dichiara_security_invoker():
    """Senza, CREATE VIEW eredita SECURITY DEFINER dal ruolo di chi la crea e
    bypassa RLS (audit anti-hacker del 20/6: 14 view chiuse per questo). La
    gemella v_riparto_incoerenze lo imposta; questa e' l'unica che potrebbe
    dimenticarlo, e l'advisor Supabase lo segnalerebbe appena applicata."""
    testo = VIEW_SQL.read_text(encoding="utf-8")
    assert "SET (security_invoker = true)" in testo


def test_la_view_non_scrive_niente():
    """Vincolo della fase: il monitor e' sola lettura. Una view con dentro un
    INSERT/UPDATE/DELETE non sarebbe piu' un osservatore."""
    sql = VIEW_SQL.read_text(encoding="utf-8").upper()
    corpo = sql.split("CREATE OR REPLACE VIEW", 1)[1]
    for vietato in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE", "DROP "):
        assert vietato not in corpo, f"la view contiene {vietato}"
