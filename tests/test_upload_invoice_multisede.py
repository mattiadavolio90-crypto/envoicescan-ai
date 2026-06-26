"""Decisione di destinazione dell'upload manuale (guardia P.IVA + smistamento).

Testa decidi_destinazione_upload (services/multisede_routing.py), la funzione pura
che l'endpoint /api/upload/invoice usa per decidere su quale sede salvare una
fattura. Copre lo scenario reale che ha motivato la fix (SUSHILAND: 7/10 fatture
finite sulla sede sbagliata) e la compatibilita' con OFFSIDE (stessa P.IVA).
"""
from services.multisede_routing import decidi_destinazione_upload, _piva_norm

# Sedi SUSHILAND reali (P.IVA diverse per sede).
SG = "12557550964"   # San Giuliano
VG = "12222020963"   # Villa Guardia
MA = "04140610132"   # Mariano
SUSHILAND = [
    {"id": "sg", "nome_ristorante": "SAN GIULIANO", "partita_iva": SG, "indirizzo_match": "via roma 1 milano"},
    {"id": "vg", "nome_ristorante": "VILLA GUARDIA", "partita_iva": VG, "indirizzo_match": "via como 2 villa guardia"},
    {"id": "ma", "nome_ristorante": "MARIANO", "partita_iva": MA, "indirizzo_match": "via brera 3 mariano comense"},
]

# Sedi OFFSIDE (STESSA P.IVA, indirizzi diversi).
OFF = "07863990961"
OFFSIDE = [
    {"id": "pub", "nome_ristorante": "OFFSIDE SPORTS PUB", "partita_iva": OFF, "indirizzo_match": "via losanna 46 20154 milano"},
    {"id": "ov", "nome_ristorante": "OVERTIME", "partita_iva": OFF, "indirizzo_match": "via luigi settembrini 36 20124 milano"},
]


# ─── _piva_norm ───────────────────────────────────────────────────────────────

def test_piva_norm_pulisce():
    assert _piva_norm(" 1255 7550964 ") == "12557550964"
    assert _piva_norm("IT12557550964") == "12557550964"
    assert _piva_norm(None) == ""


# ─── SUSHILAND: smistamento per P.IVA (1 match) ───────────────────────────────

def test_sushiland_fattura_villaguardia_su_sangiuliano_va_a_villaguardia():
    # Sto su San Giuliano ma carico una fattura di Villa Guardia: deve andare a VG.
    d = decidi_destinazione_upload(VG, "via como 2 villa guardia", SUSHILAND, sede_attiva_id="sg")
    assert d["mode"] == "auto"
    assert d["ristorante_id"] == "vg"
    assert d["cross_sede"] is True   # diversa dalla sede attiva (sg) -> evidenziata


def test_sushiland_fattura_propria_sede_non_cross():
    d = decidi_destinazione_upload(SG, "via roma 1 milano", SUSHILAND, sede_attiva_id="sg")
    assert d["mode"] == "auto"
    assert d["ristorante_id"] == "sg"
    assert d["cross_sede"] is False


# ─── Guardia: P.IVA non di nessuna sede -> scartata ───────────────────────────

def test_piva_estranea_scartata():
    d = decidi_destinazione_upload("99999999999", "via x", SUSHILAND, sede_attiva_id="sg")
    assert d["mode"] == "piva_estranea"
    assert "ristorante_id" not in d


# ─── P.IVA destinatario assente -> fallback sede attiva ───────────────────────

def test_piva_assente_fallback_sede_attiva():
    d = decidi_destinazione_upload(None, None, SUSHILAND, sede_attiva_id="sg")
    assert d["mode"] == "fallback"
    assert d["ristorante_id"] == "sg"


# ─── OFFSIDE: stessa P.IVA -> distingue per indirizzo (>=2 match) ──────────────

def test_offside_due_sedi_stessa_piva_smista_per_indirizzo():
    d = decidi_destinazione_upload(OFF, "Via Losanna 46 20154 Milano", OFFSIDE, sede_attiva_id="ov")
    assert d["mode"] == "auto"
    assert d["ristorante_id"] == "pub"
    assert d["cross_sede"] is True   # stavo su OVERTIME, va al PUB


def test_offside_stessa_piva_indirizzo_ambiguo_scartata():
    # Indirizzo generico che non distingue le due sedi OFFSIDE.
    d = decidi_destinazione_upload(OFF, "Via Mazzini 1 Milano", OFFSIDE, sede_attiva_id="pub")
    assert d["mode"] == "ambiguo"


# ─── Mono-sede: comportamento invariato (protetto) ────────────────────────────

def test_monosede_fattura_propria_va_alla_sede():
    sedi = [{"id": "only", "nome_ristorante": "UNICA", "partita_iva": SG, "indirizzo_match": "via x"}]
    d = decidi_destinazione_upload(SG, "via x", sedi, sede_attiva_id="only")
    assert d["mode"] == "auto"
    assert d["ristorante_id"] == "only"
    assert d["cross_sede"] is False


def test_monosede_fattura_di_terzi_scartata():
    # Cliente mono-sede a cui arriva (per errore) una fattura di un'altra azienda.
    sedi = [{"id": "only", "nome_ristorante": "UNICA", "partita_iva": SG, "indirizzo_match": "via x"}]
    d = decidi_destinazione_upload("11111111111", "via y", sedi, sede_attiva_id="only")
    assert d["mode"] == "piva_estranea"
