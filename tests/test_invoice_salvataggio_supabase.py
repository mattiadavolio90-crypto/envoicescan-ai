"""`salva_fattura_processata` — scrittura su Supabase sotto guardia (audit §3, 10/8/2026).

E' il punto da cui sono passate tutte le 34.000 righe attive del sistema: upsert
idempotente a chunk, cleanup delle righe orfane, guardia anti-doppione,
invalidazione cache. Un errore qui non produce un'eccezione, produce dati
sbagliati che sembrano giusti.

Il fake Supabase di questo file **applica davvero i filtri** (eq / neq / in_ /
not_.in_ / is_("deleted_at","null")), non li registra soltanto. E' la lezione
gia' pagata su upload_handler: un fake che memorizza `.eq('user_id')` senza
filtrare lascia passare verde una perdita di isolamento multi-tenant in lettura.
Per lo stesso motivo lo store di prova contiene sempre **un secondo utente, una
seconda sede e una riga cestinata**: senza righe da escludere, un filtro non ha
nulla da dimostrare e il test resta vacuo comunque.

Patch point: `get_supabase_client`, `filter_active`, `upsert_fattura_documento`,
`invalidate_today_briefing` sono import LOCALI dentro la funzione
(`:1787, :1948, :1980, :2100`). Vanno patchati sul modulo sorgente
(`services.db_service.filter_active`, ...), mai su `services.invoice_service.*`,
o il patch non ha effetto e il test passa senza esercitare nulla.

Mutazioni verificate rosse: M5-M14, M22, M23 del piano.
"""
import pytest
from unittest.mock import MagicMock, patch


# ─── Fake Supabase che filtra davvero ─────────────────────────────────────────

class _Not:
    """Emula `query.not_.in_(col, values)` di PostgREST: nega il filtro."""

    def __init__(self, query):
        self._q = query

    def in_(self, col, values):
        vals = list(values)
        self._q._rows = [r for r in self._q._rows if r.get(col) not in vals]
        self._q._rec["filters"].append(("not.in", col, vals))
        return self._q

    def is_(self, col, val):
        if val == "null":
            self._q._rows = [r for r in self._q._rows if r.get(col) is not None]
        return self._q


class _FakeQuery:
    def __init__(self, table, client):
        self._table = table
        self._client = client
        self._rows = list(client.store.get(table, []))
        self._rec = client.rec
        self._mode = "select"
        self._payload = None
        self._on_conflict = None
        self._limit = None

    # -- costruzione --
    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        self._rec["filters"].append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) != val]
        self._rec["filters"].append(("neq", col, val))
        return self

    def is_(self, col, val):
        if val == "null":
            self._rows = [r for r in self._rows if r.get(col) is None]
        self._rec["filters"].append(("is", col, val))
        return self

    def in_(self, col, values):
        vals = list(values)
        self._rows = [r for r in self._rows if r.get(col) in vals]
        self._rec["filters"].append(("in", col, vals))
        return self

    @property
    def not_(self):
        return _Not(self)

    def limit(self, n):
        self._limit = n
        return self

    def upsert(self, payload, on_conflict=None):
        self._mode = "upsert"
        self._payload = payload if isinstance(payload, list) else [payload]
        self._on_conflict = on_conflict
        return self

    def delete(self):
        self._mode = "delete"
        return self

    # -- esecuzione --
    def execute(self):
        store = self._client.store.setdefault(self._table, [])

        if self._mode == "upsert":
            if self._client.upsert_fails_from_chunk is not None:
                self._rec["chunk_calls"] += 1
                if self._rec["chunk_calls"] >= self._client.upsert_fails_from_chunk:
                    raise RuntimeError("upsert fallito (simulato)")
            else:
                self._rec["chunk_calls"] += 1
            self._rec["chunk_sizes"].append(len(self._payload))
            self._rec["on_conflict"].append(self._on_conflict)
            keys = (self._on_conflict or "").split(",") if self._on_conflict else []
            written = []
            for rec in self._payload:
                existing = None
                if keys:
                    for r in store:
                        if all(r.get(k) == rec.get(k) for k in keys):
                            existing = r
                            break
                if existing is not None:
                    existing.update(rec)
                    written.append(dict(existing))
                else:
                    store.append(dict(rec))
                    written.append(dict(rec))
            self._rec["upserted"].extend(written)
            return type("R", (), {"data": written})()

        if self._mode == "delete":
            if self._client.delete_raises:
                raise RuntimeError("delete fallito (simulato)")
            to_remove = {id(r) for r in self._rows}
            removed = [r for r in store if id(r) in to_remove]
            self._client.store[self._table] = [r for r in store if id(r) not in to_remove]
            self._rec["deleted"].extend(removed)
            return type("R", (), {"data": removed})()

        rows = self._rows[: self._limit] if self._limit else self._rows
        return type("R", (), {"data": list(rows)})()


