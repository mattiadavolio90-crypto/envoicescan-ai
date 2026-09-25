"""Il worker decide il cliente dall'XML quando il webhook non l'ha potuto leggere (passo 0-bis).

Una GET a Invoicetronic fallita nel webhook (saldo esaurito, 404, timeout) crea
una riga senza cliente. Prima del 25/09/2026 il worker la riscaricava e si
fermava a «Tenant non risolto»: `dead`, e «Riprova» non la salvava. Qui si
prova che adesso la decide come il webhook — e che nel dubbio NON assegna.

Il database e' un finto RIGOROSO: risponde solo alle catene attese e registra
ogni scrittura. Un MagicMock risponderebbe a qualunque catena, anche a una
query senza il filtro sulla P.IVA.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from worker import queue_processor as qp

U1 = "2f3f93a1-c1f4-4804-858e-a161e6f36f3f"
U2 = "9b9b9b9b-1111-4222-8333-444444444444"
PIVA = "07863990961"
SEDE_A = {"id": "aaaaaaaa-0000-4000-8000-000000000001", "user_id": U1, "indirizzo_match": "via roma 5 20100 milano", "nome_ristorante": "A"}
SEDE_B = {"id": "bbbbbbbb-0000-4000-8000-000000000002", "user_id": U1, "indirizzo_match": "viale monza 10 20127 milano", "nome_ristorante": "B"}

PARITA = json.loads(
    (Path(__file__).resolve().parents[1] / "supabase" / "functions" / "invoicetronic-webhook" / "routing_parita.json")
    .read_text(encoding="utf-8")
)


def _fattura(indirizzo="Via Roma", civico="5", cap="20100", comune="Milano", body=""):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
        "<FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese>"
        "<IdCodice>01234567890</IdCodice></IdFiscaleIVA></DatiAnagrafici></CedentePrestatore>"
        "<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese>"
        f"<IdCodice>{PIVA}</IdCodice></IdFiscaleIVA></DatiAnagrafici>"
        f"<Sede><Indirizzo>{indirizzo}</Indirizzo><NumeroCivico>{civico}</NumeroCivico><CAP>{cap}</CAP><Comune>{comune}</Comune></Sede>"
        "</CessionarioCommittente></FatturaElettronicaHeader><FatturaElettronicaBody>"
        "<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>2026-09-20</Data>"
        f"<Numero>77</Numero><ImportoTotaleDocumento>122.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>{body}"
        "</FatturaElettronicaBody></p:FatturaElettronica>"
    )


class _Esito:
    def __init__(self, data):
        self.data = data


class DBFinto:
    """Due catene conosciute: la lettura delle sedi e l'UPDATE della riga."""

    def __init__(self, sedi=None, aggiornate=1, errore_sedi=None, errore_update=None):
        self.sedi = sedi or []
        self.aggiornate = aggiornate
        self.errore_sedi = errore_sedi
        self.errore_update = errore_update
        self.letture_sedi = []
        self.update = []

    def table(self, nome):
        return _Catena(self, nome)


class _Catena:
    def __init__(self, db, tabella):
        self.db, self.tabella, self.passi = db, tabella, []

    def select(self, colonne):
        assert self.tabella == "ristoranti", f"lettura inattesa su {self.tabella}"
        self.passi.append(("select", colonne))
        return self

    def update(self, valori):
        assert self.tabella == "fatture_queue", f"scrittura inattesa su {self.tabella}"
        self.passi.append(("update", valori))
        return self

    def eq(self, col, val):
        self.passi.append(("eq", col, val))
        return self

    def order(self, col, desc=False):
        self.passi.append(("order", col, desc))
        return self

    def execute(self):
        if self.tabella == "ristoranti":
            self.db.letture_sedi.append(self.passi)
            if self.db.errore_sedi:
                raise self.db.errore_sedi
            filtri = {(p[1], p[2]) for p in self.passi if p[0] == "eq"}
            assert ("partita_iva", PIVA) in filtri and ("attivo", True) in filtri, self.passi
            return _Esito([dict(s) for s in self.db.sedi])
        self.db.update.append(self.passi)
        if self.db.errore_update:
            raise self.db.errore_update
        return _Esito([{"id": 1}] * self.db.aggiornate)


