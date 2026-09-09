"""Il briefing non deve dire la stessa cosa due volte a due righe di distanza.

Difetto visto sullo screenshot della Home del 9/9/2026, percorso template
(deterministico, non un capriccio dell'AI):

    📥 Ieri è arrivata una fattura per € 3.283, già registrata; UNA RIGA È DA
    CONTROLLARE, LA TROVI QUI SOTTO.
    Da sistemare oggi:
    🏷️ CI SONO ALCUNE RIGHE DA CONTROLLARE: TROVI IL DETTAGLIO QUI SOTTO.

Due topic diversi generavano la stessa frase e rimandavano alla STESSA card,
senza sapere l'uno dell'altro: l'apertura `fatture_arrivate`
(_fatture_arrivate_frase) e la voce to-do `uncategorized_rows`
(_narrative_phrase_for). In _build_snapshot apertura e corpo vengono concatenati
senza controllo di sovrapposizione.

Il principio era gia' scritto nel codice — "un solo posto possiede i numeri, il
briefing accenna" (docstring di _fatture_arrivate_frase) — ma non era stato
applicato a questa coda. Il posto che possiede il dato e' la voce to-do, che ha
anche la CTA verso Analisi Fatture.

Lo stesso difetto esisteva in CATENA su un altro tema (fatture di gruppo da
collocare): vedi tests/test_gruppo_briefing.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.daily_briefing_service import (  # noqa: E402
    _build_snapshot,
    _fatture_arrivate_frase,
)
from services.routers.gruppo import RankingPV, SalutePV, _build_briefing  # noqa: E402


def _notifiche(righe_ieri: int, prodotti_da_controllare: int):
    """Lo scenario dello screenshot: fatture arrivate ieri CON righe dubbie, e la
    card 'da controllare' che quelle righe le contiene gia'."""
    return [
        # topic_key "buona_notizia" + payload tipo "fatture_arrivate": e' cosi'
        # che l'apertura entra nello snapshot (_build_snapshot riga 1369).
        {"id": "1", "topic_key": "buona_notizia", "severity": "info",
         "title": "Fatture arrivate", "payload": {
             "tipo": "fatture_arrivate", "n_fatture": 1, "importo": 3283,
             "righe_da_controllare": righe_ieri}},
        {"id": "2", "topic_key": "uncategorized_rows", "severity": "warning",
         "title": f"{prodotti_da_controllare} prodotti da controllare",
         "payload": {"count": prodotti_da_controllare,
                     "uncategorized_rows": prodotti_da_controllare}},
    ]


class TestNienteRipetizionePV:
    def test_da_controllare_compare_una_volta_sola_nel_briefing(self):
        """Il test che mancava del tutto: misura il testo COMPLETO servito al
        cliente (apertura + corpo), non la singola frase."""
        snap = _build_snapshot(_notifiche(righe_ieri=1, prodotti_da_controllare=2),
                               use_ai=False)
        testo = snap["narrative"]

        assert testo.count("da controllare") == 1, (
            f"'da controllare' detto {testo.count('da controllare')} volte: {testo!r}"
        )

    def test_la_novita_delle_fatture_si_dice_comunque(self):
        """Contro-prova: il fix non deve zittire l'apertura positiva — che per le
        sedi SDI senza incasso e' l'UNICA buona notizia del briefing."""
        snap = _build_snapshot(_notifiche(righe_ieri=1, prodotti_da_controllare=2),
                               use_ai=False)
        testo = snap["narrative"]

        assert "3.283" in testo
        assert "fattura" in testo

    def test_la_voce_to_do_resta_quella_che_rimanda_alla_card(self):
        """Chi possiede il dato e' la voce to-do: se sparisse anche quella, il
        cliente non saprebbe piu' delle righe da controllare."""
        snap = _build_snapshot(_notifiche(righe_ieri=1, prodotti_da_controllare=2),
                               use_ai=False)

        assert "da controllare" in snap["narrative"]
        assert any(a["topic_key"] == "uncategorized_rows" for a in snap["azioni"]), (
            "la card deve restare: e' il posto che ha il conteggio e la CTA"
        )

    def test_apertura_da_sola_non_parla_di_righe(self):
        """La frase in isolamento, con il caso dello screenshot (una riga)."""
        f = _fatture_arrivate_frase(
            {"tipo": "fatture_arrivate", "n_fatture": 1, "importo": 3283,
             "righe_da_controllare": 1}
        )

        assert "controllare" not in f
        assert "qui sotto" not in f
        assert "3.283" in f

    def test_senza_la_card_l_informazione_non_la_dice_nessuno(self):
        """LIMITE NOTO, non un difetto introdotto qui — ma va scritto, non
        nascosto.

        L'apertura tace sulle righe da controllare perche' lo dice la voce to-do.
        La prima stesura di questo test affermava che la card c'e' SEMPRE ("righe
        di ieri => dentro la finestra di 7 giorni"): vero per la finestra
        temporale — entrambe filtrano su `created_at` — ma NON in assoluto. La
        review ha trovato tre casi in cui la card non compare:

          1. TOGGLE UTENTE: la card e' calcolata solo `if "uncategorized_rows"
             not in spenti` (fastapi_worker:6902) e il topic e' disattivabile dal
             configuratore. Il filtro agisce sul `topic_key`, e l'apertura ha
             `topic_key = "buona_notizia"`: chi spegne quella voce PRIMA riceveva
             comunque l'accenno, ora non lo riceve piu' da nessuna parte.
          2. UNITA' DIVERSE: l'apertura conta RIGHE needs_review di ieri, la card
             DESCRIZIONI DISTINTE su 7 giorni; con 0 novita' e arretrato sotto
             soglia _briefing_righe_da_classificare torna None.
          3. _MAX_CARD = 4: `uncategorized_rows` ha priorita' 30, dopo topic piu'
             urgenti; con 4 topic sopra di lui la card viene troncata.

        Il caso 1 e' l'unico dove il taglio PEGGIORA qualcosa, ed e' difendibile:
        chi spegne "Righe da controllare" ha chiesto di non sentirne parlare. I
        casi 2 e 3 esistevano identici prima del fix, perche' la coda
        dell'apertura richiedeva comunque righe dubbie DI IERI.

        Questo test blinda il comportamento E il suo limite: se un domani si
        volesse riportare l'informazione in apertura, si riparte da qui.
        """
        snap = _build_snapshot(_notifiche(righe_ieri=3, prodotti_da_controllare=0),
                               use_ai=False)

        assert not any(a["topic_key"] == "uncategorized_rows" for a in snap["azioni"])
        assert "da controllare" not in snap["narrative"], (
            "senza card nessuno lo dice: limite noto e documentato, non una svista"
        )

    def test_col_toggle_spento_la_novita_delle_fatture_resta(self):
        """Contro-prova sul caso 1: spegnere "Righe da controllare" non deve
        zittire anche l'apertura positiva, che e' un topic diverso."""
        snap = _build_snapshot(
            _notifiche(righe_ieri=1, prodotti_da_controllare=2),
            use_ai=False, topics_disabled=["uncategorized_rows"],
        )

        assert "3.283" in snap["narrative"], "l'apertura non dipende da quel toggle"
        assert "da controllare" not in snap["narrative"], (
            "il cliente ha chiesto di non sentir parlare di righe da controllare"
        )


