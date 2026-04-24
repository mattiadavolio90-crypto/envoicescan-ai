"""
Test per services/db_service.py

GROUP A: calcola_alert  (logica pura DataFrame, pandas reale)
GROUP B: normalizzazione categorie in carica_e_prepara_dataframe (mock Supabase)
"""
import ast
import sys
import importlib
import re
from pathlib import Path

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

import services.db_service as _db_mod
importlib.reload(_db_mod)

from services.db_service import calcola_alert, get_custom_tags, aggiungi_associazioni, carica_sconti_e_omaggi
from config.constants import CATEGORIE_SPESE_GENERALI


DB_SERVICE_FILE = Path(__file__).resolve().parents[1] / 'services' / 'db_service.py'


def _load_db_service_functions(*function_names):
    """Estrae funzioni dal sorgente evitando l'effetto del decorator mockato di Streamlit."""
    source = DB_SERVICE_FILE.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(DB_SERVICE_FILE))

    wanted = set(function_names)
    selected_nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]

    for node in selected_nodes:
        node.decorator_list = []

    found = {node.name for node in selected_nodes}
    missing = wanted - found
    if missing:
        raise AssertionError(f"Funzioni non trovate in {DB_SERVICE_FILE.name}: {sorted(missing)}")

    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)

    namespace = {
        'List': list,
        'Dict': dict,
        'Any': object,
        're': re,
        'logger': MagicMock(),
    }
    exec(compile(module, str(DB_SERVICE_FILE), 'exec'), namespace)
    return [namespace[name] for name in function_names]


_normalize_custom_tag_key_pure, get_custom_tags_pure, aggiungi_associazioni_pure = _load_db_service_functions(
    '_normalize_custom_tag_key',
    'get_custom_tags',
    'aggiungi_associazioni',
)


# ============================================================
# HELPER: costruisce DataFrame con schema minimo per calcola_alert
# ============================================================

def _make_df(rows):
    """
    rows: lista di dict con chiavi opzionali.
    Campi mancanti ricevono valori di default sensati.
    """
    records = []
    for r in rows:
        records.append({
            'Descrizione':    r.get('Descrizione', 'PRODOTTO TEST'),
            'Fornitore':      r.get('Fornitore', 'FORNITORE SRL'),
            'DataDocumento':  r.get('DataDocumento', '2025-01-01'),
            'PrezzoUnitario': float(r.get('PrezzoUnitario', 10.0)),
            'Categoria':      r.get('Categoria', '🥩 CARNE'),
            'FileOrigine':    r.get('FileOrigine', 'fattura_001.xml'),
            'Quantita':       float(r.get('Quantita', 1.0)),
            'UnitaMisura':    r.get('UnitaMisura', 'KG'),
            'TotaleRiga':     float(r.get('TotaleRiga', r.get('PrezzoUnitario', 10.0))),
        })
    return pd.DataFrame(records)


# ============================================================
# GROUP A: calcola_alert
# ============================================================