class _FakeClient:
    def __init__(self, fatture=None, documenti=None,
                 upsert_fails_from_chunk=None, delete_raises=False):
        self.store = {
            "fatture": list(fatture or []),
            "fatture_documenti": list(documenti or []),
        }
        self.upsert_fails_from_chunk = upsert_fails_from_chunk
        self.delete_raises = delete_raises
        self.rec = {
            "filters": [], "upserted": [], "deleted": [],
            "chunk_sizes": [], "on_conflict": [], "chunk_calls": 0,
        }

    def table(self, name):
        return _FakeQuery(name, self)


USER = "user-1"
RIST = "rist-1"
FILE = "fattura_test.xml"


def _riga(numero_riga, descrizione="MOZZARELLA", user_id=USER, ristorante_id=RIST,
          file_origine=FILE, deleted_at=None):
    return {
        "user_id": user_id, "ristorante_id": ristorante_id,
        "file_origine": file_origine, "numero_riga": numero_riga,
        "descrizione": descrizione, "categoria": "🧀 LATTICINI E FORMAGGI",
        "deleted_at": deleted_at,
    }


def _store_con_vicini():
    """Store popolato in modo che ogni filtro abbia qualcosa da escludere.

    Senza questi 'vicini' (altro utente, altra sede, riga cestinata) i test sui
    filtri sarebbero vacui: nessuna riga da tenere fuori, nessuna prova.
    """
    return [
        _riga(1), _riga(2),
        _riga(9, descrizione="ORFANA DA RIMUOVERE"),
        # numero_riga 3 esiste solo cestinata: l'indice UNIQUE del DB
        # (user_id, ristorante_id, file_origine, numero_riga) e' PIENO, quindi
        # una riga attiva e una cestinata con la stessa quaterna non possono
        # coesistere. Il re-upload deve riattivare QUESTA.
        _riga(3, descrizione="CESTINATA", deleted_at="2026-07-01T00:00:00Z"),
        _riga(1, descrizione="ALTRO UTENTE", user_id="user-2"),
        _riga(1, descrizione="ALTRA SEDE", ristorante_id="rist-2"),
        # I vicini qui sotto hanno numero_riga FUORI da quelli caricati (1,2,3):
        # senza di loro il `.not_.in_` li escluderebbe comunque e i filtri
        # `filter_active` / `.eq(ristorante_id)` / `.eq(user_id)` non avrebbero
        # nulla da dimostrare — le mutazioni M7 e M9 restavano verdi (misurato).
        # Sono l'unico motivo per cui quel delete e' davvero sotto guardia.
        _riga(8, descrizione="CESTINATA FUORI RANGE", deleted_at="2026-07-01T00:00:00Z"),
        _riga(8, descrizione="ALTRO UTENTE FUORI RANGE", user_id="user-2"),
        _riga(8, descrizione="ALTRA SEDE FUORI RANGE", ristorante_id="rist-2"),
    ]


def _dati(n_righe=3, **override):
    base = []
    for i in range(1, n_righe + 1):
        riga = {
            "Numero_Riga": i, "Descrizione": f"PRODOTTO {i}",
            "Categoria": "🧀 LATTICINI E FORMAGGI", "Quantita": 1.0,
            "Prezzo_Unitario": 10.0, "Totale_Riga": 10.0,
            "Fornitore": "FORNITORE TEST SRL", "piva_cedente": "01234567890",
            "numero_documento": "F-100", "Data_Documento": "2026-03-31",
            "tipo_documento": "TD01", "needs_review": False,
        }
        riga.update(override)
        base.append(riga)
    return base