class TestNienteRipetizioneCatena:
    """Lo stesso difetto, su un altro tema: le fatture di gruppo da collocare.

    Con arretrato e nessuna novita' di ieri uscivano due righe adiacenti:
      "Ci sono fatture di gruppo da collocare: le trovi qui sotto."   (backend)
      "Ci sono 3 fatture di gruppo da collocare qui sotto: assegnale..."  (client)
    I due `if` guardavano la STESSA variabile con polarita' opposta, e la
    protezione lato client copriva solo il caso opposto.
    """

    @staticmethod
    def _briefing(**kw):
        base = dict(
            nome_gruppo="G",
            ranking=[RankingPV(ristorante_id="a", nome="PV A", margine_perc=30.0,
                               fatturato=1000.0, colore="verde", dati_incompleti=False)],
            salute_indice=88, salute_colore="verde", n_segnali=0, sev_max="info",
            salute_pv=[SalutePV(ristorante_id="a", nome="PV A", indice=88, colore="verde")],
        )
        base.update(kw)
        return _build_briefing(**base)

    @pytest.mark.parametrize("arrivate_ieri", [None, 11])
    def test_la_narrativa_non_dice_mai_qui_sotto_sulle_fatture_da_collocare(
        self, arrivate_ieri
    ):
        """La regola generale, non il caso singolo: la narrativa e' CONDIVISA fra
        desktop e mobile, e solo il client sa se la coda esiste. Parametrizzato
        sulle due polarita' proprio perche' il difetto nasceva dal fatto che i due
        rami erano protetti in modo diverso."""
        out = self._briefing(
            n_fatture_da_collocare=3, n_fatture_arrivate_ieri=arrivate_ieri,
            fatture_ieri_da_assegnare=bool(arrivate_ieri),
        )

        assert "qui sotto" not in out.narrativa.lower()

    def test_il_tema_da_collocare_esce_dalla_narrativa_del_tutto(self):
        """Un solo posto possiede il tema: il campo strutturato, che il client
        rende sapendo se la coda c'e'."""
        out = self._briefing(n_fatture_da_collocare=365, n_fatture_arrivate_ieri=None)

        assert "da collocare" not in out.narrativa.lower()
        assert out.n_fatture_da_collocare == 365

    def test_la_novita_di_ieri_si_dice_comunque(self):
        """Contro-prova: l'apertura positiva resta, e' il taglio a essere mirato."""
        out = self._briefing(n_fatture_arrivate_ieri=11, fatture_ieri_da_assegnare=True)

        assert "11 fatture" in out.narrativa
        assert "da assegnare a un locale" in out.narrativa