def _item(user_id=None, ristorante_id=None, **meta):
    return {
        "id": 901, "event_id": "evt-0bis", "user_id": user_id, "ristorante_id": ristorante_id,
        "xml_content": None, "xml_url": None, "piva_raw": "UNKNOWN", "attempt_count": 3,
        "source": "invoicetronic",
        "payload_meta": {"resource_id": 96551, "invoicetronic_company_id": 1756, "api_error": "HTTP 403", **meta},
    }


def _esegui(db, xml, nome_sdi="IT01234567890_abc12.xml.p7m", item=None, worker_id="w-1"):
    parser = mock.MagicMock(return_value=[{"Descrizione": "Birra", "Totale": 1.0}])
    salva = mock.MagicMock(return_value={"success": True, "righe": 1})
    with mock.patch.object(qp, "_scarica_via_api", return_value=(xml, nome_sdi) if xml is not None else None), \
         mock.patch.object(qp, "estrai_dati_da_xml", parser), \
         mock.patch.object(qp, "salva_fattura_processata", salva), \
         mock.patch.object(qp, "_claim_ancora_valido", return_value=True), \
         mock.patch.object(qp, "_auto_classify_saved_rows", return_value=(1, 0)), \
         mock.patch.object(qp, "_mark_ripartita_se_sede_tecnica", return_value=None), \
         mock.patch.object(qp, "_advance_nuovi_da_daily", return_value=None), \
         mock.patch.object(qp, "_avvisa_se_troncata", return_value=None):
        res = qp._process_item(db, item or _item(), worker_id=worker_id)
    return res, parser, salva


def _registra_rpc(db):
    db.rpc_chiamate = []

    def rpc(nome, params):
        db.rpc_chiamate.append((nome, params))
        return mock.MagicMock(execute=mock.MagicMock(return_value=_Esito(0)))

    return rpc


def _filtri(passi):
    return {(p[1], p[2]) for p in passi if p[0] == "eq"}


def _valori(passi):
    return next(p[1] for p in passi if p[0] == "update")


# ─── Si decide e si salva ────────────────────────────────────────────────────

def test_una_sede_la_fattura_si_salva_sul_cliente_giusto():
    db = DBFinto(sedi=[SEDE_A])
    res, parser, salva = _esegui(db, _fattura())

    assert res.status == "done"
    assert parser.call_args.kwargs["user_id"] == U1, "memoria e settore del cliente servono GIA' al parsing"
    assert parser.call_args.args[0].name == "IT01234567890_abc12.xml.p7m", "il nome SDI vero, non webhook_<id>.xml"
    assert salva.call_args.kwargs["user_id"] == U1
    assert salva.call_args.kwargs["ristoranteid"] == SEDE_A["id"]
    assert salva.call_args.kwargs["nome_file"] == "IT01234567890_abc12.xml.p7m"

    assert len(db.update) == 1
    assert _filtri(db.update[0]) == {("id", 901), ("status", "processing"), ("locked_by", "w-1")}
    valori = _valori(db.update[0])
    assert valori["user_id"] == U1 and valori["ristorante_id"] == SEDE_A["id"] and valori["piva_raw"] == PIVA
    assert "status" not in valori, "resta processing: la chiude mark_done"
    meta = valori["payload_meta"]
    assert meta["resource_id"] == 96551 and meta["invoicetronic_company_id"] == 1756, "il meta si fonde, non si sostituisce"
    assert meta["nome_file"] == "IT01234567890_abc12.xml.p7m"
    assert meta["numero_fattura"] == "77" and meta["importo_totale"] == 122.0 and meta["piva_cedente"] == "01234567890"
    assert meta["cliente_dal_worker"]["esito"] == "assegnata"


