"""La scheda «Fatture al commercialista» in Impostazioni (`lib/fatture-commercialista.ts`).

Il cliente attiva l'invio, e quell'attivazione e' il suo consenso: la scheda la
vede solo il titolare, solo a servizio acceso, e il testo che autorizza e' quello
che il worker salvera'.
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/fatture-commercialista"
WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
FREQUENZE = {"settimanale": "ogni lunedì", "quindicinale": "il 1° e il 16 di ogni mese", "mensile": "il 1° di ogni mese"}


def _voce(**campi):
    voce = {"piva": "07863990961", "sedi": ["OFFSIDE", "OVERTIME"], "attivo": False, "sospeso": False,
            "email": None, "frequenza": "settimanale", "attivato_il": None, "recupero_dal": None,
            "ultimo_invio": None, "prossimo_invio": None}
    voce.update(campi)
    return voce


def _stato(**campi):
    stato = {"disponibile": True, "impersonazione": False, "oggi": "2026-10-02", "frequenze": FREQUENZE,
             "testo_autorizzazione": "Autorizzo a {email}, {frequenza}, P.IVA {piva}.", "pive": [_voce()]}
    stato.update(campi)
    return stato


def _chiama(funzione, *argomenti):
    return esegui_ts(MODULO, f"emit(m.{funzione}(...input));", argomento=list(argomenti), richiede=[funzione])


# ─── Quando si vede ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("stato,account,atteso", [
    (_stato(), {}, True),
    (_stato(), {"is_admin": False, "sotto_utente": False}, True),
    (_stato(), {"is_admin": True}, False),
    (_stato(), {"sotto_utente": True}, False),
    (_stato(disponibile=False), {}, False),
    (_stato(impersonazione=True), {}, False),
    (_stato(pive=[]), {}, False),
    (None, {}, False),
])
def test_la_scheda_la_vede_solo_il_titolare_a_servizio_acceso(stato, account, atteso):
    assert _chiama("mostraFattureCommercialista", stato, account) is atteso


# ─── Le parole ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("email,valida", [
    ("studio@esempio.it", True), (" studio@esempio.it ", True), ("a@b", False),
    ("senza-chiocciola", False), ("due@@x.it", False), ("", False), ("con spazio@x.it", False),
])
def test_email_valida_come_il_worker(email, valida):
    assert _chiama("emailValida", email) is valida


def test_il_testo_autorizzato_e_compilato_come_lo_salva_il_worker():
    """Lo stesso testo del worker (TESTO_AUTORIZZAZIONE, compilato da
    testo_autorizzazione): il cliente legge cio' che si salva."""
    from services import invio_commercialista_service as svc
    testo = _chiama("testoAutorizzazione", svc.TESTO_AUTORIZZAZIONE, " Studio@Esempio.IT ",
                    svc.FREQUENZE["quindicinale"], "07863990961")
    assert testo == svc.testo_autorizzazione("studio@esempio.it", "quindicinale", "07863990961")


def test_il_testo_senza_email_non_lascia_il_segnaposto():
    testo = _chiama("testoAutorizzazione", "a {email}, {frequenza}, {piva}", "", "ogni lunedì", "07863990961")
    assert testo == "a l'indirizzo indicato, ogni lunedì, 07863990961"


@pytest.mark.parametrize("iso,atteso", [
    ("2026-10-05", "lunedì 5 ottobre"), ("2026-12-31", "giovedì 31 dicembre"), ("2027-03-28", "domenica 28 marzo"),
])
def test_giorno_esteso(iso, atteso):
    assert _chiama("giornoEsteso", iso) == atteso


def test_giorno_esteso_non_dipende_dal_fuso():
    for tz in ("America/Los_Angeles", "Pacific/Kiritimati"):
        assert esegui_ts(MODULO, "emit(m.giornoEsteso('2026-10-05'));", tz=tz) == "lunedì 5 ottobre"


@pytest.mark.parametrize("voce,testo,tono", [
    (_voce(), "Non attivo.", "neutro"),
    (_voce(attivo=True, email="studio@x.it", prossimo_invio="2026-10-05"),
     "Attivo: studio@x.it riceve le fatture ogni lunedì. Prossimo invio: lunedì 5 ottobre.", "positivo"),
    (_voce(attivo=True, email="studio@x.it", frequenza="mensile"),
     "Attivo: studio@x.it riceve le fatture il 1° di ogni mese.", "positivo"),
    (_voce(attivo=True, sospeso=True, email="studio@x.it"),
     "In verifica da parte di OneFlux: l'invio è fermo, ti contatteremo noi.", "incerto"),
])
def test_riga_di_stato(voce, testo, tono):
    assert _chiama("rigaStato", voce, FREQUENZE) == {"testo": testo, "tono": tono}


