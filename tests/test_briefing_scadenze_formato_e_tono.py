"""Audit briefing 3/9 (voce §3 #4): i due fix della passata.

1. FORMATO — i bullet delle scadenze scrivevano gli importi con l'f-string nuda
   (`{totale:,.2f}` -> "€ 1,234.50"): separatori INGLESI in un testo che legge un
   ristoratore italiano. Latente (0 bullet scadenze su 42 snapshot in cache — le
   notifiche scadenza non vengono generate dall'1/6), ma il primo cliente con una
   scadenza in card avrebbe letto migliaia e decimali invertiti.

2. TONO — il validatore della narrativa scartava numeri inventati e burocratese,
   ma l'entusiasmo vietato dalla regola 3/3-bis del prompt ('fantastico',
   'continua così'...) viveva solo nel prompt. Un prompt senza validazione è un
   auspicio: il burocratese l'aveva già dimostrato.
"""
import pytest

from services.daily_briefing_service import _bullet_for, _narrazione_e_valida


class TestFormatoItalianoScadenze:
    def test_scadenza_superata_migliaia_col_punto_decimali_con_virgola(self):
        b = _bullet_for({
            "topic_key": "scadenza_superata",
            "payload": {"count": 2, "totale": 1234.5},
            "title": "x",
        })
        assert "€ 1.234,50" in b
        assert "1,234.50" not in b

    def test_scadenza_imminente_stesso_formato(self):
        b = _bullet_for({
            "topic_key": "scadenza_imminente",
            "payload": {"count": 1, "totale": 987.4},
            "title": "x",
        })
        assert "€ 987,40" in b

    def test_importo_grande_reale(self):
        """300 scadenze per 4,4 M€ è il caso vero dello scadenziario."""
        b = _bullet_for({
            "topic_key": "scadenza_superata",
            "payload": {"count": 300, "totale": 4400000.0},
            "title": "x",
        })
        assert "€ 4.400.000,00" in b


class TestValidatoreTono:
    _BULLETS = ["🔥 Maggio chiuso con € 13.059 di margine, +26,5% rispetto ad aprile."]

    @pytest.mark.parametrize("testo", [
        "Fantastico! Maggio chiuso con € 13.059 di margine.",
        "Maggio è andato bene, continua così.",
        "Che bello, il margine cresce: € 13.059.",
        "Il margine di maggio è ottimo: € 13.059.",
    ])
    def test_l_entusiasmo_vietato_fa_cadere_la_narrativa(self, testo):
        valida, motivo = _narrazione_e_valida(testo, self._BULLETS)
        assert valida is False
        assert "formula vietata" in motivo

    def test_il_tono_sobrio_passa(self):
        valida, _ = _narrazione_e_valida(
            "Maggio si è chiuso con € 13.059 di margine, +26,5% su aprile.",
            self._BULLETS,
        )
        assert valida is True

    @pytest.mark.parametrize("testo", [
        # Linguaggio contabile legittimo (rilievo review 3/9): la degradazione al
        # template è silenziosa, un falso positivo qui costa più del beneficio.
        "Nel margine di maggio (€ 13.059) pesano spese straordinarie da controllare.",
        "La manutenzione straordinaria è registrata nel margine di maggio: € 13.059.",
    ])
    def test_il_linguaggio_contabile_non_e_entusiasmo(self, testo):
        valida, _ = _narrazione_e_valida(testo, self._BULLETS)
        assert valida is True

    def test_ottimizzare_non_e_ottimo(self):
        """' ottimo' non deve matchare dentro parole diverse."""
        valida, _ = _narrazione_e_valida(
            "Per ottimizzare i margini di maggio (€ 13.059) controlla i costi.",
            self._BULLETS,
        )
        assert valida is True
