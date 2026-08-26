"""Test della remediation §3c MEDIUM/LOW (26/8/2026).

Ogni classe difende UNA divergenza frontend↔backend trovata dall'audit e
fallisce se il fix viene tolto. Il filo comune e' lo stesso dei HIGH: il client
ri-derivava localmente uno stato che il worker gia' conosceva, oppure il worker
non mandava il dato che il client dichiarava obbligatorio.

I fix di sola UI (etichette di troncamento, colori dei gauge, toast) non sono
testabili qui: il frontend non ha framework di test. Sono verificati con
`tsc --noEmit` + `next build` e annotati nel verbale.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.fastapi_worker as fw  # noqa: F401 — carica i moduli condivisi
import services.routers.admin as admin
import services.routers.fatture as fatture


# ─── 1. KPI: solo_da_verificare / solo_ripartite ─────────────────────────────

class TestKpiRispettaIFiltriDellaTabella:
    """La KpiBar sta SOPRA la tabella Articoli. Senza questi due filtri mostrava
    il periodo intero mentre la tabella si restringeva: "Spesa totale 120.000"
    sopra righe che ne sommano 3.200."""

    ROWS = [
        {"id": 1, "descrizione": "A", "totale_riga": 100.0, "data_documento": "2026-08-01",
         "needs_review": True, "ripartita_su_gruppo": False, "created_at": "2026-08-01"},
        {"id": 2, "descrizione": "B", "totale_riga": 900.0, "data_documento": "2026-08-02",
         "needs_review": False, "ripartita_su_gruppo": True, "created_at": "2026-08-02"},
    ]

    def _kpi(self, **kw):
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=MagicMock()),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=MagicMock(side_effect=lambda *a, **k: list(self.ROWS)),
            _compute_periodo_precedente=MagicMock(return_value=(None, None)),
        ):
            return fatture.get_fatture_kpi(
                data_da="2026-08-01", data_a="2026-08-31", authorization="Bearer t", **kw
            )

    def test_senza_filtri_somma_tutto(self):
        assert self._kpi().totale == 1000.0

    def test_solo_da_verificare_restringe_il_totale(self):
        assert self._kpi(solo_da_verificare=True).totale == 100.0

    def test_solo_ripartite_restringe_il_totale(self):
        assert self._kpi(solo_ripartite=True).totale == 900.0

    def test_solo_ripartite_inerte_se_non_ci_sono_ripartite(self):
        """Stessa guardia del client (articoli-tab.tsx:199): il chip che lo spegne
        e' nascosto quando non ci sono righe ripartite, e un ?ripartite=1 rimasto
        nell'URL avrebbe azzerato i KPI sopra una tabella piena — lo stesso
        difetto che si sta correggendo, di segno opposto."""
        rows = [dict(r, ripartita_su_gruppo=False) for r in self.ROWS]
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=MagicMock()),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=MagicMock(side_effect=lambda *a, **k: list(rows)),
            _compute_periodo_precedente=MagicMock(return_value=(None, None)),
        ):
            out = fatture.get_fatture_kpi(
                data_da="2026-08-01", data_a="2026-08-31",
                solo_ripartite=True, authorization="Bearer t",
            )
        assert out.totale == 1000.0


# ─── 2. righe-articolo propaga tipo_prodotti ─────────────────────────────────

class TestRigheArticoloFiltraComeLAggregato:
    """22 descrizioni reali hanno righe sia F&B sia spese-generali: senza il
    filtro il totale della riga padre (aggregato, filtrato) non era la somma
    delle righe figlie mostrate (tutte)."""

    def _chiama(self, tipo):
        spy = MagicMock(return_value=[])
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=MagicMock()),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=spy,
            _load_num_documento_map=MagicMock(return_value={}),
        ):
            fatture.get_righe_articolo(
                descrizione="X", data_da="2026-01-01", data_a="2026-12-31",
                tipo_prodotti=tipo, authorization="Bearer t",
            )
        return spy.call_args

    def test_tipo_prodotti_arriva_al_fetch(self):
        args = self._chiama("food_beverage")
        assert "food_beverage" in args.args or args.kwargs.get("tipo_prodotti") == "food_beverage"

    def test_none_resta_none(self):
        args = self._chiama(None)
        passati = list(args.args) + list(args.kwargs.values())
        assert "food_beverage" not in passati


# ─── 3. articoli-aggregati: total_con_acquisti ───────────────────────────────

class TestTotalConAcquisti:
    """Il KPI "Prodotti diversi" conta ACQUISTI (righe con importo != 0), la
    tabella elenca anche note e diciture. Il secondo numero DEVE venire dal
    worker: un articolo i cui storni si annullano ha totale_speso 0 ma righe di
    acquisto vere (misurato: fino a 14 articoli per sede), quindi il client non
    puo' ricavarlo da totale_speso."""

    ROWS = [
        # acquisto normale
        {"id": 1, "descrizione": "PANE", "totale_riga": 10.0, "categoria": "PANE",
         "fornitore": "F1", "data_documento": "2026-08-01", "quantita": 1,
         "prezzo_unitario": 10.0, "unita_misura": "PZ", "created_at": "2026-08-01"},
        # dicitura a importo zero
        {"id": 2, "descrizione": "TRASPORTO GRATUITO", "totale_riga": 0.0,
         "categoria": "📝 NOTE E DICITURE", "fornitore": "F1",
         "data_documento": "2026-08-01", "quantita": 0, "prezzo_unitario": 0.0,
         "unita_misura": "PZ", "created_at": "2026-08-01"},
        # acquisto + storno che si annullano: totale 0 ma righe vere
        {"id": 3, "descrizione": "OLIO", "totale_riga": 50.0, "categoria": "OLI",
         "fornitore": "F1", "data_documento": "2026-08-01", "quantita": 1,
         "prezzo_unitario": 50.0, "unita_misura": "LT", "created_at": "2026-08-01"},
        {"id": 4, "descrizione": "OLIO", "totale_riga": -50.0, "categoria": "OLI",
         "fornitore": "F1", "data_documento": "2026-08-02", "quantita": -1,
         "prezzo_unitario": -50.0, "unita_misura": "LT", "created_at": "2026-08-02"},
    ]

    def _agg(self):
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = SimpleNamespace(data={"nuovi_da": None})
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=sb),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=MagicMock(side_effect=lambda *a, **k: list(self.ROWS)),
            _compute_periodo_precedente=MagicMock(return_value=(None, None)),
            _load_num_documento_map=MagicMock(return_value={}),
        ):
            return fatture.get_articoli_aggregati(
                data_da="2026-08-01", data_a="2026-08-31", authorization="Bearer t"
            )

    def test_total_conta_tutte_le_descrizioni(self):
        assert self._agg().total == 3  # PANE, TRASPORTO, OLIO

    def test_total_con_acquisti_esclude_solo_le_diciture(self):
        """OLIO deve contare: i suoi storni si annullano ma le righe sono acquisti."""
        assert self._agg().total_con_acquisti == 2  # PANE + OLIO

    def test_non_coincide_con_il_conteggio_su_totale_speso(self):
        """Difende la scelta di calcolarlo sul worker: l'approssimazione lato
        client (contare gli articoli con totale_speso != 0) darebbe 1, non 2."""
        out = self._agg()
        approssimazione = sum(1 for a in out.articoli if a.totale_speso != 0)
        assert approssimazione == 1
        assert out.total_con_acquisti == 2


