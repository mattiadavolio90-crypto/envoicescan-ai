"""Il contenuto dell'email settimanale (fase 7b, deciso da Mattia il 25/09/2026).

«Mi spaventa inviare informazioni inutili o incomplete»: ogni sezione parla
SOLO se per quel cliente il dato e' affidabile. Qui si prova, sezione per
sezione, sia quando parla sia quando tace:
- incasso della settimana: entrambe le settimane con i giorni registrati;
- fatture dallo SDI: solo dove arrivano in automatico, note di credito fuori,
  settimana sul calendario di ROMA;
- osservazioni della fase 4: il producer vero, con le voci spente del PV;
- invito a riprendere: solo a chi non manda dati da 4 settimane.

Il finto database confronta date e istanti come Postgres (con il fuso), non
come stringhe: e' li' che una fattura delle 00:30 del lunedi' a Roma cade
nella settimana giusta o in quella sbagliata.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import pytest

import services.fastapi_worker as fw
from services import email_settimanale_service as svc

LUNEDI = date(2026, 9, 21)                 # settimana chiusa: 14-20 settembre
UID = "11111111-1111-4111-8111-111111111111"


# ── Finto database ──────────────────────────────────────────────────────────

def _valore(v):
    if isinstance(v, str):
        try:
            if "T" in v:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            return date.fromisoformat(v)
        except ValueError:
            return v
    return v


class _Q:
    def __init__(self, righe):
        self.righe, self.filtri, self._ordine, self._limite = list(righe), [], None, None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, valori):
        self.filtri.append(lambda r: r.get(col) in valori)
        return self

    def gte(self, col, val):
        self.filtri.append(lambda r: r.get(col) is not None and _valore(r[col]) >= _valore(val))
        return self

    def lte(self, col, val):
        self.filtri.append(lambda r: r.get(col) is not None and _valore(r[col]) <= _valore(val))
        return self

    def lt(self, col, val):
        self.filtri.append(lambda r: r.get(col) is not None and _valore(r[col]) < _valore(val))
        return self

    def is_(self, col, val):
        assert val == "null"
        self.filtri.append(lambda r: r.get(col) is None)
        return self

    def order(self, col, desc=False):
        self._ordine = (col, desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def range(self, a, b):
        self._range = (a, b)
        return self

    def execute(self):
        out = [r for r in self.righe if all(f(r) for f in self.filtri)]
        if self._ordine:
            col, desc = self._ordine
            out.sort(key=lambda r: _valore(r.get(col)), reverse=desc)
        if getattr(self, "_range", None):
            a, b = self._range
            out = out[a:b + 1]
        if self._limite is not None:
            out = out[: self._limite]
        return type("R", (), {"data": out})()


class _DB:
    def __init__(self):
        self.tabelle: Dict[str, List[Dict[str, Any]]] = {
            "ricavi_giornalieri": [], "fatture_documenti": [],
            "users": [{"id": UID, "email": "anna@cliente.it", "attivo": True, "ruolo": "cliente",
                       "email_settimanale": True, "nome_referente": "Anna"}],
            "ristoranti": [{"id": "r1", "user_id": UID, "nome_ristorante": "Trattoria",
                            "attivo": True, "sede_tecnica": False}],
        }

    def table(self, nome):
        return _Q(self.tabelle.get(nome, []))

    def incasso(self, rid, giorno: date, valore=1000.0):
        self.tabelle["ricavi_giornalieri"].append({
            "id": len(self.tabelle["ricavi_giornalieri"]) + 1, "ristorante_id": rid,
            "data": giorno.isoformat(), "fatturato_iva10": valore,
            "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        })

    def settimana(self, rid, lunedi: date, valore=1000.0, giorni=7):
        for i in range(giorni):
            self.incasso(rid, lunedi + timedelta(days=i), valore)

    def fattura(self, rid, creata_utc: str, totale=100.0, tipo="TD01", fonte="invoicetronic", cancellata=False):
        self.tabelle["fatture_documenti"].append({
            "id": len(self.tabelle["fatture_documenti"]) + 1, "ristorante_id": rid,
            "created_at": creata_utc, "totale_documento": totale, "tipo_documento": tipo,
            "source_origin": fonte, "deleted_at": "2026-09-20T00:00:00+00:00" if cancellata else None,
        })


@pytest.fixture(autouse=True)
def preferenze(monkeypatch):
    stato = {"chiusura": {}, "spenti": {}}
    monkeypatch.setattr(fw, "_get_assistant_preferences", lambda rid, sb: {
        "giorni_chiusura_settimanali": stato["chiusura"].get(rid, 0),
        "topics_disabled": list(stato["spenti"].get(rid, [])),
    })
    return stato


def _dest(*sedi):
    sedi = sedi or (("r1", "Trattoria"),)
    return svc.Destinatario(user_id=UID, email="a@b.it", nome="Anna",
                            sedi=[{"id": rid, "nome": nome} for rid, nome in sedi])


PRIMA = date(2026, 9, 7)     # lunedi' della settimana prima
ORA = date(2026, 9, 14)      # lunedi' della settimana chiusa


# ── Incasso della settimana ─────────────────────────────────────────────────

def test_incasso_salito_una_sede():
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 1100)
    assert svc._sezione_incasso(db, _dest(), LUNEDI) == (
        "La settimana scorsa hai incassato € 7.700, il 10% in più della settimana prima."
    )


def test_incasso_sceso_con_l_articolo_giusto():
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 920)
    assert "l'8% in meno della settimana prima" in svc._sezione_incasso(db, _dest(), LUNEDI)


def test_incasso_stabile_sotto_la_soglia_della_fase_4():
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 1020)
    assert svc._sezione_incasso(db, _dest(), LUNEDI).endswith("in linea con la settimana prima.")


@pytest.mark.parametrize("giorni_prima, giorni_ora", [(5, 7), (7, 5), (0, 7), (7, 0)])
def test_incasso_tace_se_una_delle_due_settimane_ha_buchi(giorni_prima, giorni_ora):
    """Una settimana a 5 giorni direbbe «-30%» per un dato che manca."""
    db = _DB()
    db.settimana("r1", PRIMA, 1000, giorni=giorni_prima)
    db.settimana("r1", ORA, 1000, giorni=giorni_ora)
    assert svc._sezione_incasso(db, _dest(), LUNEDI) is None


def test_sei_giorni_bastano():
    db = _DB()
    db.settimana("r1", PRIMA, 1000, giorni=6)
    db.settimana("r1", ORA, 1000, giorni=6)
    assert svc._sezione_incasso(db, _dest(), LUNEDI) is not None


def test_il_giorno_di_chiusura_dichiarato_abbassa_la_soglia(preferenze):
    db = _DB()
    db.settimana("r1", PRIMA, 1000, giorni=5)
    db.settimana("r1", ORA, 1000, giorni=5)
    assert svc._sezione_incasso(db, _dest(), LUNEDI) is None
    preferenze["chiusura"]["r1"] = 1
    assert svc._sezione_incasso(db, _dest(), LUNEDI) is not None
    db2 = _DB()
    db2.settimana("r1", PRIMA, 1000, giorni=4)
    db2.settimana("r1", ORA, 1000, giorni=4)
    assert svc._sezione_incasso(db2, _dest(), LUNEDI) is None


def test_contano_solo_i_giorni_delle_due_settimane():
    """L'incasso di oggi (lunedi') e quello del giorno prima della settimana
    precedente non entrano nei conti."""
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 1000)
    db.incasso("r1", LUNEDI, 50_000)
    db.incasso("r1", PRIMA - timedelta(days=1), 50_000)
    assert svc._sezione_incasso(db, _dest(), LUNEDI) == (
        "La settimana scorsa hai incassato € 7.000, in linea con la settimana prima."
    )


def test_un_giorno_a_zero_non_e_un_giorno_registrato():
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 1000, giorni=5)
    db.incasso("r1", ORA + timedelta(days=5), 0)
    assert svc._sezione_incasso(db, _dest(), LUNEDI) is None


def test_catena_elenco_solo_delle_sedi_affidabili():
    db = _DB()
    db.settimana("a", PRIMA, 1000)
    db.settimana("a", ORA, 1100)
    db.settimana("b", ORA, 1000, giorni=3)
    testo = svc._sezione_incasso(db, _dest(("a", "Alfa"), ("b", "Beta")), LUNEDI)
    assert testo == "Incasso della settimana scorsa:\n• Alfa: € 7.700, il 10% in più della settimana prima"


@pytest.mark.parametrize("n, atteso", [
    (1, "l'1%"), (5, "il 5%"), (8, "l'8%"), (11, "l'11%"), (18, "il 18%"),
    (80, "l'80%"), (85, "l'85%"), (100, "il 100%"), (800, "l'800%"), (21, "il 21%"),
])
def test_articolo_della_percentuale(n, atteso):
    assert svc.percentuale_con_articolo(n) == atteso


# ── Fatture arrivate dallo SDI ──────────────────────────────────────────────

def test_fatture_sdi_della_settimana_senza_note_di_credito():
    db = _DB()
    db.fattura("r1", "2026-09-15T09:00:00+00:00", 300)
    db.fattura("r1", "2026-09-18T09:00:00+00:00", 200)
    db.fattura("r1", "2026-09-16T09:00:00+00:00", 50, tipo="TD04")
    db.fattura("r1", "2026-09-17T09:00:00+00:00", 999, cancellata=True)
    assert svc._sezione_fatture_sdi(db, _dest(), LUNEDI) == (
        "La settimana scorsa sono arrivate dallo SDI 2 fatture per € 500."
    )


def test_una_fattura_al_singolare():
    db = _DB()
    db.fattura("r1", "2026-09-15T09:00:00+00:00", 300)
    assert "1 fattura per € 300" in svc._sezione_fatture_sdi(db, _dest(), LUNEDI)


def test_chi_carica_a_mano_non_riceve_il_conteggio():
    """Il caricamento manuale va a blocchi: «0 fatture questa settimana»
    sarebbe falso. Conta solo il canale automatico."""
    db = _DB()
    for i in range(20):
        db.fattura("r1", "2026-09-15T09:00:00+00:00", 100, fonte="manual")
    assert svc._sezione_fatture_sdi(db, _dest(), LUNEDI) is None


def test_settimana_senza_fatture_sdi_tace_anche_col_flusso_attivo():
    db = _DB()
    db.fattura("r1", "2026-09-02T09:00:00+00:00", 300)
    assert svc._sezione_fatture_sdi(db, _dest(), LUNEDI) is None


@pytest.mark.parametrize("creata_utc, dentro", [
    ("2026-09-13T22:30:00+00:00", True),    # 14/9 00:30 a Roma: lunedi' della settimana chiusa
    ("2026-09-13T21:30:00+00:00", False),   # 13/9 23:30 a Roma: settimana prima
    ("2026-09-20T21:30:00+00:00", True),    # 20/9 23:30 a Roma: domenica, dentro
    ("2026-09-20T22:30:00+00:00", False),   # 21/9 00:30 a Roma: oggi, fuori
])
def test_la_settimana_e_quella_di_roma(creata_utc, dentro):
    """Il calendario UTC e quello di Roma divergono fra le 22 e le 24 UTC."""
    db = _DB()
    db.fattura("r1", "2026-09-10T09:00:00+00:00", 1)   # tiene vivo il flusso
    db.fattura("r1", creata_utc, 300)
    testo = svc._sezione_fatture_sdi(db, _dest(), LUNEDI)
    assert (testo is not None and "€ 300" in testo) is dentro, testo


def test_fatture_catena_elenco():
    db = _DB()
    db.fattura("a", "2026-09-15T09:00:00+00:00", 300)
    db.fattura("b", "2026-09-15T09:00:00+00:00", 100)
    db.fattura("b", "2026-09-16T09:00:00+00:00", 100)
    assert svc._sezione_fatture_sdi(db, _dest(("a", "Alfa"), ("b", "Beta")), LUNEDI) == (
        "Fatture arrivate dallo SDI la settimana scorsa:\n• Alfa: 1 fattura per € 300\n"
        "• Beta: 2 fatture per € 200"
    )


def _con_comuni(*sedi):
    d = _dest(*sedi)
    d.sedi_tecniche = [{"id": "t", "nome": "Costi comuni di gruppo"}]
    return d


def test_i_costi_comuni_entrano_nelle_fatture_sdi():
    """Mattia (25/09): senza, per OFFSIDE l'email elencava 7 + 8 fatture e
    taceva sulle 10 arrivate ai costi comuni — ogni riga vera, quadro
    incompleto."""
    db = _DB()
    db.fattura("a", "2026-09-15T09:00:00+00:00", 300)
    db.fattura("t", "2026-09-16T09:00:00+00:00", 150)
    db.fattura("t", "2026-09-17T09:00:00+00:00", 150)
    assert svc._sezione_fatture_sdi(db, _con_comuni(("a", "Alfa"), ("b", "Beta")), LUNEDI) == (
        "Fatture arrivate dallo SDI la settimana scorsa:\n• Alfa: 1 fattura per € 300\n"
        "• Costi comuni di gruppo: 2 fatture per € 300"
    )


def test_una_sede_piu_i_costi_comuni_e_un_elenco():
    db = _DB()
    db.fattura("r1", "2026-09-15T09:00:00+00:00", 300)
    db.fattura("t", "2026-09-16T09:00:00+00:00", 100)
    testo = svc._sezione_fatture_sdi(db, _con_comuni(), LUNEDI)
    assert testo.startswith("Fatture arrivate dallo SDI la settimana scorsa:\n• Trattoria")
    assert "• Costi comuni di gruppo: 1 fattura per € 100" in testo


def test_i_costi_comuni_non_entrano_nell_incasso_ne_nell_invito():
    db = _DB()
    db.settimana("t", PRIMA, 1000)
    db.settimana("t", ORA, 1000)
    db.fattura("t", "2026-09-15T09:00:00+00:00", 100)
    assert svc._sezione_incasso(db, _con_comuni(), LUNEDI) is None
    assert svc._sezione_invito(db, _con_comuni(), LUNEDI) is not None


# ── Invito a riprendere ─────────────────────────────────────────────────────

def test_mai_un_dato_invito_a_cominciare():
    assert svc._sezione_invito(_DB(), _dest(), LUNEDI) == (
        "Non abbiamo ancora ricevuto dati dal tuo locale: bastano le fatture per cominciare."
    )
    assert "dai tuoi locali" in svc._sezione_invito(_DB(), _dest(("a", "A"), ("b", "B")), LUNEDI)


def test_fermo_da_luglio_invito_a_ricominciare_con_la_data():
    db = _DB()
    db.fattura("r1", "2026-07-15T10:00:00+00:00", fonte="manual")
    db.incasso("r1", date(2026, 6, 9))
    assert svc._sezione_invito(db, _dest(), LUNEDI) == (
        "Non riceviamo dati dal 15 luglio: bastano le fatture per ricominciare."
    )


@pytest.mark.parametrize("giorno, atteso", [
    (date(2026, 8, 1), "dal 1° agosto"), (date(2026, 8, 8), "dall'8 agosto"),
    (date(2026, 8, 11), "dall'11 agosto"), (date(2026, 8, 15), "dal 15 agosto"),
    (date(2026, 8, 18), "dal 18 agosto"), (date(2025, 12, 8), "dall'8 dicembre 2025"),
])
def test_la_preposizione_davanti_alla_data(giorno, atteso):
    """«dal 8 agosto» e «dal 11 agosto» trovati dalla review del 25/09 sulle
    date vere: tre giorni del mese su 31, nel testo che il cliente legge."""
    assert svc.dal_giorno(giorno, 2026) == atteso


def test_fermo_dall_anno_prima_dice_l_anno():
    db = _DB()
    db.incasso("r1", date(2025, 12, 20))
    assert "dal 20 dicembre 2025:" in svc._sezione_invito(db, _dest(), date(2026, 1, 26))


@pytest.mark.parametrize("giorni_fa, invito", [(27, False), (28, True)])
def test_la_soglia_delle_quattro_settimane(giorni_fa, invito):
    db = _DB()
    db.incasso("r1", LUNEDI - timedelta(days=giorni_fa))
    assert (svc._sezione_invito(db, _dest(), LUNEDI) is not None) is invito


def test_una_fattura_recente_basta_a_non_essere_fermi():
    db = _DB()
    db.fattura("r1", "2026-09-10T10:00:00+00:00", fonte="manual")
    assert svc._sezione_invito(db, _dest(), LUNEDI) is None


def test_non_contano_ne_le_fatture_cancellate_ne_gli_incassi_futuri():
    db = _DB()
    db.fattura("r1", "2026-09-10T10:00:00+00:00", cancellata=True)
    db.incasso("r1", LUNEDI + timedelta(days=3))
    assert svc._sezione_invito(db, _dest(), LUNEDI) is not None


def test_catena_con_una_sede_viva_non_e_ferma():
    db = _DB()
    db.incasso("b", LUNEDI - timedelta(days=2))
    assert svc._sezione_invito(db, _dest(("a", "A"), ("b", "B")), LUNEDI) is None


# ── Osservazioni della fase 4 (producer vero) ───────────────────────────────

MARTEDI = date(2026, 9, 22)


def _otto_settimane(db, rid):
    fine = MARTEDI - timedelta(days=MARTEDI.weekday() + 1)
    for i in range(56):
        db.incasso(rid, fine - timedelta(days=i), 1200 if i < 28 else 1000)


def test_osservazione_andamento_col_producer_vero(monkeypatch):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: MARTEDI)
    db = _DB()
    _otto_settimane(db, "r1")
    testo = svc._sezione_osservazioni(db, _dest(), MARTEDI)
    assert "il 20% in più" in testo and "•" not in testo


def test_osservazione_spenta_nel_configuratore_della_sede(monkeypatch, preferenze):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: MARTEDI)
    db = _DB()
    _otto_settimane(db, "r1")
    preferenze["spenti"]["r1"] = ["andamento_incasso"]
    assert svc._sezione_osservazioni(db, _dest(), MARTEDI) is None


def test_osservazioni_catena_col_nome_della_sede(monkeypatch):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: MARTEDI)
    db = _DB()
    _otto_settimane(db, "b")
    testo = svc._sezione_osservazioni(db, _dest(("a", "Alfa"), ("b", "Beta")), MARTEDI)
    assert testo.startswith("• Beta: ") and "Alfa" not in testo


def test_osservazioni_senza_preferenze_tacciono(monkeypatch):
    """Fail-closed: senza le preferenze non sappiamo se il cliente ha spento
    l'osservazione, e un'email spedita non si ritira."""
    monkeypatch.setattr(fw, "_oggi_rome", lambda: MARTEDI)

    def _rotte(rid, sb):
        raise RuntimeError("preferenze giu'")

    monkeypatch.setattr(fw, "_get_assistant_preferences", _rotte)
    db = _DB()
    _otto_settimane(db, "r1")
    assert svc._sezione_osservazioni(db, _dest(), MARTEDI) is None


def test_osservazioni_usano_il_giorno_dell_email_non_quello_di_oggi(monkeypatch):
    """L'anteprima fatta di martedi' non deve mostrare l'andamento, che
    l'email del lunedi' non conterra' (review del 25/09)."""
    monkeypatch.setattr(fw, "_oggi_rome", lambda: MARTEDI)
    db = _DB()
    _otto_settimane(db, "r1")
    assert svc._sezione_osservazioni(db, _dest(), MARTEDI - timedelta(days=1)) is None
    assert svc._sezione_osservazioni(db, _dest(), MARTEDI) is not None


