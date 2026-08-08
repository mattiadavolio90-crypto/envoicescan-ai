"""Test del codice VIVO di services/upload_handler.py — le funzioni raggiungibili
dal worker FastAPI di produzione (`_run_post_upload_ai_categorization` e' importata
da services/fastapi_worker.py:2125). `handle_uploaded_files` NON e' qui: e' legacy
Streamlit, raggiungibile solo da legacy_streamlit/app_controllers.py.

Due blocchi:

1. **Paginazione** (originale): difesa dei 2 punti toccati dalla remediation
   Performance HIGH (0bed331, 3/8): `response = query.execute(); rows = response.data or []`
   sostituito da `rows = fetch_all(query)` per non troncare a 1000 righe (limite
   PostgREST). I test NON verificano che il codice "chiami fetch_all" (forma):
   verificano che, davanti a una fonte che tronca come fa PostgREST, il risultato
   resti completo oltre la millesima riga.

2. **Gating AI + guardrail dominio**: il ramo che decide quale categoria viene
   davvero SCRITTA sulle righe fattura del cliente. Difende le regole di dominio
   di CLAUDE.md: #1 (niente fallback travestito, si resta 'Da Classificare' se
   nessuno riconosce la riga) e #2 ('📝 NOTE E DICITURE' solo a totale_riga == 0).
   I test dell'AI usano righe ELEGGIBILI: quelli di paginazione usano di proposito
   descrizioni vuote e non entrano mai in questo ramo.
"""
import pytest
from unittest.mock import patch

from services.ai_service import AIDailyLimitExceededError
from services.upload_handler import (
    _collect_post_upload_quality_checks,
    _find_active_exact_files_for_targets,
    _find_active_existing_files,
    _find_existing_saved_ok_events,
    _run_post_upload_ai_categorization,
)


