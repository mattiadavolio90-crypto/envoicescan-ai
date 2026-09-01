"""Payload del pannello Assistente (`lib/home-config.ts`).

Perche' esiste: questo modulo costruisce il corpo del POST /api/home/config,
cioe' quello che il cliente SALVA. Un campo con il nome sbagliato o un numero
fuori scala non da' nessun errore visibile — il backend accetta e ignora, e la
configurazione resta silenziosamente quella vecchia.

I nomi dei campi sono un contratto con il worker, non una scelta di stile: sono
asseriti qui uno per uno perche' rinominarli e' esattamente il tipo di modifica
che passa `tsc` e rompe la produzione.
"""

from tests.helpers_ts import esegui_ts

MODULO = "lib/home-config"


def _chiama(fn, args, richiede=None):
    return esegui_ts(MODULO, f"emit(m.{fn}(...input));", argomento=args, richiede=richiede or [fn])


def _topic(key, enabled=True, bloccato=False):
    return {"key": key, "enabled": enabled, "bloccato": bloccato}


# ─── normalizzaSoglia: clamp [0,50], default 5 ────────────────────────────

def test_soglia_valore_normale():
    assert _chiama("normalizzaSoglia", ["12"]) == 12


def test_soglia_accetta_la_virgola_italiana():
    """Il campo e' testo libero: un ristoratore ci scrive 7,5."""
    assert _chiama("normalizzaSoglia", ["7,5"]) == 7.5


def test_soglia_sopra_il_massimo_viene_clampata():
    assert _chiama("normalizzaSoglia", ["999"]) == 50


def test_soglia_negativa_viene_clampata_a_zero_dal_max():
    """-10 -> Math.max(0, -10) = 0. Il clamp inferiore esiste ed e' raggiungibile."""
    assert _chiama("normalizzaSoglia", ["-10"]) == 0


def test_soglia_testo_non_numerico_usa_il_default():
    assert _chiama("normalizzaSoglia", ["ciao"]) == 5
    assert _chiama("normalizzaSoglia", [""]) == 5
    assert _chiama("normalizzaSoglia", [None]) == 5


def test_soglia_ZERO_diventa_cinque_ed_e_voluto():
    """`|| 5` cattura NaN ma anche lo zero scritto apposta.

    Non e' una svista: soglia 0 vorrebbe dire "avvisami per qualunque
    variazione", cioe' rumore continuo. Il test lo fissa per iscritto, cosi'
    chi un giorno lo "correggera'" sapra' che stava cambiando una decisione.
    """
    assert _chiama("normalizzaSoglia", ["0"]) == 5


# ─── topics: un bloccato non si spegne mai ────────────────────────────────

def test_disabilitati_elenca_solo_gli_spenti():
    topics = [_topic("a", enabled=False), _topic("b", enabled=True)]
    assert _chiama("topicsDisabilitati", [topics]) == ["a"]


def test_un_topic_BLOCCATO_non_finisce_mai_fra_i_disabilitati():
    """Regola di dominio: i topic non ignorabili restano accesi.

    Anche se arrivasse gia' con enabled=false (payload vecchio, bug altrove),
    non deve essere mandato come disabilitato.
    """
    topics = [_topic("critico", enabled=False, bloccato=True), _topic("x", enabled=False)]
    assert _chiama("topicsDisabilitati", [topics]) == ["x"]


def test_toggle_non_spegne_un_bloccato():
    topics = [_topic("critico", enabled=True, bloccato=True)]
    out = _chiama("toggleTopic", [topics, "critico", False])
    assert out[0]["enabled"] is True


def test_toggle_conserva_i_campi_extra():
    """I topic reali portano label/descrizione: il toggle non deve perderli.

    Una firma non generica li scartava — preso da `tsc`, fissato qui.
    """
    topics = [{"key": "a", "enabled": True, "bloccato": False, "label": "Alert", "descrizione": "d"}]
    out = _chiama("toggleTopic", [topics, "a", False])
    assert out[0]["label"] == "Alert" and out[0]["descrizione"] == "d"
    assert out[0]["enabled"] is False


def test_alert_prezzi_default_acceso_se_il_topic_manca():
    assert _chiama("alertPrezziAttivo", [[]]) is True
    assert _chiama("alertPrezziAttivo", [[_topic("price_alert", enabled=False)]]) is False


# ─── il payload intero: i nomi dei campi sono il contratto ────────────────

def test_payload_ha_ESATTAMENTE_i_campi_che_il_backend_si_aspetta():
    """`price_alert_threshold`, non "soglia". Il nome e' il contratto.

    Scrivendo questo modulo avevo inventato `soglia_variazione_prezzo`: il
    backend l'avrebbe ignorato in silenzio, e la soglia non si sarebbe piu'
    salvata senza un solo errore a schermo.
    """
    out = _chiama("costruisciPayloadConfig", [{
        "topics": [_topic("a", enabled=False)],
        "soglia": "10",
        "nome": "  Mario  ",
        "chatEnabled": True,
        "giorniChiusura": 2,
    }])
    assert sorted(out.keys()) == sorted([
        "nome_referente", "topics_disabled", "chat_ai_enabled",
        "price_alert_threshold", "giorni_chiusura_settimanali",
    ])
    assert out["nome_referente"] == "Mario"        # trimmato
    assert out["price_alert_threshold"] == 10
    assert out["topics_disabled"] == ["a"]


def test_payload_nome_vuoto_diventa_null_non_stringa_vuota():
    """Il backend distingue "nessun referente" (null) da "" — che salverebbe
    un nome vuoto e romperebbe il saluto della Home."""
    out = _chiama("costruisciPayloadConfig", [{
        "topics": [], "soglia": "5", "nome": "   ", "chatEnabled": False, "giorniChiusura": 0,
    }])
    assert out["nome_referente"] is None