def test_il_lunedi_l_andamento_tace(monkeypatch):
    """L'andamento della fase 4 parla il martedi': l'email del lunedi' ha
    gia' l'incasso della settimana, non lo ripete."""
    monkeypatch.setattr(fw, "_oggi_rome", lambda: LUNEDI)
    db = _DB()
    _otto_settimane(db, "r1")
    assert svc._sezione_osservazioni(db, _dest(), LUNEDI) is None


# ── L'insieme ───────────────────────────────────────────────────────────────

def test_le_sezioni_e_il_loro_ordine():
    assert svc.SEZIONI == [svc._sezione_invito, svc._sezione_incasso,
                           svc._sezione_fatture_sdi, svc._sezione_osservazioni]


def test_cliente_attivo_riceve_solo_cio_che_e_affidabile(monkeypatch):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: LUNEDI)
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 1000)
    for i in range(5):
        db.fattura("r1", "2026-09-15T09:00:00+00:00", 100, fonte="manual")
    assert svc.calcola_frasi(db, _dest(), LUNEDI) == [
        "La settimana scorsa hai incassato € 7.000, in linea con la settimana prima."
    ]


def test_il_lavoro_del_lunedi_passa_il_database_alle_sezioni(monkeypatch):
    """Da `esegui` e `anteprima`, con le SEZIONI vere: un `sb` non passato
    farebbe fallire ogni sezione (mutante sopravvissuto alla review del 25/09,
    perche' gli altri test usavano una sezione fissa)."""
    monkeypatch.setenv(svc.ENV_SEGRETO, "s")
    monkeypatch.setattr(fw, "_oggi_rome", lambda: LUNEDI)
    db = _DB()
    db.settimana("r1", PRIMA, 1000)
    db.settimana("r1", ORA, 1000)
    r = svc.esegui(db, adesso=datetime(2026, 9, 21, 7, 35, tzinfo=svc._roma()), dry_run=True)
    assert r["composte"] == 1 and r["errori"] == 0 and r["sezioni_fallite"] == 0
    a = svc.anteprima(db, UID, adesso=datetime(2026, 9, 21, 7, 35, tzinfo=svc._roma()))
    assert a["frasi"] == ["La settimana scorsa hai incassato € 7.000, in linea con la settimana prima."]


def test_cliente_attivo_senza_dati_affidabili_non_riceve_niente(monkeypatch):
    monkeypatch.setattr(fw, "_oggi_rome", lambda: LUNEDI)
    db = _DB()
    db.settimana("r1", ORA, 1000, giorni=3)
    assert svc.calcola_frasi(db, _dest(), LUNEDI) == []
