"""Fase K3: lo script che porta i dati gia' caricati nel nuovo elenco.

Si provano le funzioni che DECIDONO (`piano_*`), separate dall'I/O apposta, sulle
descrizioni reali del DB; e il punto in cui lo script scrive, per la guardia sulle
righe decise a mano. Il dry-run sul DB vero del 10/10 ha dato: giappone 516 righe
(le 426 di SUSHI VARIE tutte decise + sake, mirin, olio di sesamo, salsa unagi),
pasti 31 righe e 11 saltate perche' gia' decise a mano.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fase_k_categorie.py"


@pytest.fixture(scope="module")
def fk():
    spec = importlib.util.spec_from_file_location("fase_k_categorie", _SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["fase_k_categorie"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _r(id_, desc, cat, totale=10.0, file="f1.xml", user="u1", **extra):
    return {"id": id_, "descrizione": desc, "categoria": cat, "totale_riga": totale,
            "file_origine": file, "user_id": user, "fornitore": "FORNITORE",
            "categoria_fonte": None, "reviewed_at": None, **extra}


# ── giappone ─────────────────────────────────────────────────────────────────

def test_giappone_porta_ogni_riga_sushi_varie_nella_sua_famiglia(fk):
    righe = [
        _r(1, "YAKI NORI MISURAKI (A) 10X140G ( )", "SUSHI VARIE"),
        _r(2, "PANKO DA SACCO 10KG", "SUSHI VARIE"),
        _r(3, "TOBIKO ROSSO 12X500G", "SUSHI VARIE"),
        _r(4, "BAMBU CONSERVATO 6X2900G", "SUSHI VARIE"),
        _r(5, "VETRINA SUSHI 135", "SUSHI VARIE"),
    ]
    aggiorna, saltate, non_decise = fk.piano_giappone(righe)
    assert aggiorna == {1: "VERDURE", 2: "PASTA E CEREALI", 3: "PESCE",
                        4: "SCATOLAME E CONSERVE", 5: "MANUTENZIONE E ATTREZZATURE"}
    assert saltate == [] and non_decise == []


def test_giappone_sposta_anche_sake_mirin_e_salsa_unagi(fk):
    righe = [
        _r(1, "SAKE PER CUCINA(MISURAKI) 18 LT", "SCATOLAME E CONSERVE"),
        _r(2, "GEKKEIKAN SAKE 1,8LT 14,5% 6*1,8LT", "DISTILLATI"),
        _r(3, "MIZKAN MIRIN 18L Y", "SALSE E CREME"),
        _r(4, "UNAGI SAUCE NIPPON SHOKKEN 6*2KG", "PESCE"),
        _r(5, "OLIO DI SESAMO 100% 1,8LT", "SPEZIE E AROMI"),
    ]
    aggiorna, _s, _n = fk.piano_giappone(righe)
    assert aggiorna == {1: "VINI", 2: "VINI", 3: "OLIO E CONDIMENTI",
                        4: "SALSE E CREME", 5: "OLIO E CONDIMENTI"}


def test_giappone_non_tocca_cio_che_la_fase_k_non_ha_cambiato(fk):
    """Fuori dalle famiglie decise il nucleo deterministico puo' dissentire dalla
    riga per ragioni che non c'entrano (una memoria del cliente, l'AI): lo script
    non deve riscriverla. "SALMONE" in VERDURE e' sbagliato, ma non e' lavoro suo."""
    righe = [_r(1, "SALMONE NORVEGESE FILETTO", "VERDURE"),
             _r(2, "PIZZA MARGHERITA SURGELATA", "SERVIZI E CONSULENZE")]
    assert fk.piano_giappone(righe) == ({}, [], [])


def test_giappone_salta_le_righe_decise_a_mano(fk):
    righe = [
        _r(1, "PANKO DA SACCO 10KG", "SUSHI VARIE", reviewed_at="2026-09-01T10:00:00"),
        _r(2, "MIZKAN MIRIN 18L Y", "SALSE E CREME", categoria_fonte="correzione_cliente"),
    ]
    aggiorna, saltate, _n = fk.piano_giappone(righe)
    assert aggiorna == {}
    assert [(r["id"], nuova) for r, nuova in saltate] == [(1, "PASTA E CEREALI"), (2, "OLIO E CONDIMENTI")]


def test_giappone_lascia_ed_elenca_cio_che_non_sa_dire(fk):
    """Mai "Da Classificare" forzato su una riga che oggi ha un valore."""
    aggiorna, _s, non_decise = fk.piano_giappone([_r(1, "SUSHI ROLL DI BAMB 27C", "SUSHI VARIE")])
    assert aggiorna == {}
    assert [r["id"] for r in non_decise] == [1]


# ── pasti ────────────────────────────────────────────────────────────────────

def test_pasti_la_fattura_col_coperto_va_tutta(fk):
    righe = [
        _r(1, "COPERTO", "Da Classificare", 40.91, file="pranzo.xml"),
        _r(2, "PIZZA", "PRODOTTI DA FORNO", 9.09, file="pranzo.xml"),
        _r(3, "OMAGGIO", "📝 NOTE E DICITURE", 0.0, file="pranzo.xml"),
        _r(4, "PIZZA", "PRODOTTI DA FORNO", 9.09, file="fornitore.xml"),
        _r(5, "PIZZA", "PRODOTTI DA FORNO", 9.09, file="pranzo.xml", user="u2"),
    ]
    aggiorna, saltate = fk.piano_pasti(righe)
    assert aggiorna == {1: ("RAPPRESENTANZA", "L0_documento_pasto"),
                        2: ("RAPPRESENTANZA", "L0_documento_pasto")}
    assert saltate == []


def test_pasti_le_righe_di_pasto_fuori_da_una_fattura_col_coperto(fk):
    aggiorna, _s = fk.piano_pasti([_r(1, "MENU FISSO", "Da Classificare", 33.0),
                                   _r(2, "4 PASTI COMPLETI", "SERVIZI E CONSULENZE", 90.91)])
    assert aggiorna == {1: ("RAPPRESENTANZA", "L7_regola_forte"),
                        2: ("RAPPRESENTANZA", "L7_regola_forte")}


def test_pasti_salta_le_righe_decise_a_mano(fk):
    """Sul live sono 11 (MONOPOLI e LA PESCHERIA in SERVIZI, decise a mano)."""
    righe = [_r(1, "COPERTO", "Da Classificare", 40.91),
             _r(2, "MARGHERITA", "SERVIZI E CONSULENZE", 19.09, reviewed_at="2026-08-01")]
    aggiorna, saltate = fk.piano_pasti(righe)
    assert list(aggiorna) == [1]
    assert [r["id"] for r, _ in saltate] == [2]


# ── memoria ──────────────────────────────────────────────────────────────────

def test_memoria_rimappa_e_cancella_cio_che_non_sa_dire(fk):
    voci = [
        {"id": "a", "descrizione": "YAKI NORI MISURAKI (A) 10X140G ( )", "categoria": "SUSHI VARIE"},
        {"id": "b", "descrizione": "SUSHI ROLL DI BAMB 27C", "categoria": "SUSHI VARIE"},
        {"id": "c", "descrizione": "SAKE PER CUCINA(MISURAKI)", "categoria": "SCATOLAME E CONSERVE"},
        {"id": "d", "descrizione": "SALMONE NORVEGESE", "categoria": "VERDURE"},
    ]
    aggiorna, cancella, saltate = fk.piano_memoria(voci)
    assert aggiorna == {"a": "VERDURE", "c": "VINI"}
    assert cancella == ["b"]
    assert saltate == []


def test_memoria_shop_si_rinomina_solo_nei_residui(fk):
    """Prima del deploy il codice vecchio leggerebbe dalla memoria un RIVENDITA che
    non conosce: la rinomina della memoria aspetta il passo `residui`."""
    voci = [{"id": 1, "descrizione": "CARAMELLE GOLIA", "categoria_finale": "SHOP"}]
    assert fk.piano_memoria(voci, "categoria_finale") == ({}, [], [])
    assert fk.piano_memoria(voci, "categoria_finale", rinomina_shop=True) == ({1: "RIVENDITA"}, [], [])


def test_memoria_non_tocca_la_scelta_di_un_cliente_se_la_categoria_esiste(fk):
    """Sul live: "SAKE PER CUCINA" -> SCATOLAME E CONSERVE, scelto a mano da un
    cliente. La regola del sake (Mattia: tutto VINI) decide le righe nuove, ma la
    voce del cliente non la riscrive uno script: si salta e si stampa. Su una
    categoria abolita invece la scelta non puo' restare e si traduce."""
    voci = [
        {"id": 1, "descrizione": "SAKE PER CUCINA(MISURAKI)", "categoria": "SCATOLAME E CONSERVE",
         "classificato_da": "Manuale (cliente@esempio.it)"},
        {"id": 2, "descrizione": "MIZKAN MIRIN Y", "categoria": "SALSE E CREME",
         "classificato_da": "Manuale (reviewer-agent)"},
        {"id": 3, "descrizione": "TOBIKO ROSSO 12X500G", "categoria": "SUSHI VARIE",
         "classificato_da": "Manuale (cliente@esempio.it)"},
    ]
    aggiorna, cancella, saltate = fk.piano_memoria(voci)
    assert aggiorna == {2: "OLIO E CONDIMENTI", 3: "PESCE"}
    assert [(v["id"], nuova) for v, nuova in saltate] == [(1, "VINI")]
    assert cancella == []