def test_piu_sedi_l_indirizzo_sceglie_la_sede():
    db = DBFinto(sedi=[SEDE_B, SEDE_A])
    res, _, salva = _esegui(db, _fattura("Viale Monza", "10", "20127", "Milano"))
    assert res.status == "done"
    assert salva.call_args.kwargs["ristoranteid"] == SEDE_B["id"]
    assert _valori(db.update[0])["payload_meta"]["routing"]["source"] == "sede"


def test_senza_nome_sdi_resta_il_nome_di_ripiego_anche_nel_meta():
    db = DBFinto(sedi=[SEDE_A])
    _, _, salva = _esegui(db, _fattura(), nome_sdi=None)
    assert salva.call_args.kwargs["nome_file"] == "webhook_evt-0bis.xml"
    assert _valori(db.update[0])["payload_meta"]["nome_file"] == "webhook_evt-0bis.xml"


# ─── Si parcheggia ───────────────────────────────────────────────────────────

def test_piu_sedi_nessun_indirizzo_decisivo_la_riga_va_da_assegnare():
    db = DBFinto(sedi=[SEDE_A, SEDE_B])
    xml = _fattura("Via Sede Legale", "99", "00100", "Roma")
    res, parser, salva = _esegui(db, xml)

    assert res.status == "skip" and "da_assegnare" in res.error
    parser.assert_not_called()
    salva.assert_not_called()
    valori = _valori(db.update[0])
    assert valori["status"] == "da_assegnare"
    assert valori["user_id"] == U1 and valori["ristorante_id"] is None
    assert valori["xml_content"] == xml, "la coda da assegnare mostra il fornitore dall'XML"
    assert valori["attempt_count"] == 0, "con i tentativi esauriti, rimessa pending non verrebbe piu' presa"
    assert valori["locked_by"] is None and valori["locked_at"] is None
    assert len(valori["xml_hash"]) == 64
    assert valori["payload_meta"]["routing"]["mode"] == "manual"
    assert valori["payload_meta"]["nome_file"] == "IT01234567890_abc12.xml.p7m", "senza, «Ripartisci dalla coda» risponde 400"


def test_piva_di_nessuno_la_riga_va_in_unknown_tenant_con_la_piva_vera():
    db = DBFinto(sedi=[])
    db.rpc = _registra_rpc(db)
    res, parser, _ = _esegui(db, _fattura())
    assert res.status == "skip" and "unknown_tenant" in res.error
    parser.assert_not_called()
    valori = _valori(db.update[0])
    assert valori["status"] == "unknown_tenant"
    assert valori["user_id"] is None and valori["ristorante_id"] is None
    assert valori["piva_raw"] == PIVA, "resolve_unknown_tenant la cerca per piva_raw"
    assert valori["attempt_count"] == 0
    assert db.rpc_chiamate == [("resolve_unknown_tenant", {"p_piva": PIVA})], \
        "una sede registrata durante la decisione non verrebbe mai piu' agganciata"


# ─── Nel dubbio non si assegna ───────────────────────────────────────────────

def _conservata(db, xml, piva_attesa, esito):
    """La riga ferma tiene XML e metadati (niente nuovi download ai tentativi
    dopo) ma NON prende un cliente ne' cambia stato."""
    assert len(db.update) == 1
    assert _filtri(db.update[0]) == {("id", 901), ("status", "processing"), ("locked_by", "w-1")}
    valori = _valori(db.update[0])
    assert set(valori) == {"xml_content", "xml_hash", "payload_meta", "piva_raw"}
    assert valori["xml_content"] == xml and valori["piva_raw"] == piva_attesa
    assert valori["payload_meta"]["resource_id"] == 96551
    assert valori["payload_meta"]["cliente_dal_worker"]["esito"] == esito


