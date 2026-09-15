"""Un importo non finito non deve entrare nei dati del cliente (L7, 15/09/2026).

FatturaPA avversaria: `<PrezzoTotale>nan</PrezzoTotale>`. `float("nan")` e
`float("inf")` sono conversioni VALIDE in Python, quindi i due `_to_float_safe`
del progetto (`invoice_service` e il gemello in `documenti_service`) li
lasciavano passare fino alla riga scritta a DB.

**Cosa succede DAVVERO oggi** (la prima stesura di questo file diceva «il NaN
arriva fino in pagina»: falso, e l'ha smentito un agente refutatore). `httpx`
serializza il body con `allow_nan=False`, quindi via PostgREST un NaN non
raggiunge mai Postgres: solleva `ValueError` *durante* l'upsert del chunk da 500
righe, e una fattura piu' lunga resta **scritta a meta'**. Sul DB live il
15/09/2026: **0 righe** con NaN/Infinity su 39.660.

**Perche' la guardia sta comunque a monte**: il DB non farebbe da rete. Misurato
su Postgres vero (vedi `test_nan_attraversa_il_db_e_i_margini`):

* `numeric(10,2)` **accetta** NaN (rifiuta invece `inf`: overflow);
* `SUM()`/`AVG()` lo **propagano**: un NaN su 3 righe rende NaN il food cost
  dell'intero mese — non un numero sbagliato, un numero inutilizzabile;
* in Postgres **`NaN > qualunque numero` e' vero**, quindi la riga supera anche
  i filtri di soglia e si mette in cima agli ordinamenti per spesa;
* a valle `formatEuro` non ha la guardia che `formatPct` ha (`isFinite` -> "—"):
  il cliente leggerebbe **"NaN €"** nel KPI.

Basta un client che non passi da httpx (SQL diretto, psycopg, una RPC) perche'
il danno diventi quello.

`_to_int_safe` aveva in piu' un difetto suo: `int(float("inf"))` solleva
`OverflowError`, che il suo `except (TypeError, ValueError)` NON cattura — un
helper "safe" che esplode invece di tornare il default.
"""
from __future__ import annotations

import io
import math
import uuid

import pytest

from services import documenti_service
from services import invoice_service

NON_FINITI = ["nan", "NaN", "  nan  ", "inf", "-inf", "Infinity", "1e400", "-1e400"]

# Valori legittimi che NON devono cambiare comportamento: il formato it-IT con la
# virgola decimale e i negativi delle note di credito sono il traffico normale.
LEGITTIMI = [
    ("2,5", 2.5),
    ("1.234,56", 1234.56),
    ("10.00", 10.0),
    ("-15.00", -15.0),
    ("0", 0.0),
    ("999999.99", 999999.99),
]


@pytest.mark.parametrize("testo", NON_FINITI)
@pytest.mark.parametrize(
    "helper",
    [invoice_service._to_float_safe, documenti_service._to_float_safe],
    ids=["invoice_service", "documenti_service"],
)
def test_un_importo_non_finito_non_diventa_un_float(helper, testo):
    """Entrambe le copie dell'helper, o il gemello resta il buco che era."""
    risultato = helper(testo)
    assert risultato is None or math.isfinite(risultato), (
        f"{helper.__module__}._to_float_safe({testo!r}) -> {risultato!r}: "
        "un valore non finito arriva ai campi soldi"
    )


@pytest.mark.parametrize("testo,atteso", LEGITTIMI)
@pytest.mark.parametrize(
    "helper",
    [invoice_service._to_float_safe, documenti_service._to_float_safe],
    ids=["invoice_service", "documenti_service"],
)
def test_gli_importi_veri_non_cambiano(helper, testo, atteso):
    """Controllo positivo: la guardia non deve mangiarsi il traffico normale.

    Divergenza NOTA e preesistente al fix (misurata il 15/09/2026, non
    introdotta qui): `invoice_service` toglie i punti delle migliaia prima di
    convertire, `documenti_service` no — su "1.234,56" quest'ultimo fa
    `"1.234.56"` -> `ValueError` -> `None`. Fuori dal perimetro L7, dichiarata
    nel verbale: qui il caso e' escluso esplicitamente per quella copia, cosi'
    se un domani venisse allineata il test lo dice invece di tacere.
    """
    risultato = helper(testo)
    if testo == "1.234,56" and helper is documenti_service._to_float_safe:
        assert risultato is None, (
            "documenti_service ora gestisce le migliaia it-IT: allinea questo test "
            "(e valuta di unificare le due copie dell'helper)"
        )
        return
    assert risultato is not None and math.isfinite(risultato)
    assert risultato == pytest.approx(atteso)