# ── dove lo script scrive ────────────────────────────────────────────────────

def _scritture(fk, monkeypatch):
    chiamate = []

    def _finto(sb, **kw):
        chiamate.append(kw)
        return len(kw["ids"])

    monkeypatch.setattr(fk, "aggiorna_categoria_fatture", _finto)
    return chiamate


def test_lo_script_scrive_saltando_le_righe_decise_a_mano(fk, monkeypatch):
    """La seconda cintura: anche se la selezione sbagliasse, la RPC non scrive
    sulle righe arbitrate."""
    chiamate = _scritture(fk, monkeypatch)
    righe = [_r(1, "PANKO DA SACCO 10KG", "SUSHI VARIE")]
    fk._passo_fatture(object(), "giappone", righe, commit=True, lotto="L")
    assert chiamate and all(c["salta_correzioni_manuali"] is True for c in chiamate)
    assert chiamate[0]["categoria"] == "PASTA E CEREALI"
    assert chiamate[0]["source"] == fk.SOURCE


def test_i_pasti_scrivono_fonte_e_fiducia(fk, monkeypatch):
    chiamate = _scritture(fk, monkeypatch)
    fk._passo_fatture(object(), "pasti", [_r(1, "COPERTO", "Da Classificare", 40.91)],
                      commit=True, lotto="L")
    assert chiamate[0]["extra"] == {"needs_review": False,
                                    "categoria_fonte": "L0_documento_pasto",
                                    "categoria_fiducia": "certa"}