def test_piva_su_piu_account_non_si_assegna():
    altra = {**SEDE_B, "user_id": U2}
    db = DBFinto(sedi=[SEDE_A, altra])
    xml = _fattura("Viale Monza", "10", "20127", "Milano")
    res, parser, salva = _esegui(db, xml)
    assert res.status == "retry" and "account diversi" in res.error
    _conservata(db, xml, PIVA, "piu_account")
    parser.assert_not_called()
    salva.assert_not_called()


@pytest.mark.parametrize("nome", ["commento_ingannevole", "trattino_e_rappresentante", "cdata"])
def test_piva_letta_in_due_modi_non_si_assegna_e_non_si_cercano_sedi(nome):
    xml = next(c["xml"] for c in PARITA["piva_destinatario"] if c["nome"] == nome)
    db = DBFinto(sedi=[SEDE_A])
    res, parser, _ = _esegui(db, xml)
    assert res.status == "retry" and "due modi" in res.error
    assert db.letture_sedi == []
    _conservata(db, xml, "UNKNOWN", "piva_illeggibile")
    parser.assert_not_called()


def test_sedi_illeggibili_si_ritenta_invece_di_dire_sconosciuta():
    """Il webhook su errore di lettura scrive unknown_tenant; nel worker la riga
    resterebbe ferma per sempre (il trigger non la riscatta): si ritenta."""
    db = DBFinto(errore_sedi=RuntimeError("timeout"))
    res, _, _ = _esegui(db, _fattura())
    assert res.status == "retry" and "lettura delle sedi fallita" in res.error
    assert db.update == []


@pytest.mark.parametrize("sedi", [[SEDE_A], [SEDE_A, SEDE_B], []])
def test_riga_passata_di_mano_non_si_tocca_piu(sedi):
    db = DBFinto(sedi=sedi, aggiornate=0)
    xml = _fattura("Via Sede Legale", "99", "00100", "Roma") if len(sedi) == 2 else _fattura()
    res, parser, salva = _esegui(db, xml)
    assert res.status == "skip" and "non piu' in lavorazione" in res.error
    parser.assert_not_called()
    salva.assert_not_called()


def test_scrittura_fallita_si_ritenta():
    db = DBFinto(sedi=[SEDE_A], errore_update=RuntimeError("db giu'"))
    res, parser, _ = _esegui(db, _fattura())
    assert res.status == "retry" and "aggiornamento della coda fallito" in res.error
    parser.assert_not_called()


def test_senza_worker_id_la_guardia_resta_sullo_stato():
    db = DBFinto(sedi=[SEDE_A])
    _esegui(db, _fattura(), worker_id=None)
    assert _filtri(db.update[0]) == {("id", 901), ("status", "processing")}


# ─── Le righe che il cliente ce l'hanno non cambiano ─────────────────────────

def test_riga_col_cliente_non_cerca_sedi_e_non_riscrive_la_coda():
    db = DBFinto(sedi=[SEDE_B])
    res, parser, salva = _esegui(db, _fattura(), item=_item(user_id=U1, ristorante_id=SEDE_A["id"]))
    assert res.status == "done"
    assert db.letture_sedi == [] and db.update == []
    assert salva.call_args.kwargs["ristoranteid"] == SEDE_A["id"]
    assert parser.call_args.kwargs["user_id"] == U1


def test_una_decisione_incoerente_non_arriva_mai_al_salvataggio():
    """Difesa in profondita': se lo smistamento sbagliasse la coppia (la sede
    di un cliente assegnata a un altro), il worker non salva."""
    db = DBFinto(sedi=[SEDE_A])
    incoerente = {"esito": "assegnata", "user_id": U2, "ristorante_id": SEDE_A["id"]}
    with mock.patch.object(qp.routing_coda, "decidi_cliente", return_value=incoerente):
        res, parser, salva = _esegui(db, _fattura())
    assert res.status == "retry" and "non appartiene al cliente" in res.error
    assert db.update == []
    parser.assert_not_called()
    salva.assert_not_called()
