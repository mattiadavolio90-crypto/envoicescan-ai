"""Il settore della sede nel pannello admin (retail, Fase 1.1).

Cosa presidia:
  - i body accettano solo (ristorazione, retail);
  - `admin_crea_sede` scrive sempre `tipo_attivita`: quello richiesto, o quello
    ereditato dalle sedi dell'account, o 'ristorazione' se e' la prima sede;
  - il vincolo di omogeneita' (v1: un account = un settore) rifiuta con 400 una
    sede di settore diverso, in creazione e in modifica, SENZA scrivere;
  - la sede tecnica non conta nel vincolo (la crea una funzione SQL);
  - in modifica la sede stessa e' esclusa dal confronto, altrimenti un
    mono-sede non potrebbe mai cambiare settore;
  - `UserPublic` nasce 'ristorazione' e rifiuta altro.

Fake Supabase in memoria: riproduce solo il chaining che questi endpoint usano
(table/select/insert/update/eq/neq/limit/single/execute) e registra le
scritture, cosi' "non scrive" e' un'asserzione, non una speranza. Il `select`
PROIETTA le colonne chieste: un fake che restituisse tutto lascerebbe verde un
`_SEDE_SELECT` senza `tipo_attivita` (mock generoso = test che mente).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import services.fastapi_worker as fw  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin

CLIENTE = "cliente-1"
PIVA_VALIDA = "01234567897"
ADMIN = {"email": "md@oneflux.it"}


class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, scritture):
        self._store = store
        self._scritture = scritture
        self._op = "select"
        self._eq: list = []
        self._neq: list = []
        self._payload = None
        self._single = False
        self._limit = None
        self._colonne = None

    def select(self, colonne="*", **_k):
        self._op = "select"
        self._colonne = None if colonne == "*" else [c.strip() for c in colonne.split(",")]
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = dict(row)
        return self

    def update(self, row):
        self._op = "update"
        self._payload = dict(row)
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, campo, valore):
        self._eq.append((campo, valore))
        return self

    def neq(self, campo, valore):
        self._neq.append((campo, valore))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    def _match(self, riga):
        return all(riga.get(c) == v for c, v in self._eq) and all(riga.get(c) != v for c, v in self._neq)

    def execute(self):
        if self._op == "insert":
            riga = {"id": f"sede-{len(self._store) + 1}", **self._payload}
            self._store.append(riga)
            self._scritture.append(("insert", dict(riga)))
            return _Res([dict(riga)])
        if self._op == "update":
            for riga in self._store:
                if self._match(riga):
                    riga.update(self._payload)
            self._scritture.append(("update", dict(self._payload)))
            return _Res([])
        if self._op == "delete":
            self._store[:] = [r for r in self._store if not self._match(r)]
            self._scritture.append(("delete", list(self._eq)))
            return _Res([])
        righe = [dict(r) for r in self._store if self._match(r)]
        if self._colonne is not None:
            righe = [{c: r[c] for c in self._colonne if c in r} for r in righe]
        if self._limit is not None:
            righe = righe[: self._limit]
        if self._single:
            return _Res(righe[0] if righe else None)
        return _Res(righe)


class _FakeSB:
    def __init__(self, ristoranti):
        self.tables = {"ristoranti": [dict(r) for r in ristoranti]}
        self.scritture: list = []

    def table(self, nome):
        return _Query(self.tables.setdefault(nome, []), self.scritture)


def _sede(id_, tipo=None, *, tecnica=False, piva=PIVA_VALIDA):
    riga = {"id": id_, "user_id": CLIENTE, "nome_ristorante": id_, "partita_iva": piva,
            "sede_tecnica": tecnica, "attivo": True}
    if tipo is not None:
        riga["tipo_attivita"] = tipo
    return riga


@pytest.fixture
def sb(monkeypatch):
    def _monta(ristoranti):
        fake = _FakeSB(ristoranti)
        monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: fake)
        return fake
    return _monta


def _crea(tipo=None, **extra):
    body = admin.NuovaSedeBody(nome_ristorante="Nuova", partita_iva="09876543217", tipo_attivita=tipo, **extra)
    return admin.admin_crea_sede(CLIENTE, body, admin_user=ADMIN)


def _inserita(fake):
    inserts = [r for op, r in fake.scritture if op == "insert"]
    assert len(inserts) == 1, fake.scritture
    return inserts[0]


# ── body ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("modello", [admin.NuovaSedeBody, admin.ModificaSedeBody])
def test_il_body_rifiuta_un_settore_sconosciuto(modello):
    with pytest.raises(ValidationError):
        modello(nome_ristorante="X", partita_iva=PIVA_VALIDA, tipo_attivita="bar")


@pytest.mark.parametrize("modello", [admin.NuovaSedeBody, admin.ModificaSedeBody])
@pytest.mark.parametrize("tipo", ["ristorazione", "retail"])
def test_il_body_accetta_i_due_settori(modello, tipo):
    assert modello(nome_ristorante="X", partita_iva=PIVA_VALIDA, tipo_attivita=tipo).tipo_attivita == tipo


# ── crea ─────────────────────────────────────────────────────────────────────

def test_la_prima_sede_senza_settore_nasce_ristorazione(sb):
    fake = sb([])
    _crea()
    assert _inserita(fake)["tipo_attivita"] == "ristorazione"


def test_la_prima_sede_puo_nascere_retail(sb):
    fake = sb([])
    _crea("retail")
    assert _inserita(fake)["tipo_attivita"] == "retail"


def test_una_sede_senza_settore_eredita_quello_dell_account(sb):
    fake = sb([_sede("a", "retail")])
    _crea(indirizzo="Via Roma 1")
    assert _inserita(fake)["tipo_attivita"] == "retail"


def test_una_sede_di_settore_diverso_dall_account_e_rifiutata_senza_scrivere(sb):
    fake = sb([_sede("a", "retail")])
    with pytest.raises(HTTPException) as exc:
        _crea("ristorazione", indirizzo="Via Roma 1")
    assert exc.value.status_code == 400
    assert "stesso settore" in exc.value.detail
    assert fake.scritture == []


def test_una_sede_dello_stesso_settore_dell_account_passa(sb):
    fake = sb([_sede("a", "retail")])
    _crea("retail", indirizzo="Via Roma 1")
    assert _inserita(fake)["tipo_attivita"] == "retail"


def test_la_sede_tecnica_non_conta_nel_vincolo(sb):
    # "Costi comuni di gruppo" la crea una funzione SQL: prima della migration
    # nasceva per default 'ristorazione' anche su un account retail. Non e' un
    # punto vendita e non deve bloccare ne' guidare il settore delle sedi vere.
    fake = sb([_sede("tecnica", "ristorazione", tecnica=True), _sede("a", "retail")])
    _crea(indirizzo="Via Roma 1")
    assert _inserita(fake)["tipo_attivita"] == "retail"


def test_sedi_gia_incoerenti_senza_settore_esplicito_e_un_400(sb):
    # Stato impossibile dal pannello, possibile da SQL: la guardia non tace.
    fake = sb([_sede("a", "retail"), _sede("b", "ristorazione")])
    with pytest.raises(HTTPException) as exc:
        _crea(indirizzo="Via Roma 1")
    assert exc.value.status_code == 400
    assert fake.scritture == []


def test_le_sedi_senza_valore_contano_come_ristorazione(sb):
    # Una riga letta senza tipo_attivita (mock, risposta parziale) vale
    # 'ristorazione': lo stesso default della colonna.
    fake = sb([_sede("a")])
    with pytest.raises(HTTPException):
        _crea("retail", indirizzo="Via Roma 1")
    assert fake.scritture == []


# ── modifica ─────────────────────────────────────────────────────────────────

def _modifica(sede_id, **campi):
    return admin.admin_modifica_sede(CLIENTE, sede_id, admin.ModificaSedeBody(**campi), admin_user=ADMIN)


def _aggiornamento(fake):
    updates = [r for op, r in fake.scritture if op == "update"]
    assert len(updates) == 1, fake.scritture
    return updates[0]


def test_un_mono_sede_cambia_settore(sb):
    fake = sb([_sede("a", "ristorazione")])
    out = _modifica("a", tipo_attivita="retail")
    assert _aggiornamento(fake) == {"tipo_attivita": "retail"}
    assert out["tipo_attivita"] == "retail"


def test_con_altre_sedi_di_settore_diverso_la_modifica_e_rifiutata_senza_scrivere(sb):
    fake = sb([_sede("a", "ristorazione"), _sede("b", "ristorazione")])
    with pytest.raises(HTTPException) as exc:
        _modifica("a", tipo_attivita="retail")
    assert exc.value.status_code == 400
    assert fake.scritture == []


def test_ribadire_il_settore_delle_altre_sedi_passa(sb):
    fake = sb([_sede("a", "retail"), _sede("b", "retail")])
    _modifica("a", tipo_attivita="retail")
    assert _aggiornamento(fake) == {"tipo_attivita": "retail"}


def test_una_modifica_senza_settore_non_lo_tocca(sb):
    fake = sb([_sede("a", "retail")])
    _modifica("a", nome_ristorante="Rinominata")
    assert _aggiornamento(fake) == {"nome_ristorante": "Rinominata"}


def test_la_risposta_della_modifica_porta_il_settore(sb):
    sb([_sede("a", "retail")])
    assert _modifica("a", nome_ristorante="Rinominata")["tipo_attivita"] == "retail"


# ── UserPublic ───────────────────────────────────────────────────────────────

def test_user_public_nasce_ristorazione():
    assert fw.UserPublic(id="1", email="a@b.it").tipo_attivita == "ristorazione"


def test_user_public_rifiuta_un_settore_sconosciuto():
    with pytest.raises(ValidationError):
        fw.UserPublic(id="1", email="a@b.it", tipo_attivita="bar")


# ── invalidazione della cache del settore ────────────────────────────────────

@pytest.fixture
def invalidazioni(monkeypatch):
    import services.settore_service as ss
    registro: list = []
    monkeypatch.setattr(ss, "invalida_cache", lambda user_id=None: registro.append(user_id))
    return registro


def test_creare_una_sede_invalida_la_cache_del_settore(sb, invalidazioni):
    sb([])
    _crea("retail")
    assert invalidazioni == [CLIENTE]


def test_cambiare_il_settore_invalida_la_cache(sb, invalidazioni):
    sb([_sede("a", "ristorazione")])
    _modifica("a", tipo_attivita="retail")
    assert invalidazioni == [CLIENTE]


def test_una_modifica_senza_settore_non_invalida(sb, invalidazioni):
    sb([_sede("a", "retail")])
    _modifica("a", nome_ristorante="Rinominata")
    assert invalidazioni == []


def test_eliminare_una_sede_invalida_la_cache(sb, invalidazioni):
    fake = sb([_sede("a", "retail")])
    admin.admin_elimina_sede(CLIENTE, "a", admin_user=ADMIN)
    assert invalidazioni == [CLIENTE]
    assert fake.tables["ristoranti"] == []
