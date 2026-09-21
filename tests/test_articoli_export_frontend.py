"""Test dell'export Excel del tab Articoli (`lib/articoli-export.ts`).

Eseguono il TypeScript vero via node (`helpers_ts.esegui_ts`): `apps/web/` non
ha un runner proprio per scelta strutturale — `deploy-vercel.yml` si attiva su
`apps/web/**`, quindi un runner li' farebbe deployare la produzione a ogni
merge di test.

Cosa misurano: le celle che il cliente apre in Excel. Gli assert sono su
stringhe e oggetti INTERI, non su "contiene": un'intestazione sbagliata in modo
coerente passerebbe un assert di coerenza interna.

Il foglio 1 e' quello che esisteva prima dei due fogli: i suoi test sono una
rete di non-regressione: chi usava l'export per il riepilogo deve ritrovare le
stesse 11 colonne, con gli stessi accenti e lo stesso ordine.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/articoli-export"

# `richiede` del prologo condiviso controlla `typeof m[nome] === "function"`:
# ci vanno le sole funzioni. Le esportazioni che sono VALORI (le due liste di
# intestazioni, i due nomi foglio) sarebbero un falso negativo silenzioso — una
# rinomina le farebbe arrivare `undefined` senza che il prologo se ne accorga —
# quindi la loro esistenza la presidia test_esportazioni_valore_presenti.
FUNZIONI = ["rigaExportArticolo", "rigaExportDettaglio", "nomeFileArticoli"]

VALORI = ["headerArticoli", "headerDettaglio", "FOGLIO_ARTICOLI", "FOGLIO_DETTAGLIO"]


def _esegui(espressione, argomento=None):
    return esegui_ts(MODULO, espressione, argomento=argomento, richiede=FUNZIONI)


def test_esportazioni_valore_presenti():
    """Le esportazioni che non sono funzioni sfuggono al controllo di `richiede`.
    Senza questo test una rinomina di `headerDettaglio` non fallirebbe qui: il
    modulo restituirebbe `undefined` e il foglio uscirebbe con le colonne in
    ordine di inserimento, che e' proprio cio' che l'header esplicito evita."""
    presenti = _esegui("emit(input.map((n) => typeof m[n] !== \"undefined\"));", VALORI)
    assert presenti == [True] * len(VALORI), dict(zip(VALORI, presenti))


def _articolo(**kw):
    base = {
        "descrizione": "POMODORO PELATO", "categoria": "ORTOFRUTTA",
        "fornitore_principale": "ORTOFRUTTA SRL", "altri_fornitori": ["MERCATO SPA"],
        "ultimo_acquisto": "2026-09-17", "quantita_totale": 240.0,
        "unita_misura": "KG", "prezzo_unit_medio": 1.2,
        "prezzo_unit_trend_pct": -3.5, "totale_speso": 288.0, "num_acquisti": 3,
        "righe_ids": [1, 2, 3], "needs_review": False, "is_nuovo": False,
    }
    base.update(kw)
    return base


def _riga(**kw):
    base = {
        "id": 1, "file_origine": "IT123_001.xml", "numero_riga": 4,
        "data_documento": "2026-09-03", "fornitore": "ORTOFRUTTA SRL",
        "descrizione": "POMODORO PELATO", "quantita": 80.0, "unita_misura": "KG",
        "prezzo_unitario": 1.2, "totale_riga": 96.0, "categoria": "ORTOFRUTTA",
        "needs_review": False, "tipo_documento": "TD01",
        "data_competenza": "2026-09-03", "piva_cedente": "IT00000000000",
        "created_at": "2026-09-03T10:00:00Z", "numero_documento": "1204",
        "ripartita_su_gruppo": False,
    }
    base.update(kw)
    return base


# ─── Foglio 1: il riepilogo, invariato ──────────────────────────────────────

def test_riga_articolo_oggetto_completo_con_chiavi_esatte():
    """Le chiavi sono intestazioni di colonna: l'accento, il simbolo e lo spazio
    contano. Sono le stesse dell'export a foglio singolo di prima."""
    r = _esegui("emit(m.rigaExportArticolo(input));", _articolo())
    assert r == {
        "Descrizione": "POMODORO PELATO",
        "Categoria": "ORTOFRUTTA",
        "Fornitore": "ORTOFRUTTA SRL",
        "Altri fornitori": "MERCATO SPA",
        "Ultimo acquisto": "2026-09-17",
        "Quantità": 240.0,
        "UM": "KG",
        "€ medio": 1.2,
        "Trend prezzo %": -3.5,
        "Totale speso": 288.0,
        "N° acquisti": 3,
    }


def test_riga_articolo_piu_fornitori_separati_da_punto_e_virgola():
    r = _esegui(
        "emit(m.rigaExportArticolo(input));",
        _articolo(altri_fornitori=["A SRL", "B SPA"]),
    )
    assert r["Altri fornitori"] == "A SRL; B SPA"


def test_riga_articolo_campi_nulli_diventano_celle_vuote():
    """Un `null` serializzato come "null" in una cella e' un dato falso."""
    r = _esegui(
        "emit(m.rigaExportArticolo(input));",
        _articolo(categoria=None, ultimo_acquisto=None, unita_misura=None,
                  prezzo_unit_medio=None, prezzo_unit_trend_pct=None),
    )
    assert r["Categoria"] == ""
    assert r["Ultimo acquisto"] == ""
    assert r["UM"] == ""
    assert r["€ medio"] == ""
    assert r["Trend prezzo %"] == ""


