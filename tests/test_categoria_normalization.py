"""Test per la normalizzazione delle categorie anomale - fix C1 e C2 (audit 2026-04-20)."""
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# FIX C2 — NOTE E DICITURE senza emoji deve essere esclusa dal calcolo costi
# ---------------------------------------------------------------------------

def _apply_note_mask(df: pd.DataFrame) -> pd.Series:
    """Replica la logica di esclusione NOTE E DICITURE da dashboard_renderer.py."""
    col = df['Categoria'].fillna('')
    return (col == '📝 NOTE E DICITURE') | (col == 'NOTE E DICITURE')


class TestNoteEDicitureEsclusione:
    def test_emoji_version_excluded(self):
        df = pd.DataFrame({'Categoria': ['📝 NOTE E DICITURE', 'CARNE']})
        mask = _apply_note_mask(df)
        assert mask.tolist() == [True, False]

    def test_plain_version_excluded(self):
        df = pd.DataFrame({'Categoria': ['NOTE E DICITURE', 'PESCE']})
        mask = _apply_note_mask(df)
        assert mask.tolist() == [True, False]

    def test_other_categories_not_excluded(self):
        df = pd.DataFrame({'Categoria': ['CARNE', 'PESCE', 'LATTICINI', 'Da Classificare']})
        mask = _apply_note_mask(df)
        assert mask.sum() == 0

    def test_mixed_dataset(self):
        df = pd.DataFrame({
            'Categoria': ['📝 NOTE E DICITURE', 'NOTE E DICITURE', 'CARNE', 'PESCE']
        })
        mask = _apply_note_mask(df)
        assert mask.tolist() == [True, True, False, False]

    def test_nan_not_excluded(self):
        df = pd.DataFrame({'Categoria': [None, float('nan'), 'CARNE']})
        mask = _apply_note_mask(df)
        assert mask.sum() == 0


# ---------------------------------------------------------------------------
# FIX C1 — normalizzazione CAFFÈ E THE → CAFFE E THE in category_editor
# ---------------------------------------------------------------------------

def _normalize_caffe(cat: str) -> str:
    """Replica la logica di normalizzazione da category_editor.py."""
    if str(cat).strip().upper() in ['CAFFÈ', 'CAFFE', 'CAFFÈ E THE']:
        return 'CAFFE E THE'
    return cat


class TestCaffeNormalizzazione:
    @pytest.mark.parametrize("input_cat, expected", [
        ('CAFFÈ', 'CAFFE E THE'),
        ('CAFFE', 'CAFFE E THE'),
        ('CAFFÈ E THE', 'CAFFE E THE'),
        ('caffè e the', 'CAFFE E THE'),   # case insensitive
        ('CAFFE E THE', 'CAFFE E THE'),   # già corretto, invariato
        ('CARNE', 'CARNE'),
        ('LATTICINI', 'LATTICINI'),
    ])
    def test_normalizzazione(self, input_cat, expected):
        assert _normalize_caffe(input_cat) == expected

    def test_lista_categorie(self):
        categorie = ['CAFFÈ E THE', 'CAFFÈ', 'CAFFE', 'CARNE', 'PESCE']
        normalizzate = [
            ('CAFFE E THE' if str(c).strip().upper() in ['CAFFÈ', 'CAFFE', 'CAFFÈ E THE'] else c)
            for c in categorie
        ]
        assert normalizzate == ['CAFFE E THE', 'CAFFE E THE', 'CAFFE E THE', 'CARNE', 'PESCE']