# ─── 4. prezzi: storico_valori grezzi ────────────────────────────────────────

class TestStoricoValori:
    def test_i_valori_grezzi_non_sono_troncati_a_due_decimali(self):
        """`storico` e' presentazione ("€1,20 → €1,35"): il client la ri-splittava
        per la sparkline, perdendo i decimali oltre il secondo su un dominio che
        tiene i prezzi a 4."""
        from services.routers.prezzi import VariazionePrezzo
        v = VariazionePrezzo(
            prodotto="X", categoria="C", fornitore="F",
            storico="€1,20 → €1,35", storico_valori=[1.2049, 1.3512],
            media=1.3, penultimo=1.2049, ultimo=1.3512, aumento_perc=12.1,
            data="2026-08-01", n_fattura="1", trend="su",
            impatto_stimato=10.0, delta_euro=0.15,
        )
        assert v.storico_valori == [1.2049, 1.3512]
        assert round(v.storico_valori[0], 4) != round(1.20, 4)

    def test_il_calcolo_reale_non_arrotonda_i_valori(self):
        """Esercita _calcola_variazioni_prezzi_sync, non un modello costruito a
        mano: e' li' che nasce storico_valori, ed e' li' che un round(...,2)
        reintrodurrebbe esattamente il difetto che il fix ha chiuso — la
        sparkline disegnata su prezzi troncati."""
        from services.routers.prezzi import _calcola_variazioni_prezzi_sync

        rows = [
            {"descrizione": "OLIO EVO", "fornitore": "F1", "categoria": "OLI",
             "prezzo_unitario": 1.2049, "quantita": 1, "totale_riga": 1.2049,
             "data_documento": "2026-06-01", "numero_documento": "1",
             "tipo_documento": "TD01", "file_origine": "a.xml"},
            {"descrizione": "OLIO EVO", "fornitore": "F1", "categoria": "OLI",
             "prezzo_unitario": 1.9873, "quantita": 1, "totale_riga": 1.9873,
             "data_documento": "2026-07-01", "numero_documento": "2",
             "tipo_documento": "TD01", "file_origine": "b.xml"},
        ]
        out = _calcola_variazioni_prezzi_sync(rows, soglia=1.0)
        assert out, "la variazione deve superare la soglia"
        valori = out[0]["storico_valori"]
        assert valori == [1.2049, 1.9873]
        # La stringa di presentazione resta a 2 decimali: sono due cose diverse.
        assert "1.20" in out[0]["storico"] or "1,20" in out[0]["storico"]

    def test_default_vuoto_non_none(self):
        """Il client fa `r.storico_valori ?? parseStorico(...)`: una lista vuota
        non deve far cadere il fallback su una response senza dati."""
        from services.routers.prezzi import VariazionePrezzo
        v = VariazionePrezzo(
            prodotto="X", categoria="C", fornitore="F", storico="",
            media=1.0, penultimo=1.0, ultimo=1.0, aumento_perc=0.0,
            data="2026-08-01", n_fattura="1", trend="stabile",
            impatto_stimato=0.0, delta_euro=0.0,
        )
        assert v.storico_valori == []