@pytest.fixture
def salva(monkeypatch):
    """Chiama salva_fattura_processata con gli esterni patchati sui moduli sorgente."""
    from services.invoice_service import salva_fattura_processata

    def _call(client, dati=None, nome_file=FILE, user_id=USER, ristorante_id=RIST,
              integrita=None, **kwargs):
        dati = _dati() if dati is None else dati
        # Forma reale del contratto di verifica_integrita_fattura
        # (utils/validation.py:412-421): il codice legge verifica["integrita_ok"].
        verifica = integrita or {
            "file": nome_file, "righe_parsed": len(dati), "righe_db": len(dati),
            "perdite": 0, "integrita_ok": True,
        }

        with patch("services.db_service.filter_active", side_effect=lambda q: q.is_("deleted_at", "null")), \
             patch("services.invoice_service.verifica_integrita_fattura", return_value=verifica), \
             patch("services.invoice_service.log_upload_event"), \
             patch("services.documenti_service.upsert_fattura_documento") as m_doc, \
             patch("services.ai_service.enforce_no_unclassified_category",
                   side_effect=lambda cat, desc, source=None: (cat, False)), \
             patch("services.invoice_service.st", MagicMock()):
            res = salva_fattura_processata(
                nome_file, dati, client, silent=True,
                ristoranteid=ristorante_id, user_id=user_id, **kwargs
            )
        return res, m_doc

    return _call


class TestCapRighe:
    """M5/M6 — il cap 2000 deve TRONCARE, non solo esistere come costante.

    Il test preesistente (test_audit_bug_remediation.py:476) asserisce
    `_MAX_RIGHE_PER_FATTURA == 2000`: resta verde anche se lo slice sparisce.
    """

    def test_oltre_il_cap_le_righe_sono_troncate(self, salva):
        client = _FakeClient()
        res, _ = salva(client, dati=_dati(2500))
        assert res["success"] is True
        assert len(client.rec["upserted"]) == 2000, "oltre il cap le righe vanno troncate"

    def test_esattamente_al_cap_nessun_troncamento(self, salva):
        """Confine: 2000 righe esatte devono passare intere.

        Nota di metodo: la mutazione `>` -> `>=` su :1818 resta VERDE, e non e'
        una debolezza del test. Con esattamente 2000 righe lo slice
        `dati_prodotti[:2000]` non rimuove nulla, quindi i due operatori
        producono lo stesso identico risultato: cambia solo un warning nel log.
        La mutazione e' **inosservabile per costruzione**, come il ramo
        `base <= 0` documentato nella sessione MOL del 10/8. Il comportamento
        osservabile del cap e' difeso dal test qui sopra (M5, rossa).
        """
        client = _FakeClient()
        salva(client, dati=_dati(2000))
        assert len(client.rec["upserted"]) == 2000

    def test_sotto_il_cap_passa_tutto(self, salva):
        client = _FakeClient()
        salva(client, dati=_dati(50))
        assert len(client.rec["upserted"]) == 50


class TestChunkingEIdempotenza:

    def test_chunk_da_500(self, salva):
        client = _FakeClient()
        salva(client, dati=_dati(1200))
        assert client.rec["chunk_sizes"] == [500, 500, 200]

    def test_on_conflict_e_la_quaterna_esatta(self, salva):
        """M13 — se la chiave di conflitto perde ristorante_id, due sedi dello
        stesso utente si sovrascrivono a vicenda."""
        client = _FakeClient()
        salva(client, dati=_dati(3))
        assert client.rec["on_conflict"] == ["user_id,ristorante_id,file_origine,numero_riga"] * 1

    def test_riga_cestinata_riattivata_dall_upsert(self, salva):
        """M14 — `deleted_at: None` nel record: un re-upload deve far tornare
        visibile una riga che era finita nel cestino, non crearne una doppia.

        La riga 3 nello store esiste SOLO cestinata (l'indice UNIQUE sulla
        quaterna impedisce che ne esista anche una attiva): dopo il salvataggio
        deve risultare attiva, e resta una sola.
        """
        client = _FakeClient(fatture=_store_con_vicini())
        salva(client, dati=_dati(3))
        riga3 = [
            r for r in client.store["fatture"]
            if r["user_id"] == USER and r["ristorante_id"] == RIST
            and r["file_origine"] == FILE and r["numero_riga"] == 3
        ]
        assert len(riga3) == 1, "l'upsert non deve duplicare la riga cestinata"
        assert riga3[0]["deleted_at"] is None, "la riga cestinata va riattivata"


