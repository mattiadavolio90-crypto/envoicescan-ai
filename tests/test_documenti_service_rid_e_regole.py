"""Audit §3 — Scadenziario: fix HIGH "auto-pagato RID irreversibile" +
motore regole fornitore (`_applica_regole_fornitore`) + guardia soft-delete
sullo Step 3 di `get_documenti_scadenziario`.

Prima di questi test, il ramo RID (documenti_service.py:919-920) e il motore
regole (:279-345) erano a copertura zero: tutti i test esistenti neutralizzano
`_get_fornitori_pagamenti_config_cached` a lista vuota. Confermato sul DB live
(project vthikmfpywilukizputn, 11/8/2026): 9 regole su 11 configurate sono
'rid', su 3 clienti reali (CASATI 14, LAND DEI SAPORI, TIME CAFE), 53 documenti
sotto regola RID di cui 40 con pagata=false in DB — cioè il percorso normale
della feature, non un caso di bordo.
"""
from datetime import date, timedelta

from services.documenti_service import (
    _applica_regole_fornitore,
    delete_fornitori_pagamenti_config,
    get_documenti_scadenziario,
    segna_fattura_pagata,
    upsert_fornitori_pagamenti_config,
)


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    """Fake Supabase con `.is_()` REALE (a differenza di
    test_documenti_service_scadenziario._Query, dove è no-op) e supporto a
    `.update()`: serve a difendere davvero il filtro soft-delete sullo Step 3
    e a verificare il payload scritto da segna_fattura_pagata."""

    def __init__(self, table_name, tables):
        self.table_name = table_name
        self.tables = tables
        self._filters = {}
        self._is_null = []
        self._op = "select"
        self._update_vals = None
        self._range = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def update(self, vals):
        self._op = "update"
        self._update_vals = dict(vals)
        return self

    def insert(self, vals):
        self._op = "insert"
        self._update_vals = dict(vals)
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, vals, on_conflict=None):
        self._op = "upsert"
        self._update_vals = dict(vals)
        return self

    def eq(self, key, value):
        self._filters[key] = value
        return self

    def in_(self, key, values):
        self._filters[key] = ("__in__", list(values))
        return self

    def is_(self, field, value):
        if value == "null":
            self._is_null.append(field)
        return self

    @property
    def not_(self):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def _matches(self, row):
        for k, v in self._filters.items():
            if isinstance(v, tuple) and v[0] == "__in__":
                if row.get(k) not in v[1]:
                    return False
            elif row.get(k) != v:
                return False
        for f in self._is_null:
            if row.get(f) is not None:
                return False
        return True

    def execute(self):
        rows = self.tables.setdefault(self.table_name, [])
        if self._op == "insert":
            new_row = dict(self._update_vals)
            new_row.setdefault("id", f"gen-{len(rows) + 1}")
            rows.append(new_row)
            return _Response([dict(new_row)])
        if self._op == "upsert":
            key_field = "key"  # unico uso reale: cache_version(key=...)
            key_val = self._update_vals.get(key_field)
            existing = next((r for r in rows if r.get(key_field) == key_val), None)
            if existing is not None:
                existing.update(self._update_vals)
            else:
                rows.append(dict(self._update_vals))
            return _Response([dict(self._update_vals)])

        matching = [r for r in rows if self._matches(r)]
        if self._op == "update":
            for r in matching:
                r.update(self._update_vals)
            return _Response([dict(r) for r in matching])
        if self._op == "delete":
            remaining = [r for r in rows if r not in matching]
            self.tables[self.table_name] = remaining
            return _Response([dict(r) for r in matching])
        out = [dict(r) for r in matching]
        if self._range is not None:
            start, end = self._range
            out = out[start : end + 1]
        return _Response(out)


class _RpcCall:
    def __init__(self, data):
        self._data = data

    def range(self, start, end):
        return self

    def execute(self):
        return _Response(self._data)