def test_header_articoli_ordine_esatto():
    assert _esegui("emit(m.headerArticoli);") == [
        "Descrizione", "Categoria", "Fornitore", "Altri fornitori",
        "Ultimo acquisto", "Quantità", "UM", "€ medio", "Trend prezzo %",
        "Totale speso", "N° acquisti",
    ]


def test_header_articoli_copre_esattamente_le_chiavi_della_riga():
    """Una colonna in `header` che nessuna riga valorizza esce vuota; una chiave
    non elencata in `header` non esce affatto. Le due liste devono coincidere."""
    chiavi = _esegui("emit(Object.keys(m.rigaExportArticolo(input)));", _articolo())
    assert chiavi == _esegui("emit(m.headerArticoli);")


# ─── Foglio 2: il dettaglio riga per riga ───────────────────────────────────

def test_riga_dettaglio_oggetto_completo_con_chiavi_esatte():
    r = _esegui("emit(m.rigaExportDettaglio(input));", _riga())
    assert r == {
        "Data documento": "2026-09-03",
        "N° documento": "1204",
        "Fornitore": "ORTOFRUTTA SRL",
        "Descrizione": "POMODORO PELATO",
        "Categoria": "ORTOFRUTTA",
        "Quantità": 80.0,
        "UM": "KG",
        "Prezzo unitario": 1.2,
        "Totale riga": 96.0,
        "Da classificare": "No",
        "Quota di gruppo": "No",
    }


def test_nota_di_credito_esce_col_segno_negativo():
    """Regola di dominio: le note di credito non si scartano e non si portano in
    valore assoluto. Un export che le perde falsa il totale del periodo."""
    r = _esegui("emit(m.rigaExportDettaglio(input));", _riga(totale_riga=-96.0))
    assert r["Totale riga"] == -96.0


def test_needs_review_diventa_si_leggibile():
    """A schermo il cliente legge "Da classificare": la cella usa la stessa parola."""
    r = _esegui("emit(m.rigaExportDettaglio(input));", _riga(needs_review=True))
    assert r["Da classificare"] == "Sì"


def test_quota_di_gruppo_marcata():
    """Una quota proiettata da un documento di struttura non e' una riga di
    fattura del punto vendita: chi legge il foglio deve poterle distinguere."""
    r = _esegui("emit(m.rigaExportDettaglio(input));", _riga(ripartita_su_gruppo=True))
    assert r["Quota di gruppo"] == "Sì"


def test_riga_dettaglio_campi_nulli_diventano_celle_vuote():
    r = _esegui(
        "emit(m.rigaExportDettaglio(input));",
        _riga(data_documento=None, numero_documento=None, categoria=None,
              quantita=None, unita_misura=None, prezzo_unitario=None,
              totale_riga=None),
    )
    assert r["Data documento"] == ""
    assert r["N° documento"] == ""
    assert r["Categoria"] == ""
    assert r["Quantità"] == ""
    assert r["Prezzo unitario"] == ""
    assert r["Totale riga"] == ""


def test_zero_non_diventa_cella_vuota():
    """`?? ""` e non `|| ""`: uno 0 e' un dato, non un'assenza. Una quantita' 0 o
    un importo 0 (omaggio, dicitura) devono restare leggibili come zero."""
    r = _esegui(
        "emit(m.rigaExportDettaglio(input));",
        _riga(quantita=0, prezzo_unitario=0, totale_riga=0),
    )
    assert r["Quantità"] == 0
    assert r["Prezzo unitario"] == 0
    assert r["Totale riga"] == 0


def test_header_dettaglio_ordine_esatto():
    assert _esegui("emit(m.headerDettaglio);") == [
        "Data documento", "N° documento", "Fornitore", "Descrizione",
        "Categoria", "Quantità", "UM", "Prezzo unitario", "Totale riga",
        "Da classificare", "Quota di gruppo",
    ]


def test_header_dettaglio_copre_esattamente_le_chiavi_della_riga():
    chiavi = _esegui("emit(Object.keys(m.rigaExportDettaglio(input)));", _riga())
    assert chiavi == _esegui("emit(m.headerDettaglio);")


# ─── Nomi di foglio e di file ───────────────────────────────────────────────

def test_nomi_dei_due_fogli():
    """Sono cio' che il cliente vede nelle linguette in fondo a Excel."""
    assert _esegui("emit(m.FOGLIO_ARTICOLI);") == "Articoli"
    assert _esegui("emit(m.FOGLIO_DETTAGLIO);") == "Dettaglio righe"


def test_nomi_dei_fogli_entro_il_limite_di_excel():
    """Excel tronca (e in certi casi rifiuta) i nomi foglio oltre 31 caratteri."""
    for nome in ("FOGLIO_ARTICOLI", "FOGLIO_DETTAGLIO"):
        assert len(_esegui(f"emit(m.{nome});")) <= 31


def test_nome_file_invariato_rispetto_al_foglio_singolo():
    """Chi ha una cartella o un automatismo che cerca questo nome non deve
    accorgersi del secondo foglio."""
    nome = _esegui("emit(m.nomeFileArticoli(new Date('2026-09-21T14:30:00Z')));")
    assert nome == "articoli_2026-09-21.xlsx"