def test_la_rinomina_di_shop_vale_anche_per_le_righe_decise_a_mano(fk, monkeypatch):
    """E' la stessa scelta del cliente con un altro nome: saltarla lascerebbe la
    riga in una categoria che non esiste piu'."""
    chiamate = _scritture(fk, monkeypatch)
    righe = [_r(1, "CARAMELLE", "SHOP", reviewed_at="2026-08-01")]
    fk._passo_fatture(object(), "residui", righe, commit=True, lotto="L")
    rinomina = [c for c in chiamate if c["categoria"] == "RIVENDITA"]
    assert rinomina and rinomina[0]["salta_correzioni_manuali"] is False
    # rinomina pura, come la migration: coda, fonte e fiducia restano com'erano
    assert rinomina[0]["extra"] == {}


def test_senza_commit_non_scrive_niente(fk, monkeypatch):
    chiamate = _scritture(fk, monkeypatch)
    righe = [_r(1, "PANKO DA SACCO 10KG", "SUSHI VARIE"), _r(2, "CARAMELLE", "SHOP")]
    for passo in ("giappone", "pasti", "residui"):
        fk._passo_fatture(object(), passo, righe, commit=False, lotto="L")
    assert chiamate == []


# ── l'I/O: un dry-run non scrive, i negozi restano fuori ────────────────────

class _Query:
    def __init__(self, registro, tabella, dati):
        self.registro, self.tabella, self.dati = registro, tabella, dati

    def __getattr__(self, nome):
        def _metodo(*args, **kwargs):
            if nome in ("update", "delete", "upsert", "insert"):
                self.registro.append((self.tabella, nome, args))
            if nome == "is_":
                self.registro.append((self.tabella, "is_", args))
            return self
        return _metodo

    def execute(self):
        return type("R", (), {"data": self.dati})()


class _Sb:
    def __init__(self, tabelle=None):
        self.registro, self.tabelle = [], tabelle or {}

    def table(self, nome):
        return _Query(self.registro, nome, list(self.tabelle.get(nome, [])))


def _scritture_sb(sb):
    return [r for r in sb.registro if r[1] in ("update", "delete", "upsert", "insert")]


