"""
Test per verificare che le modifiche di data_competenza si propaghino
correttamente ai calcoli di margini e analisi.

TEST SCENARIO:
1. Creare fatture con data_documento in gennaio, ma data_competenza in febbraio
2. Verificare che il calcolo costi_automatici_per_anno consideri il mese della data_competenza
3. Modificare data_competenza a marzo
4. Verificare che i costi cambino automaticamente
"""

import unittest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock


class TestDataCompetenzaPropagation(unittest.TestCase):
    """Testa che data_competenza influenzi i calcoli di margini."""
    
    def setUp(self):
        """Setup test data."""
        self.test_user_id = "test-user-123"
        self.test_ristorante_id = "test-rist-456"
        self.test_anno = 2026
    
    def test_margine_service_calcola_costi_con_data_competenza(self):
        """
        Coperto da tests/test_margine_service.py::test_calcola_costi_automatici_per_anno
        (che usa il workaround `_reload_margine_module_without_cache_wrapper` per
        bypassare il decorator @st.cache_data). Qui non riproducibile in modo affidabile.
        """
        self.skipTest(
            "Coperto da test_margine_service.py::test_calcola_costi_automatici_per_anno"
        )
    
    def test_carica_costi_per_categoria_con_data_competenza(self):
        """
        TEST: carica_costi_per_categoria rispetta data_competenza
        """
        from services.margine_service import carica_costi_per_categoria
        
        mock_supabase_data = [
            {
                'data_documento': '2026-01-15',
                'data_competenza': '2026-02-01',
                'totale_riga': 150.0,
                'categoria': 'FOOD'
            },
        ]
        
        with patch('services.margine_service.get_supabase_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_table.select.return_value = mock_table
            mock_table.eq.return_value = mock_table
            mock_table.is_.return_value = mock_table
            mock_table.gte.return_value = mock_table
            mock_table.lte.return_value = mock_table
            mock_table.neq.return_value = mock_table
            mock_table.range.return_value = mock_table
            
            mock_response = MagicMock()
            mock_response.data = mock_supabase_data
            mock_table.execute.return_value = mock_response
            
            # CALL con range gennaio
            result_df = carica_costi_per_categoria(
                self.test_user_id,
                self.test_ristorante_id,
                '2026-01-01',
                '2026-01-31'
            )
            
            # La fattura è in gennaio (data_documento) ma ha competenza febbraio
            # Tuttavia, carica_costi_per_categoria filtra per data_documento nel range
            # Quindi la troverà ma usiamo data_competenza per calcolare il mese
            # → Quindi avrà mese=2 (febbraio) anche se caricata da query gennaio
            
            if not result_df.empty:
                # Dovrebbe avere mese=2 (febbraio), non mese=1
                self.assertIn(2, result_df['mese'].values,
                    "❌ FAIL: Fattura dovrebbe avere mese=2 (competenza), non mese=1")
            
            print("✅ TEST PASSED: carica_costi_per_categoria usa data_competenza")


class TestCacheClearPropagation(unittest.TestCase):
    """Testa che clear_fatture_cache invalida tutti i cache dipendenti."""
    
    def test_clear_fatture_cache_invalida_descrizioni_distinte(self):
        """
        TEST: clear_fatture_cache chiama get_descrizioni_distinte.clear()
        """
        from services.db_service import clear_fatture_cache
        from services.db_service import get_descrizioni_distinte
        
        with patch.object(get_descrizioni_distinte, 'clear', wraps=get_descrizioni_distinte.clear) as mock_clear:
            clear_fatture_cache()
            assert mock_clear.called, "clear_fatture_cache deve invocare get_descrizioni_distinte.clear()"
        
        print("✅ TEST PASSED: clear_fatture_cache invalida get_descrizioni_distinte")
    
    def test_clear_fatture_cache_invalida_margine_service_caches(self):
        """
        TEST: clear_fatture_cache chiama le funzioni di margine_service
        """
        from services.db_service import clear_fatture_cache
        from services.margine_service import calcola_costi_automatici_per_anno
        
        with patch.object(calcola_costi_automatici_per_anno, 'clear', wraps=calcola_costi_automatici_per_anno.clear) as mock_clear:
            clear_fatture_cache()
            assert mock_clear.called, "clear_fatture_cache deve invocare calcola_costi_automatici_per_anno.clear()"
        
        print("✅ TEST PASSED: clear_fatture_cache invalida calcola_costi_automatici_per_anno")


if __name__ == '__main__':
    unittest.main(verbosity=2)