class FakePostgrest:
    """Query-builder che si comporta come PostgREST: senza `.range()` non
    restituisce mai piu' di `max_rows` righe, e non segnala il troncamento."""

    def __init__(self, rows, max_rows=1000):
        self._rows = rows
        self._max_rows = max_rows
        self._range = None
        self.eq_filters = {}

    def table(self, *_a, **_k):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, campo=None, valore=None, *_a, **_k):
        if campo is not None:
            self.eq_filters[campo] = valore
        return self

    def is_(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._range is None:
            rows = self._rows[: self._max_rows]
        else:
            start, end = self._range
            rows = self._rows[start: min(end + 1, start + self._max_rows)]
        return type("R", (), {"data": rows})()


def _quality_row(prezzo=1.0, needs_review=False, categoria="ALIMENTARI"):
    return {
        "file_origine": "f.xml",
        "prezzo_unitario": prezzo,
        "categoria": categoria,
        "needs_review": needs_review,
        "descrizione": "PASTA",
    }


class TestCollectPostUploadQualityChecksPaginazione:
    def test_rows_saved_conta_tutte_le_righe_oltre_1000(self):
        righe = [_quality_row() for _ in range(1500)]
        client = FakePostgrest(righe)

        checks = _collect_post_upload_quality_checks(client, "u1", ["f.xml"])

        assert checks["verification_ok"] is True
        assert checks["rows_saved"] == 1500

    def test_contatori_qualita_visti_su_tutte_le_pagine(self):
        righe = [_quality_row() for _ in range(1500)]
        # una riga "sospetta" nella prima pagina, una nella seconda
        righe[500] = _quality_row(prezzo=0.0, needs_review=True, categoria="Da Classificare")
        righe[1200] = _quality_row(prezzo=0.0, needs_review=True, categoria="Da Classificare")
        client = FakePostgrest(righe)

        checks = _collect_post_upload_quality_checks(client, "u1", ["f.xml"])

        assert checks["zero_price_rows"] == 2
        assert checks["needs_review_rows"] == 2
        assert checks["uncategorized_rows"] == 2

    def test_paginazione_completa_anche_con_ristorante_id(self):
        """Il ramo multi-sede: add_ristorante_filter aggiunge .eq('ristorante_id')
        PRIMA di fetch_all. E' il ramo che gira in produzione per i clienti con
        piu' sedi, e va paginato come l'altro."""
        righe = [_quality_row() for _ in range(1500)]
        client = FakePostgrest(righe)

        checks = _collect_post_upload_quality_checks(
            client, "u1", ["f.xml"], ristorante_id="r1"
        )

        # senza questa asserzione il test passerebbe anche se il filtro sede
        # non fosse mai stato applicato
        assert client.eq_filters.get("ristorante_id") == "r1"
        assert checks["rows_saved"] == 1500

    def test_supabase_client_none_ritorna_default_senza_verificare(self):
        checks = _collect_post_upload_quality_checks(None, "u1", ["f.xml"])
        assert checks["verification_ok"] is False
        assert checks["rows_saved"] == 0

    def test_file_names_vuoto_ritorna_default_senza_verificare(self):
        client = FakePostgrest([_quality_row()])
        checks = _collect_post_upload_quality_checks(client, "u1", [])
        assert checks["verification_ok"] is False
        assert checks["rows_saved"] == 0


class TestRunPostUploadAiCategorizationPaginazione:
    def _row_non_eligible(self):
        # descrizione vuota -> _should_skip_post_upload_ai_for_row ritorna
        # True/'dati_insufficienti': la riga resta "unresolved" ma non chiama l'AI.
        return {
            "id": 1,
            "descrizione": "",
            "fornitore": "",
            "iva_percentuale": 0,
            "prezzo_unitario": 0,
            "totale_riga": 0,
            "quantita": 0,
            "categoria": "Da Classificare",
            "needs_review": True,
            "tipo_documento": "TD01",
            "file_origine": "f.xml",
        }

    @patch("services.upload_handler.carica_memoria_completa", return_value=None)
    @patch("services.upload_handler.invalida_cache_memoria", return_value=None)
    def test_rows_scanned_conta_le_righe_non_classificate_oltre_1000(self, _mock_inv, _mock_mem):
        righe = [self._row_non_eligible() for _ in range(1500)]
        client = FakePostgrest(righe)

        summary = _run_post_upload_ai_categorization(client, "u1", ["f.xml"])

        assert summary["rows_scanned"] == 1500
        assert summary["completed"] is True

    @patch("services.upload_handler.carica_memoria_completa", return_value=None)
    @patch("services.upload_handler.invalida_cache_memoria", return_value=None)
    def test_paginazione_completa_anche_con_ristorante_id(self, _mock_inv, _mock_mem):
        righe = [self._row_non_eligible() for _ in range(1500)]
        client = FakePostgrest(righe)

        summary = _run_post_upload_ai_categorization(
            client, "u1", ["f.xml"], ristorante_id="r1"
        )

        assert client.eq_filters.get("ristorante_id") == "r1"
        assert summary["rows_scanned"] == 1500

    def test_supabase_client_none_ritorna_summary_default(self):
        summary = _run_post_upload_ai_categorization(None, "u1", ["f.xml"])
        assert summary["rows_scanned"] == 0
        assert summary["completed"] is False

    def test_user_id_vuoto_ritorna_summary_default(self):
        client = FakePostgrest([self._row_non_eligible()])
        summary = _run_post_upload_ai_categorization(client, "", ["f.xml"])
        assert summary["rows_scanned"] == 0
        assert summary["completed"] is False


# ---------------------------------------------------------------------------
# Gruppo B — dedup: quali file risultano gia' presenti
# ---------------------------------------------------------------------------


class FakeTableRouter:
    """Client Supabase che serve righe diverse per tabella e registra le
    scritture. Serve dove FakePostgrest non basta perche' la funzione sotto
    test tocca piu' tabelle (fatture + prodotti_utente) o scrive."""

    def __init__(self, rows_by_table=None, max_rows=1000, raise_on_select=None):
        self._rows_by_table = rows_by_table or {}
        self._max_rows = max_rows
        self._raise_on_select = raise_on_select
        self.updates = []
        self.upserts = []

    def table(self, name):
        return _FakeQuery(self, name)


class _FakeQuery:
    def __init__(self, router, table_name):
        self._router = router
        self._table = table_name
        self._range = None
        self._in_values = None
        self._in_field = None
        self._deleted_at_null = False
        self._update_payload = None
        self.eq_filters = {}

    def select(self, *_a, **_k):
        if self._router._raise_on_select == self._table:
            raise RuntimeError("query fallita")
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def upsert(self, rows, **_k):
        self._router.upserts.append(list(rows))
        return self

    def eq(self, campo=None, valore=None, *_a, **_k):
        if campo is not None:
            self.eq_filters[campo] = valore
        return self

    def is_(self, campo=None, valore=None, *_a, **_k):
        # filter_active() = .is_("deleted_at", "null"): regola di dominio #5
        if campo == "deleted_at" and str(valore) == "null":
            self._deleted_at_null = True
        return self

    def in_(self, campo=None, valori=None, *_a, **_k):
        self._in_field = campo
        self._in_values = list(valori or [])
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._update_payload is not None:
            self._router.updates.append({
                "table": self._table,
                "payload": dict(self._update_payload),
                "ids": list(self._in_values or []),
                "ristorante_id": self.eq_filters.get("ristorante_id"),
            })
            return type("R", (), {"data": []})()

        rows = self._router._rows_by_table.get(self._table, [])
        # I filtri vanno APPLICATI davvero, non solo registrati: un fake che
        # restituisce l'intera tabella non si accorgerebbe della rimozione di
        # .eq('user_id') o .in_('file_origine') — cioe' proprio di una perdita
        # di isolamento multi-tenant in lettura.
        rows = [r for r in rows if self._matches(r)]
        if self._range is None:
            rows = rows[: self._router._max_rows]
        else:
            start, end = self._range
            rows = rows[start: min(end + 1, start + self._router._max_rows)]
        return type("R", (), {"data": rows})()

    def _matches(self, row):
        for campo, valore in self.eq_filters.items():
            if campo in row and str(row.get(campo)) != str(valore):
                return False
        if self._in_field is not None and self._in_field in row:
            if str(row.get(self._in_field)) not in {str(v) for v in (self._in_values or [])}:
                return False
        if self._deleted_at_null and row.get("deleted_at") is not None:
            return False
        return True


class TestFindExistingSavedOkEvents:
    def _event(self, file_name="F.XML", created_at="2026-05-01T10:00:00Z", ristorante_id=None):
        return {
            "file_name": file_name,
            "created_at": created_at,
            "details": {"ristorante_id": ristorante_id} if ristorante_id else {},
        }

    def test_nessun_evento(self):
        client = FakeTableRouter({"upload_events": []})
        assert _find_existing_saved_ok_events(client, "u1", "r1", ["f.xml"]) == {}

    def test_client_none(self):
        assert _find_existing_saved_ok_events(None, "u1", "r1", ["f.xml"]) == {}

    def test_file_names_vuoto(self):
        client = FakeTableRouter({"upload_events": [self._event()]})
        assert _find_existing_saved_ok_events(client, "u1", "r1", []) == {}

    def test_match_case_insensitive_sulla_chiave_di_ritorno(self):
        """La chiave del dict di ritorno e' sempre lowercase, anche se a DB il
        nome ha maiuscole.

        NB: la case-insensitivity vale solo DOPO che PostgREST ha restituito la
        riga. Il filtro `.in_("file_name", raw_targets)` usa i nomi grezzi ed e'
        case-SENSITIVE lato DB: se il client chiede 'fattura.xml' e a DB c'e'
        'Fattura.XML', la riga non torna proprio. Qui passo il nome con la
        stessa grafia del DB per restare nello scenario reale."""
        client = FakeTableRouter({"upload_events": [self._event(file_name="Fattura.XML")]})
        out = _find_existing_saved_ok_events(client, "u1", None, ["Fattura.XML"])
        assert "fattura.xml" in out

    def test_evento_di_altra_sede_escluso(self):
        client = FakeTableRouter({"upload_events": [self._event(ristorante_id="r2")]})
        assert _find_existing_saved_ok_events(client, "u1", "r1", ["F.XML"]) == {}

    def test_evento_legacy_senza_sede_accettato(self):
        """Eventi salvati prima del multi-sede non hanno ristorante_id nei
        details: vanno considerati compatibili, non scartati."""
        client = FakeTableRouter({"upload_events": [self._event()]})
        out = _find_existing_saved_ok_events(client, "u1", "r1", ["F.XML"])
        assert "f.xml" in out

    def test_details_non_dict_non_solleva(self):
        ev = self._event()
        ev["details"] = "stringa-legacy"
        client = FakeTableRouter({"upload_events": [ev]})
        out = _find_existing_saved_ok_events(client, "u1", "r1", ["F.XML"])
        assert "f.xml" in out

    def test_tiene_evento_piu_recente(self):
        client = FakeTableRouter({"upload_events": [
            self._event(created_at="2026-05-01T10:00:00Z"),
            self._event(created_at="2026-06-01T10:00:00Z"),
        ]})
        out = _find_existing_saved_ok_events(client, "u1", None, ["F.XML"])
        assert out["f.xml"]["created_at"] == "2026-06-01T10:00:00Z"

    def test_file_name_vuoto_ignorato(self):
        client = FakeTableRouter({"upload_events": [self._event(file_name="  ")]})
        assert _find_existing_saved_ok_events(client, "u1", None, ["F.XML"]) == {}

    def test_eccezione_non_solleva(self):
        client = FakeTableRouter({}, raise_on_select="upload_events")
        assert _find_existing_saved_ok_events(client, "u1", "r1", ["f.xml"]) == {}


class TestFindActiveExistingFiles:
    def _row(self, nome):
        return {"file_origine": nome}

    def test_client_none(self):
        assert _find_active_existing_files(None, "u1", None) == (set(), set())

    def test_user_id_vuoto(self):
        assert _find_active_existing_files(FakePostgrest([]), "", None) == (set(), set())

    def test_nessuna_riga(self):
        exact, base = _find_active_existing_files(FakePostgrest([]), "u1", None)
        assert exact == set() and base == set()

    def test_una_pagina(self):
        client = FakePostgrest([self._row("A.xml"), self._row("B.xml")])
        exact, base = _find_active_existing_files(client, "u1", None)
        assert exact == {"a.xml", "b.xml"}
        assert len(base) == 2

    def test_oltre_mille_righe_non_troncato(self):
        """Il cliente con molte fatture: se la dedup vedesse solo le prime 1000
        ricaricherebbe file gia' presenti."""
        righe = [self._row(f"F{i}.xml") for i in range(1500)]
        exact, _ = _find_active_existing_files(FakePostgrest(righe), "u1", None)
        assert len(exact) == 1500

    def test_esattamente_mille_righe_chiede_pagina_successiva(self):
        righe = [self._row(f"F{i}.xml") for i in range(1000)]
        exact, _ = _find_active_existing_files(FakePostgrest(righe), "u1", None)
        assert len(exact) == 1000

    def test_filtro_sede_applicato(self):
        client = FakePostgrest([self._row("A.xml")])
        _find_active_existing_files(client, "u1", "r1")
        assert client.eq_filters.get("ristorante_id") == "r1"

    def test_file_origine_vuoto_ignorato(self):
        client = FakePostgrest([self._row("  "), self._row("A.xml")])
        exact, _ = _find_active_existing_files(client, "u1", None)
        assert exact == {"a.xml"}


class TestFindActiveExactFilesForTargets:
    def test_client_none(self):
        assert _find_active_exact_files_for_targets(None, "u1", None, ["f.xml"]) == set()

    def test_file_names_vuoto(self):
        assert _find_active_exact_files_for_targets(FakePostgrest([]), "u1", None, []) == set()

    def test_solo_nomi_bianchi(self):
        assert _find_active_exact_files_for_targets(FakePostgrest([]), "u1", None, ["  ", ""]) == set()

    def test_normalizza_lower(self):
        client = FakePostgrest([{"file_origine": " Fattura.XML "}])
        out = _find_active_exact_files_for_targets(client, "u1", None, ["Fattura.XML"])
        assert out == {"fattura.xml"}

    def test_filtro_sede_applicato(self):
        client = FakePostgrest([{"file_origine": "a.xml"}])
        _find_active_exact_files_for_targets(client, "u1", "r1", ["a.xml"])
        assert client.eq_filters.get("ristorante_id") == "r1"

    def test_eccezione_non_solleva(self):
        client = FakeTableRouter({}, raise_on_select="fatture")
        assert _find_active_exact_files_for_targets(client, "u1", None, ["f.xml"]) == set()


class TestCollectPostUploadQualityChecksDettaglio:
    def _row(self, categoria="ALIMENTARI", descrizione="PASTA", prezzo=1.0, needs_review=False):
        return {
            "file_origine": "f.xml",
            "prezzo_unitario": prezzo,
            "categoria": categoria,
            "needs_review": needs_review,
            "descrizione": descrizione,
        }

    def test_esempi_non_classificati_cappati_a_otto(self):
        righe = [
            self._row(categoria="Da Classificare", descrizione=f"PRODOTTO {i}")
            for i in range(20)
        ]
        checks = _collect_post_upload_quality_checks(FakePostgrest(righe), "u1", ["f.xml"])
        assert checks["uncategorized_rows"] == 20
        assert len(checks["uncategorized_examples"]) == 8
        assert checks["uncategorized_unique_products"] == 20

    def test_dedup_esempi_case_insensitive(self):
        righe = [
            self._row(categoria="Da Classificare", descrizione="Pasta"),
            self._row(categoria="Da Classificare", descrizione="PASTA"),
            self._row(categoria="Da Classificare", descrizione="pasta"),
        ]
        checks = _collect_post_upload_quality_checks(FakePostgrest(righe), "u1", ["f.xml"])
        assert checks["uncategorized_rows"] == 3
        assert checks["uncategorized_unique_products"] == 1
        assert checks["uncategorized_examples"] == ["Pasta"]

    def test_note_rows_contate(self):
        righe = [
            self._row(categoria="📝 NOTE E DICITURE"),
            self._row(categoria="📝 NOTE E DICITURE"),
            self._row(),
        ]
        checks = _collect_post_upload_quality_checks(FakePostgrest(righe), "u1", ["f.xml"])
        assert checks["note_rows"] == 2

    def test_descrizione_vuota_non_finisce_negli_esempi(self):
        righe = [self._row(categoria="Da Classificare", descrizione="   ")]
        checks = _collect_post_upload_quality_checks(FakePostgrest(righe), "u1", ["f.xml"])
        assert checks["uncategorized_rows"] == 1
        assert checks["uncategorized_examples"] == []

    def test_prezzo_non_convertibile_conta_come_zero(self):
        righe = [self._row(prezzo="non-un-numero")]
        checks = _collect_post_upload_quality_checks(FakePostgrest(righe), "u1", ["f.xml"])
        assert checks["zero_price_rows"] == 1

    def test_eccezione_popola_verification_error(self):
        client = FakeTableRouter({}, raise_on_select="fatture")
        checks = _collect_post_upload_quality_checks(client, "u1", ["f.xml"])
        assert checks["verification_ok"] is False
        assert "verification_error" in checks


# ---------------------------------------------------------------------------
# Gruppo C — gating AI: quale categoria viene davvero SCRITTA
# ---------------------------------------------------------------------------


def _eligible_row(row_id=1, descrizione="PASTA PENNE RIGATE 500G", totale_riga=10.0,
                  prezzo=2.5, categoria="Da Classificare", **extra):
    """Riga che SUPERA _should_skip_post_upload_ai_for_row e arriva all'AI."""
    row = {
        "id": row_id,
        "descrizione": descrizione,
        "fornitore": "FORNITORE SPA",
        "iva_percentuale": 10,
        "prezzo_unitario": prezzo,
        "totale_riga": totale_riga,
        "quantita": 1,
        "categoria": categoria,
        "needs_review": True,
        "tipo_documento": "TD01",
        "file_origine": "f.xml",
        # user_id/deleted_at servono al fake per applicare davvero i filtri
        # .eq('user_id') e filter_active(): senza, l'isolamento non e' difeso.
        "user_id": "u1",
        "deleted_at": None,
    }
    row.update(extra)
    return row


def _run_with_ai(rows, categories, confidences, rows_by_table=None, ristorante_id=None,
                 ai_side_effect=None):
    """Esegue la funzione con l'AI mockata. classify_special_row e
    _categoria_affidabile restano REALI: sono loro a decidere, mockarle
    renderebbe il test una tautologia."""
    tables = {"fatture": rows}
    tables.update(rows_by_table or {})
    client = FakeTableRouter(tables)

    if ai_side_effect is not None:
        ai_mock = patch("services.upload_handler.classifica_via_worker_con_confidenza",
                        side_effect=ai_side_effect)
    else:
        ai_mock = patch("services.upload_handler.classifica_via_worker_con_confidenza",
                        return_value=(categories, confidences))

    with patch("services.upload_handler.carica_memoria_completa", return_value=None), \
         patch("services.upload_handler.invalida_cache_memoria", return_value=None), \
         patch("services.upload_handler.ottieni_hint_per_ai", return_value=""), \
         ai_mock:
        summary = _run_post_upload_ai_categorization(
            client, "u1", ["f.xml"], ristorante_id=ristorante_id
        )
    return summary, client


def _categorie_scritte(client):
    """(categoria, needs_review) -> ids, come effettivamente scritto su fatture."""
    return {
        (u["payload"]["categoria"], u["payload"]["needs_review"]): u["ids"]
        for u in client.updates if u["table"] == "fatture"
    }


class TestGuardrailNoteEDiciture:
    """Regola di dominio #2 (CLAUDE.md): '📝 NOTE E DICITURE' e' consentita SOLO
    per righe con totale_riga == 0. Una dicitura con importo != 0 non e' una nota
    a costo nullo: metterla in NOTE la toglierebbe dai costi e sottostimerebbe il
    foodcost del cliente."""

    def test_dicitura_a_importo_zero_diventa_note(self):
        rows = [_eligible_row(row_id=1, descrizione="DDT N. 4455", totale_riga=0.0, prezzo=0.0)]
        summary, client = _run_with_ai(rows, [], [])

        scritte = _categorie_scritte(client)
        assert ("📝 NOTE E DICITURE", False) in scritte
        assert scritte[("📝 NOTE E DICITURE", False)] == [1]
        assert summary["resolved_rows"] == 1

    def test_riga_gemella_con_importo_non_va_in_note(self):
        """Stessa descrizione, due righe: quella a zero diventa NOTE, quella con
        importo NO — resta da classificare e va all'AI. E' il caso che il
        guardrail esiste per impedire."""
        rows = [
            _eligible_row(row_id=1, descrizione="SPESE TRASPORTO", totale_riga=0.0, prezzo=0.0),
            _eligible_row(row_id=2, descrizione="SPESE TRASPORTO", totale_riga=25.0, prezzo=25.0),
        ]
        summary, client = _run_with_ai(rows, [], [])

        scritte = _categorie_scritte(client)
        note_ids = scritte.get(("📝 NOTE E DICITURE", False), [])
        assert note_ids == [1], "solo la riga a importo zero puo' diventare NOTE"
        assert 2 not in note_ids
        assert "SPESE TRASPORTO" in summary["remaining_descriptions"]

    def test_riga_con_solo_prezzo_non_va_in_note(self):
        """totale_riga == 0 ma prezzo != 0: _row_importo ricade sul prezzo, la
        riga NON e' a costo nullo."""
        rows = [_eligible_row(row_id=1, descrizione="RIF. ORDINE 99", totale_riga=0.0, prezzo=12.0)]
        summary, client = _run_with_ai(rows, [], [])

        assert ("📝 NOTE E DICITURE", False) not in _categorie_scritte(client)
        assert summary["resolved_rows"] == 0
        # senza questa, l'assert sopra sarebbe vero anche su updates vuoto
        assert "RIF. ORDINE 99" in summary["remaining_descriptions"]

    def test_importo_negativo_non_va_in_note(self):
        """Storni/note di credito: importo != 0, quindi fuori da NOTE.

        L'asserzione NON puo' essere solo `NOTE not in updates`: con questa riga
        gli update sono vuoti, e su un dict vuoto quell'assert e' vero per
        costruzione (passerebbe anche se il guardrail non esistesse). Verifico
        quindi anche che la riga sia rimasta davvero in coda al cliente."""
        rows = [_eligible_row(row_id=1, descrizione="RIF. ORDINE 99", totale_riga=-30.0, prezzo=-30.0)]
        summary, client = _run_with_ai(rows, [], [])

        assert ("📝 NOTE E DICITURE", False) not in _categorie_scritte(client)
        assert summary["resolved_rows"] == 0
        assert "RIF. ORDINE 99" in summary["remaining_descriptions"]

    def test_secondo_guardrail_dopo_lai_su_prodotto_normale(self):
        """Il guardrail DENTRO il loop AI (riga 712), diverso da quello pre-AI.

        Ci si arriva per DUE strade, perche' `categoria_target` e'
        `force_categoria or categoria_finale`: la seconda e' la risposta
        dell'AI. Quindi basta che l'AI risponda NOTE su un prodotto qualunque —
        ed e' lo scenario piu' probabile in produzione, non un caso limite.
        Con importo != 0 la riga NON puo' restare in NOTE, altrimenti il costo
        sparisce dai margini."""
        rows = [_eligible_row(row_id=1, descrizione="PASTA PENNE RIGATE 500G",
                              totale_riga=25.0, prezzo=5.0)]
        _summary, client = _run_with_ai(rows, ["📝 NOTE E DICITURE"], ["alta"])

        scritte = _categorie_scritte(client)
        assert ("📝 NOTE E DICITURE", False) not in scritte
        assert scritte.get(("Da Classificare", True)) == [1]

    def test_secondo_guardrail_dopo_lai_via_force_categoria(self):
        """L'altra strada per la riga 712: `force_categoria` valorizzato da
        classify_special_row. 'FUSTI' (da _PURE_DICITURE_EXACT) e' una delle
        due sole descrizioni che superano _should_skip_post_upload_ai_for_row
        e finiscono comunque nel bucket DICITURA — qui la categoria NOTE non
        arriva dall'AI ma dalla regola speciale."""
        rows = [_eligible_row(row_id=1, descrizione="FUSTI", totale_riga=25.0, prezzo=5.0)]
        _summary, client = _run_with_ai(rows, ["CARNE E SALUMI"], ["alta"])

        scritte = _categorie_scritte(client)
        assert ("📝 NOTE E DICITURE", False) not in scritte
        assert scritte.get(("Da Classificare", True)) == [1]

    def test_secondo_guardrail_lascia_passare_omaggio_totale_zero(self):
        """Stessa riga con totale_riga == 0 ma prezzo di listino > 0 (omaggio,
        sconto 100%): li' NOTE E DICITURE e' legittima. E' lo scenario che i
        commenti del codice chiedono esplicitamente di NON rompere ricadendo
        sul prezzo: la fonte di verita' e' totale_riga."""
        rows = [_eligible_row(row_id=1, descrizione="FUSTI", totale_riga=0.0, prezzo=5.0)]
        _summary, client = _run_with_ai(rows, ["📝 NOTE E DICITURE"], ["alta"])

        assert ("📝 NOTE E DICITURE", False) in _categorie_scritte(client)


class TestPrincipio2406Gating:
    """Regola di dominio #1: si SCRIVE una categoria solo se il runtime
    deterministico la conferma o l'AI e' 'alta' su descrizione non dubbia.
    Altrimenti resta 'Da Classificare' — mai un'ipotesi travestita da dato."""

    def test_confidence_bassa_resta_da_classificare(self):
        rows = [_eligible_row(row_id=1)]
        summary, client = _run_with_ai(rows, ["CARNE E SALUMI"], ["bassa"])

        scritte = _categorie_scritte(client)
        assert ("CARNE E SALUMI", False) not in scritte
        assert scritte.get(("Da Classificare", True)) == [1]

    def test_confidence_media_non_confermata_resta_da_classificare(self):
        rows = [_eligible_row(row_id=1)]
        _summary, client = _run_with_ai(rows, ["CARNE E SALUMI"], ["media"])

        scritte = _categorie_scritte(client)
        assert scritte.get(("Da Classificare", True)) == [1]
        assert ("CARNE E SALUMI", False) not in scritte

    def test_confidence_alta_scrive_la_categoria(self):
        rows = [_eligible_row(row_id=1)]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            summary, client = _run_with_ai(rows, ["PASTA RISO E CEREALI"], ["alta"])

        scritte = _categorie_scritte(client)
        assert ("PASTA RISO E CEREALI", False) in scritte
        assert summary["resolved_rows"] == 1

    def test_confidence_alta_ma_descrizione_dubbia_resta_da_classificare(self):
        rows = [_eligible_row(row_id=1)]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=True), \
             patch("services.upload_handler.applica_correzioni_dizionario",
                   return_value="Da Classificare"), \
             patch("services.upload_handler.applica_regole_categoria_forti",
                   return_value=("Da Classificare", None)):
            _summary, client = _run_with_ai(rows, ["CARNE E SALUMI"], ["alta"])

        assert _categorie_scritte(client).get(("Da Classificare", True)) == [1]

    def test_conferma_deterministica_basta_anche_con_confidence_media(self):
        """Se dizionario/regole forti confermano, la categoria e' affidabile
        anche senza 'alta': e' il runtime a garantirla, non il modello."""
        rows = [_eligible_row(row_id=1)]
        with patch("services.upload_handler.applica_correzioni_dizionario",
                   return_value="CARNE E SALUMI"), \
             patch("services.upload_handler.applica_regole_categoria_forti",
                   return_value=("CARNE E SALUMI", None)):
            _summary, client = _run_with_ai(rows, ["CARNE E SALUMI"], ["media"])

        assert ("CARNE E SALUMI", False) in _categorie_scritte(client)

    def test_ai_ritorna_servizi_e_consulenze_non_e_affidabile(self):
        """SERVIZI E CONSULENZE era il vecchio fallback travestito: non deve
        mai essere scritto come esito di un'ipotesi AI."""
        rows = [_eligible_row(row_id=1)]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            _summary, client = _run_with_ai(rows, ["SERVIZI E CONSULENZE"], ["alta"])

        scritte = _categorie_scritte(client)
        assert scritte.get(("Da Classificare", True)) == [1]

    def test_ai_ritorna_da_classificare_finisce_nei_remaining(self):
        rows = [_eligible_row(row_id=1)]
        summary, client = _run_with_ai(rows, ["Da Classificare"], ["bassa"])

        assert _categorie_scritte(client) == {}
        assert summary["remaining_reason_counts"].get("dati_insufficienti") == 1

    def test_invariante_da_classificare_sempre_needs_review(self):
        """Nessuna riga 'Da Classificare' puo' uscire con needs_review=False,
        altrimenti sparisce dalla coda del cliente."""
        rows = [_eligible_row(row_id=i) for i in range(1, 4)]
        _summary, client = _run_with_ai(
            rows, ["CARNE E SALUMI"] * 3, ["bassa"] * 3
        )
        for (categoria, needs_review) in _categorie_scritte(client):
            if str(categoria).strip() == "Da Classificare":
                assert needs_review is True


