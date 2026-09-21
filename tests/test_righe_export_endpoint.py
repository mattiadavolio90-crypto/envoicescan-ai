"""Test dell'endpoint POST /api/fatture/righe-export.

Serve il foglio "Dettaglio righe" dell'export Excel del tab Articoli. Esiste
perche' l'aggregazione avviene nel worker e il client non ha mai le righe
singole: senza questo endpoint il file conteneva solo i totali per articolo.

Gli helper sono patchati SUL MODULO ROUTER (`fatture`), che e' cio' che i
wrapper espliciti rendono possibile — `patch.multiple` sul worker non
intercetterebbe i lookup di nome globale dentro le funzioni del router.
"""
from unittest.mock import MagicMock, patch

import pytest

from services.routers import fatture


def _riga(**kw):
    base = {
        "id": 1, "file_origine": "IT1_001.xml", "numero_riga": 1,
        "data_documento": "2026-09-03", "fornitore": "ORTOFRUTTA SRL",
        "descrizione": "POMODORO", "quantita": 10.0, "unita_misura": "KG",
        "prezzo_unitario": 1.2, "totale_riga": 12.0, "categoria": "ORTOFRUTTA",
        "needs_review": False, "tipo_documento": "TD01",
        "data_competenza": "2026-09-03", "piva_cedente": "IT00000000000",
        "created_at": "2026-09-03T10:00:00Z", "ripartita_su_gruppo": False,
    }
    base.update(kw)
    return base


def _chiama(rows, descrizioni=None, tipo_prodotti=None, num_map=None, spy=None):
    fetch = spy or MagicMock(side_effect=lambda *a, **k: list(rows))
    with patch.multiple(
        fatture,
        _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
        _get_supabase_client=MagicMock(return_value=MagicMock()),
        _resolve_ristorante_id=MagicMock(return_value="rid-1"),
        _fetch_fatture_rows=fetch,
        _load_num_documento_map=MagicMock(return_value=num_map or {}),
    ):
        return fatture.get_righe_export(
            payload=fatture.RigheExportRequest(descrizioni=descrizioni),
            data_da="2026-09-01", data_a="2026-09-30",
            tipo_prodotti=tipo_prodotti, authorization="Bearer t",
        )


# ─── Il filtro per descrizione ──────────────────────────────────────────────

class TestFiltroDescrizioni:
    """I filtri Cerca / Fornitore / Categoria / Solo verifica / Solo ripartite del
    tab Articoli vivono SOLO nel browser. Il client manda le descrizioni che ha a
    schermo: senza questo filtro il foglio di dettaglio conterrebbe articoli che
    l'utente aveva appena escluso dalla vista."""

    ROWS = [
        _riga(id=1, descrizione="POMODORO"),
        _riga(id=2, descrizione="MOZZARELLA"),
        _riga(id=3, descrizione="BASILICO"),
    ]

    def test_solo_le_descrizioni_richieste(self):
        out = _chiama(self.ROWS, descrizioni=["POMODORO", "BASILICO"])
        assert [r.descrizione for r in out.righe] == ["BASILICO", "POMODORO"]

    def test_senza_elenco_tutto_il_periodo(self):
        """`None` significa "nessun filtro a schermo", non "niente"."""
        out = _chiama(self.ROWS, descrizioni=None)
        assert len(out.righe) == 3

    def test_elenco_vuoto_non_e_assenza_di_filtro(self):
        """Lista vuota = "a schermo non c'e' nulla". Interpretarla come `None`
        farebbe uscire l'intero periodo proprio quando l'utente ha filtrato via
        tutto — il difetto piu' vistoso possibile per questo endpoint."""
        out = _chiama(self.ROWS, descrizioni=[])
        assert out.righe == []

    def test_match_esatto_non_per_sottostringa(self):
        """"POMODORO" non deve trascinarsi "POMODORO PELATO": a schermo sono due
        articoli distinti con due totali distinti."""
        rows = [_riga(id=1, descrizione="POMODORO"), _riga(id=2, descrizione="POMODORO PELATO")]
        out = _chiama(rows, descrizioni=["POMODORO"])
        assert [r.descrizione for r in out.righe] == ["POMODORO"]

    def test_spazi_attorno_non_fanno_mancare_la_riga(self):
        """L'aggregato fa `.strip()` sulla descrizione, quindi il client rimanda
        la forma strippata: confrontarla con la grezza perderebbe quelle righe."""
        rows = [_riga(id=1, descrizione="  POMODORO  ")]
        out = _chiama(rows, descrizioni=["POMODORO"])
        assert len(out.righe) == 1


# ─── Propagazione dei filtri di periodo ─────────────────────────────────────