class _FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(name, self.tables)

    def rpc(self, name, params):
        assert name == "scadenziario_fatture_aggregate"
        user_id = params["p_user_id"]
        ristorante_ids = set(params["p_ristorante_ids"])
        rows = [
            r
            for r in self.tables.get("fatture", [])
            if r.get("user_id") == user_id
            and r.get("ristorante_id") in ristorante_ids
            and not r.get("deleted_at")
        ]
        agg = {}
        for row in rows:
            key = (row["file_origine"], row["ristorante_id"])
            if key not in agg:
                agg[key] = {
                    "file_origine": row["file_origine"],
                    "ristorante_id": row["ristorante_id"],
                    "fornitore": row.get("fornitore") or "Sconosciuto",
                    "tipo_documento": row.get("tipo_documento") or "TD01",
                    "data_documento": row.get("data_documento"),
                    "created_at": row.get("created_at"),
                    "totale_documento": 0.0,
                }
            agg[key]["totale_documento"] = round(
                agg[key]["totale_documento"] + float(row.get("totale_riga") or 0), 2
            )
        return _RpcCall(list(agg.values()))


def _doc_rid(**overrides):
    base = {
        "user_id": "u1",
        "ristorante_id": "rist-1",
        "file_origine": "rid.xml",
        "piva_fornitore": "12345678901",
        "numero_documento": "1",
        "totale_documento": 100.0,
        "scadenza_xml": None,
        "giorni_termini_xml": None,
        "scadenza_effettiva": None,
        "scadenza_source": None,
        "scadenza_override": None,
        "pagata": False,
        "pagata_at": None,
        "pagata_manuale_at": None,
        "deleted_at": None,
    }
    base.update(overrides)
    return base


def _fattura_riga(**overrides):
    base = {
        "user_id": "u1",
        "ristorante_id": "rist-1",
        "file_origine": "rid.xml",
        "fornitore": "Fornitore RID SRL",
        "tipo_documento": "TD01",
        "totale_riga": 100.0,
        "data_documento": "2026-06-01",
        "created_at": "2026-06-01T09:00:00Z",
        "deleted_at": None,
    }
    base.update(overrides)
    return base


def _regola_rid(piva="12345678901"):
    return {"piva_fornitore": piva, "modalita": "rid"}


# ─── Fix HIGH: auto-pagato RID non deve sovrascrivere la dichiarazione utente ──


def test_regola_rid_marca_pagata_quando_utente_non_ha_mai_deciso(monkeypatch):
    """Comportamento invariato: senza alcuna azione dell'utente, un fornitore
    RID continua a essere mostrato come pagato (l'automatismo è il default)."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [_regola_rid()],
    )
    fatture_rows = [_fattura_riga()]
    fatture_documenti_rows = [_doc_rid(pagata=False, pagata_manuale_at=None)]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["pagata"] is True
    assert result[0]["scadenza_source"] == "fornitore_rid"


def test_regola_rid_non_sovrascrive_depagamento_esplicito_dellutente(monkeypatch):
    """Il difetto: prima del fix, un utente che clicca "segna come non pagata"
    su una fattura RID la vedeva tornare "Pagata" al primo reload, perché il
    ramo automatico ignorava pagata=False in DB. Con pagata_manuale_at
    valorizzato (scritto da segna_fattura_pagata), la dichiarazione esplicita
    deve vincere sull'automatismo."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [_regola_rid()],
    )
    fatture_rows = [_fattura_riga()]
    fatture_documenti_rows = [
        _doc_rid(pagata=False, pagata_manuale_at="2026-08-11T10:00:00+00:00")
    ]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["pagata"] is False


