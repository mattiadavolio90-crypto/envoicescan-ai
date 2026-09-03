"""Fase 8 (D8+D10): igiene tecnica della categorizzazione, provata sul comportamento.

D8 — il correttore di refusi (collasso doppie) valeva anche per parole corte,
dove la forma collassata è troppo spesso una parola REALE diversa: POLLO->POLO
classificava CARNE una polo personalizzata da 60 EUR (danno accertato), e a DB
c'erano 65 keyword in quella condizione (BOLLO->BOLO, CAFFE->CAFE, CAPPA->CAPA).
Ora il collasso vale solo per forme >=6 char: il refuso su parola lunga si
recupera ancora, quello su parola corta lo gestiscono AI e memoria.

D10 — l'A/B test misurava su ground truth parziale: il filtro
`LIKE 'Manuale (%@%'` ignorava la grafia legacy `'User'` (319 correzioni reali).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.ai_service import (
    _PATTERNS_ALIMENTI_COLLASSATI,
    _PATTERNS_CONTENITORI_COLLASSATI,
    applica_correzioni_dizionario,
)


class TestCollassoSoloParoleLunghe:
    def test_polo_non_e_piu_carne(self):
        """Il danno accertato: la polo personalizzata classificata CARNE via
        POLLO->POLO. Deve restare Da Classificare (la decide l'AI, col contesto)."""
        assert applica_correzioni_dizionario("POLO RALPH LAUREN TG M", "Da Classificare") == "Da Classificare"

    def test_cafe_non_matcha_caffe(self):
        assert applica_correzioni_dizionario("CAFE MISCELA", "Da Classificare") == "Da Classificare"

    def test_il_refuso_su_parola_lunga_si_recupera_ancora(self):
        """MOZARELLA (refuso reale) deve continuare a diventare LATTICINI:
        la soglia toglie i falsi positivi, non la tolleranza ai refusi."""
        assert applica_correzioni_dizionario("MOZARELLA FIOR DI LATTE", "Da Classificare") == "LATTICINI"

    def test_nessun_pattern_collassato_sotto_le_6_lettere(self):
        """Il criterio, verificato sull'artefatto compilato (non sul sorgente):
        se una forma corta rientra, il falso positivo torna in silenzio."""
        import re
        for pattern, _cat in _PATTERNS_ALIMENTI_COLLASSATI + _PATTERNS_CONTENITORI_COLLASSATI:
            # il pattern è (?:^|[\s\W\d])<forma_escapata>(?:[\s\W]|$): la forma è in mezzo
            m = re.match(r"\(\?\:\^\|\[\\s\\W\\d\]\)(.+)\(\?\:\[\\s\\W\]\|\$\)", pattern.pattern)
            assert m, f"pattern inatteso: {pattern.pattern}"
            forma = re.sub(r"\\(.)", r"\1", m.group(1))
            assert len(forma) >= 6, f"forma collassata corta nel dizionario: {forma!r}"


class TestGroundTruthCompleto:
    def test_include_manuale_e_user_e_deduplica(self):
        import scripts.ab_test_modello_categorizzazione as ab

        def _query(rows):
            q = MagicMock()
            q.select.return_value = q
            q.like.return_value = q
            q.eq.return_value = q
            q.execute.return_value = SimpleNamespace(data=rows)
            return q

        chiamate = []

        def _table(_name):
            q = _query([])
            def _like(col, pat):
                chiamate.append(("like", pat))
                q.execute.return_value = SimpleNamespace(data=[
                    {"descrizione": "POLLO KG1", "categoria": "CARNE", "classificato_da": "Manuale (a@b.it)"},
                    {"descrizione": "DOPPIO", "categoria": "CARNE", "classificato_da": "Manuale (a@b.it)"},
                ])
                return q
            def _eq(col, val):
                chiamate.append(("eq", val))
                q.execute.return_value = SimpleNamespace(data=[
                    {"descrizione": "COCA COLA", "categoria": "BEVANDE", "classificato_da": "User"},
                    {"descrizione": "DOPPIO", "categoria": "BEVANDE", "classificato_da": "User"},
                ])
                return q
            q.like.side_effect = _like
            q.eq.side_effect = _eq
            return q

        sb = MagicMock()
        sb.table.side_effect = _table

        import unittest.mock as um
        with um.patch.object(ab, "get_supabase_client", return_value=sb):
            casi = ab.carica_ground_truth()

        descs = [d for d, _ in casi]
        assert "POLLO KG1" in descs, "le correzioni 'Manuale (email)' sono sparite dal campione"
        assert "COCA COLA" in descs, "le correzioni legacy 'User' restano fuori dal ground truth (D10)"
        assert descs.count("DOPPIO") == 1, "descrizione presente in entrambe le grafie: va deduplicata"
        assert ("eq", "User") in chiamate
