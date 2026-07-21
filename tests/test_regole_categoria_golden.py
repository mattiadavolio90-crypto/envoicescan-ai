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

Aggiornato 20/07 (cert. OFFSIDE, menù pub): regola "burger" come sotto-stringa
(ANGUSBURGER/CHEESEBURGER/... → CARNE) + eccezione pane (PANE BURGER, PANE MAXI
HAMBURGER, PANBURGER → PRODOTTI DA FORNO) + ALETTE/WINGS → CARNE. Effetto: 6 righe
cambiate su 8378, tutte miglioria o neutre — inclusa la CORREZIONE di "PANE MAXI
HAMBURGER" che la baseline classificava CARNE (era il pane, non la carne).

Aggiornato 20/07 (golive-certificatore su gen-mar): regole forti FILLET SOUTHERN
FRIED → CARNE e FISH & CHIPS → PESCE (era catturato da "CHIPS"→SHOP). Effetto: 2
righe, entrambe da Da Classificare a categoria corretta.

Aggiornato 21/07 (cert. OFFSIDE, documenti amministrativi): regole forti per 3
famiglie trasversali a tutti i clienti — LEASING/NOLEGGIO → SERVIZI E CONSULENZE,
CANONE + qualificatore-servizio pulito (SERVIZI/ASS/ISTRUTTORIA/LEASING, MAI
LOCAZIONE che resta UTENZE) → SERVIZI, abbigliamento/merchandising (felpa, t-shirt,
camicia, pantalone, grembiule…) → MANUTENZIONE E ATTREZZATURE. Effetto: 6 righe, tutte
da Da Classificare a categoria corretta. Audit anti-collisione: 0 override su 23.704
righe food/bevande già categorizzate su tutti i clienti reali.

Aggiornato 21/07 (cert. SUSHILAND Vimodrone/San Giuliano): SAKE distinto per
formato/uso — da bere (bottiglia) → DISTILLATI, da cucina ("PER CUCINA"/tanica
18L) → SCATOLAME E CONSERVE. Prima lo stesso prodotto era sparso su 4 categorie
diverse (AMARI/LIQUORI, DISTILLATI, SERVIZI, SCATOLAME). Effetto: 3 righe golden,
tutte da Da Classificare a categoria corretta. Stesso commit: "PESCE <animale di
terra>" (es. "PESCE BOVINO S/V" = manzo) tolto da PESCE via _ECCEZIONI_REGOLE, e
"FILTRO OLIO" (ricambio officina) → MANUTENZIONE (non più rubato da keyword OLIO) —
questi due non erano nel campione golden, verificati a parte.
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