def test_regola_rid_pagata_manuale_true_resta_pagata(monkeypatch):
    """Simmetria: se l'utente ha esplicitamente confermato il pagamento
    (pagata=True + pagata_manuale_at), il RID non deve alterare nulla —
    l'automatismo era comunque d'accordo."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [_regola_rid()],
    )
    fatture_rows = [_fattura_riga()]
    fatture_documenti_rows = [
        _doc_rid(pagata=True, pagata_manuale_at="2026-08-10T08:00:00+00:00")
    ]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["pagata"] is True


# ─── segna_fattura_pagata scrive sempre pagata_manuale_at ──────────────────


def test_segna_fattura_pagata_scrive_pagata_manuale_at_su_pagata_true():
    doc = _doc_rid(pagata=False, pagata_manuale_at=None)
    sb = _FakeSupabase({"fatture_documenti": [doc]})

    result = segna_fattura_pagata(
        file_origine="rid.xml", user_id="u1", ristorante_id="rist-1",
        pagata=True, supabase_client=sb,
    )

    assert result["success"] is True
    assert doc["pagata"] is True
    assert doc["pagata_manuale_at"] is not None


def test_segna_fattura_pagata_scrive_pagata_manuale_at_su_pagata_false():
    """È il caso che il fix protegge: de-pagare esplicitamente deve lasciare
    una traccia diversa da "mai toccata", anche se pagata_at torna a None."""
    doc = _doc_rid(pagata=True, pagata_at="2026-08-01", pagata_manuale_at=None)
    sb = _FakeSupabase({"fatture_documenti": [doc]})

    result = segna_fattura_pagata(
        file_origine="rid.xml", user_id="u1", ristorante_id="rist-1",
        pagata=False, supabase_client=sb,
    )

    assert result["success"] is True
    assert doc["pagata"] is False
    assert doc["pagata_at"] is None
    assert doc["pagata_manuale_at"] is not None


# ─── Motore regole fornitore: le 7 modalità mai esercitate dalla suite ─────


def test_applica_regole_fornitore_rid_usa_data_documento():
    scad, src = _applica_regole_fornitore(
        fornitore="F", piva_fornitore="12345678901", data_documento="2026-06-15",
        scadenza_xml=None, giorni_termini_xml=None, user_id="u1", ristorante_id="r1",
        regole_map={"12345678901": {"modalita": "rid"}},
    )
    assert scad == "2026-06-15"
    assert src == "fornitore_rid"


def test_applica_regole_fornitore_giorni_fissi():
    for modalita, giorni in (("30gg", 30), ("60gg", 60), ("90gg", 90)):
        scad, src = _applica_regole_fornitore(
            fornitore="F", piva_fornitore="p", data_documento="2026-01-01",
            scadenza_xml=None, giorni_termini_xml=None, user_id="u1", ristorante_id="r1",
            regole_map={"p": {"modalita": modalita}},
        )
        atteso = (date(2026, 1, 1) + timedelta(days=giorni)).isoformat()
        assert scad == atteso, modalita
        assert src == "fornitore"


def test_applica_regole_fornitore_fine_mese():
    """30gg_fm/60gg_fm/90gg_fm: fine mese + N mesi, non semplice +giorni."""
    scad, src = _applica_regole_fornitore(
        fornitore="F", piva_fornitore="p", data_documento="2026-01-15",
        scadenza_xml=None, giorni_termini_xml=None, user_id="u1", ristorante_id="r1",
        regole_map={"p": {"modalita": "30gg_fm"}},
    )
    assert scad == "2026-02-28"
    assert src == "fornitore"


def test_applica_regole_fornitore_nessuna_regola_fallback_xml():
    scad, src = _applica_regole_fornitore(
        fornitore="F", piva_fornitore="nessuna-regola", data_documento="2026-01-01",
        scadenza_xml="2026-02-01", giorni_termini_xml=None, user_id="u1", ristorante_id="r1",
        regole_map={},
    )
    assert scad == "2026-02-01"
    assert src == "xml"


def test_applica_regole_fornitore_nessuna_regola_ne_xml_fallback_giorni_termini():
    scad, src = _applica_regole_fornitore(
        fornitore="F", piva_fornitore=None, data_documento="2026-01-01",
        scadenza_xml=None, giorni_termini_xml=30, user_id="u1", ristorante_id="r1",
        regole_map={},
    )
    assert scad == "2026-01-31"
    assert src == "xml"


def test_applica_regole_fornitore_niente_ritorna_none():
    scad, src = _applica_regole_fornitore(
        fornitore=None, piva_fornitore=None, data_documento=None,
        scadenza_xml=None, giorni_termini_xml=None, user_id="u1", ristorante_id="r1",
        regole_map={},
    )
    assert scad is None
    assert src == "none"


# ─── MEDIUM: regola disattivata deve smettere di applicarsi (fix in questa sessione) ──


def test_regola_disattivata_non_si_applica_piu(monkeypatch):
    """Prima del fix, il path batch (quello realmente usato da
    get_documenti_scadenziario) non filtrava su `attiva`: disattivare una
    regola dalla UI non aveva alcun effetto sullo scadenziario."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [{"piva_fornitore": "12345678901", "modalita": "rid", "attiva": False}],
    )
    fatture_rows = [_fattura_riga()]
    fatture_documenti_rows = [_doc_rid(pagata=False, scadenza_xml="2026-07-15")]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    # Regola RID disattivata: niente auto-pagato, fallback su scadenza_xml.
    assert result[0]["pagata"] is False
    assert result[0]["scadenza_source"] == "xml"
    assert result[0]["scadenza_effettiva"] == "2026-07-15"


