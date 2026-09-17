"""«Prezzi stabili» si puo' dire solo se le fatture ci sono.

Perche' esiste
==============
L'Osservatorio, quando non trova variazioni sopra la soglia, mostrava uno stato
vuoto *positivo*: «I prezzi dei tuoi fornitori sono stabili nel {anno}». E' una
rassicurazione, e vale solo se l'app ha guardato qualcosa.

Misurato il 16/09/2026 su una sede reale: scegliendo il 2025 — anno in cui quel
cliente non ha UNA fattura caricata — l'app rassicurava lo stesso. Zero
variazioni e zero fatture producevano la stessa schermata, e la seconda e'
l'assenza del dato, non una buona notizia.

`VariazioniResponse` non esponeva nulla per distinguerle: il frontend non
*poteva* saperlo. `fatture_nel_periodo` e' il campo che glielo dice.

Documenti, non righe
====================
Il conteggio sta su `file_origine` e non sulla lunghezza della lista: le righe
in arrivo sono righe di fattura (una fattura da 40 articoli e' 40 righe). Un
conteggio di righe direbbe "40 fatture" dove ce n'e' una — e resterebbe verde su
un test che passa una riga per documento, che e' il modo tipico di non
accorgersene.
"""
from services.routers.prezzi import _conta_fatture_distinte


def _riga(file_origine, **kw):
    """Le colonne che `_load_fatture_for_prezzi` seleziona davvero: il calcolo
    vero le legge tutte, e una fixture piu' magra lo fa esplodere invece di
    misurarlo."""
    r = {
        "file_origine": file_origine,
        "descrizione": "X",
        "categoria": "CARNE",
        "fornitore": "FORN",
        "prezzo_unitario": 1.0,
        "quantita": 1.0,
        "totale_riga": 1.0,
        "data_documento": "2025-03-01",
        "tipo_documento": "TD01",
    }
    r.update(kw)
    return r


def test_nessuna_riga_nessuna_fattura():
    """Il caso che fa la differenza: 0 e' cio' che spegne la rassicurazione."""
    assert _conta_fatture_distinte([]) == 0


def test_una_fattura_di_molte_righe_resta_una():
    """La direzione che un conteggio di righe sbaglierebbe: 40 righe, 1 fattura."""
    righe = [_riga("F1.xml", descrizione=f"ART{i}") for i in range(40)]
    assert _conta_fatture_distinte(righe) == 1


def test_fatture_diverse_si_contano_tutte():
    righe = [_riga("F1.xml"), _riga("F2.xml"), _riga("F3.xml")]
    assert _conta_fatture_distinte(righe) == 3


def test_righe_mescolate_contano_i_documenti():
    """L'ordine non e' garantito: le righe arrivano ordinate per data, non per
    documento, quindi lo stesso file_origine ricompare piu' avanti."""
    righe = [_riga("F1.xml"), _riga("F2.xml"), _riga("F1.xml"), _riga("F2.xml"), _riga("F3.xml")]
    assert _conta_fatture_distinte(righe) == 3


def test_file_origine_assente_non_conta():
    """Una riga senza documento non e' una fattura in piu'. Conta perche' `None`
    dentro un set diventerebbe un elemento, cioe' una fattura fantasma."""
    righe = [_riga("F1.xml"), {"descrizione": "senza origine"}]
    assert _conta_fatture_distinte(righe) == 1


def test_file_origine_vuoto_non_conta():
    """Stringa vuota: stesso caso di `None`, e piu' facile da lasciar passare."""
    righe = [_riga("F1.xml"), _riga("")]
    assert _conta_fatture_distinte(righe) == 1


def test_solo_righe_senza_origine_danno_zero():
    """Il caso che deve comportarsi come "nessuna fattura", non come "una"."""
    assert _conta_fatture_distinte([{"descrizione": "a"}, _riga("")]) == 0


# ── Il wiring: che l'endpoint lo POPOLI davvero ─────────────────────────────
#
# I test sopra provano la funzione. Provare la funzione non prova che qualcuno la
# usi: mutando via `fatture_nel_periodo=...` dalla `return VariazioniResponse(...)`
# restavano tutti verdi, e anche `export_openapi --check-drift` (lo schema nasce
# dalla DICHIARAZIONE del campo, non dall'assegnazione). Il rilievo e' del
# code-reviewer; questi due test chiudono il buco.

from unittest.mock import MagicMock, patch

import services.routers.prezzi as prezzi_router


def _endpoint_con(righe):
    """Chiama l'endpoint vero con auth e Supabase fuori gioco.

    `_calcola_variazioni_prezzi_sync` resta quello vero: non e' il soggetto qui,
    e su righe con un solo prezzo per prodotto non produce variazioni — lo stato
    vuoto, cioe' proprio il caso in cui il campo decide il messaggio.
    """
    with patch.object(prezzi_router, "_resolve_user_from_token", MagicMock(return_value={"id": "u1"})), \
         patch.object(prezzi_router, "_get_supabase_client", MagicMock(return_value=object())), \
         patch.object(prezzi_router, "_resolve_ristorante_id", MagicMock(return_value="r1")), \
         patch.object(prezzi_router, "_load_fatture_for_prezzi", MagicMock(return_value=righe)), \
         patch.object(prezzi_router, "_carica_preferiti_keys", MagicMock(return_value=set())):
        return prezzi_router.get_variazioni_prezzi(
            data_da="2025-01-01", data_a="2025-12-31", authorization="Bearer x",
        )


def test_endpoint_riporta_le_fatture_del_periodo():
    """Due documenti, quattro righe: la response deve dire 2, non 4 e non 0."""
    righe = [
        _riga("F1.xml", descrizione="A", data_documento="2025-03-01"),
        _riga("F1.xml", descrizione="B", data_documento="2025-03-01"),
        _riga("F2.xml", descrizione="C", data_documento="2025-04-01"),
        _riga("F2.xml", descrizione="D", data_documento="2025-04-01"),
    ]
    assert _endpoint_con(righe).fatture_nel_periodo == 2


def test_endpoint_su_periodo_vuoto_dice_zero_non_none():
    """La distinzione che regge tutto il messaggio dell'Osservatorio: `0` e'
    "nessuna fattura" (niente rassicurazione), `None` sarebbe "non lo so".
    Il periodo vuoto e' un fatto misurato, e deve arrivare come 0."""
    resp = _endpoint_con([])
    assert resp.fatture_nel_periodo == 0
    assert resp.fatture_nel_periodo is not None
    assert resp.variazioni == []