# ─── 5. admin: dettaglio cliente allineato alla lista ────────────────────────

class TestDettaglioClienteCampiObbligatori:
    """n_fatture/n_sedi/piano_inizio_at sono dichiarati OBBLIGATORI in
    lib/admin.ts ma non venivano restituiti: "Fatture totali" mostrava "—" nel
    dettaglio mentre la lista mostrava il numero vero, e n_sedi undefined
    diventava NaN dopo crea/elimina sede."""

    def _dettaglio(self, sedi_rows, rpc_n=7):
        sb = MagicMock()

        def _table(name):
            q = MagicMock()
            if name == "users":
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
                    data=[{
                        "id": "u1", "email": "c@x.it", "nome_ristorante": "R",
                        "attivo": True, "piano": "base",
                        "piano_inizio_at": "2026-01-15", "pagine_abilitate": {},
                    }]
                )
            elif name == "ristoranti":
                q.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=sedi_rows)
            else:
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
            return q

        sb.table.side_effect = _table
        sb.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[{"user_id": "u1", "n": rpc_n}]
        )
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _get_ristorante_id_for_user=MagicMock(return_value="rid-1"),
        ):
            return admin.admin_dettaglio_cliente("u1")

    def test_n_fatture_arriva_dalla_stessa_rpc_della_lista(self):
        assert self._dettaglio([{"id": "s1", "piano_inizio_at": None}])["n_fatture"] == 7

    def test_n_sedi_presente_e_coerente_con_sedi(self):
        out = self._dettaglio([{"id": "s1"}, {"id": "s2"}])
        assert out["n_sedi"] == 2 == len(out["sedi"])

    def test_piano_inizio_at_viene_da_users_non_dalla_sede(self):
        """La lista lo legge da users (admin.py:374): leggerlo dalla sede avrebbe
        dato un valore diverso nella stessa schermata."""
        out = self._dettaglio([{"id": "s1", "piano_inizio_at": "2099-12-31"}])
        assert out["piano_inizio_at"] == "2026-01-15"

    def test_rpc_fallita_non_rompe_il_dettaglio(self):
        sb = MagicMock()

        def _table(name):
            q = MagicMock()
            if name == "users":
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
                    data=[{"id": "u1", "email": "c@x.it", "nome_ristorante": "R",
                           "attivo": True, "piano": "base", "pagine_abilitate": {}}]
                )
            elif name == "ristoranti":
                q.select.return_value.eq.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[])
            else:
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
            return q

        sb.table.side_effect = _table
        sb.rpc.side_effect = Exception("rpc giù")
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _get_ristorante_id_for_user=MagicMock(return_value=None),
        ):
            out = admin.admin_dettaglio_cliente("u1")
        assert out["n_fatture"] == 0


class TestDettaglioClienteEscludeSedeTecnica:
    def test_il_filtro_sede_tecnica_e_applicato(self):
        """Terzo punto in cui lo stesso cliente aveva due conteggi di sedi: la
        lista filtrava sede_tecnica, il dettaglio no."""
        sb = MagicMock()
        chiamate = []

        def _table(name):
            q = MagicMock()
            if name == "users":
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(
                    data=[{"id": "u1", "email": "c@x.it", "nome_ristorante": "R",
                           "attivo": True, "piano": "base", "pagine_abilitate": {}}]
                )
            elif name == "ristoranti":
                sel = q.select.return_value
                def _eq1(col, val):
                    chiamate.append((col, val))
                    inner = MagicMock()
                    def _eq2(c2, v2):
                        chiamate.append((c2, v2))
                        r = MagicMock()
                        r.execute.return_value = SimpleNamespace(data=[])
                        return r
                    inner.eq.side_effect = _eq2
                    return inner
                sel.eq.side_effect = _eq1
            else:
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[])
            return q

        sb.table.side_effect = _table
        sb.rpc.return_value.execute.return_value = SimpleNamespace(data=[])
        with patch.multiple(
            admin,
            get_supabase_client=MagicMock(return_value=sb),
            _get_ristorante_id_for_user=MagicMock(return_value=None),
        ):
            admin.admin_dettaglio_cliente("u1")
        assert ("sede_tecnica", False) in chiamate