class TestCleanupRigheOrfane:
    """Re-upload con MENO righe: le orfane attive vanno rimosse, il cestino no."""

    def test_rimuove_solo_le_orfane_del_file_corrente(self, salva):
        client = _FakeClient(fatture=_store_con_vicini())
        salva(client, dati=_dati(3))
        descr_rimosse = {r["descrizione"] for r in client.rec["deleted"]}
        assert "ORFANA DA RIMUOVERE" in descr_rimosse

    def test_non_cancella_la_riga_cestinata(self, salva):
        """M7 — senza filter_active l'hard-delete mirato colpirebbe anche il
        cestino (1.622 righe soft-deleted sul DB live): regola di dominio #5.

        La riga che rende osservabile la mutazione e' quella con numero_riga
        fuori dai correnti: le altre sarebbero escluse gia' dal `.not_.in_`.
        """
        client = _FakeClient(fatture=_store_con_vicini())
        salva(client, dati=_dati(3))
        descr = {r["descrizione"] for r in client.rec["deleted"]}
        assert "CESTINATA" not in descr
        assert "CESTINATA FUORI RANGE" not in descr
        # NB: la riga "CESTINATA" (numero_riga 3) viene RIATTIVATA dall'upsert,
        # quindi a fine salvataggio non e' piu' nel cestino: e' il comportamento
        # difeso da test_riga_cestinata_riattivata_dall_upsert. Quella che deve
        # restare cestinata e' la fuori-range, che l'upsert non tocca.
        superstiti = {
            r["descrizione"] for r in client.store["fatture"] if r["deleted_at"] is not None
        }
        assert "CESTINATA FUORI RANGE" in superstiti

    def test_non_tocca_le_righe_di_un_altro_utente_o_sede(self, salva):
        """M9 — perdita multi-tenant in scrittura: il delete deve essere
        ancorato a user_id E ristorante_id."""
        client = _FakeClient(fatture=_store_con_vicini())
        salva(client, dati=_dati(3))
        descr = {r["descrizione"] for r in client.rec["deleted"]}
        assert "ALTRO UTENTE" not in descr
        assert "ALTRA SEDE" not in descr
        assert "ALTRO UTENTE FUORI RANGE" not in descr
        assert "ALTRA SEDE FUORI RANGE" not in descr
        rimasti = {r["descrizione"] for r in client.store["fatture"]}
        assert {"ALTRO UTENTE FUORI RANGE", "ALTRA SEDE FUORI RANGE"} <= rimasti

    def test_non_cancella_le_righe_correnti(self, salva):
        """M8 — `.not_.in_` negato in `.in_` cancellerebbe esattamente le righe
        appena scritte, lasciando la fattura vuota."""
        client = _FakeClient(fatture=_store_con_vicini())
        salva(client, dati=_dati(3))
        rimaste = [
            r for r in client.store["fatture"]
            if r["user_id"] == USER and r["ristorante_id"] == RIST
            and r["file_origine"] == FILE and r["deleted_at"] is None
        ]
        assert {r["numero_riga"] for r in rimaste} == {1, 2, 3}

    def test_cleanup_fallito_non_blocca_il_salvataggio(self, salva):
        client = _FakeClient(fatture=_store_con_vicini(), delete_raises=True)
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True, "il cleanup e' best-effort, non deve far fallire l'upload"


