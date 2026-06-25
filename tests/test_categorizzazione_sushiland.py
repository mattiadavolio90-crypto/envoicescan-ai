"""Regole di categorizzazione derivate dalla certificazione SUSHILAND (25/06/2026).

Blinda i pattern di errore reali trovati su MARIANO: ogni caso qui è un prodotto
vero estratto dalle fatture, con la categoria corretta verificata su documento
(fornitore + descrizione + UM + IVA). Se una regola regredisce, questi test rompono.

Si testa la pipeline reale `categorizza_con_memoria` (fornitore→UM→keyword), non
solo il dizionario, perché l'ordine di precedenza è parte della correttezza.
"""
import pytest

from services.ai_service import categorizza_con_memoria


# (descrizione, fornitore, um, iva, categoria_attesa)
CASI = [
    # --- Fornitori mono-categoria (regola FORNITORE) ---
    ("POMPA SOMMERSA PEDROLLO 370W TOP 2 F", "BRICOMAN ITALIA S.R.L. SOCIETA' A SOCIO UNICO", "PZ", 22, "MANUTENZIONE E ATTREZZATURE"),
    ("NASTRO ISOLANTE BM NERO 19X0,15 MM 25", "BRICOMAN ITALIA S.R.L. SOCIETA' A SOCIO UNICO", "PZ", 22, "MANUTENZIONE E ATTREZZATURE"),
    ("RETE METALL.PLASTIF.RECINT-PLAST 1 X25", "CIESSECI SPA", "PZ", 22, "MANUTENZIONE E ATTREZZATURE"),
    ("RETE STIRATA ART. STIRATAN15 RETE STIRATA FERRO GREZZO", "PARAMIDANI S.R.L", "N.", 22, "MANUTENZIONE E ATTREZZATURE"),
    ("PACK MINUTI ILLIMITATI GIUGNO 2026", "HAL SERVICE SPA", "NR", 22, "UTENZE E LOCALI"),
    ("AGGIORNAMENTO SITO WEB CON REGOLAMENTO CARD", "TAURUSLAB SRL", "PZ", 22, "SERVIZI E CONSULENZE"),
    # --- Gestore acqua (FORNITORI_UTENZE_SEMPRE) ---
    ("ONERI PEREQUAZIONE", "COMO ACQUA S.R.L", "NR", 10, "UTENZE E LOCALI"),
    # --- Noodle/pasta asiatici (keyword) ---
    ("VERMICELLI DI SOIA 50X100GX5", "H.D. ITALIA S.R.L", "PZ", 10, "PASTA E CEREALI"),
    ("WAIWAI VERMICELLI DI RISO GROS 400G/30", "SHIDU INTERNATIONAL SRL", "PZ", 10, "PASTA E CEREALI"),
    ("QZSP SOBA SPAGHETTI SARACENO 300G/24", "SHIDU INTERNATIONAL SRL", "PZ", 10, "PASTA E CEREALI"),
    ("PASTA DI RISO 16CM 400GX50PZ", "H.D. ITALIA S.R.L", "PZ", 10, "PASTA E CEREALI"),
    # --- Salse asiatiche scambiate per bevande ---
    ("MIZKAN PONZU SUCCO DI AGRUMI 6X1,8LT", "H.D. ITALIA S.R.L", "PZ", 10, "SALSE E CREME"),
    # --- Gelati per gusto ---
    ("GELATO LIMONE LT.4,8", "FROZEN FOOD SRL", "PZ", 10, "GELATI E DESSERT"),
    # --- Esaltatori sapidità ---
    ("GLUTTAMATO MONOSODICO 1X25KG", "H.D. ITALIA S.R.L", "PZ", 22, "SPEZIE E AROMI"),
    # --- Pesce con nomenclatura specifica ---
    ("MITILI FRESCHE - - MYTILUS GALLOPROVINCIALIS ALLEVATO GRECIA", "LODI S.R.L", "KG", 10, "PESCE"),
    ("SCORFANO ATLANTICO 300/500 6KG", "ASIANTRADE SRL", "KG", 10, "PESCE"),
    # --- Pulizia/cancelleria ---
    ("TORK T9 IGIENICA MINI SMARTONE PZ.12", "BRESCIANINI E CO.SRL", "PZ", 22, "MATERIALE DI CONSUMO"),
]


@pytest.mark.parametrize("descrizione,fornitore,um,iva,attesa", CASI)
def test_categoria_corretta(descrizione, fornitore, um, iva, attesa):
    cat = categorizza_con_memoria(
        descrizione=descrizione,
        prezzo=10.0,
        quantita=1.0,
        user_id=None,
        supabase_client=None,
        fornitore=fornitore,
        unita_misura=um,
        iva_percentuale=float(iva),
    )
    assert cat == attesa, f"{descrizione!r} ({fornitore}) → {cat}, atteso {attesa}"


def test_lodi_philadelphia_resta_latticini():
    """Guardia anti-regressione: LODI NON è in CATEGORIA_PER_FORNITORE perché
    vende anche Philadelphia. Una regola-fornitore secca la trasformerebbe in PESCE."""
    cat = categorizza_con_memoria(
        descrizione="PHILADELPHIA PANETTO 1,65KG",
        prezzo=10.0, quantita=1.0, user_id=None, supabase_client=None,
        fornitore="LODI S.R.L", unita_misura="PZ", iva_percentuale=10.0,
    )
    assert cat != "PESCE", f"Philadelphia di LODI non deve diventare PESCE (era {cat})"
