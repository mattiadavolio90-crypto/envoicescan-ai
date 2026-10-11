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
    """La memoria SHOP la rinomina la migration dei dati; lo script lo rifa' solo nei
    residui, per le voci scritte col nome vecchio dal worker vecchio dopo la
    migration. Il passo giappone resta sulle sole famiglie della Fase K."""
    sb = _Sb(_MEMORIA_LIVE)
    _scritture(fk, monkeypatch)
    monkeypatch.setattr(fk, "_client", lambda: sb)
    monkeypatch.setattr(fk, "carica_fatture", lambda _sb: [])
    monkeypatch.setattr(fk, "sedi_e_utenti_retail", lambda _sb, _righe: (set(), set()))
    fk.main([passo, "--commit"])
    rinominate = [a for t, nome, a in _scritture_sb(sb) if nome == "update" and "RIVENDITA" in a[0].values()]
    assert bool(rinominate) is rinomina_attesa


# ── i documenti ripartiti sul gruppo: si rifanno le quote, come fa l'app ────

class _SbRiparti(_Sb):
    """Client finto che risponde alla lettura dei riparti di un documento."""

    def __init__(self, riparti, tabelle=None):
        super().__init__(tabelle)
        self.riparti = riparti

    def table(self, nome):
        if nome == "riparto_costi_catena":
            return _Query(self.registro, nome, list(self.riparti))
        return super().table(nome)


@pytest.fixture
def percorso_app(monkeypatch):
    """Intercetta le due funzioni dell'app che rifanno quote e MOL del riparto."""
    import services.riparto_service as rs
    import services.routers.riparto as router

    chiamate = {"esplodi": [], "post": []}
    monkeypatch.setattr(rs, "esplodi_quote_per_categoria",
                        lambda sb, uid, rid, fo, forza=False: chiamate["esplodi"].append((uid, rid, fo, forza)) or True)
    monkeypatch.setattr(router, "_post_scrittura_riparto",
                        lambda sb, uid, anno, mese: chiamate["post"].append((uid, anno, mese)) or True)
    return chiamate


def test_una_riga_ripartita_spostata_rifa_le_quote_e_il_mol(fk, monkeypatch, percorso_app):
    """Il MOL delle sedi legge le QUOTE del riparto, non le righe: senza rifarle il
    pasto resterebbe nel food cost delle sedi (i 31 pasti del live sono tutti cosi')."""
    _scritture(fk, monkeypatch)
    sb = _SbRiparti([{"id": "rip-1", "anno": 2026, "mese": 7}])
    righe = [_r(1, "COPERTO", "Da Classificare", 40.91, file="pranzo.xml", ripartita_su_gruppo=True),
             _r(2, "PIZZA", "PRODOTTI DA FORNO", 9.09, file="pranzo.xml", ripartita_su_gruppo=True)]
    fk._passo_fatture(sb, "pasti", righe, commit=True, lotto="L")
    assert percorso_app["esplodi"] == [("u1", "rip-1", "pranzo.xml", True)]
    assert percorso_app["post"] == [("u1", 2026, 7)]


def test_in_dry_run_i_riparti_si_elencano_e_basta(fk, monkeypatch, percorso_app, capsys):
    _scritture(fk, monkeypatch)
    sb = _SbRiparti([{"id": "rip-1", "anno": 2026, "mese": 7}])
    righe = [_r(1, "COPERTO", "Da Classificare", 40.91, file="pranzo.xml", ripartita_su_gruppo=True)]
    fk._passo_fatture(sb, "pasti", righe, commit=False, lotto="L")
    assert percorso_app == {"esplodi": [], "post": []}
    assert "riparto da rifare: pranzo.xml [2026-07]" in capsys.readouterr().out


def test_le_righe_non_ripartite_non_toccano_i_riparti(fk, monkeypatch, percorso_app):
    _scritture(fk, monkeypatch)
    fk._passo_fatture(_SbRiparti([{"id": "rip-1", "anno": 2026, "mese": 7}]), "pasti",
                      [_r(1, "COPERTO", "Da Classificare", 40.91)], commit=True, lotto="L")
    assert percorso_app == {"esplodi": [], "post": []}