@pytest.mark.parametrize("testo", ["inf", "-inf", "1e400", "nan"])
@pytest.mark.parametrize(
    "helper",
    [invoice_service._to_int_safe, documenti_service._to_int_safe],
    ids=["invoice_service", "documenti_service"],
)
def test_int_safe_non_solleva_su_infinito(helper, testo):
    """`int(float('inf'))` -> OverflowError, non catturato dall'except originale."""
    assert helper(testo) is None


# I non finiti non arrivano solo come STRINGA. Il percorso Vision (scontrini PDF)
# legge la risposta dell'AI con `json.loads`, che accetta i letterali NUDI `NaN` e
# `Infinity` (estensione Python: `{"totale": NaN}` e' JSON valido) e produce un
# float non finito VERO. `_to_float_safe` aveva un ritorno anticipato per i valori
# gia' numerici che saltava la guardia, e `_to_int_safe` faceva `int(value)` nudo:
# ValueError su NaN, OverflowError su inf.
NON_FINITI_NATIVI = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("valore", NON_FINITI_NATIVI, ids=["nan", "inf", "-inf"])
def test_un_float_non_finito_gia_numerico_non_passa(valore):
    assert invoice_service._to_float_safe(valore, 0.0) == 0.0
    assert invoice_service._to_float_safe(valore) is None


@pytest.mark.parametrize("valore", NON_FINITI_NATIVI, ids=["nan", "inf", "-inf"])
def test_int_safe_non_solleva_su_float_non_finito(valore):
    """Prima: ValueError (NaN) / OverflowError (inf), fuori dall'except."""
    assert invoice_service._to_int_safe(valore, 0) == 0


def test_json_del_vision_produce_davvero_un_nan_nativo():
    """La premessa del caso sopra, verificata invece che supposta."""
    import json

    assert math.isnan(json.loads('{"totale": NaN}')["totale"])
    assert math.isinf(json.loads('{"totale": Infinity}')["totale"])


@pytest.mark.parametrize("campo", ["quantita", "prezzo_unitario", "totale"])
@pytest.mark.parametrize("valore", ["nan", float("nan"), "inf", float("inf")],
                         ids=["str-nan", "float-nan", "str-inf", "float-inf"])
def test_il_percorso_vision_non_emette_campi_non_finiti(campo, valore, monkeypatch):
    """Il percorso scontrino/PDF usava `float()` nudo su ogni campo numerico.

    Si esercita la funzione vera (`estrai_dati_da_scontrino_vision`) con la
    risposta del Vision gia' decodificata, senza chiamare l'AI.
    """
    riga = {"descrizione": "POMODORO PELATO", "quantita": 2, "prezzo_unitario": 1.5,
            "totale": 3.0, "unita_misura": "PZ", "iva": 10}
    riga[campo] = valore
    valori = invoice_service._numeri_riga_scontrino(riga)
    for nome, numero in valori.items():
        assert math.isfinite(numero), f"{campo}={valore!r} -> {nome}={numero!r} non finito"


