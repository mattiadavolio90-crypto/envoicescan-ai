"""
Test per la feature Spese Extra (F&B / Generali).

Copre la logica di aggregazione lato worker:
- get_costo_spese_da_voci: somma le voci del mese separate per tipo (alimenta margini_mensili)
- ws_spese_list: totali per tipo nel periodo
- ws_spese_crea: validazione tipo/descrizione/importo

Le dipendenze su Supabase e auth sono mockate, come per gli altri test del modulo.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.fastapi_worker as worker
import services.routers.margini as margini
import services.routers.workspace as workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query_mock(execute_data=None):
    """Mock chain del client Supabase Python (select/eq/gte/lte/order/execute)."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.gte.return_value = q
    q.lte.return_value = q
    q.order.return_value = q
    q.limit.return_value = q
    q.insert.return_value = q
    q.update.return_value = q
    q.execute.return_value = SimpleNamespace(data=execute_data or [])
    return q


def _patch_common(voci):
    """Patcha auth + supabase + risoluzione ristorante sul router workspace
    (dove ora vivono ws_spese_*); il client restituisce `voci`."""
    client = MagicMock()
    client.table.return_value = _query_mock(voci)
    return patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    )


def _patch_margini(voci):
    """Come _patch_common ma sul modulo router margini (dove vive get_costo_spese_da_voci)."""
    client = MagicMock()
    client.table.return_value = _query_mock(voci)
    return patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    )


# ---------------------------------------------------------------------------
# get_costo_spese_da_voci — aggregatore per margini
# ---------------------------------------------------------------------------

class TestCostoSpeseDaVoci:

    def test_aggrega_per_tipo(self):
        voci = [
            {"tipo": "fb", "importo": 100.0},
            {"tipo": "fb", "importo": 50.5},
            {"tipo": "generale", "importo": 30.0},
        ]
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 150.5
        assert res["totale_generale"] == 30.0
        assert res["n_voci_fb"] == 2
        assert res["n_voci_generale"] == 1

    def test_nessuna_voce(self):
        with _patch_margini([]):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 0.0
        assert res["totale_generale"] == 0.0
        assert res["n_voci_fb"] == 0
        assert res["n_voci_generale"] == 0

    def test_importo_none_non_rompe(self):
        voci = [
            {"tipo": "fb", "importo": None},
            {"tipo": "generale", "importo": 20.0},
        ]
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 0.0
        assert res["totale_generale"] == 20.0

    def test_tipo_sconosciuto_ignorato(self):
        voci = [
            {"tipo": "fb", "importo": 10.0},
            {"tipo": "altro", "importo": 999.0},  # non deve confluire da nessuna parte
        ]
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 10.0
        assert res["totale_generale"] == 0.0


# ---------------------------------------------------------------------------
# ws_spese_list — totali per periodo
# ---------------------------------------------------------------------------

class TestSpeseList:

    def test_totali_per_tipo(self):
        voci = [
            {"id": "1", "tipo": "fb", "importo": 40.0},
            {"id": "2", "tipo": "generale", "importo": 60.0},
            {"id": "3", "tipo": "generale", "importo": 15.0},
        ]
        with _patch_common(voci):
            res = workspace.ws_spese_list(da="2026-06-01", a="2026-06-30", authorization="Bearer x")
        assert res["totale_fb"] == 40.0
        assert res["totale_generale"] == 75.0
        assert res["totale"] == 115.0
        assert len(res["voci"]) == 3


# ---------------------------------------------------------------------------
# ws_spese_crea — validazione
# ---------------------------------------------------------------------------

class TestSpeseCrea:

    def test_tipo_non_valido(self):
        body = workspace.NuovaSpesaBody(data_spesa="2026-06-10", tipo="xxx", importo=10.0, descrizione="Test")
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_descrizione_vuota(self):
        body = workspace.NuovaSpesaBody(data_spesa="2026-06-10", tipo="fb", importo=10.0, descrizione="   ")
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_importo_negativo(self):
        body = workspace.NuovaSpesaBody(data_spesa="2026-06-10", tipo="fb", importo=-5.0, descrizione="Test")
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_creazione_valida(self):
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="fb", importo=12.345, descrizione="  Pesce  ", note=None
        )
        client = MagicMock()
        inserted = {"id": "new", "tipo": "fb", "importo": 12.35, "descrizione": "Pesce"}
        q = _query_mock([inserted])
        client.table.return_value = q
        with patch.multiple(
            workspace,
            _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
            _get_supabase_client=MagicMock(return_value=client),
            _resolve_ristorante_id=MagicMock(return_value="rist-1"),
        ):
            res = workspace.ws_spese_crea(body=body, authorization="Bearer x")
        # Verifica che l'importo sia stato arrotondato a 2 decimali e descrizione strippata nel payload
        args, kwargs = q.insert.call_args
        payload = args[0]
        assert payload["importo"] == 12.35
        assert payload["descrizione"] == "Pesce"
        assert payload["tipo"] == "fb"
        assert res == inserted