class TestGuardiaDuplicati:
    """Identita' naturale: P.IVA + numero + data + tipo, con file_origine diverso."""

    def _documento(self, file_origine="altro_nome.xml", ristorante_id=RIST,
                   piva="01234567890", numero="F-100", data="2026-03-31",
                   user_id=USER, deleted_at=None):
        return {
            "user_id": user_id, "ristorante_id": ristorante_id,
            "file_origine": file_origine, "piva_fornitore": piva,
            "numero_documento": numero, "data_documento": data,
            "tipo_documento": "TD01", "fornitore": "FORNITORE TEST SRL",
            "created_at": "2026-03-31T10:00:00Z", "deleted_at": deleted_at,
        }

    def _vicini(self):
        """Documenti che NON devono mai far scattare la guardia.

        Stessa lezione dei vicini di `fatture`, applicata a `fatture_documenti`:
        senza documenti da escludere, i filtri `eq(user_id)`, `filter_active` e
        la guardia sull'identita' incompleta non hanno nulla da dimostrare e
        restano verdi anche se rimossi (misurato dal code-reviewer, 10/8/2026).

        Ognuno corrisponde a un caso reale contato sul DB live:
        - 334 documenti cestinati (265 a identita' completa)
        - 4 identita' naturali condivise fra utenti diversi
        - 402 documenti su 3.094 (13%) a identita' incompleta
        """
        return [
            self._documento(file_origine="cestinato.xml",
                            deleted_at="2026-07-01T00:00:00Z"),
            self._documento(file_origine="altro_utente.xml", user_id="user-2"),
            self._documento(file_origine="senza_identita.xml", piva="", numero=""),
        ]

    def test_stesso_documento_altro_nome_file_e_bloccato(self, salva):
        client = _FakeClient(documenti=[self._documento()])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is False
        assert res["error"] == "duplicate_document"
        assert res["duplicate_of"] == "altro_nome.xml"
        assert client.rec["upserted"] == [], "un duplicato non deve scrivere righe"

    def test_stesso_file_non_e_un_duplicato(self, salva):
        """M10 — senza `.neq(file_origine)` la guardia bloccherebbe il normale
        re-upload dello stesso file, che invece deve essere idempotente."""
        client = _FakeClient(documenti=[self._documento(file_origine=FILE)])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    def test_documento_di_un_altra_sede_non_blocca(self, salva):
        """M11 — senza `.eq(ristorante_id)` una sede impedirebbe a un'altra di
        caricare la propria copia dello stesso documento."""
        client = _FakeClient(documenti=[self._documento(ristorante_id="rist-2")])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    @pytest.mark.parametrize("campo,valore", [
        ("piva_cedente", ""), ("numero_documento", ""), ("Data_Documento", None),
    ])
    def test_identita_incompleta_non_blocca_mai(self, salva, campo, valore):
        """M12 — ramo VIVO: 402 documenti su 3.094 (13%) sul DB live hanno
        identita' incompleta. Per scelta non blocca: mai far fallire un
        caricamento legittimo per un dato che il fornitore non ha messo.
        """
        # Il vicino dev'essere il GEMELLO del documento in ingresso, con vuoto
        # solo il campo mancante: cosi' senza l'early-return la query
        # `.eq(<campo>, "")` lo troverebbe e bloccherebbe il caricamento.
        # Un vicino con piu' campi vuoti non matcherebbe sugli altri `.eq()` e
        # lascerebbe la mutazione verde (misurato: prima versione cosi').
        gemello = {
            "piva_cedente": dict(piva=""),
            "numero_documento": dict(numero=""),
            "Data_Documento": dict(data=None),
        }[campo]
        client = _FakeClient(documenti=[
            self._documento(file_origine="gemello_incompleto.xml", **gemello),
        ])
        res, _ = salva(client, dati=_dati(3, **{campo: valore}))
        assert res["success"] is True

    def test_altro_numero_stesso_fornitore_e_giorno_non_blocca(self, salva):
        """`eq(numero_documento)` — due fatture dello stesso fornitore nello
        stesso giorno sono normali (consegne multiple): a distinguerle e' solo
        il numero. Senza quel filtro la seconda verrebbe rifiutata come
        duplicato della prima."""
        client = _FakeClient(documenti=[
            self._documento(file_origine="stesso_giorno.xml", numero="F-999")])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    def test_altro_fornitore_stesso_numero_e_data_non_blocca(self, salva):
        """`eq(piva_fornitore)` — fornitori diversi numerano le fatture in modo
        indipendente: "F-100 del 31/03" esiste per molti di loro. Senza il
        filtro sulla P.IVA il documento di un fornitore bloccherebbe quello di
        un altro. Sul DB live ci sono 239 fornitori distinti."""
        client = _FakeClient(documenti=[
            self._documento(file_origine="altro_fornitore.xml", piva="09876543210")])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    def test_altra_data_stesso_numero_non_blocca(self, salva):
        """`eq(data_documento)` — stesso numero su anni/date diverse."""
        client = _FakeClient(documenti=[
            self._documento(file_origine="altra_data.xml", data="2025-03-31")])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    def test_documento_cestinato_non_blocca(self, salva):
        """MZ-b (regola di dominio #5) — `filter_active` sulla guardia: un
        documento nel cestino non deve impedire di ricaricarne uno nuovo con la
        stessa identita'. Sul DB live: 334 documenti cestinati, e 1 caso reale
        di ri-upload con file_origine diverso dopo cestinamento.
        """
        client = _FakeClient(documenti=[
            self._documento(file_origine="cestinato.xml",
                            deleted_at="2026-07-01T00:00:00Z")])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    def test_documento_di_un_altro_utente_non_blocca(self, salva):
        """MZ-c — `eq(user_id)`: senza, il documento di un cliente farebbe
        rifiutare il caricamento a un altro cliente. Sul DB live esistono 4
        identita' naturali condivise fra utenti diversi: perdita di isolamento
        multi-tenant in lettura."""
        client = _FakeClient(documenti=[
            self._documento(file_origine="altro_utente.xml", user_id="user-2")])
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True

    def test_vicini_non_bloccano_e_il_duplicato_vero_si(self, salva):
        """Tutti i vicini insieme + il duplicato vero: la guardia deve
        distinguere, non solo bloccare."""
        client = _FakeClient(documenti=self._vicini())
        res, _ = salva(client, dati=_dati(3))
        assert res["success"] is True, "nessun vicino deve bloccare"

        client2 = _FakeClient(documenti=self._vicini() + [self._documento()])
        res2, _ = salva(client2, dati=_dati(3))
        assert res2["error"] == "duplicate_document"
        assert res2["duplicate_of"] == "altro_nome.xml"

    def test_guardia_in_errore_lascia_passare(self, salva):
        """Fail-open documentato, NON un difetto da fixare: sul DB live (10/8/2026)
        ci sono 0 identita' naturali con piu' di un file_origine attivo. Renderlo
        fail-closed farebbe fallire caricamenti legittimi a ogni hiccup di
        Supabase. Il test fissa il comportamento attuale perche' sia una scelta
        visibile e non una svista.

        Il guasto va iniettato nella QUERY, che e' cio' che il `try` di
        `_trova_documento_duplicato_per_identita` (:1733) copre davvero, e che e'
        anche l'unico guasto realistico (rete/PostgREST). Primo tentativo
        scartato: forzare un'eccezione da `_to_date_iso`, che sta a :1728 FUORI
        dal try — ma quella funzione ha gia' il proprio except interno e
        restituisce None su qualunque input, quindi era un guasto che il codice
        reale non puo' produrre.
        """
        client = _FakeClient(documenti=[self._documento()])
        with patch.object(_FakeQuery, "execute", side_effect=RuntimeError("PostgREST down")):
            res, _ = salva(client, dati=_dati(3))
        # La query di guardia fallisce -> non blocca; il salvataggio prosegue e
        # fallisce piu' avanti sull'upsert (stessa iniezione), ma NON con
        # duplicate_document: la guardia ha lasciato passare.
        assert res.get("error") != "duplicate_document"


