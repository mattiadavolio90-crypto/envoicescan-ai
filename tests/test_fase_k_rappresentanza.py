"""Fase K2 (10/10/2026): riconoscere da sola la RAPPRESENTANZA.

Decisione di Mattia: un pasto consumato in un altro locale e' RAPPRESENTANZA, e se
la fattura e' di un locale dove si e' mangiato (c'e' la riga del coperto) ci va
TUTTA — pizza e birra comprese, che riga per riga sembrerebbero materia prima e
gonfierebbero il food cost (RISTORANTE MONOPOLI, misurato il 10/10: 26 righe in
9 categorie diverse).

Le regole sono strette apposta e misurate sulle 7.173 descrizioni reali del DB:
prendono "COPERTO", "4 PASTI COMPLETI", "MENU FISSO" e nient'altro.
"""
import io
from unittest.mock import MagicMock, patch

import pytest

import services.ai_service as ai_mod


@pytest.mark.parametrize("descrizione", [
    "COPERTO",
    "COPERTI",
    "N.4 COPERTI",
    "4 COPERTI",
    "COPERTO X 4",
    "SERVIZIO E COPERTO",
    "COPERTO E SERVIZIO",
    "4 PASTI COMPLETI",
    "PASTO COMPLETO",
    "PRANZO DI LAVORO",
    "CENA AZIENDALE",
    "SPESE DI RAPPRESENTANZA",
    "MENU FISSO",
    "MENU DEL GIORNO",
])
def test_un_pasto_consumato_fuori_e_rappresentanza(descrizione):
    categoria, _motivo, _conf = ai_mod.decisione_deterministica(descrizione)
    assert categoria == "RAPPRESENTANZA", descrizione


@pytest.mark.parametrize("descrizione", [
    # misurati a DB il 10/10: tipografia dei menu e pasta per ravioli
    "STAMPA 10 PZ. MENU PRANZO FERIALI - 64 FACCIATE - 20X28 CM",
    "REALIZZAZIONE FOTOGRAFIE IMPAGINAZIONE MENU CENA MENU PRANZO FESTIVO",
    "PASTO DI RAVIOLI 30X300G",
    "PASTO DI GRANO(215MM)GRANDE 20X550G",
    # il menu servito e' la riga intera: dentro un'altra riga e' carta o una lavagna
    "STAMPA 50 MENU FISSO A5",
    "LAVAGNA MENU DEL GIORNO",
    # "coperto" come aggettivo
    "PARCHEGGIO COPERTO",
    "GAZEBO COPERTO 3X3",
    "TELO COPERTURA PISCINA",
    # la riga coperto e' la riga INTERA: "COPERTONE" e' un pneumatico
    "COPERTONE 195/65 R15",
])
def test_non_ogni_coperto_o_menu_e_un_pasto(descrizione):
    categoria, _motivo, _conf = ai_mod.decisione_deterministica(descrizione)
    assert categoria != "RAPPRESENTANZA", descrizione


def test_e_riga_coperto_vuole_la_riga_intera():
    assert ai_mod.e_riga_coperto("  coperto ")
    assert ai_mod.e_riga_coperto("N.4 COPERTI")
    assert not ai_mod.e_riga_coperto("PARCHEGGIO COPERTO")
    assert not ai_mod.e_riga_coperto(None)


# ── il guardrail dell'IVA bassa ──────────────────────────────────────────────

def test_il_pasto_al_dieci_per_cento_resta_rappresentanza():
    """Un pasto servito si fattura al 10%: per RAPPRESENTANZA non e' un indizio di
    cibo da cucina, e la riga non deve tornare nel food cost."""
    out = ai_mod._applica_guardrail_iva_bassa_spese_generali(
        "SPAGHETTI VONGOLE", "RAPPRESENTANZA", iva_percentuale=10,
    )
    assert out == "RAPPRESENTANZA"


def test_il_guardrail_resta_acceso_sulle_altre_spese_generali():
    """Contro-prova: senza questa il test sopra passerebbe anche con un
    guardrail spento per tutti."""
    out = ai_mod._applica_guardrail_iva_bassa_spese_generali(
        "SPAGHETTI VONGOLE", "SERVIZI E CONSULENZE", iva_percentuale=10,
    )
    assert out == "PESCE"