# ---------------------------------------------------------------------------
# Categoria -> tipo: la derivazione e' il punto in cui un errore muove il MOL
# ---------------------------------------------------------------------------

def _crea_e_leggi_payload(body):
    """Esegue ws_spese_crea e restituisce il payload passato a insert()."""
    client = MagicMock()
    q = _query_mock([{"id": "new"}])
    client.table.return_value = q
    with patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ):
        workspace.ws_spese_crea(body=body, authorization="Bearer x")
    return q.insert.call_args[0][0]


def _patch_e_leggi_updates(body, categoria_corrente):
    """Esegue ws_spese_aggiorna su una riga con `categoria_corrente` gia' salvata
    e restituisce il dict passato a update()."""
    client = MagicMock()
    q = _query_mock([{"categoria": categoria_corrente}])
    client.table.return_value = q
    with patch.multiple(
        workspace,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ):
        workspace.ws_spese_aggiorna(spesa_id="sp-1", body=body, authorization="Bearer x")
    return q.update.call_args[0][0]


class TestTipoDaCategoria:
    """La categoria decide il binario contabile. Se questa derivazione sbaglia,
    il totale finisce nella cella sbagliata di margini_mensili e il MOL si muove."""

    @pytest.mark.parametrize("categoria", ["PESCE", "CARNE", "VINI", "RIVENDITA", "GELATI E DESSERT"])
    def test_food_beverage_va_su_fb(self, categoria):
        assert workspace._tipo_da_categoria(categoria) == "fb"

    @pytest.mark.parametrize("categoria", [
        "SERVIZI E CONSULENZE",
        "UTENZE E LOCALI",
        "MANUTENZIONE E ATTREZZATURE",
        # Non e' ovvio: la stringa dice "MATERIALE" ma logicamente e' spesa generale.
        "MATERIALE DI CONSUMO",
        # Fase K (10/10/2026): un pranzo con un cliente non e' food cost.
        "RAPPRESENTANZA",
    ])
    def test_spese_generali_vanno_su_generale(self, categoria):
        assert workspace._tipo_da_categoria(categoria) == "generale"

    def test_le_29_canoniche_sono_tutte_valide(self):
        from config.constants import CATEGORIE_FOOD_BEVERAGE, CATEGORIE_SPESE_GENERALI
        assert len(workspace._CATEGORIE_SPESA_VALIDE) == 29
        for c in CATEGORIE_FOOD_BEVERAGE + CATEGORIE_SPESE_GENERALI:
            assert c in workspace._CATEGORIE_SPESA_VALIDE

    def test_note_e_diciture_e_da_classificare_escluse(self):
        # NOTE E DICITURE e' riservata alle righe fattura a importo zero (CLAUDE.md §2);
        # "Da Classificare" non ha senso su una spesa scritta a mano dall'utente.
        assert "📝 NOTE E DICITURE" not in workspace._CATEGORIE_SPESA_VALIDE
        assert "Da Classificare" not in workspace._CATEGORIE_SPESA_VALIDE


class TestSpeseCreaConCategoria:

    def test_categoria_fuori_lista_400(self):
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="fb", importo=10.0,
            descrizione="Test", categoria="CATEGORIA INVENTATA",
        )
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("categoria", ["📝 NOTE E DICITURE", "Da Classificare"])
    def test_categorie_speciali_rifiutate(self, categoria):
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="generale", importo=10.0,
            descrizione="Test", categoria=categoria,
        )
        with _patch_common([]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_categoria_sovrascrive_il_tipo_del_client(self):
        # Il client manda 'generale' ma la categoria e' F&B: vince la categoria.
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="generale", importo=10.0,
            descrizione="Pesce mercato", categoria="PESCE",
        )
        payload = _crea_e_leggi_payload(body)
        assert payload["categoria"] == "PESCE"
        assert payload["tipo"] == "fb"

    def test_categoria_generale_sovrascrive_tipo_fb(self):
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="fb", importo=10.0,
            descrizione="Bolletta", categoria="UTENZE E LOCALI",
        )
        payload = _crea_e_leggi_payload(body)
        assert payload["tipo"] == "generale"

    def test_senza_categoria_retrocompatibile(self):
        # Client vecchio: nessuna categoria, il tipo resta quello mandato e la
        # colonna non viene scritta (NULL = voce senza categoria, non inventata).
        body = workspace.NuovaSpesaBody(
            data_spesa="2026-06-10", tipo="fb", importo=10.0, descrizione="Storica",
        )
        payload = _crea_e_leggi_payload(body)
        assert payload["tipo"] == "fb"
        assert "categoria" not in payload


