"""Gli euro fuori dai margini sopravvivono alla morte del banner (Fase 4, 9/9/2026).

La card grande «Righe da classificare» in fondo alla Home è stata eliminata: era
un doppione visivo della voce «N prodotti da controllare» che il briefing mostra
già in cima. La sua informazione — quanti € restano ESCLUSI da margini e food
cost — è entrata nel briefing come SECONDA riga della stessa card.

Tre cose che questi test tengono ferme, e che senza presidio si perderebbero in
silenzio:

1. **Le due popolazioni non si fondono.** `testo` conta i PRODOTTI DISTINTI
   `needs_review` degli ultimi 7 giorni; `dettaglio` conta le RIGHE
   'Da Classificare' di tutto lo storico, che sono quelle davvero fuori dai
   margini. Sono due fatti diversi sulla stessa pagina: restano due frasi.
   Legarle ("2 prodotti, 86 € esclusi") sarebbe falso — è il bug B3 daccapo.

2. **Dato assente ≠ zero.** Se la lettura degli esclusi fallisce nel worker, le
   chiavi non entrano nel payload e la riga non si stampa. Un "0 €" direbbe al
   cliente «nessun euro escluso» mentre la query è morta: il falso verde già
   pagato da card-segnali.

3. **L'arretrato piccolo continua a parlare.** Un cliente con 0 novità e meno di
   DA_CONTROLLARE_ARRETRATO_SOGLIA prodotti arretrati non ha né card né riga
   dell'arretrato: prima gli euro glieli diceva SOLO il banner. Ora gli euro sono
   una ragione PROPRIA per emettere il record e per dirlo in narrativa.
"""
import pytest

from services.fastapi_worker import (
    DA_CONTROLLARE_ARRETRATO_SOGLIA,
    SaluteDaClassificare,
    _briefing_righe_da_classificare,
)
from services.daily_briefing_service import _action_for, _dettaglio_esclusi


# ─── Impalcatura: il worker legge `fatture` due volte (needs_review, poi gli
# esclusi via _card_da_classificare). Si serve l'una o l'altra dai filtri.

class _Query:
    def __init__(self, risolvi):
        self._risolvi = risolvi
        self.filtri = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self.filtri.append(("neq", col, val))
        return self

    def is_(self, col, val):
        self.filtri.append(("is", col, val))
        return self

    def range(self, offset, end):
        self._offset, self._end = offset, end
        return self

    def execute(self):
        righe = self._risolvi(self.filtri)

        class _R:
            data = righe[self._offset:self._end + 1]
        return _R()


class _SB:
    def __init__(self, risolvi):
        self._risolvi = risolvi

    def table(self, _nome):
        return _Query(self._risolvi)


def _sb(needs_review=(), esclusi=()):
    def risolvi(filtri):
        if ("eq", "needs_review", True) in filtri:
            return list(needs_review)
        if ("eq", "categoria", "Da Classificare") in filtri:
            return list(esclusi)
        raise AssertionError(f"query inattesa: {filtri}")
    return _SB(risolvi)


def _riga(desc, quando="2099-01-01T00:00:00"):
    """Una riga needs_review. Data lontana nel futuro = sempre 'novità'."""
    return {"descrizione": desc, "created_at": quando}


VECCHIA = "2000-01-01T00:00:00"


# ─── 1. Le due popolazioni convivono senza fondersi ────────────────────────

def test_gli_euro_esclusi_arrivano_nel_payload_accanto_ai_prodotti():
    rec = _briefing_righe_da_classificare(
        "rid", _sb(needs_review=[_riga("PANE"), _riga("OLIO")],
                   esclusi=[{"totale_riga": 86.4}]),
    )
    assert rec is not None
    pay = rec["payload"]
    # Il conteggio dei prodotti resta quello di prima: gli esclusi non lo toccano.
    assert pay["count"] == 2
    assert pay["esclusi_righe"] == 1
    assert pay["esclusi_importo"] == pytest.approx(86.4)


def test_le_due_frasi_restano_separate_e_dicono_numeri_diversi():
    """Il testo parla di 2 prodotti, il dettaglio di 1 riga da 86 €: due fatti."""
    rec = _briefing_righe_da_classificare(
        "rid", _sb(needs_review=[_riga("PANE"), _riga("OLIO")],
                   esclusi=[{"totale_riga": 86.4}]),
    )
    azione = _action_for(rec)
    assert azione["testo"] == "\U0001F3F7️ 2 prodotti da controllare."
    assert azione["dettaglio"] == (
        "€ 86 esclusi da margini e food cost finché non la sistemi"
    )
    # Nessuna frase che leghi il conteggio all'importo: sarebbero due
    # popolazioni accostate come se fossero la stessa.
    assert "2 prodotti" not in azione["dettaglio"]