TESTATA = """<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">
<FatturaElettronicaHeader>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>12345678901</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>FORNITORE TEST</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>98765432109</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>RISTORANTE TEST</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody>
<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>2026-09-01</Data>
<Numero>1</Numero><ImportoTotaleDocumento>100.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi>
<DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>POMODORO PELATO</Descrizione>
<Quantita>{QTA}</Quantita><PrezzoUnitario>{PREZZO}</PrezzoUnitario>
<PrezzoTotale>{TOTALE}</PrezzoTotale><AliquotaIVA>10.00</AliquotaIVA></DettaglioLinee>
<DatiRiepilogo><AliquotaIVA>10.00</AliquotaIVA><ImponibileImporto>100.00</ImponibileImporto><Imposta>10.00</Imposta></DatiRiepilogo>
</DatiBeniServizi>
</FatturaElettronicaBody>
</p:FatturaElettronica>"""


def _parsa(nome: str, qta: str, prezzo: str, totale: str):
    xml = TESTATA.replace("{QTA}", qta).replace("{PREZZO}", prezzo).replace("{TOTALE}", totale)
    finto_file = io.BytesIO(xml.encode("utf-8"))
    finto_file.name = f"{nome}.xml"
    return invoice_service.estrai_dati_da_xml(finto_file, user_id=None, settore="ristorazione")


@pytest.mark.parametrize(
    "nome,qta,prezzo,totale",
    [
        ("totale_nan", "10", "2.00", "nan"),
        ("totale_inf", "5", "10.00", "inf"),
        ("esponente_enorme", "1", "1.00", "1e400"),
        ("quantita_nan", "nan", "5.00", "50.00"),
    ],
)
def test_il_parser_vero_non_emette_campi_non_finiti(nome, qta, prezzo, totale):
    """Il parser di produzione su una FatturaPA ostile: nessun campo non finito.

    Non basta provare l'helper: quello che conta e' la riga che esce da
    `estrai_dati_da_xml`, che e' esattamente il dict che finisce nell'upsert.
    """
    righe = _parsa(nome, qta, prezzo, totale)
    assert righe, f"{nome}: il parser non ha prodotto righe, il caso non misura piu' nulla"
    for riga in righe:
        for campo in ("Totale_Riga", "Prezzo_Unitario", "Quantita"):
            valore = riga.get(campo)
            assert not isinstance(valore, float) or math.isfinite(valore), (
                f"{nome}: {campo}={valore!r} esce dal parser e finisce a DB"
            )


def test_una_fattura_normale_resta_intatta():
    """Controllo positivo sul parser: il fix non cambia una fattura sana."""
    righe = _parsa("sana", "10", "2.00", "20.00")
    assert righe, "il parser non legge piu' una fattura valida"
    riga = righe[0]
    assert riga["Totale_Riga"] == pytest.approx(20.0)
    assert riga["Quantita"] == pytest.approx(10.0)


@pytest.mark.sql
def test_nan_attraversa_il_db_e_i_margini(db_sql):
    """Perche' il fix sta a monte: a valle NON c'e' nessuna rete.

    Questo test NON prova il fix — documenta il danno che il fix evita, scrivendo
    il NaN direttamente in SQL (cioe' saltando il parser). Se un domani il DB
    rifiutasse NaN, o `costi_automatici_mensili` lo filtrasse, questo test
    diventa rosso e la guardia a monte si puo' rivalutare.
    """
    user_id = str(uuid.uuid4())
    ristorante_id = str(uuid.uuid4())
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, email, password_hash, nome_ristorante) VALUES (%s,%s,%s,%s)",
            (user_id, f"{user_id}@esempio.it", "x", "Test"),
        )
        cur.execute(
            "INSERT INTO ristoranti (id, user_id, nome_ristorante, partita_iva)"
            " VALUES (%s,%s,%s,%s)",
            (ristorante_id, user_id, "Test", "12345678901"),
        )
        for numero, totale in enumerate(["100.00", "50.00", "NaN"]):
            cur.execute(
                "INSERT INTO fatture (user_id, ristorante_id, file_origine, numero_riga,"
                " data_documento, fornitore, descrizione, quantita, prezzo_unitario,"
                " totale_riga, categoria)"
                " VALUES (%s,%s,'ostile.xml',%s,'2026-09-01','F','D',1,1,%s,'CARNE E SALUMI')",
                (user_id, ristorante_id, numero, totale),
            )

        cur.execute(
            "SELECT mese, food FROM costi_automatici_mensili(%s,%s,2026,%s,%s)",
            (user_id, ristorante_id, ["CARNE E SALUMI"], ["SERVIZI E CONSULENZE"]),
        )
        righe = cur.fetchall()
        assert righe, "la funzione dei costi non ha risposto"
        food = righe[0][1]
        assert math.isnan(float(food)), (
            "una riga NaN non rende piu' NaN il food cost del mese: la rete a valle "
            "e' cambiata, rivaluta la guardia a monte"
        )

        # NaN in Postgres e' PIU' GRANDE di qualunque numero: passa i filtri di soglia.
        cur.execute(
            "SELECT count(*) FROM fatture WHERE user_id=%s AND totale_riga > 1000000",
            (user_id,),
        )
        assert cur.fetchone()[0] == 1, "NaN non ordina piu' come il massimo"