def test_tipo_prodotti_arriva_al_fetch():
    """Stessa ragione di /righe-articolo: per le descrizioni a cavallo fra F&B e
    spese generali, senza il filtro la somma del foglio 2 non tornerebbe col
    totale del foglio 1."""
    spy = MagicMock(return_value=[])
    _chiama([], tipo_prodotti="food_beverage", spy=spy)
    args = spy.call_args
    assert "food_beverage" in args.args or args.kwargs.get("tipo_prodotti") == "food_beverage"


def test_periodo_arriva_al_fetch():
    spy = MagicMock(return_value=[])
    _chiama([], spy=spy)
    passati = list(spy.call_args.args) + list(spy.call_args.kwargs.values())
    assert "2026-09-01" in passati and "2026-09-30" in passati


# ─── Regole di dominio ──────────────────────────────────────────────────────

def test_nota_di_credito_sopravvive():
    """Le note di credito non si scartano: un export che le perde gonfia la spesa
    del periodo. Regola presidiata anche da test_regole_dominio_guardia."""
    rows = [_riga(id=1, totale_riga=-50.0, tipo_documento="TD04")]
    out = _chiama(rows)
    assert len(out.righe) == 1
    assert out.righe[0].totale_riga == -50.0


def test_riga_da_classificare_esce():
    """`Da Classificare` e' uno stato esplicito, visibile al cliente: le sue
    righe devono stare nel file come le altre."""
    rows = [_riga(id=1, categoria="Da Classificare", needs_review=True)]
    out = _chiama(rows)
    assert out.righe[0].categoria == "Da Classificare"
    assert out.righe[0].needs_review is True


def test_numero_documento_risolto_dalla_mappa():
    """In fattura il numero sta sul documento, non sulla riga: senza la mappa la
    colonna "N° documento" uscirebbe vuota su tutto il foglio."""
    rows = [_riga(id=1, file_origine="IT1_001.xml")]
    out = _chiama(rows, num_map={"IT1_001.xml": "1204"})
    assert out.righe[0].numero_documento == "1204"


def test_quota_di_gruppo_conservata():
    """Le righe proiettate (id sintetico negativo) compongono i totali del PV di
    catena: vanno nel foglio, marcate per quello che sono."""
    rows = [_riga(id=-7, ripartita_su_gruppo=True)]
    out = _chiama(rows)
    assert out.righe[0].ripartita_su_gruppo is True


# ─── Ordinamento ────────────────────────────────────────────────────────────

def test_righe_dello_stesso_articolo_contigue_e_per_data_decrescente():
    """E' il foglio che il cliente scorre: le righe di un articolo devono stare
    insieme, e la piu' recente per prima come nell'espansione a video."""
    rows = [
        _riga(id=1, descrizione="POMODORO", data_documento="2026-09-01"),
        _riga(id=2, descrizione="MOZZARELLA", data_documento="2026-09-02"),
        _riga(id=3, descrizione="POMODORO", data_documento="2026-09-10"),
        _riga(id=4, descrizione="MOZZARELLA", data_documento="2026-09-20"),
    ]
    out = _chiama(rows)
    assert [(r.descrizione, r.data_documento) for r in out.righe] == [
        ("MOZZARELLA", "2026-09-20"),
        ("MOZZARELLA", "2026-09-02"),
        ("POMODORO", "2026-09-10"),
        ("POMODORO", "2026-09-01"),
    ]


def test_data_mancante_non_rompe_l_ordinamento():
    rows = [
        _riga(id=1, descrizione="POMODORO", data_documento=None),
        _riga(id=2, descrizione="POMODORO", data_documento="2026-09-10"),
    ]
    out = _chiama(rows)
    assert [r.data_documento for r in out.righe] == ["2026-09-10", None]


# ─── Avviso di troncamento ──────────────────────────────────────────────────

class TestTroncato:
    """Il tetto di scansione di _fetch_fatture_rows e' un `break` silenzioso.
    Senza questo flag l'export consegnerebbe un file con meno righe del dovuto
    senza che nulla lo dica: peggio del difetto che l'endpoint rimedia."""

    def test_sotto_il_tetto_non_avvisa(self):
        out = _chiama([_riga(id=i) for i in range(1, 6)])
        assert out.troncato is False

    def test_al_tetto_avvisa(self):
        cap = fatture._fatture_rows_cap()
        rows = [_riga(id=i) for i in range(1, cap + 1)]
        out = _chiama(rows)
        assert out.troncato is True

    def test_il_tetto_e_quello_del_worker_non_una_copia(self):
        """Il valore si legge dal worker via wrapper: un 50000 ricopiato nel
        router avrebbe smesso di corrispondere al primo ritocco la'."""
        import services.fastapi_worker as fw
        assert fatture._fatture_rows_cap() == fw._FATTURE_ROWS_CAP

    def test_troncato_guarda_le_righe_lette_non_quelle_filtrate(self):
        """Il filtro per descrizione si applica DOPO: se restringesse il conteggio,
        un export filtrato su un periodo enorme direbbe "tutto bene" proprio nel
        caso in cui il dato di partenza era incompleto."""
        cap = fatture._fatture_rows_cap()
        rows = [_riga(id=i, descrizione="POMODORO") for i in range(1, cap)]
        rows.append(_riga(id=cap, descrizione="MOZZARELLA"))
        out = _chiama(rows, descrizioni=["MOZZARELLA"])
        assert len(out.righe) == 1
        assert out.troncato is True