def test_singolare_e_plurale_sopravvivono_alla_migrazione():
    una = _dettaglio_esclusi({
        "topic_key": "uncategorized_rows",
        "payload": {"esclusi_righe": 1, "esclusi_importo": 86.4},
    })
    tante = _dettaglio_esclusi({
        "topic_key": "uncategorized_rows",
        "payload": {"esclusi_righe": 7, "esclusi_importo": 1234.5},
    })
    assert una.endswith("non la sistemi")
    assert tante.endswith("non le sistemi")
    assert "€ 1.234" in tante   # formato italiano, non "1,234.50"


# ─── 2. Dato assente ≠ zero ────────────────────────────────────────────────

def test_su_errore_le_chiavi_restano_assenti_e_la_riga_non_si_stampa(monkeypatch):
    """La lettura degli esclusi fallisce: niente chiavi, niente riga. Mai "0 €"."""
    monkeypatch.setattr(
        "services.fastapi_worker._card_da_classificare", lambda *_a, **_k: None
    )
    rec = _briefing_righe_da_classificare(
        "rid", _sb(needs_review=[_riga("PANE"), _riga("OLIO")]),
    )
    assert rec is not None            # la card dei prodotti c'è comunque
    assert "esclusi_importo" not in rec["payload"]
    assert "esclusi_righe" not in rec["payload"]
    azione = _action_for(rec)
    assert "dettaglio" not in azione
    assert "esclusi" not in azione["testo"]


def test_zero_euro_esclusi_non_produce_la_riga():
    """Zero VERO (non errore): non c'è nulla da dire, e non si dice."""
    rec = _briefing_righe_da_classificare(
        "rid", _sb(needs_review=[_riga("PANE")], esclusi=[]),
    )
    assert rec["payload"]["esclusi_importo"] == 0
    assert "dettaglio" not in _action_for(rec)


# ─── 3. L'arretrato piccolo continua a parlare ─────────────────────────────

def test_arretrato_piccolo_con_euro_esclusi_emette_comunque_il_record():
    """0 novità, 3 prodotti arretrati (sotto soglia 20), 86 € esclusi.

    È lo stato normale di un piccolo arretrato — il PV dello screenshot del 9/9
    ci arriva fra otto giorni. Prima lo copriva SOLO il banner: senza questo
    ramo gli 86 € non sarebbero scritti da nessuna parte.
    """
    assert DA_CONTROLLARE_ARRETRATO_SOGLIA == 20
    rec = _briefing_righe_da_classificare(
        "rid",
        _sb(needs_review=[_riga(f"P{i}", VECCHIA) for i in range(3)],
            esclusi=[{"totale_riga": 86.4}]),
    )
    assert rec is not None, "gli euro esclusi sono una ragione propria per parlare"
    assert rec["payload"]["count"] == 0        # nessuna novità: nessuna card
    assert rec["payload"]["arretrato"] == 3
    assert rec["payload"]["esclusi_importo"] == pytest.approx(86.4)


def test_arretrato_piccolo_il_titolo_non_accosta_prodotti_e_righe():
    """Se si parla solo per gli euro, il titolo conta le RIGHE escluse.

    Dire "3 prodotti da controllare in arretrato" quando la ragione del record
    sono 1 riga e 86 € accosterebbe due popolazioni diverse.
    """
    rec = _briefing_righe_da_classificare(
        "rid",
        _sb(needs_review=[_riga(f"P{i}", VECCHIA) for i in range(3)],
            esclusi=[{"totale_riga": 86.4}]),
    )
    assert rec["title"] == "1 riga non classificata"
    assert "prodotti" not in rec["title"]


def test_arretrato_piccolo_senza_euro_resta_muto():
    """Nessuna novità, arretrato sotto soglia, zero euro esclusi: zero rumore."""
    rec = _briefing_righe_da_classificare(
        "rid",
        _sb(needs_review=[_riga(f"P{i}", VECCHIA) for i in range(3)], esclusi=[]),
    )
    assert rec is None


def test_arretrato_grande_conserva_il_titolo_dei_prodotti():
    """Sopra soglia il record esisteva già: gli euro non gli cambiano il titolo."""
    rec = _briefing_righe_da_classificare(
        "rid",
        _sb(needs_review=[_riga(f"P{i}", VECCHIA) for i in range(25)],
            esclusi=[{"totale_riga": 86.4}]),
    )
    assert rec["title"] == "25 prodotti da controllare in arretrato"
    assert rec["payload"]["esclusi_importo"] == pytest.approx(86.4)