# ---------------------------------------------------------------------------
# Scrittura incompleta: il chiamante deve poterlo sapere
#
# Due difetti della stessa famiglia, trovati da un agente refutatore che
# contestava la mia conclusione «un upsert fallito e' comportamento sicuro»:
#
# 1. il tetto di `_MAX_RIGHE_PER_FATTURA` righe TRONCA e prosegue. Fuori da
#    Streamlit (worker, `silent=True`) il messaggio a video non esiste, e
#    `verifica_integrita_fattura` confronta il gia'-troncato col DB: risultato
#    "OK" su una fattura incompleta;
# 2. il ritorno d'errore diceva `righe: 0` anche quando un chunk da 500 era gia'
#    passato: su esaurimento dei tentativi l'item muore "senza righe scritte"
#    mentre il cliente vede meta' fattura nei costi.
#
# Misurato sul DB live il 15/09/2026: 3.557 documenti, il piu' lungo ha 657
# righe — nessuno ha mai toccato il tetto. Il difetto e' reale ma oggi NON
# raggiungibile: e' un presidio per quando arrivera' un fornitore piu' grosso.
# ---------------------------------------------------------------------------


class _RispostaUpsert:
    def __init__(self, dati):
        self.data = dati


class _TabellaFinta:
    """Minimo per far girare `salva_fattura_processata` senza rete.

    `esplodi_dal_chunk`: numero di chunk da far passare prima di sollevare,
    per riprodurre la scrittura parziale.
    """

    def __init__(self, registro, esplodi_dal_chunk=None):
        self._registro = registro
        self._esplodi = esplodi_dal_chunk
        self._ultimo_upsert = None

    def upsert(self, righe, on_conflict=None):
        self._ultimo_upsert = righe
        return self

    def select(self, *a, **k):
        return self

    def delete(self):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def not_(self):
        return self

    def execute(self):
        righe = self._ultimo_upsert
        if righe is None:
            return _RispostaUpsert([])
        indice = self._registro["chunk"]
        self._registro["chunk"] += 1
        if self._esplodi is not None and indice >= self._esplodi:
            raise ValueError("Out of range float values are not JSON compliant")
        self._registro["scritte"] += len(righe)
        return _RispostaUpsert(list(righe))


class _ClientFinto:
    def __init__(self, registro, esplodi_dal_chunk=None):
        self._registro = registro
        self._esplodi = esplodi_dal_chunk

    def table(self, nome):
        if nome == "fatture":
            return _TabellaFinta(self._registro, self._esplodi)
        return _TabellaFinta({"chunk": 0, "scritte": 0})


def _righe_finte(quante: int):
    return [
        {
            "Numero_Riga": i,
            "Descrizione": f"ARTICOLO {i}",
            "Quantita": 1.0,
            "Prezzo_Unitario": 1.0,
            "Totale_Riga": 1.0,
            "Fornitore": "FORNITORE",
            "Categoria": "CARNE E SALUMI",
            "Data_Documento": "2026-09-01",
            "IVA_Percentuale": 10,
        }
        for i in range(1, quante + 1)
    ]


