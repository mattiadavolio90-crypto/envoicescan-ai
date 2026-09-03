"""Fase 4 piano categorizzazione: le righe `da_verificare` fuori dai margini,
dietro flag SPENTO.

Tre invarianti, ognuna col suo modo di rompersi in silenzio:
1. **A flag spento non cambia NULLA**: né la query PostgREST né i parametri RPC.
   È ciò che rende il deploy sicuro in qualunque ordine rispetto alla migration.
2. **A flag acceso la clausola è NULL-safe**: `.neq('categoria_fiducia', ...)`
   scarterebbe anche i NULL — e NULL è lo storico legacy (39.224 righe = `certa`
   per la regola S3), che DEVE restare nei margini.
3. **Le due sponde usano la stessa stringa**: il gate (`valuta_fiducia`) scrive
   `da_verificare`, il filtro la confronta. Se divergono, il filtro filtra
   niente, in silenzio — la stessa classe del refuso 'Da Clasificare'.
"""
import pathlib

import pytest

from config.constants import (
    CATEGORIA_FIDUCIA_DA_VERIFICARE,
    ESCLUDI_DA_VERIFICARE_DAI_MARGINI,
)
from services.db_service import escludi_da_verificare_margini, rpc_params_fase4

_MIGRATION = (
    pathlib.Path(__file__).resolve().parents[1]
    / "supabase" / "migrations" / "20260903210000_fase4_escludi_da_verificare_flag.sql"
)


class _QueryFinta:
    def __init__(self):
        self.or_chiamate = []

    def or_(self, clausola):
        self.or_chiamate.append(clausola)
        return self


class TestFlagSpento:
    def test_il_flag_parte_spento(self):
        """L'attivazione è di Mattia (delta per sede misurato e portato a lui,
        migration applicata PRIMA del flip). Se questo test è rosso, qualcuno ha
        acceso il flag: verificare che l'ordine di attivazione sia stato seguito,
        poi aggiornare QUESTO test insieme al verbale."""
        assert ESCLUDI_DA_VERIFICARE_DAI_MARGINI is False

    def test_query_intoccata(self):
        q = _QueryFinta()
        assert escludi_da_verificare_margini(q) is q
        assert q.or_chiamate == []

    def test_parametri_rpc_intoccati(self):
        params = {"p_ristorante_ids": ["x"], "p_anno": 2026}
        out = rpc_params_fase4(params)
        assert out == {"p_ristorante_ids": ["x"], "p_anno": 2026}
        assert "p_escludi_da_verificare" not in out

    def test_rpc_reale_non_riceve_il_parametro(self, monkeypatch):
        """Contratto col DB: a flag spento la chiamata è identica a prima della
        Fase 4, quindi funziona anche su un DB senza la migration."""
        from services import margine_service

        registrate = []

        class _RPC:
            def __init__(self, nome, params):
                registrate.append((nome, params))

            def execute(self):
                class _R:
                    data = []
                return _R()

        class _SB:
            def rpc(self, nome, params):
                return _RPC(nome, params)

        monkeypatch.setattr(margine_service, "get_supabase_client", lambda: _SB())
        margine_service.calcola_costi_automatici_per_anno_sql("u", "r", 2026)
        assert len(registrate) == 1
        nome, params = registrate[0]
        assert nome == "costi_automatici_mensili"
        assert "p_escludi_da_verificare" not in params


class TestFlagAcceso:
    @pytest.fixture(autouse=True)
    def _accendi(self, monkeypatch):
        import config.constants as C
        monkeypatch.setattr(C, "ESCLUDI_DA_VERIFICARE_DAI_MARGINI", True)

    def test_clausola_null_safe(self):
        q = _QueryFinta()
        escludi_da_verificare_margini(q)
        assert len(q.or_chiamate) == 1
        clausola = q.or_chiamate[0]
        # La parte che salva lo storico legacy: senza is.null, 39.224 righe
        # NULL = certa sparirebbero dai margini.
        assert "categoria_fiducia.is.null" in clausola
        assert f"categoria_fiducia.neq.{CATEGORIA_FIDUCIA_DA_VERIFICARE}" in clausola

    def test_parametro_rpc_aggiunto_senza_mutare_l_input(self):
        params = {"p_anno": 2026}
        out = rpc_params_fase4(params)
        assert out["p_escludi_da_verificare"] is True
        assert params == {"p_anno": 2026}


class TestStessaStringaSulleDueSponde:
    def test_il_gate_scrive_cio_che_il_filtro_confronta(self):
        """Comportamentale: una fonte sconosciuta viene declassata dal gate, e il
        valore che scrive DEVE essere quello che il filtro esclude."""
        from services.ai_service import valuta_fiducia

        esito = valuta_fiducia("fonte_che_non_esiste", "CARNE", "PIPPO", None)
        assert esito == CATEGORIA_FIDUCIA_DA_VERIFICARE

    def test_la_migration_confronta_la_stessa_stringa(self):
        sql = "\n".join(
            r for r in _MIGRATION.read_text(encoding="utf-8").splitlines()
            if not r.lstrip().startswith("--")
        )
        attesa = (
            "(NOT p_escludi_da_verificare OR "
            f"COALESCE(f.categoria_fiducia, '') <> '{CATEGORIA_FIDUCIA_DA_VERIFICARE}')"
        )
        # 7 RPC vive (misurate su pg_proc il 3/9), una condizione ciascuna.
        assert sql.count(attesa) == 7, (
            f"la condizione Fase 4 compare {sql.count(attesa)} volte nella "
            "migration, attese 7 (una per RPC). O manca una RPC, o la stringa "
            "è divergente dal Python — e allora il filtro SQL non esclude nulla"
        )

    def test_la_migration_da_il_default_spento(self):
        sql = "\n".join(
            r for r in _MIGRATION.read_text(encoding="utf-8").splitlines()
            if not r.lstrip().startswith("--")
        )
        assert sql.count("p_escludi_da_verificare boolean DEFAULT false") == 7