# ─── 4. Il canale narrativa: lo snapshot vero, non solo il record ──────────
#
# Presidio scritto DOVE vive la riga, non su un helper: nelle fasi 2 e 3 di
# questo stesso piano un mutante è sopravvissuto due volte perché il test
# guardava una funzione ausiliaria mentre la riga mutata stava altrove.

def _notifica_uncat(count, arretrato, esclusi_righe=None, esclusi_importo=None):
    payload = {
        "uncategorized_rows": count,
        "count": count,
        "arretrato": arretrato,
        "totale": count + arretrato,
    }
    if esclusi_importo is not None:
        payload["esclusi_righe"] = esclusi_righe
        payload["esclusi_importo"] = esclusi_importo
    return {
        "id": "uncategorized-rows-live-rid",
        "topic_key": "uncategorized_rows",
        "source_type": "live",
        "severity": "info" if count == 0 else "warning",
        "title": "1 riga non classificata" if count == 0 else f"{count} prodotti da controllare",
        "body": "",
        "action_page": "/analisi-fatture?tab=articoli&verifica=1",
        "payload": payload,
        "source_event_at": None,
        "dedupe_key": "uncategorized-rows-live-rid",
    }


def test_narrativa_arretrato_piccolo_dice_gli_euro():
    """0 novità + 3 arretrati (sotto soglia) + 86 €: la narrativa parla lo stesso."""
    from services.daily_briefing_service import _build_snapshot

    snap = _build_snapshot(
        [_notifica_uncat(0, 3, esclusi_righe=1, esclusi_importo=86.4)], use_ai=False
    )
    testo = snap["narrative"]
    assert "86" in testo, "gli euro esclusi devono comparire: prima li diceva il banner"
    assert "esclusi da margini e food cost" in testo
    # Nessuna card: 0 novità. La riga è dell'assistente, non un compito di oggi.
    assert snap["azioni"] == []


def test_narrativa_arretrato_grande_dice_arretrato_e_euro():
    from services.daily_briefing_service import _build_snapshot

    snap = _build_snapshot(
        [_notifica_uncat(0, 112, esclusi_righe=46, esclusi_importo=944.89)],
        use_ai=False,
    )
    testo = snap["narrative"]
    assert "112 prodotti da controllare" in testo
    # _euro_it arrotonda all'intero (944,89 -> "945"), come ovunque nel briefing.
    assert "945" in testo and "esclusi da margini" in testo


def test_narrativa_senza_esclusi_non_inventa_lo_zero():
    """Chiavi assenti (query fallita): la narrativa tace sugli euro, non dice 0."""
    from services.daily_briefing_service import _build_snapshot

    snap = _build_snapshot([_notifica_uncat(0, 112)], use_ai=False)
    testo = snap["narrative"]
    assert "112 prodotti da controllare" in testo
    assert "esclusi da margini" not in testo
    assert "0 esclusi" not in testo and "€ 0" not in testo


def test_la_card_porta_il_dettaglio_fino_allo_snapshot():
    """Percorso completo: notifica -> azioni dello snapshot -> campo dettaglio."""
    from services.daily_briefing_service import _build_snapshot

    snap = _build_snapshot(
        [_notifica_uncat(2, 0, esclusi_righe=1, esclusi_importo=86.4)], use_ai=False
    )
    azioni = [a for a in snap["azioni"] if a["topic_key"] == "uncategorized_rows"]
    assert len(azioni) == 1
    assert azioni[0]["dettaglio"] == (
        "€ 86 esclusi da margini e food cost finché non la sistemi"
    )


# ─── 5. Il totale negativo è un dato, non un'assenza ───────────────────────

def test_importo_negativo_si_dice_comunque():
    """LAND: -1.302,36 € di note di credito non classificate (misurato il 3/9).

    La card grande glielo diceva. Gateare sull'importo (`importo <= 0`) invece
    che sulle righe farebbe sparire la riga proprio dove c'è più da sistemare —
    e in silenzio, che è il modo peggiore.
    """
    out = _dettaglio_esclusi({
        "topic_key": "uncategorized_rows",
        "payload": {"esclusi_righe": 5, "esclusi_importo": -1302.36},
    })
    assert out is not None, "un totale negativo è un dato vero, non un'assenza"
    assert "1.302" in out


def test_zero_righe_tace_anche_con_un_importo_qualsiasi():
    """Nessuna riga esclusa = niente da dire, qualunque cosa dica l'importo."""
    assert _dettaglio_esclusi({
        "topic_key": "uncategorized_rows",
        "payload": {"esclusi_righe": 0, "esclusi_importo": 0.0},
    }) is None