# ─── Isolamento fra clienti ─────────────────────────────────────────────────

class TestIsolamento:
    """L'endpoint legge righe fattura, quindi deve stare dentro al ristorante del
    chiamante. I presidi strutturali di test_isolamento_per_risorsa NON lo
    vedono: coprono le GET a tenant di sessione e le operazioni che prendono
    l'id di una risorsa, e questo e' un POST senza id (il body porta descrizioni,
    non identificatori). Verificato qui, o resterebbe scoperto.
    """

    def test_le_righe_si_chiedono_per_il_ristorante_del_chiamante(self):
        """L'id non arriva dal client: si risolve dal token. Un `ristorante_id` che
        entrasse dal body o dalla query sarebbe il modo per leggere i dati altrui."""
        spy = MagicMock(return_value=[])
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=MagicMock()),
            _resolve_ristorante_id=MagicMock(return_value="rid-del-chiamante"),
            _fetch_fatture_rows=spy,
            _load_num_documento_map=MagicMock(return_value={}),
        ):
            fatture.get_righe_export(
                payload=fatture.RigheExportRequest(descrizioni=None),
                data_da=None, data_a=None, tipo_prodotti=None,
                authorization="Bearer t",
            )
        passati = list(spy.call_args.args) + list(spy.call_args.kwargs.values())
        assert "rid-del-chiamante" in passati

    def test_senza_ristorante_non_si_legge_nulla(self):
        """Fail-closed: niente sede risolta -> 400, non una lettura senza filtro."""
        spy = MagicMock(return_value=[_riga(id=1)])
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=MagicMock()),
            _resolve_ristorante_id=MagicMock(return_value=None),
            _fetch_fatture_rows=spy,
            _load_num_documento_map=MagicMock(return_value={}),
        ):
            with pytest.raises(fatture.HTTPException) as e:
                fatture.get_righe_export(
                    payload=fatture.RigheExportRequest(descrizioni=None),
                    data_da=None, data_a=None, tipo_prodotti=None,
                    authorization="Bearer t",
                )
        assert e.value.status_code == 400
        spy.assert_not_called()

    def test_l_endpoint_e_dietro_la_guardia_worker(self):
        """Il router monta `_verify_worker_key` a livello di APIRouter, ma la
        convenzione del file e' ripeterlo nel decoratore: se un giorno la guardia
        di router sparisse, questo endpoint non resterebbe aperto."""
        import services.fastapi_worker as fw
        rotta = next(
            r for r in fw.app.routes
            if getattr(r, "path", None) == "/api/fatture/righe-export"
        )
        nomi = [
            getattr(d.call, "__name__", None) for d in rotta.dependant.dependencies
        ]
        assert "_verify_worker_key" in nomi
        assert rotta.methods == {"POST"}


# ─── Il filtro "Nuovi caricati" ─────────────────────────────────────────────