class TestFallbackAiNonDisponibile:
    def test_quota_esaurita_marca_rate_limited(self):
        rows = [_eligible_row(row_id=1)]
        summary, client = _run_with_ai(
            rows, [], [], ai_side_effect=AIDailyLimitExceededError(500, 500)
        )

        assert summary["ai_rate_limited"] is True
        assert _categorie_scritte(client).get(("Da Classificare", True)) is None
        assert summary["remaining_reason_counts"].get("dati_insufficienti") == 1

    def test_quota_esaurita_non_ritenta_sui_chunk_successivi(self):
        """>30 descrizioni eleggibili = 2 chunk. Il secondo non deve nemmeno
        chiamare l'AI: fallirebbe uguale e costerebbe una richiesta."""
        rows = [_eligible_row(row_id=i, descrizione=f"PRODOTTO ALIMENTARE NUMERO {i}")
                for i in range(1, 41)]
        chiamate = []

        def _ai(chunk, **_k):
            chiamate.append(list(chunk))
            raise AIDailyLimitExceededError(500, 500)

        summary, _client = _run_with_ai(rows, [], [], ai_side_effect=_ai)

        assert len(chiamate) == 1, "il secondo chunk non deve ritentare"
        assert summary["ai_rate_limited"] is True
        assert summary["remaining_reason_counts"].get("quota_ai_esaurita") == 10

    def test_errore_generico_non_marca_rate_limited(self):
        rows = [_eligible_row(row_id=1)]
        summary, _client = _run_with_ai(
            rows, [], [], ai_side_effect=RuntimeError("worker giu")
        )

        assert summary["ai_rate_limited"] is False
        assert summary["completed"] is True