class TestCalcolaAlert:

    def test_alert_aumento_rilevato(self):
        """2 acquisti: 10 euro → 12 euro (+20%), soglia 5% → alert presente."""
        df = _make_df([
            {'Descrizione': 'SALMONE FRESCO', 'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'SALMONE FRESCO', 'PrezzoUnitario': 12.0, 'DataDocumento': '2025-02-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert not result.empty, "Atteso almeno un alert con aumento del 20%"
        assert 'Aumento_Perc' in result.columns
        assert abs(result.iloc[0]['Aumento_Perc'] - 20.0) < 0.5
        assert 'SALMONE' in str(result.iloc[0]['Prodotto']).upper()

    def test_alert_sotto_soglia_ignorato(self):
        """Variazione 3% < soglia 5% → nessun alert."""
        df = _make_df([
            {'Descrizione': 'MANZO FETTINE', 'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'MANZO FETTINE', 'PrezzoUnitario': 10.3, 'DataDocumento': '2025-02-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert result.empty, "Nessun alert atteso: variazione 3% < soglia 5%"

    def test_alert_ribasso_rilevato(self):
        """Ribasso 10 euro → 8 euro (-20%), soglia 5% → alert con aumento_perc negativo."""
        df = _make_df([
            {'Descrizione': 'POMODORI FRESCHI', 'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'POMODORI FRESCHI', 'PrezzoUnitario': 8.0,  'DataDocumento': '2025-02-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert not result.empty, "Atteso alert per ribasso del 20%"
        assert result.iloc[0]['Aumento_Perc'] < 0, "Il ribasso deve avere Aumento_Perc negativo"

    def test_alert_un_solo_acquisto_ignorato(self):
        """Un solo acquisto → impossibile confrontare → nessun alert."""
        df = _make_df([
            {'Descrizione': 'TONNO IN SCATOLA', 'PrezzoUnitario': 5.0, 'DataDocumento': '2025-01-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert result.empty, "Nessun alert con un solo acquisto"

    def test_alert_categoria_spese_generali_esclusa(self):
        """Categorie in CATEGORIE_SPESE_GENERALI non devono generare alert."""
        cat_esclusa = CATEGORIE_SPESE_GENERALI[0]  # "SERVIZI E CONSULENZE"
        df = _make_df([
            {'Descrizione': 'CONSULENZA HACCP', 'Categoria': cat_esclusa,
             'PrezzoUnitario': 100.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'CONSULENZA HACCP', 'Categoria': cat_esclusa,
             'PrezzoUnitario': 150.0, 'DataDocumento': '2025-02-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert result.empty, f"Spese generali ({cat_esclusa}) non devono generare alert"

    def test_alert_filtro_prodotto(self):
        """filtro_prodotto='SALMONE' filtra solo i prodotti che matchano."""
        df = _make_df([
            {'Descrizione': 'SALMONE FRESCO', 'Fornitore': 'FORN_A',
             'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'SALMONE FRESCO', 'Fornitore': 'FORN_A',
             'PrezzoUnitario': 12.0, 'DataDocumento': '2025-02-01'},
            {'Descrizione': 'MANZO TAGLIO',   'Fornitore': 'FORN_B',
             'PrezzoUnitario': 8.0,  'DataDocumento': '2025-01-01'},
            {'Descrizione': 'MANZO TAGLIO',   'Fornitore': 'FORN_B',
             'PrezzoUnitario': 10.0, 'DataDocumento': '2025-02-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0, filtro_prodotto='SALMONE')
        assert not result.empty
        for _, row in result.iterrows():
            assert 'SALMONE' in str(row['Prodotto']).upper(), "Solo SALMONE atteso nel filtro"
            assert 'MANZO' not in str(row['Prodotto']).upper()

    def test_alert_df_vuoto(self):
        """DataFrame vuoto → restituisce DataFrame vuoto senza eccezioni."""
        result = calcola_alert(pd.DataFrame(), soglia_minima=5.0)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_alert_ordinamento_decrescente(self):
        """3 prodotti con aumenti diversi → ordinati decrescente per Aumento_Perc."""
        df = _make_df([
            # Prodotto B: +25%
            {'Descrizione': 'PROD_B', 'Fornitore': 'F_B',
             'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'PROD_B', 'Fornitore': 'F_B',
             'PrezzoUnitario': 12.5, 'DataDocumento': '2025-02-01'},
            # Prodotto C: +12%
            {'Descrizione': 'PROD_C', 'Fornitore': 'F_C',
             'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'PROD_C', 'Fornitore': 'F_C',
             'PrezzoUnitario': 11.2, 'DataDocumento': '2025-02-01'},
            # Prodotto A: +5%
            {'Descrizione': 'PROD_A', 'Fornitore': 'F_A',
             'PrezzoUnitario': 10.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'PROD_A', 'Fornitore': 'F_A',
             'PrezzoUnitario': 10.5, 'DataDocumento': '2025-02-01'},
        ])
        result = calcola_alert(df, soglia_minima=4.0)
        assert len(result) >= 2
        percs = result['Aumento_Perc'].tolist()
        for i in range(len(percs) - 1):
            assert percs[i] >= percs[i + 1], "Alert devono essere ordinati decrescente per Aumento_Perc"

    def test_alert_aggiunge_trend_e_impatto_stimato(self):
        """Con almeno 3 acquisti deve esporre trend sintetico e impatto economico stimato."""
        df = _make_df([
            {'Descrizione': 'OLIO EVO', 'Fornitore': 'FORN_X', 'PrezzoUnitario': 10.0, 'Quantita': 4, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'OLIO EVO', 'Fornitore': 'FORN_X', 'PrezzoUnitario': 11.0, 'Quantita': 5, 'DataDocumento': '2025-02-01'},
            {'Descrizione': 'OLIO EVO', 'Fornitore': 'FORN_X', 'PrezzoUnitario': 13.0, 'Quantita': 6, 'DataDocumento': '2025-03-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert not result.empty
        assert 'Trend' in result.columns
        assert 'Impatto_Stimato' in result.columns
        assert result.iloc[0]['Trend'] in ['⬆️', '⬆️⬆️', '⬇️', '↕️']
        assert pd.notna(result.iloc[0]['Impatto_Stimato'])
        assert result.iloc[0]['Impatto_Stimato'] > 0

    def test_alert_storico_include_ultimo_nei_5_valori(self):
        """La colonna Storico deve mostrare gli ultimi 5 prezzi incluso l'ultimo acquisto."""
        df = _make_df([
            {'Descrizione': 'BURRATA', 'Fornitore': 'FORN_Y', 'PrezzoUnitario': 8.0, 'DataDocumento': '2025-01-01'},
            {'Descrizione': 'BURRATA', 'Fornitore': 'FORN_Y', 'PrezzoUnitario': 9.0, 'DataDocumento': '2025-02-01'},
            {'Descrizione': 'BURRATA', 'Fornitore': 'FORN_Y', 'PrezzoUnitario': 10.0, 'DataDocumento': '2025-03-01'},
            {'Descrizione': 'BURRATA', 'Fornitore': 'FORN_Y', 'PrezzoUnitario': 11.0, 'DataDocumento': '2025-04-01'},
            {'Descrizione': 'BURRATA', 'Fornitore': 'FORN_Y', 'PrezzoUnitario': 12.0, 'DataDocumento': '2025-05-01'},
            {'Descrizione': 'BURRATA', 'Fornitore': 'FORN_Y', 'PrezzoUnitario': 14.0, 'DataDocumento': '2025-06-01'},
        ])
        result = calcola_alert(df, soglia_minima=5.0)
        assert not result.empty
        storico = str(result.iloc[0]['Storico'])
        assert storico == '€9.00 → €10.00 → €11.00 → €12.00 → €14.00'
        assert abs(float(result.iloc[0]['Ultimo']) - 14.0) < 0.001


# ============================================================
# GROUP B: normalizzazione in carica_e_prepara_dataframe
# ============================================================

def _supabase_df_fixture(categoria):
    """
    Crea DataFrame con colonne uppercase, forma restituita da _carica_fatture_da_supabase.
    """
    return pd.DataFrame([{
        'FileOrigine':       'test.xml',
        'NumeroRiga':        1,
        'DataDocumento':     '2025-01-01',
        'Fornitore':         'TEST SRL',
        'Descrizione':       'PRODOTTO TEST',
        'Quantita':          1.0,
        'UnitaMisura':       'KG',
        'PrezzoUnitario':    10.0,
        'IVAPercentuale':    10.0,
        'TotaleRiga':        10.0,
        'Categoria':         categoria,
        'CodiceArticolo':    '',
        'PrezzoStandard':    None,
        'RistoranteId':      None,
        'NeedsReview':       False,
        'TipoDocumento':     'TD01',
        'ScontoPercentuale': 0.0,
    }])


class TestCaricaScontiEOmaggi:

    def test_omaggi_recuperano_ultimo_prezzo_disponibile(self):
        class _Response:
            def __init__(self, data):
                self.data = data

        class _Query:
            def __init__(self, table_name, period_rows, hist_rows):
                self.table_name = table_name
                self.period_rows = period_rows
                self.hist_rows = hist_rows
                self._offset = 0
                self._is_history = False

            def select(self, *args, **kwargs):
                return self

            def eq(self, *args, **kwargs):
                return self

            def gte(self, *args, **kwargs):
                return self

            def lte(self, *args, **kwargs):
                return self

            def gt(self, *args, **kwargs):
                self._is_history = True
                return self

            def in_(self, *args, **kwargs):
                return self

            def order(self, *args, **kwargs):
                return self

            def range(self, start, end):
                self._offset = start
                return self

            def execute(self):
                if self._offset > 0:
                    return _Response([])
                return _Response(self.hist_rows if self._is_history else self.period_rows)

        class _Supabase:
            def __init__(self, period_rows, hist_rows):
                self.period_rows = period_rows
                self.hist_rows = hist_rows

            def table(self, table_name):
                return _Query(table_name, self.period_rows, self.hist_rows)

        period_rows = [{
            'id': 1,
            'descrizione': 'TOPRINSE JET LT.5',
            'categoria': '🥤 BEVANDE',
            'fornitore': 'BRESCIANINI E CO.SRL',
            'prezzo_unitario': 0.0,
            'quantita': 2.0,
            'totale_riga': 0.0,
            'data_documento': '2026-01-30',
            'file_origine': 'omaggio.xml',
        }]
        hist_rows = [{
            'descrizione': 'TOPRINSE JET LT.5 ',
            'fornitore': 'brescianini e co.srl ',
            'prezzo_unitario': 7.5,
            'data_documento': '2026-01-10',
        }]

        result = carica_sconti_e_omaggi(
            user_id='user_test',
            data_inizio='2026-01-01',
            data_fine='2026-01-31',
            ristorante_id='rist_test',
            supabase_client=_Supabase(period_rows, hist_rows),
        )

        assert not result['omaggi'].empty
        assert float(result['omaggi'].iloc[0]['ultimo_prezzo']) == 7.5
        assert float(result['omaggi'].iloc[0]['valore_stimato']) == 15.0
        assert float(result['totale_omaggi']) == 15.0


class TestNormalizzazioneCategorie:

    def _carica(self, categoria, force_refresh=False):
        """
        Patcha _carica_fatture_da_supabase e st.session_state, poi esegue
        carica_e_prepara_dataframe e restituisce il DataFrame risultante.
        """
        from services.db_service import carica_e_prepara_dataframe

        df_mock = _supabase_df_fixture(categoria)

        with patch('services.db_service._carica_fatture_da_supabase', return_value=df_mock), \
             patch('services.db_service.st') as mock_st:
            mock_st.session_state.get = MagicMock(return_value=False)
            result = carica_e_prepara_dataframe(
                user_id='user_test',
                ristorante_id=None,
                force_refresh=force_refresh,
            )
        return result

    def test_none_diventa_da_classificare(self):
        """Categoria None → 'Da Classificare'."""
        result = self._carica(categoria=None)
        assert not result.empty
        assert (result['Categoria'] == 'Da Classificare').all(), \
            f"Atteso 'Da Classificare', trovato: {result['Categoria'].unique()}"

    def test_stringa_vuota_diventa_da_classificare(self):
        """Categoria '' (stringa vuota) → 'Da Classificare'."""
        result = self._carica(categoria='')
        assert not result.empty
        assert (result['Categoria'] == 'Da Classificare').all()

    def test_migrazione_salse(self):
        """Categoria 'SALSE' (vecchio nome) → 'SALSE E CREME' dopo migrazione."""
        result = self._carica(categoria='SALSE')
        assert not result.empty
        assert (result['Categoria'] == 'SALSE E CREME').all(), \
            f"Atteso 'SALSE E CREME', trovato: {result['Categoria'].unique()}"

    def test_righe_needs_review_incluse_di_default(self):
        """Le righe needs_review devono comparire nel flusso standard cliente (default)."""
        from services.db_service import carica_e_prepara_dataframe

        df_mock = _supabase_df_fixture('Da Classificare')
        df_mock.loc[0, 'NeedsReview'] = True
        df_mock.loc[0, 'PrezzoUnitario'] = 0.0
        df_mock.loc[0, 'TotaleRiga'] = 0.0

        with patch('services.db_service._carica_fatture_da_supabase', return_value=df_mock), \
             patch('services.db_service.st') as mock_st:
            mock_st.session_state.get = MagicMock(return_value=False)
            result = carica_e_prepara_dataframe(
                user_id='user_test',
                ristorante_id=None,
            )

        assert not result.empty

    def test_righe_needs_review_escluse_con_filtro_esplicito(self):
        """Con include_review_rows=False le righe needs_review restano nascoste."""
        from services.db_service import carica_e_prepara_dataframe

        df_mock = _supabase_df_fixture('Da Classificare')
        df_mock.loc[0, 'NeedsReview'] = True
        df_mock.loc[0, 'PrezzoUnitario'] = 0.0
        df_mock.loc[0, 'TotaleRiga'] = 0.0

        with patch('services.db_service._carica_fatture_da_supabase', return_value=df_mock), \
             patch('services.db_service.st') as mock_st:
            mock_st.session_state.get = MagicMock(return_value=False)
            result = carica_e_prepara_dataframe(
                user_id='user_test',
                ristorante_id=None,
                include_review_rows=False,
            )

        assert result.empty

    @pytest.mark.parametrize('legacy_cat', ['NO FOOD', 'MATERIALI', 'MATERIALE CONSUMO'])
    def test_migrazione_materiale_consumo_legacy(self, legacy_cat):
        """Vecchie etichette cliente devono convergere a 'MATERIALE DI CONSUMO'."""
        result = self._carica(categoria=legacy_cat)
        assert not result.empty
        assert (result['Categoria'] == 'MATERIALE DI CONSUMO').all(), \
            f"Atteso 'MATERIALE DI CONSUMO' per {legacy_cat}, trovato: {result['Categoria'].unique()}"

    def test_forcerefresh_chiama_clear(self):
        """force_refresh=True → _carica_fatture_da_supabase.clear() invocato esattamente una volta."""
        from services.db_service import carica_e_prepara_dataframe

        df_mock = _supabase_df_fixture('🥩 CARNE')
        mock_fn = MagicMock(return_value=df_mock)
        mock_fn.clear = MagicMock()

        with patch('services.db_service._carica_fatture_da_supabase', mock_fn), \
             patch('services.db_service.st') as mock_st:
            mock_st.session_state.get = MagicMock(return_value=False)
            carica_e_prepara_dataframe(
                user_id='user_test',
                ristorante_id=None,
                force_refresh=True,
            )

        mock_fn.clear.assert_called_once()


class TestCustomTagsDbService:

    def test_get_custom_tags_errore_restituisce_lista_vuota(self):
        """Errore Supabase in get_custom_tags -> [] senza propagare eccezioni."""
        with patch('services.get_supabase_client', side_effect=RuntimeError('boom')):
            result = get_custom_tags_pure('user_test', 'ristorante_test')

        assert result == []

    def test_aggiungi_associazioni_payload_vuoto_non_esegue_query(self):
        """Payload vuoto -> ritorna [] e non inizializza nemmeno il client Supabase."""
        with patch('services.get_supabase_client') as mock_get_supabase_client:
            result = aggiungi_associazioni_pure(123, [])

        assert result == []
        mock_get_supabase_client.assert_not_called()