_MEMORIA_LIVE = {
    "prodotti_utente": [
        {"id": "a", "user_id": "u1", "descrizione": "YAKI NORI MISURAKI (A) 10X140G ( )", "categoria": "SUSHI VARIE"},
        {"id": "b", "user_id": "u1", "descrizione": "CARAMELLE GOLIA", "categoria": "SHOP"},
        {"id": "c", "user_id": "negozio", "descrizione": "SAKE GEKKEIKAN 75CL", "categoria": "ARTICOLO DI VENDITA"},
    ],
}


def test_la_memoria_in_dry_run_non_scrive_niente(fk):
    sb = _Sb(_MEMORIA_LIVE)
    fk._passo_memoria(sb, commit=False, rinomina_shop=True)
    assert _scritture_sb(sb) == []


def test_la_memoria_in_commit_scrive_e_salta_i_negozi(fk):
    sb = _Sb(_MEMORIA_LIVE)
    fk._passo_memoria(sb, commit=True, rinomina_shop=True, retail_utenti={"negozio"})
    scritte = {(t, args[0][next(iter(args[0]))]) for t, nome, args in _scritture_sb(sb)}
    assert scritte == {("prodotti_utente", "VERDURE"), ("prodotti_utente", "RIVENDITA")}


def test_main_senza_commit_e_un_dry_run(fk, monkeypatch):
    """Il default deve essere NON scrivere: un `--commit` dimenticato non tocca il live."""
    sb = _Sb(_MEMORIA_LIVE)
    chiamate = _scritture(fk, monkeypatch)
    monkeypatch.setattr(fk, "_client", lambda: sb)
    monkeypatch.setattr(fk, "carica_fatture", lambda _sb: [_r(1, "PANKO DA SACCO 10KG", "SUSHI VARIE"),
                                                            _r(2, "COPERTO", "Da Classificare", 40.0)])
    monkeypatch.setattr(fk, "sedi_e_utenti_retail", lambda _sb, _righe: (set(), set()))
    assert fk.main(["tutto"]) == 0
    assert chiamate == [] and _scritture_sb(sb) == []


def test_le_fatture_lette_sono_solo_quelle_non_cancellate(fk):
    sb = _Sb({"fatture": []})
    fk.carica_fatture(sb)
    assert ("fatture", "is_", ("deleted_at", "null")) in sb.registro


def test_giappone_non_scrive_sulle_sedi_dei_negozi(fk, monkeypatch):
    """Regola 7: VINI, VERDURE... sono categorie dei ristoranti."""
    chiamate = _scritture(fk, monkeypatch)
    righe = [_r(1, "SAKE GEKKEIKAN 75CL", "ARTICOLO DI VENDITA", ristorante_id="negozio"),
             _r(2, "SAKE GEKKEIKAN 75CL", "DISTILLATI", ristorante_id="ristorante")]
    fk._passo_fatture(object(), "giappone", righe, commit=True, lotto="L", retail_sedi={"negozio"})
    assert [c["ids"] for c in chiamate] == [[2]]


@pytest.mark.parametrize("desc,cat", [
    ("PANE AL SESAMO E OLIO", "PRODOTTI DA FORNO"),
    ("VASCHETTA UNAGI DON 50PZ", "MATERIALE DI CONSUMO"),
    ("TARALLI OLIO SESAMO", "RIVENDITA"),
])
def test_giappone_guarda_solo_le_famiglie_delle_regole(fk, desc, cat):
    """Il filtro e' fatto con gli stessi regex delle regole forti: una parola
    in comune (sesamo, unagi) non basta a far riscrivere la riga."""
    assert fk.piano_giappone([_r(1, desc, cat)]) == ({}, [], [])


@pytest.mark.parametrize("passo,rinomina_attesa", [("giappone", False), ("residui", True)])
def test_la_memoria_shop_si_rinomina_solo_nel_passo_residui(fk, monkeypatch, passo, rinomina_attesa):
    """Col codice vecchio ancora in produzione (passo giappone, prima del deploy) la
    memoria non deve contenere un RIVENDITA che quel codice non conosce."""
    sb = _Sb(_MEMORIA_LIVE)
    _scritture(fk, monkeypatch)
    monkeypatch.setattr(fk, "_client", lambda: sb)
    monkeypatch.setattr(fk, "carica_fatture", lambda _sb: [])
    monkeypatch.setattr(fk, "sedi_e_utenti_retail", lambda _sb, _righe: (set(), set()))
    fk.main([passo, "--commit"])
    rinominate = [a for t, nome, a in _scritture_sb(sb) if nome == "update" and "RIVENDITA" in a[0].values()]
    assert bool(rinominate) is rinomina_attesa