def test_regola_attiva_default_true_se_campo_assente(monkeypatch):
    """Retrocompatibilità: righe di regole senza il campo `attiva` (test/dati
    storici) devono continuare a essere applicate, non silenziosamente
    disattivate dal fix."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [_regola_rid()],
    )
    fatture_rows = [_fattura_riga()]
    fatture_documenti_rows = [_doc_rid(pagata=False)]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["pagata"] is True
    assert result[0]["scadenza_source"] == "fornitore_rid"


# ─── MEDIUM: filter_active mancante sullo Step 3 (fix in questa sessione) ──


def test_step3_non_prende_metadati_da_header_cestinato(monkeypatch):
    """Prima del fix, un header fatture_documenti con deleted_at valorizzato
    continuava a fornire scadenza/pagata a una fattura viva con lo stesso
    file_origine — mai filtrato da filter_active() come le altre 5 query dello
    stesso file. Vicino cestinato messo qui, non solo in `fatture`: è la
    seconda tabella che la funzione interroga (lezione già pagata nel ciclo)."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [_fattura_riga(file_origine="doc.xml", totale_riga=42.0)]
    fatture_documenti_rows = [
        _doc_rid(
            file_origine="doc.xml",
            pagata=True,
            scadenza_effettiva="2020-01-01",
            deleted_at="2026-05-20T08:44:24+00:00",
        )
    ]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert len(result) == 1
    # Nessun match con l'header cestinato: niente scadenza/pagata presi da lì.
    assert result[0]["pagata"] is False
    assert result[0]["scadenza_effettiva"] is None


def test_step3_prende_metadati_da_header_attivo_stesso_file_origine(monkeypatch):
    """Controllo positivo del test sopra: con l'header NON cestinato, i
    metadati devono continuare ad arrivare correttamente (altrimenti il fix
    filter_active() sarebbe troppo aggressivo e romperebbe il caso normale)."""
    monkeypatch.setattr(
        "services.documenti_service._get_fornitori_pagamenti_config_cached",
        lambda *a, **k: [],
    )
    fatture_rows = [_fattura_riga(file_origine="doc.xml", totale_riga=42.0)]
    fatture_documenti_rows = [
        _doc_rid(
            file_origine="doc.xml",
            pagata=True,
            scadenza_effettiva="2026-07-01",
            deleted_at=None,
        )
    ]
    sb = _FakeSupabase({
        "fatture": fatture_rows,
        "fatture_documenti": fatture_documenti_rows,
        "ristoranti": [{"id": "rist-1", "nuovi_da": None}],
    })

    result = get_documenti_scadenziario(user_id="u1", ristorante_id="rist-1", supabase_client=sb)

    assert result[0]["pagata"] is True
    assert result[0]["scadenza_effettiva"] == "2026-07-01"


# ─── MEDIUM: CRUD regole fornitore — cache invalidata, delete inesistente 404 ──


def test_upsert_regola_invalida_la_cache_locale(monkeypatch):
    """Prima del fix, clear_fornitori_cache() non aveva nessun chiamante in
    tutto il repo: la cache @_make_cache(ttl=120) di
    _get_fornitori_pagamenti_config_cached restava valida fino a 120s dopo il
    salvataggio, perché la sua chiave (user_id, ristorante_id) non include
    cache_version."""
    import services.documenti_service as ds

    sb = _FakeSupabase({"fornitori_pagamenti_config": [], "cache_version": []})
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)

    clear_calls = []
    monkeypatch.setattr(ds, "clear_fornitori_cache", lambda: clear_calls.append(1))

    result = upsert_fornitori_pagamenti_config(
        user_id="u1", ristorante_id="rist-1", piva_fornitore="12345678901",
        modalita="rid", supabase_client=sb,
    )

    assert result["ok"] is True
    assert clear_calls == [1]