# ── la fattura col coperto, tutta ───────────────────────────────────────────

def _riga(descrizione, categoria, totale, **extra):
    return {"Descrizione": descrizione, "Categoria": categoria, "Totale_Riga": totale,
            "categoria_fonte": "L4_dizionario", "categoria_fiducia": "probabile",
            "needs_review": True, **extra}


def _pranzo_monopoli():
    return [
        _riga("COPERTO", "RAPPRESENTANZA", 40.91, categoria_fonte="L1_5_regola"),
        _riga("PIZZA", "PRODOTTI DA FORNO", 9.09),
        _riga("SPAGHETTI VONGOLE", "PESCE", 14.54),
        _riga("BIRRA SPINA MEDIA", "BIRRE", 5.46),
        _riga("BIBITE", "Da Classificare", 8.18),
        _riga("OMAGGIO CAFFE", "📝 NOTE E DICITURE", 0.0),
    ]


def test_la_fattura_col_coperto_va_tutta_in_rappresentanza():
    righe = _pranzo_monopoli()
    spostate = ai_mod.applica_regola_documento_pasto(righe)

    assert spostate == 4
    per_desc = {r["Descrizione"]: r for r in righe}
    for desc in ("PIZZA", "SPAGHETTI VONGOLE", "BIRRA SPINA MEDIA", "BIBITE"):
        r = per_desc[desc]
        assert r["Categoria"] == "RAPPRESENTANZA", desc
        assert r["categoria_fonte"] == "L0_documento_pasto", desc
        assert r["categoria_fiducia"] == "certa", desc
        assert r["needs_review"] is False, desc
    # la riga a importo zero resta com'era
    assert per_desc["OMAGGIO CAFFE"]["Categoria"] == "📝 NOTE E DICITURE"
    # il coperto era gia' RAPPRESENTANZA: la sua fonte non si riscrive
    assert per_desc["COPERTO"]["categoria_fonte"] == "L1_5_regola"


def test_anche_lo_sconto_della_fattura_col_coperto_va_in_rappresentanza():
    """Una riga negativa (sconto, abbuono) di quella fattura riduce la spesa del
    pasto: restando nel food abbasserebbe il food cost di un pasto mai comprato."""
    righe = _pranzo_monopoli() + [_riga("SCONTO CLIENTE", "PRODOTTI DA FORNO", -5.0)]
    ai_mod.applica_regola_documento_pasto(righe)
    assert righe[-1]["Categoria"] == "RAPPRESENTANZA"


def test_senza_il_coperto_la_fattura_resta_com_era():
    righe = [r for r in _pranzo_monopoli() if r["Descrizione"] != "COPERTO"]
    prima = [dict(r) for r in righe]
    assert ai_mod.applica_regola_documento_pasto(righe) == 0
    assert righe == prima


def test_un_coperto_aggettivo_non_sposta_la_fattura():
    righe = [_riga("PARCHEGGIO COPERTO", "UTENZE E LOCALI", 50.0),
             _riga("PIZZA", "PRODOTTI DA FORNO", 9.09)]
    assert ai_mod.applica_regola_documento_pasto(righe) == 0
    assert righe[1]["Categoria"] == "PRODOTTI DA FORNO"


# ── nel parser vero ──────────────────────────────────────────────────────────

def _xml(righe):
    linee = "".join(
        f"""
      <DettaglioLinee>
        <NumeroLinea>{i}</NumeroLinea>
        <Descrizione>{desc}</Descrizione>
        <Quantita>1</Quantita>
        <PrezzoUnitario>{importo:.2f}</PrezzoUnitario>
        <PrezzoTotale>{importo:.2f}</PrezzoTotale>
        <AliquotaIVA>10.00</AliquotaIVA>
      </DettaglioLinee>"""
        for i, (desc, importo) in enumerate(righe, start=1)
    )
    totale = sum(importo for _d, importo in righe)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <Anagrafica><Denominazione>RISTORANTE DI PROVA SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento>
        <Data>2026-09-15</Data>
        <Numero>R12</Numero>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>{linee}
      <DatiRiepilogo>
        <AliquotaIVA>10.00</AliquotaIVA>
        <ImponibileImporto>{totale:.2f}</ImponibileImporto>
        <Imposta>{totale / 10:.2f}</Imposta>
      </DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode("utf-8")