def test_la_rinomina_dei_residui_ripartiti_rifa_le_quote(fk, monkeypatch, percorso_app):
    _scritture(fk, monkeypatch)
    sb = _SbRiparti([{"id": "rip-9", "anno": 2026, "mese": 3}])
    righe = [_r(1, "CARAMELLE", "SHOP", file="g.xml", ripartita_su_gruppo=True)]
    fk._passo_fatture(sb, "residui", righe, commit=True, lotto="L")
    assert percorso_app["esplodi"] == [("u1", "rip-9", "g.xml", True)]


# ── i negozi: collegati davvero dentro main ──────────────────────────────────

def test_sedi_e_utenti_retail_legge_il_settore(fk, monkeypatch):
    import services.settore_service as ss

    monkeypatch.setattr(ss, "settore_sede", lambda rid, sb: "retail" if rid == "negozio" else "ristorazione")
    monkeypatch.setattr(ss, "settore_utente", lambda uid, sb: "retail" if uid == "u-negozio" else "ristorazione")
    righe = [_r(1, "X", "PESCE", ristorante_id="negozio", user="u-negozio"),
             _r(2, "Y", "PESCE", ristorante_id="ristorante", user="u1")]
    assert fk.sedi_e_utenti_retail(object(), righe) == ({"negozio"}, {"u-negozio"})


def test_main_tiene_i_negozi_fuori_da_fatture_e_memoria(fk, monkeypatch):
    chiamate = _scritture(fk, monkeypatch)
    memoria = {"prodotti_utente": [
        {"id": "m1", "user_id": "u-negozio", "descrizione": "SAKE GEKKEIKAN 75CL", "categoria": "ARTICOLO DI VENDITA"},
    ]}
    sb = _Sb(memoria)
    monkeypatch.setattr(fk, "_client", lambda: sb)
    monkeypatch.setattr(fk, "carica_fatture", lambda _sb: [
        _r(1, "SAKE GEKKEIKAN 75CL", "ARTICOLO DI VENDITA", ristorante_id="negozio", user="u-negozio"),
    ])
    monkeypatch.setattr(fk, "sedi_e_utenti_retail", lambda _sb, _righe: ({"negozio"}, {"u-negozio"}))
    fk.main(["tutto", "--commit"])
    assert chiamate == []
    assert _scritture_sb(sb) == []


def test_residui_tiene_fuori_i_negozi(fk, monkeypatch):
    chiamate = _scritture(fk, monkeypatch)
    righe = [_r(1, "SAKE GEKKEIKAN 75CL", "ARTICOLO DI VENDITA", ristorante_id="negozio")]
    fk._passo_fatture(object(), "residui", righe, commit=True, lotto="L", retail_sedi={"negozio"})
    assert chiamate == []


@pytest.mark.parametrize("desc,cat", [
    ("TARALLI OLIO SESAMO", "PRODOTTI DA FORNO"),
    ("CRACKER OLIO SESAMO", "PRODOTTI DA FORNO"),
    ("BICCHIERI SAKE CERAMICA 6PZ", "MATERIALE DI CONSUMO"),
])
def test_le_eccezioni_delle_regole_valgono_anche_per_lo_script(fk, desc, cat):
    """Il filtro delle famiglie ha le eccezioni delle regole: senza, il dizionario
    riscriverebbe un tarallo o un bicchiere su cui la Fase K non ha deciso niente."""
    assert fk.piano_giappone([_r(1, desc, cat)]) == ({}, [], [])


# ── quarto giro del revisore: ordine, filtri, errori, rilancio ─────────────