class TestValidazioniEffettiCollaterali:

    def test_senza_ristorante_id_non_scrive(self, salva):
        client = _FakeClient()
        res, _ = salva(client, ristorante_id=None)
        assert res["success"] is False and res["error"] == "missing_ristorante_id"
        assert client.rec["upserted"] == []

    def test_senza_righe_non_scrive(self, salva):
        client = _FakeClient()
        res, _ = salva(client, dati=[])
        assert res["success"] is False and res["error"] == "no_data"

    def test_nome_file_sanitizzato_contro_path_traversal(self, salva):
        """M22 — `file_origine` finisce nel DB e viene riusato nelle query:
        deve restare un nome, non un percorso."""
        client = _FakeClient()
        salva(client, dati=_dati(1), nome_file="../../etc/passwd")
        scritte = {r["file_origine"] for r in client.rec["upserted"]}
        assert scritte == {"etcpasswd"}

    def test_header_documento_upsertato(self, salva):
        client = _FakeClient()
        _, m_doc = salva(client, dati=_dati(3))
        assert m_doc.called
        payload = m_doc.call_args.kwargs["payload"]
        assert payload["numero_documento"] == "F-100"
        assert payload["piva_fornitore"] == "01234567890"

    def test_invalida_briefing_e_kpi_home(self):
        """M23 — dopo un upload la Home deve rigenerare: senza invalidazione il
        cliente vede i conti pre-upload fino allo scadere del TTL.

        L'assert e' sulla CHIAMATA, non su "non solleva": il blocco e'
        best-effort dentro un try/except, quindi un test che si limitasse a
        verificare l'assenza di eccezioni sarebbe inosservabile alla mutazione.
        """
        from services.invoice_service import salva_fattura_processata
        client = _FakeClient()
        with patch("services.db_service.filter_active", side_effect=lambda q: q.is_("deleted_at", "null")), \
             patch("services.invoice_service.verifica_integrita_fattura",
                   return_value={"file": FILE, "righe_parsed": 3, "righe_db": 3,
                                 "perdite": 0, "integrita_ok": True}), \
             patch("services.invoice_service.log_upload_event"), \
             patch("services.documenti_service.upsert_fattura_documento"), \
             patch("services.ai_service.enforce_no_unclassified_category",
                   side_effect=lambda cat, desc, source=None: (cat, False)), \
             patch("services.daily_briefing_service.invalidate_today_briefing") as m_brief, \
             patch("services.fastapi_worker._invalidate_home_kpi_cache") as m_kpi, \
             patch("services.invoice_service.st", MagicMock()):
            res = salva_fattura_processata(
                FILE, _dati(3), client, silent=True, ristoranteid=RIST, user_id=USER
            )
        assert res["success"] is True
        assert m_brief.called, "il briefing di oggi va invalidato dopo l'upload"
        assert m_brief.call_args.args[:2] == (USER, RIST)
        assert m_kpi.called, "la cache KPI Home va invalidata dopo l'upload"
        assert m_kpi.call_args.args[0] == RIST

    def test_invalidazione_cache_fallita_non_blocca(self):
        """L'invalidazione e' best-effort: un suo errore non deve trasformare
        un salvataggio riuscito in un fallimento."""
        from services.invoice_service import salva_fattura_processata
        client = _FakeClient()
        with patch("services.db_service.filter_active", side_effect=lambda q: q.is_("deleted_at", "null")), \
             patch("services.invoice_service.verifica_integrita_fattura",
                   return_value={"file": FILE, "righe_parsed": 3, "righe_db": 3,
                                 "perdite": 0, "integrita_ok": True}), \
             patch("services.invoice_service.log_upload_event"), \
             patch("services.documenti_service.upsert_fattura_documento"), \
             patch("services.ai_service.enforce_no_unclassified_category",
                   side_effect=lambda cat, desc, source=None: (cat, False)), \
             patch("services.daily_briefing_service.invalidate_today_briefing",
                   side_effect=RuntimeError("cache down")), \
             patch("services.invoice_service.st", MagicMock()):
            res = salva_fattura_processata(
                FILE, _dati(3), client, silent=True, ristoranteid=RIST, user_id=USER
            )
        assert res["success"] is True

    def test_header_documento_fallito_non_blocca(self, salva):
        from services.invoice_service import salva_fattura_processata
        client = _FakeClient()
        with patch("services.db_service.filter_active", side_effect=lambda q: q.is_("deleted_at", "null")), \
             patch("services.invoice_service.verifica_integrita_fattura",
                   return_value={"file": FILE, "righe_parsed": 3, "righe_db": 3,
                                 "perdite": 0, "integrita_ok": True}), \
             patch("services.invoice_service.log_upload_event"), \
             patch("services.documenti_service.upsert_fattura_documento",
                   side_effect=RuntimeError("boom")), \
             patch("services.ai_service.enforce_no_unclassified_category",
                   side_effect=lambda cat, desc, source=None: (cat, False)), \
             patch("services.invoice_service.st", MagicMock()):
            res = salva_fattura_processata(
                FILE, _dati(3), client, silent=True, ristoranteid=RIST, user_id=USER
            )
        assert res["success"] is True