def test_il_troncamento_viene_dichiarato_al_chiamante(monkeypatch):
    """Oltre il tetto, `righe_troncate` dice quante righe il cliente NON vedra'."""
    monkeypatch.setattr(invoice_service, "_MAX_RIGHE_PER_FATTURA", 10, raising=False)
    registro = {"chunk": 0, "scritte": 0}
    esito = invoice_service.salva_fattura_processata(
        nome_file="grossa.xml",
        dati_prodotti=_righe_finte(14),
        supabase_client=_ClientFinto(registro),
        silent=True,
        ristoranteid="r1",
        user_id="u1",
    )
    assert esito["success"] is True
    assert esito["righe_troncate"] == 4, (
        "il troncamento non viene dichiarato: nel worker (silent=True) resta invisibile "
        "e la verifica d'integrita' confronta il gia'-troncato col DB"
    )


def test_senza_troncamento_il_campo_e_zero(monkeypatch):
    """Controllo positivo: una fattura normale non deve segnalare nulla."""
    monkeypatch.setattr(invoice_service, "_MAX_RIGHE_PER_FATTURA", 10, raising=False)
    registro = {"chunk": 0, "scritte": 0}
    esito = invoice_service.salva_fattura_processata(
        nome_file="normale.xml",
        dati_prodotti=_righe_finte(3),
        supabase_client=_ClientFinto(registro),
        silent=True,
        ristoranteid="r1",
        user_id="u1",
    )
    assert esito["success"] is True
    assert esito.get("righe_troncate", 0) == 0


def test_una_scrittura_parziale_non_dichiara_zero_righe(monkeypatch):
    """Il primo chunk passa, il secondo esplode: `righe` deve dire 500, non 0."""
    monkeypatch.setattr(invoice_service, "_INSERT_CHUNK_SIZE", 500, raising=False)
    registro = {"chunk": 0, "scritte": 0}
    esito = invoice_service.salva_fattura_processata(
        nome_file="meta.xml",
        dati_prodotti=_righe_finte(700),
        supabase_client=_ClientFinto(registro, esplodi_dal_chunk=1),
        silent=True,
        ristoranteid="r1",
        user_id="u1",
    )
    assert esito["success"] is False
    assert esito["righe_parziali"] is True, "la scrittura parziale non viene dichiarata"
    assert esito["righe"] == registro["scritte"] == 500, (
        f"righe={esito['righe']} ma a DB ce ne sono {registro['scritte']}: "
        "il chiamante crede che il DB sia pulito"
    )


# ---------------------------------------------------------------------------
# Inerenza: il segnale non deve perdersi al livello sopra.
#
# `salva_fattura_processata` ora dichiara la scrittura parziale, ma
# `/api/upload/invoice` rispondeva `righe_salvate=0` su qualunque fallimento —
# lo stesso difetto un piano piu' su, con in piu' un consumatore frontend
# (`upload-modal.tsx` mostra `data.righe_salvate` accanto allo stato "error").
# ---------------------------------------------------------------------------


def test_l_api_di_upload_non_dichiara_zero_righe_su_scrittura_parziale():
    from services import fastapi_worker

    righe, errore = fastapi_worker._esito_salvataggio_fallito(
        {"success": False, "error": "boom", "righe": 500, "righe_parziali": True}
    )
    assert righe == 500, "l'API dice 0 righe mentre 500 sono a DB"
    assert "500" in errore and "salvate" in errore


def test_l_api_non_inventa_un_avviso_quando_non_c_e_scrittura_parziale():
    """Controllo positivo: un fallimento pulito resta un fallimento pulito."""
    from services import fastapi_worker

    righe, errore = fastapi_worker._esito_salvataggio_fallito(
        {"success": False, "error": "boom", "righe": 0, "righe_parziali": False}
    )
    assert righe == 0
    assert errore == "boom", "avviso di scrittura parziale su un errore che non lo e'"


def test_l_api_regge_un_result_senza_le_chiavi_nuove():
    """Retrocompatibilita': un chiamante vecchio non deve far esplodere la rotta."""
    from services import fastapi_worker

    assert fastapi_worker._esito_salvataggio_fallito({}) == (0, "Errore salvataggio")
