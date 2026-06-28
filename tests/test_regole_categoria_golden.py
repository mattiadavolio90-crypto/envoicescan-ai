"""Golden test per applica_regole_categoria_forti.

Baseline catturata da ~2900 descrizioni reali del DB (8378 casi). Garantisce che
qualunque refactor della funzione NON cambi l'output su nessun caso reale.
Rigenerare SOLO se si vuole cambiare di proposito il comportamento delle regole:
    python -c "import json; ..."  (vedi storia git / _tmp_build_golden.py)

Rigenerato 26/06 (cert. SUSHILAND): nuove regole forti (stoviglie→MATERIALE,
voci-bolletta→UTENZE, fritti-jp TEMPURA/TAKOYAKI, pet-food→Da Classificare) e
rimozione rule-trap (SPUMILIA da PESCE, VIT troncato da MANUTENZIONE). Effetto netto:
-229 righe "Da Classificare", recupero ortofrutta/carne/stoviglie. Verificato a mano
che ogni transizione è un miglioramento o neutra, nessuna regressione.

Aggiornato 28/06 (cert. SUSHILAND, misura accuratezza): _VOCE_BOLLETTA_RE estesa con
sottovoci gergali di bolletta gas/acqua (SMC, COMP. RE/UGx/UCx, COMM. AL DETTAGLIO,
BONIFICA VILLORESI, CONSUMO FATTURATO) → UTENZE E LOCALI. Riconosce la voce dalla
terminologia tecnica, NON dal fornitore (zero rischio di trascinare prodotti di un
fornitore scambiato per utility). Effetto: 1 sola riga del golden cambiata.
"""
import json
import os

import pytest

from services.ai_service import applica_regole_categoria_forti

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_regole_categoria.json")

with open(_FIXTURE, encoding="utf-8") as f:
    _GOLDEN = json.load(f)


@pytest.mark.parametrize("desc,cat_in,cat_out,motivo", _GOLDEN)
def test_regole_categoria_invariate(desc, cat_in, cat_out, motivo):
    got_cat, got_motivo = applica_regole_categoria_forti(desc, cat_in)
    assert got_cat == cat_out, f"categoria cambiata per '{desc}' (input {cat_in})"
    assert got_motivo == motivo, f"motivo cambiato per '{desc}' (input {cat_in})"
