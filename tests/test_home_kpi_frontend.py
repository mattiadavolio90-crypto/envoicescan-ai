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


import pytest

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



# ─── vociCompletezza: la card della completezza apre solo cio' che manca ────
#
# Step 3 dell'interfaccia (28/9/2026): la card era alta mezza pagina perche'
# ogni voce, anche a posto, aveva la sua riga con dettaglio. Ora si aprono solo
# le voci da sistemare; quelle a posto stanno in una riga coi nomi.


def _v(key, ok):
    return {"key": key, "label": key.upper(), "ok": ok, "dettaglio": f"d-{key}", "cta_page": None}


def test_voci_divise_in_da_sistemare_e_a_posto_nell_ordine_del_backend():
    voci = [_v("a", True), _v("b", False), _v("c", True), _v("d", False)]
    out = _chiama("vociCompletezza", [voci])
    assert [v["key"] for v in out["daSistemare"]] == ["b", "d"]
    assert [v["key"] for v in out["aPosto"]] == ["a", "c"]


def test_voce_senza_ok_non_e_a_posto():
    """Un campo assente (backend vecchio, rinomina) non deve finire fra le voci
    a posto: lo stesso default prudente di tutta la Home."""
    voce = {"key": "x", "label": "X", "dettaglio": "", "cta_page": None}
    out = _chiama("vociCompletezza", [[voce]])
    assert [v["key"] for v in out["daSistemare"]] == ["x"]
    assert out["aPosto"] == []


def test_voci_assenti_non_rompono_la_card():
    assert _chiama("vociCompletezza", [None]) == {"daSistemare": [], "aPosto": []}


# ─── I mesi di ferie (fase E del piano consulente, 8/10/2026) ──────────────
#
# Il worker azzera le frecce quando il mese mostrato o quello di confronto ha
# un incasso fuori norma (ferie): la card deve dire perche'.

def test_confronto_con_un_mese_di_ferie_dice_perche_manca():
    out = _chiama("testoConfronto", [{"confronto_label": None, "confronto_escluso": "agosto"}])
    assert out == "nessun confronto con agosto: incasso fuori dal solito"


def test_confronto_normale_resta_l_etichetta_del_worker():
    assert _chiama("testoConfronto", [{"confronto_label": "vs agosto"}]) == "vs agosto"
    assert _chiama("testoConfronto", [{"confronto_label": None, "confronto_escluso": None}]) is None


def test_avviso_mese_di_ferie():
    out = _chiama("avvisoIncassoFuoriNorma",
                  [{"incasso_fuori_norma": True, "periodo_label": "Agosto"}, "food cost"])
    assert out.startswith("Nel mese di agosto l'incasso è stato molto più basso del solito")
    assert "il food cost e il margine di questo mese non sono un allarme" in out


@pytest.mark.parametrize("valore", [False, None, "true", 1])
def test_avviso_solo_col_booleano_vero(valore):
    """Un worker vecchio (campo assente) o un valore strano: nessun avviso."""
    kpi = {"periodo_label": "Agosto"}
    if valore is not None:
        kpi["incasso_fuori_norma"] = valore
    assert _chiama("avvisoIncassoFuoriNorma", [kpi, "food cost"]) is None