_PER_RIGA = {"COPERTO": "RAPPRESENTANZA", "PIZZA": "PRODOTTI DA FORNO", "BIRRA SPINA MEDIA": "BIRRE"}


def _estrai(xml_bytes):
    from services.invoice_service import estrai_dati_da_xml

    file_mock = io.BytesIO(xml_bytes)
    file_mock.name = "pranzo.xml"
    mock_st = MagicMock()
    mock_st.session_state.get = lambda k, d=None: {"id": "user_test"} if k == "user_data" else d
    with patch("services.invoice_service.st", mock_st), \
         patch("services.ai_service.carica_memoria_completa", return_value=None), \
         patch("services.ai_service.categorizza_con_memoria",
               side_effect=lambda descrizione, **_k: (_PER_RIGA[descrizione], False)):
        return estrai_dati_da_xml(file_mock, user_id="user_test")


def test_il_parser_mette_in_rappresentanza_la_fattura_del_pranzo():
    righe = _estrai(_xml([("COPERTO", 40.91), ("PIZZA", 9.09), ("BIRRA SPINA MEDIA", 5.46)]))
    assert {r["Descrizione"]: r["Categoria"] for r in righe} == {
        "COPERTO": "RAPPRESENTANZA",
        "PIZZA": "RAPPRESENTANZA",
        "BIRRA SPINA MEDIA": "RAPPRESENTANZA",
    }


def test_il_parser_lascia_la_pizza_comprata_dal_fornitore():
    """Contro-prova: senza coperto la stessa pizza e' merce di un fornitore."""
    righe = _estrai(_xml([("PIZZA", 9.09), ("BIRRA SPINA MEDIA", 5.46)]))
    assert {r["Descrizione"]: r["Categoria"] for r in righe} == {
        "PIZZA": "PRODOTTI DA FORNO",
        "BIRRA SPINA MEDIA": "BIRRE",
    }


def test_il_pasto_batte_la_scelta_fatta_prima_che_la_categoria_esistesse():
    """OFFSIDE aveva messo a mano "MENU FISSO" in SERVIZI E CONSULENZE, quando
    RAPPRESENTANZA non c'era: la regola e' non negoziabile, o lo storico (spostato
    dallo script) e le fatture nuove (decise dalla memoria) si spaccherebbero."""
    from types import SimpleNamespace

    def _q(dati):
        q = MagicMock()
        for m in ["select", "eq", "neq", "gte", "lte", "is_", "order", "range", "or_", "in_", "limit"]:
            getattr(q, m).return_value = q
        q.execute.return_value = SimpleNamespace(data=dati)
        return q

    ai_mod.invalida_cache_memoria()
    try:
        sb = MagicMock()
        voci = [{"descrizione": "MENU FISSO", "categoria": "SERVIZI E CONSULENZE"}]
        sb.table.side_effect = lambda nome: _q(voci if nome == "prodotti_utente" else [])
        ai_mod.carica_memoria_completa("user-k", supabase_client=sb)
        categoria = ai_mod.categorizza_con_memoria(
            descrizione="MENU FISSO", prezzo=33.0, quantita=1, user_id="user-k",
            supabase_client=sb, pending_local_saves=[],
        )
    finally:
        ai_mod.invalida_cache_memoria()
    assert categoria == "RAPPRESENTANZA"


def test_la_fonte_della_fattura_col_coperto_e_certa():
    """Se un percorso ricalcola la fiducia dalla fonte, deve ritrovare `certa`:
    una fonte sconosciuta vale `da_verificare` e la riga uscirebbe dai margini."""
    assert ai_mod.valuta_fiducia("L0_documento_pasto", "RAPPRESENTANZA", "PIZZA") == "certa"
