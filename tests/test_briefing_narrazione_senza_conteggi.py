"""Il briefing non deve passare all'AI i conteggi che il prompt le vieta di ripetere,
e deve scartare le narrative che inventano numeri o usano il burocratese.

Origine: misurato su daily_briefing_state il 2/9/2026. Snapshot reale del 28/8:
"Controlla i 100 prodotti che necessitano di verifica" — il prompt (3-septies e tono
rassicurante di _narrative_phrase_for) vieta il numero crudo, ma _build_snapshot
passava all'AI il bullet della CARD, che il numero ce l'ha. Il modello lo ricopiava.
Nella stessa misura: "e' necessario completare questo dato", vietato dalla 3-octies.

I conteggi usati qui sono quelli VERI delle sedi (112 San Giuliano, 100 Villa
Guardia, 29 LAND), non valori inventati.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.daily_briefing_service import (  # noqa: E402
    _anonymize_bullets,
    _bullet_for,
    _bullet_per_narrazione,
    _narrazione_e_valida,
    _numeri_di,
)


def _notif_righe(n):
    return {
        "topic_key": "uncategorized_rows",
        "severity": "warning",
        "title": f"{n} prodotti da controllare",
        "payload": {"uncategorized_rows": n, "count": n},
    }


def _notif_prezzi(count=3, prodotto="SCAMONE WAGYU", pct=6.4, impatto=30):
    return {
        "topic_key": "price_alert",
        "severity": "warning",
        "title": "Alert prezzi",
        "payload": {
            "count": count, "top_product": prodotto,
            "top_increase_pct": pct, "impatto_mese": impatto,
        },
    }


class TestConteggioFuoriDallaNarrazione:
    @pytest.mark.parametrize("n", [112, 100, 29, 37, 18, 5, 3, 1])
    def test_il_conteggio_resta_nella_card_e_sparisce_dalla_narrazione(self, n):
        """Conteggi reali delle sedi in produzione."""
        card = _bullet_for(_notif_righe(n))
        narrazione = _bullet_per_narrazione(_notif_righe(n))
        assert str(n) in card, "la card deve portare il numero: e' utile e cliccabile"
        assert str(n) not in narrazione, (
            f"il conteggio {n} non deve arrivare all'AI: lo ricopia (caso reale 28/8)"
        )

    def test_singolare_e_plurale(self):
        assert "una voce" in _bullet_per_narrazione(_notif_righe(1))
        assert "Ci sono voci" in _bullet_per_narrazione(_notif_righe(2))

    def test_prezzi_perdono_percentuale_e_impatto(self):
        card = _bullet_for(_notif_prezzi())
        narrazione = _bullet_per_narrazione(_notif_prezzi())
        assert "6.4" in card and "30" in card
        assert "6.4" not in narrazione, "la % del singolo prodotto sta solo nella card"
        assert "30" not in narrazione, "l'impatto €/mese sta solo nella card"

    def test_prezzi_mantengono_emoji_e_nome_per_anonimizzazione(self):
        """L'emoji 📈 e' come _anonymize_bullets riconosce il bullet: se sparisce,
        il nome del prodotto verrebbe inviato in chiaro a OpenAI."""
        narrazione = _bullet_per_narrazione(_notif_prezzi())
        assert narrazione.lstrip().startswith("\U0001F4C8")
        anon, mapping = _anonymize_bullets([narrazione])
        assert "SCAMONE WAGYU" not in anon[0], "il nome non deve uscire verso OpenAI"
        assert mapping.get("<<P1>>") == "SCAMONE WAGYU", (
            "il segnaposto deve catturare SOLO il nome, non la coda della frase"
        )
        assert "card qui sotto" in anon[0], (
            "il rimando alla card deve restare leggibile per l'AI"
        )

    def test_gli_altri_topic_restano_identici(self):
        """Solo i topic in _TOPIC_SENZA_CONTEGGIO_IN_NARRAZIONE cambiano."""
        for topic, payload in [
            ("fatturato_mancante", {"mese": "agosto", "anno": 2026}),
            ("incasso_mancante", {}),
            ("scadenza_superata", {"count": 2, "totale": 1500.0}),
        ]:
            n = {"topic_key": topic, "severity": "warning", "title": "x", "payload": payload}
            assert _bullet_per_narrazione(n) == _bullet_for(n)


class TestValidazioneNarrativaAI:
    def test_rifiuta_il_caso_reale_del_28_agosto(self):
        bullets = [_bullet_per_narrazione(_notif_righe(100))]
        testo = "Ieri hai registrato un incasso. Controlla i 100 prodotti che necessitano di verifica."
        valida, motivo = _narrazione_e_valida(testo, bullets)
        assert valida is False
        assert "100" in motivo

    @pytest.mark.parametrize("formula", [
        "è necessario completare questo dato",
        "e' necessario intervenire",
        "si rende necessario un controllo",
        "provvedi a inserire il dato",
    ])
    def test_rifiuta_il_burocratese_vietato(self, formula):
        valida, motivo = _narrazione_e_valida(f"Il fatturato manca, {formula}.", [])
        assert valida is False
        assert "formula vietata" in motivo

    def test_rifiuta_numeri_inventati(self):
        valida, motivo = _narrazione_e_valida(
            "Ci sono voci da controllare e un calo del 47% sui margini.", []
        )
        assert valida is False
        assert "47" in motivo

    def test_accetta_i_numeri_veri_dei_bullet(self):
        """Regressione opposta: il validatore non deve tagliare i dati calcolati.
        L'incasso, i coperti e lo scontrino DEVONO poter essere riportati."""
        bullets = [
            "\U0001F4B0 Ieri (giovedì) sono entrati € 13.059 di incasso, in linea con "
            "la media dei giovedì (~€ 14.120). 458 coperti, scontrino medio € 26,47.",
        ]
        testo = (
            "Ieri sono entrati 13.059 euro, in linea con la media dei giovedì di "
            "14.120, con 458 coperti e uno scontrino medio di 26,47."
        )
        valida, motivo = _narrazione_e_valida(testo, bullets)
        assert valida is True, f"numeri legittimi respinti: {motivo}"

    def test_rifiuta_un_numero_alterato(self):
        bullets = ["\U0001F4B0 Ieri sono entrati € 13.059 di incasso."]
        valida, motivo = _narrazione_e_valida("Ieri sono entrati 13.559 euro.", bullets)
        assert valida is False, "un importo modificato deve essere respinto"
        assert "13559" in motivo

    def test_narrativa_vuota_non_e_valida(self):
        assert _narrazione_e_valida("", ["x"])[0] is False

    def test_numeri_normalizza_separatori_italiani(self):
        """'€ 13.059' e '13059' sono lo stesso numero; '26,47' e '26.47' pure."""
        assert _numeri_di("€ 13.059") == _numeri_di("13059")
        assert _numeri_di("26,47") == _numeri_di("26.47")


class TestFallbackSuNarrazioneInvalida:
    def test_narrate_with_ai_ricade_sul_template(self, monkeypatch):
        """Se il modello viola le regole, il cliente vede il template — non il testo
        inventato. Prima nessuno controllava: passava qualsiasi cosa non vuota."""
        import services.daily_briefing_service as dbs

        class _Msg:
            content = "Controlla i 100 prodotti che necessitano di verifica."

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]
            usage = None

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**_kw):
                        return _Resp()

        monkeypatch.setattr(
            "services.ai_service._get_openai_client", lambda: _Client(), raising=False
        )
        monkeypatch.setattr(
            "services.ai_service._resolve_ristorante_id", lambda: None, raising=False
        )

        fallback = "Ci sono voci da controllare, le trovi nelle card."
        out = dbs._narrate_with_ai(
            [_bullet_per_narrazione(_notif_righe(100))], fallback
        )
        assert out == fallback, "una narrativa invalida deve ricadere sul template"
