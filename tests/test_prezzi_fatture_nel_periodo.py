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
    r = {"file_origine": file_origine, "descrizione": "X", "prezzo_unitario": 1.0}
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