class _QueryFiltrata:
    """Query sul finto `riparto_costi_catena` che APPLICA i filtri `eq`: un finto
    che li ignorasse resterebbe verde anche togliendo il filtro sul file, e
    `forza=True` colpirebbe tutti i riparti dell'account."""

    def __init__(self, righe):
        self.righe = righe

    def select(self, *_a):
        return self

    def eq(self, campo, valore):
        self.righe = [r for r in self.righe if r.get(campo) == valore]
        return self

    def execute(self):
        return type("R", (), {"data": self.righe})()


class _SbRipartiVeri(_Sb):
    def __init__(self, riparti):
        super().__init__()
        self.riparti = riparti

    def table(self, nome):
        if nome == "riparto_costi_catena":
            return _QueryFiltrata(list(self.riparti))
        return super().table(nome)


_RIPARTI = [
    {"id": "giusto", "user_id": "u1", "file_origine": "pranzo.xml", "origine": "fattura", "anno": 2026, "mese": 7},
    {"id": "altro-file", "user_id": "u1", "file_origine": "fornitore.xml", "origine": "fattura", "anno": 2026, "mese": 7},
    {"id": "altro-utente", "user_id": "u2", "file_origine": "pranzo.xml", "origine": "fattura", "anno": 2026, "mese": 7},
    {"id": "manuale", "user_id": "u1", "file_origine": "pranzo.xml", "origine": "manuale", "anno": 2026, "mese": 7},
]


@pytest.fixture
def registro_unico(fk, monkeypatch):
    """Scritture delle righe ed esplosioni delle quote nello STESSO registro, per
    poterne controllare l'ordine."""
    import services.riparto_service as rs
    import services.routers.riparto as router

    eventi = []
    monkeypatch.setattr(fk, "aggiorna_categoria_fatture",
                        lambda sb, **kw: eventi.append(("scrivi", tuple(kw["ids"]))) or len(kw["ids"]))
    monkeypatch.setattr(rs, "esplodi_quote_per_categoria",
                        lambda sb, uid, rid, fo, forza=False: eventi.append(("esplodi", rid, forza)) or True)
    monkeypatch.setattr(router, "_post_scrittura_riparto",
                        lambda sb, uid, anno, mese: eventi.append(("mese", uid, anno, mese)) or True)
    return eventi


def _pranzo_ripartito():
    return [_r(1, "COPERTO", "Da Classificare", 40.91, file="pranzo.xml", ripartita_su_gruppo=True),
            _r(2, "PIZZA", "PRODOTTI DA FORNO", 9.09, file="pranzo.xml", ripartita_su_gruppo=True)]


def test_prima_si_scrivono_le_righe_poi_si_rifanno_le_quote(fk, registro_unico):
    """L'esplosione legge le categorie delle righe: fatta prima rifarebbe le
    quote vecchie (il difetto del terzo giro, tornato senza rumore)."""
    fk._passo_fatture(_SbRipartiVeri(_RIPARTI), "pasti", _pranzo_ripartito(), commit=True, lotto="L")
    tipi = [e[0] for e in registro_unico]
    assert tipi.index("scrivi") < tipi.index("esplodi") < tipi.index("mese")


def test_si_rifa_solo_il_riparto_del_documento_dell_utente(fk, registro_unico):
    fk._passo_fatture(_SbRipartiVeri(_RIPARTI), "pasti", _pranzo_ripartito(), commit=True, lotto="L")
    assert [e for e in registro_unico if e[0] == "esplodi"] == [("esplodi", "giusto", True)]


def test_si_rifanno_tutti_i_riparti_di_un_documento(fk, registro_unico):
    riparti = _RIPARTI + [{"id": "secondo", "user_id": "u1", "file_origine": "pranzo.xml",
                           "origine": "fattura", "anno": 2026, "mese": 8}]
    fk._passo_fatture(_SbRipartiVeri(riparti), "pasti", _pranzo_ripartito(), commit=True, lotto="L")
    assert {e[1] for e in registro_unico if e[0] == "esplodi"} == {"giusto", "secondo"}
    assert {e[3] for e in registro_unico if e[0] == "mese"} == {7, 8}