class TestSpeseAggiornaConCategoria:

    def test_cambio_categoria_ricalcola_il_tipo(self):
        # Il caso critico: da F&B a generale. Senza il ricalcolo la voce resta
        # sul binario 'fb' e sposta silenziosamente il MOL.
        body = workspace.AggiornaSpesaBody(categoria="UTENZE E LOCALI")
        updates = _patch_e_leggi_updates(body, categoria_corrente="PESCE")
        assert updates["categoria"] == "UTENZE E LOCALI"
        assert updates["tipo"] == "generale"

    def test_cambio_categoria_generale_a_fb(self):
        body = workspace.AggiornaSpesaBody(categoria="CARNE")
        updates = _patch_e_leggi_updates(body, categoria_corrente="UTENZE E LOCALI")
        assert updates["tipo"] == "fb"

    def test_tipo_a_mano_perde_contro_la_categoria_salvata(self):
        # PATCH del solo tipo su una voce gia' categorizzata: la categoria vince
        # sempre, non solo quando cambia. Nessuna riga puo' restare incoerente.
        body = workspace.AggiornaSpesaBody(tipo="generale")
        updates = _patch_e_leggi_updates(body, categoria_corrente="PESCE")
        assert updates["tipo"] == "fb"

    def test_tipo_a_mano_resta_sulle_voci_storiche(self):
        # Voce senza categoria: il tipo resta modificabile a mano (retrocompatibilita').
        body = workspace.AggiornaSpesaBody(tipo="generale")
        updates = _patch_e_leggi_updates(body, categoria_corrente=None)
        assert updates["tipo"] == "generale"

    def test_categoria_null_azzera_e_libera_il_tipo(self):
        body = workspace.AggiornaSpesaBody(categoria=None, tipo="generale")
        updates = _patch_e_leggi_updates(body, categoria_corrente="PESCE")
        assert updates["categoria"] is None
        assert updates["tipo"] == "generale"

    def test_categoria_fuori_lista_400(self):
        body = workspace.AggiornaSpesaBody(categoria="ROBA A CASO")
        with _patch_common([{"categoria": "PESCE"}]):
            with pytest.raises(worker.HTTPException) as exc:
                workspace.ws_spese_aggiorna(spesa_id="sp-1", body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_patch_di_altri_campi_non_tocca_il_tipo_senza_categoria(self):
        body = workspace.AggiornaSpesaBody(descrizione="Nuova descrizione")
        updates = _patch_e_leggi_updates(body, categoria_corrente=None)
        assert updates["descrizione"] == "Nuova descrizione"
        assert "tipo" not in updates

    def test_patch_di_altri_campi_riallinea_il_tipo_se_c_e_categoria(self):
        body = workspace.AggiornaSpesaBody(importo=99.0)
        updates = _patch_e_leggi_updates(body, categoria_corrente="MATERIALE DI CONSUMO")
        assert updates["importo"] == 99.0
        assert updates["tipo"] == "generale"


# ---------------------------------------------------------------------------
# Invarianza: i totali che alimentano il MOL non cambiano
# ---------------------------------------------------------------------------

class TestInvarianzaTotali:
    """La categoria e' un'etichetta di dettaglio: totale_fb/totale_generale e i
    conteggi devono restare identici a prima, con o senza categoria."""

    VOCI_SENZA_CATEGORIA = [
        {"tipo": "fb", "importo": 100.0},
        {"tipo": "fb", "importo": 50.5},
        {"tipo": "generale", "importo": 30.0},
    ]
    VOCI_CON_CATEGORIA = [
        {"tipo": "fb", "importo": 100.0, "categoria": "PESCE"},
        {"tipo": "fb", "importo": 50.5, "categoria": "CARNE"},
        {"tipo": "generale", "importo": 30.0, "categoria": "UTENZE E LOCALI"},
    ]
    VOCI_MISTE = [
        {"tipo": "fb", "importo": 100.0, "categoria": "PESCE"},
        {"tipo": "fb", "importo": 50.5, "categoria": None},
        {"tipo": "generale", "importo": 30.0, "categoria": "UTENZE E LOCALI"},
    ]

    @pytest.mark.parametrize("voci", [VOCI_SENZA_CATEGORIA, VOCI_CON_CATEGORIA, VOCI_MISTE])
    def test_totali_identici_comunque(self, voci):
        with _patch_margini(voci):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["totale_fb"] == 150.5
        assert res["totale_generale"] == 30.0
        assert res["n_voci_fb"] == 2
        assert res["n_voci_generale"] == 1

    def test_dettaglio_quadra_col_totale(self):
        with _patch_margini(self.VOCI_CON_CATEGORIA):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["dettaglio_fb"] == {"PESCE": 100.0, "CARNE": 50.5}
        assert res["dettaglio_generale"] == {"UTENZE E LOCALI": 30.0}
        assert round(sum(res["dettaglio_fb"].values()), 2) == res["totale_fb"]
        assert round(sum(res["dettaglio_generale"].values()), 2) == res["totale_generale"]

    def test_voci_senza_categoria_raggruppate_e_quadrano(self):
        with _patch_margini(self.VOCI_MISTE):
            res = margini.get_costo_spese_da_voci(anno=2026, mese=6, authorization="Bearer x")
        assert res["dettaglio_fb"] == {"PESCE": 100.0, "Senza categoria": 50.5}
        assert round(sum(res["dettaglio_fb"].values()), 2) == res["totale_fb"]

    def test_lista_totali_per_categoria_esclude_le_null(self):
        voci = [
            {"id": "1", "tipo": "fb", "importo": 40.0, "categoria": "PESCE"},
            {"id": "2", "tipo": "fb", "importo": 10.0, "categoria": "PESCE"},
            {"id": "3", "tipo": "generale", "importo": 60.0, "categoria": None},
        ]
        with _patch_common(voci):
            res = workspace.ws_spese_list(da="2026-06-01", a="2026-06-30", authorization="Bearer x")
        # I totali per binario non cambiano...
        assert res["totale_fb"] == 50.0
        assert res["totale_generale"] == 60.0
        # ...e il raggruppamento per categoria non inventa una riga per le NULL.
        assert res["totali_per_categoria"] == {"PESCE": 50.0}


# ---------------------------------------------------------------------------
# Categoria per settore (regola di dominio 7, 11/10/2026)
# ---------------------------------------------------------------------------

class TestCategoriaSpesaPerSettore:
    """Un negozio registra la merce come ARTICOLO DI VENDITA e non ha le famiglie
    dei ristoranti; un ristorante resta esattamente com'era (settore assente o
    'ristorazione'). Il settore lo decide la SEDE, letto una volta per richiesta."""

    def test_il_negozio_accetta_la_merce_e_rifiuta_le_famiglie_dei_ristoranti(self):
        assert workspace._valida_categoria_spesa("ARTICOLO DI VENDITA", "retail") == "ARTICOLO DI VENDITA"
        assert workspace._valida_categoria_spesa("UTENZE E LOCALI", "retail") == "UTENZE E LOCALI"
        with pytest.raises(worker.HTTPException) as exc:
            workspace._valida_categoria_spesa("CARNE", "retail")
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("settore", [None, "ristorazione"])
    def test_il_ristorante_resta_com_era(self, settore):
        assert workspace._valida_categoria_spesa("CARNE", settore) == "CARNE"
        with pytest.raises(worker.HTTPException):
            workspace._valida_categoria_spesa("ARTICOLO DI VENDITA", settore)
        assert workspace._categorie_spesa_valide(settore) == workspace._CATEGORIE_SPESA_VALIDE

    def test_la_merce_del_negozio_va_sul_binario_fb(self):
        assert workspace._tipo_da_categoria("ARTICOLO DI VENDITA") == "fb"

    def test_la_rotta_legge_il_settore_della_sede(self, monkeypatch):
        """Il settore viene da `settore_sede(ristorante_id)`, non dall'header o dal
        client: con la sede negozio la merce passa (tipo fb), con la sede
        ristorante la stessa richiesta e' un 400."""
        visto = []
        monkeypatch.setattr(workspace, "settore_sede", lambda rid, sb: visto.append(rid) or "retail")
        body = workspace.NuovaSpesaBody(data_spesa="2026-10-11", tipo="generale", importo=12.5,
                                        descrizione="Caramelle", categoria="ARTICOLO DI VENDITA")
        with _patch_common([{"id": "sp-1"}]):
            workspace.ws_spese_crea(body=body, authorization="Bearer x")
            client = workspace._get_supabase_client()
            payload = client.table.return_value.insert.call_args[0][0]
        assert visto == ["rist-1"]
        assert payload["categoria"] == "ARTICOLO DI VENDITA" and payload["tipo"] == "fb"

        monkeypatch.setattr(workspace, "settore_sede", lambda rid, sb: "ristorazione")
        with _patch_common([{"id": "sp-1"}]), pytest.raises(worker.HTTPException) as exc:
            workspace.ws_spese_crea(body=body, authorization="Bearer x")
        assert exc.value.status_code == 400

    def test_anche_la_modifica_legge_il_settore_della_sede(self, monkeypatch):
        monkeypatch.setattr(workspace, "settore_sede", lambda rid, sb: "retail")
        body = workspace.AggiornaSpesaBody(categoria="ARTICOLO DI VENDITA")
        with _patch_common([{"id": "sp-1", "categoria": None}]):
            workspace.ws_spese_aggiorna(spesa_id="sp-1", body=body, authorization="Bearer x")
            client = workspace._get_supabase_client()
            updates = client.table.return_value.update.call_args[0][0]
        assert updates == {"categoria": "ARTICOLO DI VENDITA", "tipo": "fb"}


# ---------------------------------------------------------------------------
# get_spese_extra_anno — i totali del tab Spese per mese (avviso in Margini)
# ---------------------------------------------------------------------------

class TestSpeseExtraAnno:
    """La tabella Margini dice dove la cella non coincide con l'Agenda
    (11/10/2026). I totali per mese e tipo devono essere gli stessi di
    get_costo_spese_da_voci, mese per mese, in una lettura sola."""

    VOCI = [
        {"data_spesa": "2026-01-15", "tipo": "fb", "importo": 100.0},
        {"data_spesa": "2026-01-20", "tipo": "fb", "importo": 7.0},
        {"data_spesa": "2026-01-31", "tipo": "generale", "importo": 300.0},
        {"data_spesa": "2026-06-10", "tipo": "generale", "importo": 20.5},
        {"data_spesa": "2026-06-11", "tipo": "sconosciuto", "importo": 999.0},
        {"data_spesa": "2026-06-12", "tipo": "fb", "importo": None},
    ]

    def test_totali_per_mese_e_tipo(self):
        with _patch_margini(self.VOCI):
            res = margini.get_spese_extra_anno(anno=2026, authorization="Bearer x")
        assert res["anno"] == 2026
        assert res["mesi"] == {
            "1": {"fb": 107.0, "generale": 300.0, "n_fb": 2, "n_generale": 1},
            "6": {"fb": 0.0, "generale": 20.5, "n_fb": 1, "n_generale": 1},
        }

    def test_i_mesi_senza_voci_non_compaiono(self):
        with _patch_margini([]):
            res = margini.get_spese_extra_anno(anno=2026, authorization="Bearer x")
        assert res["mesi"] == {}

    def test_legge_solo_l_anno_chiesto(self):
        """Senza i due estremi sulla data una spesa del 2025 finirebbe nel mese
        sbagliato dell'anno chiesto (si guarda solo il mese della data)."""
        with _patch_margini([]):
            margini.get_spese_extra_anno(anno=2025, authorization="Bearer x")
            q = margini._get_supabase_client().table.return_value
        assert q.gte.call_args[0] == ("data_spesa", "2025-01-01")
        assert q.lte.call_args[0] == ("data_spesa", "2025-12-31")

    def test_stessi_totali_del_recupero_mese_per_mese(self):
        """Il confronto in tabella e il «Recupera» devono dire la stessa cifra."""
        gennaio = [v for v in self.VOCI if v["data_spesa"].startswith("2026-01")]
        with _patch_margini(gennaio):
            singolo = margini.get_costo_spese_da_voci(anno=2026, mese=1, authorization="Bearer x")
        with _patch_margini(self.VOCI):
            anno = margini.get_spese_extra_anno(anno=2026, authorization="Bearer x")["mesi"]["1"]
        assert (anno["fb"], anno["generale"]) == (singolo["totale_fb"], singolo["totale_generale"])
        assert (anno["n_fb"], anno["n_generale"]) == (singolo["n_voci_fb"], singolo["n_voci_generale"])
