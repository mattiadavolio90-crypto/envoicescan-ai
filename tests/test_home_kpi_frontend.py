"""Decisioni della Home (`lib/home-kpi.ts`) — quale blocco appare e di che colore.

Perche' esiste: la Home e' la prima pagina che ogni cliente apre, e queste tre
funzioni decidono cosa ci vede. Fino all'1/9/2026 vivevano dentro i componenti,
dove nessun test poteva raggiungerle: l'unica rete su apps/web/ e' `tsc`, che
controlla i tipi e non esegue niente.

`statoBlocchi` in particolare ha gia' prodotto una regressione in produzione
(il ramo "vuoto" non scattava mai quando `salute` era presente, e restava un
buco silenzioso nella pagina): e' il motivo per cui i tre stati sono qui,
separati e coperti uno per uno.
"""

from tests.helpers_ts import esegui_ts

MODULO = "lib/home-kpi"


def _chiama(fn, args, richiede=None):
    return esegui_ts(
        MODULO,
        f"emit(m.{fn}(...input));",
        argomento=args,
        richiede=richiede or [fn],
    )


# ─── tintaTrend: la tabella di verita' a 4 ingressi ────────────────────────

def test_trend_delta_assente_non_si_mostra():
    """Nessun confronto disponibile: "—", non uno zero inventato."""
    out = _chiama("tintaTrend", [{"delta": None, "buonoSeSu": True}])
    assert out["mostra"] is False


def test_trend_sopprimi_vince_su_un_delta_valido():
    """La voce vale 0 nel mese: il confronto con un mese pieno direbbe -100%.

    `sopprimi` deve vincere anche quando il delta c'e' ed e' grande.
    """
    out = _chiama("tintaTrend", [{"delta": -100.0, "buonoSeSu": True, "sopprimi": True}])
    assert out["mostra"] is False


def test_trend_salita_su_voce_dove_salire_e_bene():
    out = _chiama("tintaTrend", [{"delta": 12.5, "buonoSeSu": True}])
    assert (out["mostra"], out["tinta"], out["direzione"]) == (True, True, "su")


def test_trend_salita_su_voce_dove_salire_e_male():
    """Food cost e costi: salire e' un peggioramento, la freccia su e' rossa."""
    out = _chiama("tintaTrend", [{"delta": 12.5, "buonoSeSu": False}])
    assert (out["tinta"], out["direzione"]) == (False, "su")


def test_trend_discesa_su_voce_dove_salire_e_male_e_VERDE():
    out = _chiama("tintaTrend", [{"delta": -3.0, "buonoSeSu": False}])
    assert (out["tinta"], out["direzione"]) == (True, "giu")


def test_trend_delta_zero_e_grigio_non_verde():
    """Un delta nullo non e' una vittoria: nessun giudizio, freccia piatta."""
    out = _chiama("tintaTrend", [{"delta": 0.0, "buonoSeSu": True}])
    assert (out["mostra"], out["tinta"], out["direzione"]) == (True, None, "piatto")


def test_trend_neutro_non_festeggia_un_mol_in_perdita():
    """Decisione Mattia 19/06: un MOL da -5000 a -1188 e' "meno peggio".

    Il delta resta visibile (la freccia sale), ma MAI in verde: colorare di
    verde una perdita che si riduce e' una falsa celebrazione.
    """
    out = _chiama("tintaTrend", [{"delta": 3812.0, "buonoSeSu": True, "neutro": True}])
    assert out["mostra"] is True
    assert out["direzione"] == "su"
    assert out["tinta"] is None       # niente verde


def test_trend_neutro_non_maschera_un_peggioramento():
    """`neutro` toglie il verde, non il rosso: un calo resta un calo."""
    out = _chiama("tintaTrend", [{"delta": -500.0, "buonoSeSu": True, "neutro": True}])
    assert out["direzione"] == "giu"
    assert out["tinta"] is None


# ─── statoBlocchi: i tre stati che si sono gia' confusi una volta ──────────

def test_stato_worker_giu_quando_non_risponde_nulla():
    """Entrambi assenti = worker giu' (cold start/timeout) -> retry.

    Mostrare "Nessuna fattura" a un cliente che ha dati veri e' il modo
    peggiore di sbagliare: sembra che i suoi dati siano spariti.
    """
    assert _chiama("statoBlocchi", [None, None]) == "worker-giu"


def test_stato_vuoto_con_risposta_ma_senza_margini():
    assert _chiama("statoBlocchi", [{"has_data": False}, None]) == "vuoto"


def test_stato_vuoto_ANCHE_con_salute_presente():
    """La regressione vera: `vuoto` non deve dipendere da `salute`.

    Un cliente nuovo puo' avere un indice di salute (calcolato su altre
    componenti) e zero margini insieme. Prima la condizione richiedeva anche
    `!salute`, quindi il messaggio non compariva mai e restava un buco muto.
    """
    out = _chiama("statoBlocchi", [{"has_data": False}, {"indice": 72}])
    assert out == "vuoto"


def test_stato_dati_quando_ci_sono():
    assert _chiama("statoBlocchi", [{"has_data": True}, {"indice": 72}]) == "dati"


def test_stato_salute_sola_non_e_worker_giu():
    """Salute risponde e kpi no: il worker c'e', non e' il caso del retry."""
    assert _chiama("statoBlocchi", [None, {"indice": 50}]) == "dati"


# ─── chatVisibile: due default con verso opposto, di proposito ─────────────

def test_chat_visibile_con_config_completa():
    assert _chiama("chatVisibile", [{"chat_ai_enabled": True, "chat_limite_giorno": 20}]) is True


def test_chat_nascosta_su_piano_senza_quota():
    """Piano free: limite 0 -> niente chat, anche se il flag e' acceso."""
    assert _chiama("chatVisibile", [{"chat_ai_enabled": True, "chat_limite_giorno": 0}]) is False


def test_chat_nascosta_se_disattivata():
    assert _chiama("chatVisibile", [{"chat_ai_enabled": False, "chat_limite_giorno": 20}]) is False


def test_chat_default_ottimista_sul_flag_ma_non_sulla_quota():
    """I due default hanno verso OPPOSTO, e non e' una svista.

    Flag assente -> `true`: una config che non arriva non deve spegnere la chat
    a chi l'ha pagata. Quota assente -> `0`: regalare quota, invece, no.
    """
    assert _chiama("chatVisibile", [{"chat_limite_giorno": 20}]) is True    # flag assente
    assert _chiama("chatVisibile", [{"chat_ai_enabled": True}]) is False    # quota assente
    assert _chiama("chatVisibile", [{}]) is False
    assert _chiama("chatVisibile", [None]) is False


def test_chat_quota_negativa_non_apre():
    """Difesa: un limite negativo non deve passare il `> 0`."""
    assert _chiama("chatVisibile", [{"chat_ai_enabled": True, "chat_limite_giorno": -5}]) is False
