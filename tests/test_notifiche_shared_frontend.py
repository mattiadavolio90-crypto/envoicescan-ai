"""Notifiche condivise (`lib/notifiche-shared.ts`) — ordinamento, CTA, testo.

Perche' esiste, e perche' solo ora: queste funzioni erano gia' pure, ma vivevano
in `app/(app)/notifiche/`, fuori dalla portata dell'harness (che risolve solo
l'alias @/ dentro lib/). Spostarle non e' bastato: importavano il tipo da
`lib/notifiche.ts`, che a sua volta importa `./worker-config` con path relativo
— e un import di SOLO TIPO basta a rendere un modulo non eseguibile sotto node.
La dipendenza e' stata invertita (il tipo vive nel modulo puro, il modulo con le
fetch lo ri-esporta).

Le usano due pagine: il widget della Home e la pagina /notifiche.
"""

from tests.helpers_ts import esegui_ts

MODULO = "lib/notifiche-shared"


def _chiama(fn, args, richiede=None):
    return esegui_ts(MODULO, f"emit(m.{fn}(...input));", argomento=args, richiede=richiede or [fn])


def _n(id_, severity="info", source="upload", created="2026-09-01T10:00:00Z", page=None):
    return {
        "id": id_, "topic_key": None, "source_type": source, "severity": severity,
        "title": f"t{id_}", "body": None, "action_page": page,
        "dismissed_at": None, "expires_at": None, "created_at": created,
    }


# ─── raggruppa: severity prima, poi la data ───────────────────────────────

def test_gruppi_ordinati_come_GRUPPO_ORDINE_non_come_arrivano():
    """Le scadenze vengono prima degli upload anche se arrivano dopo."""
    out = _chiama("raggruppa", [[_n("a", source="upload"), _n("b", source="scadenza")]])
    assert [g["key"] for g in out] == ["scadenza", "upload"]


def test_dentro_un_gruppo_vince_la_severity():
    out = _chiama("raggruppa", [[
        _n("info", severity="info"),
        _n("err", severity="error"),
        _n("warn", severity="warning"),
        _n("ok", severity="success"),
    ]])
    assert [n["id"] for n in out[0]["notifiche"]] == ["err", "warn", "info", "ok"]


def test_a_parita_di_severity_la_piu_recente_e_prima():
    out = _chiama("raggruppa", [[
        _n("vecchia", created="2026-08-01T10:00:00Z"),
        _n("nuova", created="2026-09-01T10:00:00Z"),
    ]])
    assert [n["id"] for n in out[0]["notifiche"]] == ["nuova", "vecchia"]


def test_created_at_nullo_non_rompe_l_ordinamento():
    """`?? ""` sui due lati: una data mancante finisce in fondo, non lancia."""
    out = _chiama("raggruppa", [[_n("senza", created=None), _n("con")]])
    assert [n["id"] for n in out[0]["notifiche"]] == ["con", "senza"]


def test_source_sconosciuto_finisce_in_Altro():
    out = _chiama("raggruppa", [[_n("x", source="qualcosa_di_nuovo")]])
    assert out[0]["key"] == "altro"


def test_source_case_insensitive():
    out = _chiama("raggruppa", [[_n("x", source="UPLOAD")]])
    assert out[0]["key"] == "upload"


def test_scadenziario_e_scadenza_finiscono_nello_stesso_gruppo():
    """Due source_type diversi dal backend, una sola voce per l'utente."""
    out = _chiama("raggruppa", [[_n("a", source="scadenza"), _n("b", source="scadenziario")]])
    assert len(out) == 1 and len(out[0]["notifiche"]) == 2


def test_lista_vuota():
    assert _chiama("raggruppa", [[]]) == []


# ─── ctaDi: le rotte legacy di Streamlit sopravvivono nei dati ────────────

def test_cta_assente_quando_non_c_e_pagina():
    assert _chiama("ctaDi", [_n("x", page=None)]) is None
    assert _chiama("ctaDi", [_n("x", page="   ")]) is None


def test_cta_rotta_next_passa_intera():
    assert _chiama("ctaDi", [_n("x", page="/margini")])["href"] == "/margini"


def test_cta_traduce_una_rotta_streamlit_legacy():
    """Streamlit e' stato rimosso dal repo, ma i suoi path sono ancora nelle
    notifiche vecchie a DB: senza la mappa il pulsante non porterebbe da
    nessuna parte."""
    assert _chiama("ctaDi", [_n("x", page="pages/3_controllo_prezzi.py")])["href"] == "/prezzi"


def test_cta_legacy_case_insensitive():
    assert _chiama("ctaDi", [_n("x", page="Dashboard")])["href"] == "/dashboard"


def test_cta_rotta_sconosciuta_non_produce_un_link_rotto():
    """Meglio nessun pulsante che un pulsante che porta a un 404."""
    assert _chiama("ctaDi", [_n("x", page="pages/99_inesistente.py")]) is None


# ─── pulisci: markdown grezzo -> testo ────────────────────────────────────

def test_pulisci_grassetto_e_corsivo():
    assert _chiama("pulisci", ["**Attenzione**: prezzo *alto*"]) == "Attenzione: prezzo alto"


def test_pulisci_br_diventa_a_capo():
    assert _chiama("pulisci", ["riga1<br>riga2<br />riga3"]) == "riga1\nriga2\nriga3"


def test_pulisci_backtick_spariscono():
    assert _chiama("pulisci", ["il campo `totale`"]) == "il campo totale"


def test_pulisci_trimma():
    assert _chiama("pulisci", ["  testo  "]) == "testo"


def test_pulisci_testo_gia_pulito_non_cambia():
    assert _chiama("pulisci", ["Prezzo aumentato del 12%"]) == "Prezzo aumentato del 12%"


def test_pulisci_DUE_grassetti_nella_stessa_riga():
    """Il quantificatore e' lazy (`.+?`) e deve restarlo.

    Con `.+` greedy il match parte dal primo `**` e arriva all'ULTIMO: due
    coppie diventano una sola, e gli asterischi centrali restano a schermo
    ("**a** e **b**" -> "a** e **b"). Trovato da un mutante sopravvissuto:
    tutti i casi che avevo scritto avevano una coppia sola, dove greedy e lazy
    coincidono.
    """
    assert _chiama("pulisci", ["**a** e **b**"]) == "a e b"


def test_pulisci_asterisco_singolo_non_accoppiato_resta():
    """Il regex vuole una coppia: un asterisco solo non e' markup."""
    assert _chiama("pulisci", ["2 * 3 = 6"]) == "2 * 3 = 6"