class TestMemoriaEOverrideManuale:
    def test_override_manuale_del_cliente_non_sovrascritto(self):
        """Priorita' MAX del cliente: se ha classificato a mano una descrizione,
        l'AI non deve riscriverla in memoria al prossimo upload."""
        rows = [_eligible_row(row_id=1, descrizione="PRODOTTO SPECIALE CASA")]
        prodotti_utente = [{
            "descrizione": "PRODOTTO SPECIALE CASA",
            "classificato_da": "Manuale (cliente)",
        }]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False), \
             patch("services.upload_handler.get_descrizione_normalizzata_e_originale",
                   return_value=("PRODOTTO SPECIALE CASA", "PRODOTTO SPECIALE CASA")):
            _summary, client = _run_with_ai(
                rows, ["CARNE E SALUMI"], ["alta"],
                rows_by_table={"prodotti_utente": prodotti_utente},
            )

        assert client.upserts == [], "override manuale sovrascritto"

    def test_senza_override_la_memoria_viene_scritta(self):
        rows = [_eligible_row(row_id=1, descrizione="PRODOTTO SPECIALE CASA")]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False), \
             patch("services.upload_handler.get_descrizione_normalizzata_e_originale",
                   return_value=("PRODOTTO SPECIALE CASA", "PRODOTTO SPECIALE CASA")):
            _summary, client = _run_with_ai(
                rows, ["CARNE E SALUMI"], ["alta"],
                rows_by_table={"prodotti_utente": []},
            )

        assert len(client.upserts) == 1
        assert client.upserts[0][0]["categoria"] == "CARNE E SALUMI"
        assert client.upserts[0][0]["classificato_da"] == "AI (auto-upload)"

    def test_categoria_scartata_dal_gating_non_entra_in_memoria(self):
        """Una categoria non affidabile non deve diventare 'verita'' per il
        prossimo upload: altrimenti il flusso onesto e' aggirato."""
        rows = [_eligible_row(row_id=1)]
        _summary, client = _run_with_ai(
            rows, ["CARNE E SALUMI"], ["bassa"],
            rows_by_table={"prodotti_utente": []},
        )
        assert client.upserts == []