class TestSoloNuovi:
    """`solo_nuovi` non e' un filtro client come gli altri cinque: l'aggregato lo
    applica SERVER-side e ci ricalcola sopra totale_speso/quantita/num_acquisti.
    Mandare le sole descrizioni non bastava — il foglio 1 diceva "ultimo carico"
    e il foglio 2 tutto lo storico di quegli articoli: due totali diversi nello
    stesso file. Difetto trovato in review il 21/09/2026, mai arrivato in
    produzione.
    """

    # Le date sono scelte dove le due soglie DIVERGONO: `nuovi_da` e' la sessione di
    # upload, il fallback e' "ultime 24 ore". La riga 1 e' stata caricata molto prima
    # di ieri ma dopo l'inizio di quella sessione: e' nuova per `nuovi_da` e vecchia
    # per una finestra di 24h. Con date "di oggi" le due soglie coinciderebbero e il
    # test resterebbe verde anche su un export che usa la soglia sbagliata — ci e'
    # gia' successo (mutante 7, 21/09/2026).
    CUTOFF = "2020-01-10T00:00:00Z"
    ROWS = [
        _riga(id=1, descrizione="POMODORO", created_at="2020-01-11T09:00:00Z", totale_riga=10.0),
        _riga(id=2, descrizione="POMODORO", created_at="2020-01-01T09:00:00Z", totale_riga=90.0),
    ]

    def _chiama_con_cutoff(self, solo_nuovi):
        sb = MagicMock()
        (sb.table.return_value.select.return_value.eq.return_value
           .single.return_value.execute.return_value.data) = {"nuovi_da": self.CUTOFF}
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=sb),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=MagicMock(side_effect=lambda *a, **k: list(self.ROWS)),
            _load_num_documento_map=MagicMock(return_value={}),
        ):
            return fatture.get_righe_export(
                payload=fatture.RigheExportRequest(descrizioni=["POMODORO"]),
                data_da="2026-01-01", data_a="2026-12-31", tipo_prodotti=None,
                solo_nuovi=solo_nuovi, authorization="Bearer t",
            )

    def test_attivo_tiene_solo_le_righe_dell_ultimo_carico(self):
        out = self._chiama_con_cutoff(True)
        assert [r.id for r in out.righe] == [1]
        assert sum(r.totale_riga for r in out.righe) == 10.0

    def test_spento_tiene_tutto_lo_storico(self):
        out = self._chiama_con_cutoff(False)
        assert sorted(r.id for r in out.righe) == [1, 2]
        assert sum(r.totale_riga for r in out.righe) == 100.0

    def test_il_default_non_filtra(self):
        """Un export senza la checkbox deve vedere tutto il periodo."""
        with patch.multiple(
            fatture,
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=MagicMock()),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=MagicMock(side_effect=lambda *a, **k: list(self.ROWS)),
            _load_num_documento_map=MagicMock(return_value={}),
        ):
            out = fatture.get_righe_export(
                payload=fatture.RigheExportRequest(descrizioni=None),
                data_da=None, data_a=None, tipo_prodotti=None,
                authorization="Bearer t",
            )
        assert len(out.righe) == 2

    def test_i_due_fogli_usano_LA_STESSA_soglia(self):
        """Il presidio vero di questa classe: non che l'export filtri, ma che
        filtri come l'aggregato. Due copie della regola divergono — e' cosi' che
        il difetto e' nato. Si esegue l'aggregazione reale e l'export reale sulle
        stesse righe e si confrontano i totali dei due fogli."""
        sb = MagicMock()
        (sb.table.return_value.select.return_value.eq.return_value
           .single.return_value.execute.return_value.data) = {"nuovi_da": self.CUTOFF}
        comune = dict(
            _resolve_user_from_token=MagicMock(return_value={"email": "c@x.it"}),
            _get_supabase_client=MagicMock(return_value=sb),
            _resolve_ristorante_id=MagicMock(return_value="rid-1"),
            _fetch_fatture_rows=MagicMock(side_effect=lambda *a, **k: list(self.ROWS)),
            _load_num_documento_map=MagicMock(return_value={}),
        )
        with patch.multiple(fatture, _compute_periodo_precedente=MagicMock(return_value=(None, None)), **comune):
            agg = fatture.get_articoli_aggregati(
                data_da="2026-01-01", data_a="2026-12-31",
                solo_nuovi=True, authorization="Bearer t",
            )
        with patch.multiple(fatture, **comune):
            det = fatture.get_righe_export(
                payload=fatture.RigheExportRequest(
                    descrizioni=[a.descrizione for a in agg.articoli]),
                data_da="2026-01-01", data_a="2026-12-31", tipo_prodotti=None,
                solo_nuovi=True, authorization="Bearer t",
            )
        # foglio 1 e foglio 2 devono raccontare lo stesso periodo
        assert sum(a.totale_speso for a in agg.articoli) == sum(r.totale_riga for r in det.righe)
        assert sum(a.num_acquisti for a in agg.articoli) == len(det.righe)


def test_cutoff_nuovo_condiviso_fra_i_due_endpoint():
    """`_cutoff_nuovo` e' una funzione sola perche' due copie divergono."""
    sb = MagicMock()
    (sb.table.return_value.select.return_value.eq.return_value
       .single.return_value.execute.return_value.data) = {"nuovi_da": "2026-09-20T00:00:00Z"}
    assert fatture._cutoff_nuovo(sb, "rid-1") == "2026-09-20T00:00:00Z"


def test_cutoff_nuovo_fallback_24h_al_primo_avvio():
    """Senza `nuovi_da` (prima sessione di upload) non si deve alzare un'eccezione
    ne' considerare tutto nuovo: si guarda alle ultime 24 ore."""
    from datetime import datetime, timezone
    sb = MagicMock()
    (sb.table.return_value.select.return_value.eq.return_value
       .single.return_value.execute.return_value.data) = {"nuovi_da": None}
    cutoff = fatture._cutoff_nuovo(sb, "rid-1")
    delta = datetime.now(timezone.utc) - datetime.fromisoformat(cutoff)
    assert 23 * 3600 < delta.total_seconds() < 25 * 3600
