"""Pagina Impostazioni → account (`lib/impostazioni-account.ts`).

Perche' esiste: erano tre pezzi di logica dentro il JSX di `account-client.tsx`,
cioe' fuori portata dell'unica rete del frontend (`npx tsc --noEmit`, che
controlla i tipi e non esegue niente). Coperti qui:

1. la barra di utilizzo (soglie 70/90 e clamp), che il cliente vede su fatture
   e domande all'assistente;
2. i tre stati dell'assistente AI, che nel .tsx erano due condizioni annidate;
3. le due conferme distruttive, che hanno regole DIVERSE di proposito.

La logica e' stata confrontata con l'originale di HEAD tramite un oracolo su 225
combinazioni (NaN e Infinity inclusi): 0 divergenze.
"""

from tests.helpers_ts import esegui_ts

MODULO = "lib/impostazioni-account"
FUNZIONI = [
    "statoUsageBar",
    "statoChatAi",
    "confermaSvuotamentoValida",
    "confermaEliminazioneValida",
]


def _barra(usate, limite):
    return esegui_ts(
        MODULO, "emit(m.statoUsageBar(...input));", argomento=[usate, limite], richiede=FUNZIONI
    )


def _chat(limite, usate=0, pool=False):
    return esegui_ts(
        MODULO, "emit(m.statoChatAi(...input));", argomento=[limite, usate, pool], richiede=FUNZIONI
    )


def _conferma(funzione, testo):
    return esegui_ts(
        MODULO, f"emit(m.{funzione}(input));", argomento=testo, richiede=FUNZIONI
    )


# ─── barra di utilizzo: le soglie sono confini inclusivi ─────────────────────

def test_soglie_sono_inclusive():
    """69 -> ok, 70 -> attenzione, 89 -> attenzione, 90 -> critico.
    Il confine e' il punto dove un `>=` diventato `>` non si vedrebbe a occhio."""
    assert _barra(69, 100)["livello"] == "ok"
    assert _barra(70, 100)["livello"] == "attenzione"
    assert _barra(89, 100)["livello"] == "attenzione"
    assert _barra(90, 100)["livello"] == "critico"


def test_avviso_appare_solo_in_critico():
    """Nel .tsx colore e avviso erano due confronti `>= 90` distinti: qui
    derivano dallo stesso livello e non possono disallinearsi."""
    assert _barra(89, 100)["mostraAvviso"] is False
    assert _barra(90, 100)["mostraAvviso"] is True


def test_arrotondamento_sposta_il_confine():
    """895/1000 = 89,5% -> Math.round -> 90 -> critico. Non e' un dettaglio:
    e' un cliente che riceve l'avviso mezzo punto percentuale prima."""
    assert _barra(895, 1000) == {"pct": 90, "livello": "critico", "mostraAvviso": True}


def test_oltre_il_limite_resta_a_cento():
    """Senza clamp la barra CSS andrebbe oltre il contenitore."""
    assert _barra(150, 100)["pct"] == 100
    assert _barra(150, 100)["livello"] == "critico"


def test_limite_zero_da_barra_vuota_non_illimitato():
    """Comportamento attuale DELIBERATO, congelato qui perche' e' controintuitivo:
    con limite 0 la barra e' vuota e verde, non "illimitato". In pratica non
    capita (PIANO_LIMITE_FATTURE_DEFAULT = 50), e cambiarlo sarebbe una modifica
    di prodotto, non un fix."""
    assert _barra(10, 0) == {"pct": 0, "livello": "ok", "mostraAvviso": False}
    assert _barra(10, -1)["pct"] == 0


def test_nessun_uso():
    assert _barra(0, 50) == {"pct": 0, "livello": "ok", "mostraAvviso": False}


# ─── assistente AI: tre stati, non due ───────────────────────────────────────

def test_limite_assente_nasconde_il_blocco():
    """`null` e `undefined` sono entrambi "il piano non espone il dato": il
    campo e' opzionale nel tipo, e `!=` copre tutti e due."""
    assert _chat(None)["modo"] == "nascosto"
    assert esegui_ts(
        MODULO, "emit(m.statoChatAi(undefined, 0, false));", richiede=FUNZIONI
    )["modo"] == "nascosto"


def test_limite_zero_e_non_incluso_nel_piano():
    """Distinto da "nascosto": qui il cliente vede l'invito a cambiare piano."""
    assert _chat(0)["modo"] == "non_incluso"


def test_limite_negativo_non_e_una_barra():
    """Comportamento attuale: un limite negativo non e' > 0, quindi ricade in
    "non incluso" invece di disegnare una barra con numeri assurdi."""
    assert _chat(-1)["modo"] == "non_incluso"


def test_pool_di_gruppo_cambia_label_e_nota():
    sede = _chat(10, 3, False)
    gruppo = _chat(10, 3, True)
    assert sede["modo"] == gruppo["modo"] == "barra"
    assert "del gruppo" in gruppo["label"]
    assert "del gruppo" not in sede["label"]
    assert "Pool condiviso" in gruppo["nota"]
    assert "Pool condiviso" not in sede["nota"]


def test_usate_assente_vale_zero():
    """Il contatore puo' mancare nel JSON: senza il default la barra riceverebbe
    undefined e mostrerebbe NaN."""
    assert esegui_ts(
        MODULO, "emit(m.statoChatAi(10, undefined, false));", richiede=FUNZIONI
    )["usate"] == 0


# ─── conferme distruttive: l'asimmetria e' voluta ────────────────────────────

def test_svuotamento_e_case_sensitive():
    """Il worker rivalida allo stesso modo (services/routers/account.py:284,
    confronto diretto con "SVUOTA"): uniformare qui disallineerebbe i due lati."""
    assert _conferma("confermaSvuotamentoValida", "SVUOTA") is True
    assert _conferma("confermaSvuotamentoValida", " SVUOTA ") is True
    assert _conferma("confermaSvuotamentoValida", "svuota") is False


def test_eliminazione_e_case_insensitive():
    """Anche qui e' il backend a dettarlo (account.py:405, `.upper()`).
    L'azione piu' distruttiva ha il gate piu' permissivo: e' deliberato, non una
    svista da "correggere"."""
    for variante in ("ELIMINA", "elimina", "Elimina", " elimina "):
        assert _conferma("confermaEliminazioneValida", variante) is True


def test_testo_diverso_non_conferma_mai():
    for funzione in ("confermaSvuotamentoValida", "confermaEliminazioneValida"):
        assert _conferma(funzione, "") is False
        assert _conferma(funzione, "SVUOTAX") is False
        assert _conferma(funzione, None) is False