class TestRaggruppamentoUpdate:
    def test_righe_con_stesso_esito_in_un_solo_update(self):
        """3 righe, stesso esito = 1 chiamata .update().in_(), non 3."""
        rows = [_eligible_row(row_id=i) for i in range(1, 4)]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            _summary, client = _run_with_ai(rows, ["PASTA RISO E CEREALI"], ["alta"])

        update_fatture = [u for u in client.updates if u["table"] == "fatture"]
        assert len(update_fatture) == 1
        assert sorted(update_fatture[0]["ids"]) == [1, 2, 3]

    def test_filtro_sede_propagato_sugli_update(self):
        """Scrittura multi-sede: l'update NON deve poter toccare righe di
        un'altra sede."""
        rows = [_eligible_row(row_id=1)]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            _summary, client = _run_with_ai(
                rows, ["PASTA RISO E CEREALI"], ["alta"], ristorante_id="r1"
            )

        update_fatture = [u for u in client.updates if u["table"] == "fatture"]
        assert update_fatture and all(u["ristorante_id"] == "r1" for u in update_fatture)

    def test_importi_non_numerici_non_fanno_esplodere_il_flusso(self):
        """Dati sporchi dal parser XML: totale_riga/prezzo/iva non convertibili
        vengono trattati come 0, non sollevano."""
        rows = [_eligible_row(
            row_id=1,
            descrizione="DDT N. 4455",
            totale_riga="non-un-numero",
            prezzo="nemmeno",
            iva_percentuale="x",
        )]
        summary, client = _run_with_ai(rows, [], [])

        assert summary["completed"] is True
        assert ("📝 NOTE E DICITURE", False) in _categorie_scritte(client)

    def test_riga_senza_id_saltata(self):
        rows = [_eligible_row(row_id=None), _eligible_row(row_id=2)]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            _summary, client = _run_with_ai(rows, ["PASTA RISO E CEREALI"], ["alta"])

        update_fatture = [u for u in client.updates if u["table"] == "fatture"]
        assert update_fatture and update_fatture[0]["ids"] == [2]

    def test_errore_inatteso_finisce_in_summary_error(self):
        """La funzione non deve mai propagare: l'upload del cliente e' gia'
        andato a buon fine, la categorizzazione e' un di piu'."""
        class _Boom:
            def table(self, *_a, **_k):
                raise RuntimeError("db esploso")

        summary = _run_post_upload_ai_categorization(_Boom(), "u1", ["f.xml"])
        assert summary["completed"] is False
        assert "db esploso" in summary.get("error", "")

    def test_filtro_override_manuale_fallito_non_blocca_lupsert(self):
        """Se la lettura di prodotti_utente fallisce, la memoria si scrive
        comunque: il filtro e' una protezione, non un gate bloccante."""
        rows = [_eligible_row(row_id=1, descrizione="PRODOTTO SPECIALE CASA")]
        client = FakeTableRouter({"fatture": rows}, raise_on_select="prodotti_utente")

        with patch("services.upload_handler.carica_memoria_completa", return_value=None), \
             patch("services.upload_handler.invalida_cache_memoria", return_value=None), \
             patch("services.upload_handler.ottieni_hint_per_ai", return_value=""), \
             patch("services.upload_handler.descrizione_e_dubbia", return_value=False), \
             patch("services.upload_handler.classifica_via_worker_con_confidenza",
                   return_value=(["CARNE E SALUMI"], ["alta"])):
            summary = _run_post_upload_ai_categorization(client, "u1", ["f.xml"])

        assert summary["completed"] is True
        assert len(client.upserts) == 1

    def test_non_tocca_le_righe_di_un_altro_utente(self):
        """Isolamento multi-tenant in LETTURA. Senza questo test la rimozione
        di `.eq('user_id', ...)` dalla SELECT passerebbe la suite: il fake
        filtra, ma se in tabella c'e' una sola riga non c'e' nulla da escludere."""
        rows = [
            _eligible_row(row_id=1, user_id="u1"),
            _eligible_row(row_id=99, user_id="ALTRO-UTENTE"),
        ]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            summary, client = _run_with_ai(rows, ["PASTA RISO E CEREALI"], ["alta"])

        assert summary["rows_scanned"] == 1
        update_fatture = [u for u in client.updates if u["table"] == "fatture"]
        assert update_fatture and update_fatture[0]["ids"] == [1]
        assert 99 not in update_fatture[0]["ids"]

    def test_non_tocca_le_righe_di_un_altro_file(self):
        """Stessa logica per `.in_('file_origine', ...)`: l'upload categorizza
        solo i file appena caricati, non tutto lo storico del cliente."""
        rows = [
            _eligible_row(row_id=1, file_origine="f.xml"),
            _eligible_row(row_id=99, file_origine="VECCHIA.xml"),
        ]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            summary, client = _run_with_ai(rows, ["PASTA RISO E CEREALI"], ["alta"])

        assert summary["rows_scanned"] == 1
        update_fatture = [u for u in client.updates if u["table"] == "fatture"]
        assert update_fatture and update_fatture[0]["ids"] == [1]

    def test_non_tocca_le_righe_soft_deleted(self):
        """Regola di dominio #5: le righe nel cestino non vanno ricategorizzate."""
        rows = [
            _eligible_row(row_id=1, deleted_at=None),
            _eligible_row(row_id=99, deleted_at="2026-08-01T00:00:00Z"),
        ]
        with patch("services.upload_handler.descrizione_e_dubbia", return_value=False):
            summary, client = _run_with_ai(rows, ["PASTA RISO E CEREALI"], ["alta"])

        assert summary["rows_scanned"] == 1
        update_fatture = [u for u in client.updates if u["table"] == "fatture"]
        assert update_fatture and update_fatture[0]["ids"] == [1]

    def test_nessuna_riga_da_risolvere_completa_senza_chiamare_lai(self):
        rows = [_eligible_row(row_id=1, categoria="CARNE E SALUMI", needs_review=False)]
        client = FakeTableRouter({"fatture": rows})
        with patch("services.upload_handler.classifica_via_worker_con_confidenza") as ai:
            summary = _run_post_upload_ai_categorization(client, "u1", ["f.xml"])

        ai.assert_not_called()
        assert summary["completed"] is True
        assert summary["rows_scanned"] == 0