@pytest.mark.parametrize("ultimo,atteso", [
    (None, None),
    ({"periodo_dal": "2026-09-28", "periodo_al": "2026-10-04", "n_file": 12, "conclusa_at": "2026-10-05T01:10:00+00:00"},
     "Ultimo invio il 05/10/2026: 12 fatture dal 28/09/2026 al 04/10/2026."),
    ({"periodo_dal": "2026-09-28", "periodo_al": "2026-10-04", "n_file": 1, "conclusa_at": None},
     "Ultimo invio: 1 fattura dal 28/09/2026 al 04/10/2026."),
    ({"periodo_dal": "2026-09-28", "periodo_al": "2026-10-04", "n_file": 0, "conclusa_at": None},
     "Ultimo invio: nessuna fattura arrivata dal 28/09/2026 al 04/10/2026."),
])
def test_riga_dell_ultimo_invio(ultimo, atteso):
    assert _chiama("rigaUltimoInvio", ultimo) == atteso


@pytest.mark.parametrize("voce,atteso", [
    (_voce(), None),
    (_voce(recupero_dal="2026-07-15"), "Invia anche le fatture già ricevute (dal 15/07/2026)"),
    (_voce(recupero_dal="2026-09-01", ultimo_invio={"periodo_dal": "2026-08-01", "periodo_al": "2026-08-31",
                                                   "n_file": 3, "conclusa_at": None}),
     "Invia anche le fatture arrivate mentre era disattivato (dal 01/09/2026)"),
])
def test_etichetta_del_recupero(voce, atteso):
    assert _chiama("etichettaRecupero", voce) == atteso


def test_etichetta_della_piva():
    assert _chiama("etichettaPiva", _voce()) == "OFFSIDE, OVERTIME · P.IVA 07863990961"
    assert _chiama("etichettaPiva", _voce(sedi=[])) == "P.IVA 07863990961"


# ─── Cablaggio (i .tsx non si eseguono: si legge il sorgente normalizzato) ───

def _normalizzato(percorso):
    return " ".join((WEB / percorso).read_text(encoding="utf-8").split())


def test_la_scheda_compare_nei_due_rami_solo_dietro_la_decisione():
    """Sia nella vista catena sia nella sede singola, e sempre condizionata da
    mostraFattureCommercialista (che la nasconde ad admin e sotto-utenti)."""
    sorgente = _normalizzato("app/(app)/impostazioni/account-client.tsx")
    condizionate = re.findall(
        r"\{mostraFattureCommercialista\(commercialista, data\) && \( <FattureCommercialistaCard statoIniziale=\{commercialista!\} /> \)\}",
        sorgente,
    )
    assert len(condizionate) == 2
    assert sorgente.count("<FattureCommercialistaCard") == 2


def test_la_pagina_non_chiede_lo_stato_per_un_sotto_utente():
    sorgente = _normalizzato("app/(app)/impostazioni/page.tsx")
    assert ('user.sotto_utente ? Promise.resolve(null) : workerGetJson("/api/account/invio-commercialista", token)'
            in sorgente)
    assert "commercialista={commercialista}" in sorgente


def test_il_pulsante_attiva_chiede_email_valida_e_autorizzazione():
    sorgente = _normalizzato("app/(app)/impostazioni/fatture-commercialista-card.tsx")
    assert "disabled={occupato || !emailOk || !autorizzo} onClick={attiva}" in sorgente
    assert "const emailOk = emailValida(email);" in sorgente
    assert "{ piva: voce.piva, email, frequenza, autorizzo, includi_precedenti: includi }" in sorgente


def test_disattivare_resta_possibile_anche_da_sospeso():
    """Il testo autorizzato promette che si disattiva in qualsiasi momento."""
    sorgente = _normalizzato("app/(app)/impostazioni/fatture-commercialista-card.tsx")
    assert "{!modifica && voce.attivo && (" in sorgente
    blocco = sorgente.split("{!modifica && voce.attivo && (", 1)[1].split("</div> )}", 1)[0]
    assert "onClick={() => setConfermaSpegni(true)}" in blocco
    assert blocco.index("{!voce.sospeso && (") < blocco.index("Modifica") < blocco.index("Disattiva")
    assert blocco.split("Modifica", 1)[1].count("voce.sospeso") == 0


def test_dopo_un_errore_la_scheda_riprende_lo_stato_dal_server():
    """router.refresh() porta uno statoIniziale nuovo, ma useState lo ignora: senza
    l'effetto la scheda mostrerebbe lo stato di prima dell'errore."""
    sorgente = _normalizzato("app/(app)/impostazioni/fatture-commercialista-card.tsx")
    assert "useEffect(() => setStato(statoIniziale), [statoIniziale]);" in sorgente
    errore = sorgente.split("if (!res.ok) {", 1)[1].split("return false;", 1)[0]
    assert "router.refresh();" in errore