def test_delete_regola_invalida_la_cache_locale(monkeypatch):
    import services.documenti_service as ds

    sb = _FakeSupabase({
        "fornitori_pagamenti_config": [
            {"id": "reg-1", "user_id": "u1", "ristorante_id": "rist-1", "piva_fornitore": "p"}
        ],
        "cache_version": [],
    })
    monkeypatch.setattr("services.get_supabase_client", lambda: sb)

    clear_calls = []
    monkeypatch.setattr(ds, "clear_fornitori_cache", lambda: clear_calls.append(1))

    result = delete_fornitori_pagamenti_config(
        user_id="u1", ristorante_id="rist-1", regola_id="reg-1", supabase_client=sb,
    )

    assert result["ok"] is True
    assert clear_calls == [1]


def test_delete_regola_inesistente_ritorna_ok_false():
    """Il difetto: prima del fix, cancellare un regola_id inesistente (o di un
    altro account) ritornava {'ok': True, 'row_count': 0} — la UI confermava
    una cancellazione mai avvenuta. Riprodotto sul DB live (project
    vthikmfpywilukizputn, 11/8/2026) con un UUID che non esiste."""
    sb = _FakeSupabase({"fornitori_pagamenti_config": [], "cache_version": []})

    result = delete_fornitori_pagamenti_config(
        user_id="u1", ristorante_id="rist-1",
        regola_id="00000000-0000-0000-0000-000000000000",
        supabase_client=sb,
    )

    assert result["ok"] is False
    assert result["row_count"] == 0


def test_delete_regola_di_un_altro_account_ritorna_ok_false():
    """Cross-tenant: eq(user_id)/eq(ristorante_id) impedivano già la
    cancellazione (nessun buco di sicurezza), ma il falso ok:True nascondeva
    anche questo caso al chiamante."""
    sb = _FakeSupabase({
        "fornitori_pagamenti_config": [
            {"id": "reg-1", "user_id": "altro-utente", "ristorante_id": "rist-1", "piva_fornitore": "p"}
        ],
    })

    result = delete_fornitori_pagamenti_config(
        user_id="u1", ristorante_id="rist-1", regola_id="reg-1", supabase_client=sb,
    )

    assert result["ok"] is False


def test_segna_fattura_pagata_non_e_cachata_la_seconda_scrittura_arriva_a_db():
    """Una SCRITTURA non puo' stare dietro una cache.

    Il 5/9, rimuovendo `_get_documenti_normalized_cached` (codice morto), il suo
    decoratore `@_make_cache(ttl=60)` e' rimasto orfano e si e' riattaccato alla
    funzione successiva del file: `segna_fattura_pagata`. `make_cache` non e' piu'
    un guscio vuoto ma una TTLCache vera, quindi la seconda chiamata con gli
    stessi argomenti entro 60s tornava dalla cache: nessuna UPDATE al DB, nessun
    bump di cache_version, nessun refresh di pagata_manuale_at — e l'endpoint
    rispondeva comunque success=True.

    I due test qui sopra non lo vedevano: usano pagata=True e pagata=False, cioe'
    chiavi di cache diverse. Serve la STESSA chiamata due volte.
    """
    doc = _doc_rid(pagata=False, pagata_manuale_at=None)
    sb = _FakeSupabase({"fatture_documenti": [doc]})

    kwargs = dict(
        file_origine="rid.xml", user_id="u1", ristorante_id="rist-1",
        pagata=True, supabase_client=sb,
    )

    assert segna_fattura_pagata(**kwargs)["success"] is True
    assert doc["pagata"] is True

    # l'utente de-marca fuori banda (o un'altra sessione cambia il dato):
    # la seconda chiamata identica DEVE tornare a scrivere, non servire la cache
    doc["pagata"] = False
    doc["pagata_manuale_at"] = None

    assert segna_fattura_pagata(**kwargs)["success"] is True
    assert doc["pagata"] is True, (
        "seconda chiamata servita dalla cache: l'API risponde success ma il DB "
        "non e' stato aggiornato"
    )
    assert doc["pagata_manuale_at"] is not None