def test_un_riparto_che_fallisce_non_ferma_gli_altri_ne_il_ricalcolo(fk, monkeypatch, capsys):
    """Come l'app: l'errore su un riparto si segnala, gli altri si rifanno e i mesi
    si ricalcolano comunque."""
    import services.riparto_service as rs
    import services.routers.riparto as router

    _scritture(fk, monkeypatch)
    esplosi, mesi = [], []

    def _esplodi(sb, uid, rid, fo, forza=False):
        if rid == "giusto":
            raise RuntimeError("timeout")
        esplosi.append(rid)
        return True

    monkeypatch.setattr(rs, "esplodi_quote_per_categoria", _esplodi)
    monkeypatch.setattr(router, "_post_scrittura_riparto", lambda sb, uid, a, m: mesi.append(m) or True)
    riparti = _RIPARTI + [{"id": "secondo", "user_id": "u1", "file_origine": "pranzo.xml",
                           "origine": "fattura", "anno": 2026, "mese": 8}]
    fk._passo_fatture(_SbRipartiVeri(riparti), "pasti", _pranzo_ripartito(), commit=True, lotto="L")
    assert esplosi == ["secondo"]
    assert sorted(mesi) == [7, 8]
    uscita = capsys.readouterr().out
    assert "ATTENZIONE: non riuscito giusto pranzo.xml [2026-07]" in uscita
    assert "rilanciare lo stesso passo con --commit" in uscita


def test_il_rilancio_rifa_i_riparti_anche_con_le_righe_gia_spostate(fk, registro_unico):
    """Dopo un errore le righe sono gia' in RAPPRESENTANZA e non c'e' piu' niente da
    scrivere: il rilancio deve comunque rifare le quote di quei documenti."""
    righe = [_r(1, "COPERTO", "RAPPRESENTANZA", 40.91, file="pranzo.xml", ripartita_su_gruppo=True),
             _r(2, "PIZZA", "RAPPRESENTANZA", 9.09, file="pranzo.xml", ripartita_su_gruppo=True)]
    fk._passo_fatture(_SbRipartiVeri(_RIPARTI), "pasti", righe, commit=True, lotto="L")
    assert [e for e in registro_unico if e[0] == "scrivi"] == []
    assert [e for e in registro_unico if e[0] == "esplodi"] == [("esplodi", "giusto", True)]


def test_il_rilancio_ritrova_anche_il_menu_fisso_senza_coperto(fk, registro_unico):
    """«MENU FISSO» e' un pasto per la regola di riga, senza coperto nel documento
    (10 dei 12 riparti OFFSIDE del live): il rilancio deve ritrovarlo lo stesso."""
    righe = [_r(1, "MENU FISSO", "RAPPRESENTANZA", 33.0, file="pranzo.xml", ripartita_su_gruppo=True)]
    fk._passo_fatture(_SbRipartiVeri(_RIPARTI), "pasti", righe, commit=True, lotto="L")
    assert [e for e in registro_unico if e[0] == "scrivi"] == []
    assert [e for e in registro_unico if e[0] == "esplodi"] == [("esplodi", "giusto", True)]


def test_un_mese_che_non_si_ricalcola_si_segnala(fk, monkeypatch, capsys):
    """`_post_scrittura_riparto` e' best-effort e risponde False invece di sollevare:
    senza l'avviso il MOL del mese resterebbe vecchio in silenzio."""
    import services.riparto_service as rs
    import services.routers.riparto as router

    _scritture(fk, monkeypatch)
    monkeypatch.setattr(rs, "esplodi_quote_per_categoria", lambda sb, uid, rid, fo, forza=False: True)
    monkeypatch.setattr(router, "_post_scrittura_riparto", lambda sb, uid, a, m: False)
    fk._passo_fatture(_SbRipartiVeri(_RIPARTI), "pasti", _pranzo_ripartito(), commit=True, lotto="L")
    uscita = capsys.readouterr().out
    assert "ATTENZIONE: non riuscito - quote mensili [2026-07]: ricalcolo non riuscito" in uscita
    assert "rilanciare lo stesso passo con --commit" in uscita
