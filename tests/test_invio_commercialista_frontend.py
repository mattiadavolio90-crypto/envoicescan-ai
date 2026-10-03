"""La logica pura della card admin «Invio al commercialista» (`lib/invio-commercialista.ts`).

Il pezzo che conta per la sicurezza e' `percorsoProxy`: il proxy Next.js
(app/api/admin/clienti/[id]/invio-commercialista/[[...percorso]]) inoltra al
worker SOLO cio' che questa funzione riconosce. Il resto dice all'admin le cose
giuste: cosa si puo' fare su una P.IVA, in che stato e', chi l'ha attivata.
"""
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/invio-commercialista"
WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
CLIENTE = "3e0e0000-0000-4000-8000-000000000001"
INVIO = "3e0e0000-0000-4000-8000-0000000000d1"
BASE = f"/api/admin/clienti/{CLIENTE}/invio-commercialista"
FREQUENZE = {"settimanale": "ogni lunedì", "quindicinale": "il 1° e il 16 di ogni mese", "mensile": "il 1° di ogni mese"}


def _chiama(funzione, *argomenti):
    return esegui_ts(MODULO, f"emit(m.{funzione}(...input));", argomento=list(argomenti), richiede=[funzione])


def _percorsi(casi):
    return esegui_ts(MODULO, "emit(input.map(([id, seg]) => m.percorsoProxy(id, seg)));",
                     argomento=casi, richiede=["percorsoProxy"])


def _voce(**campi):
    voce = {"piva": "07863990961", "sedi": ["OFFSIDE", "OVERTIME"], "sdi_attivo": True, "arrivate": True,
            "config_id": None, "attivo": False, "sospesa_motivo": None, "email": None, "frequenza": "settimanale",
            "attivato_il": None, "attivato_da": None, "ultimo_invio": None, "prossimo_invio": None,
            "da_chiarire": None}
    voce.update(campi)
    return voce


# ─── Il proxy ────────────────────────────────────────────────────────────────

def test_il_proxy_inoltra_i_percorsi_della_card():
    assert _percorsi([[CLIENTE, []], [CLIENTE, ["attiva"]], [CLIENTE, ["disattiva"]],
                      [CLIENTE, ["invii", INVIO, "chiarisci"]]]) == [
        BASE, f"{BASE}/attiva", f"{BASE}/disattiva", f"{BASE}/invii/{INVIO}/chiarisci",
    ]


def test_il_proxy_non_inoltra_nient_altro():
    casi = [
        ["../../utenti", []], ["../" + CLIENTE, []], [f"{CLIENTE}/..", []],
        [CLIENTE, ["..", "..", "flags"]], [CLIENTE, ["azienda"]], [CLIENTE, ["attiva", "x"]],
        [CLIENTE, ["Attiva"]], [CLIENTE, ["invii", INVIO]], [CLIENTE, ["invii", "x", "chiarisci"]],
        [CLIENTE, ["invii", INVIO, "annulla"]], [CLIENTE, ["invii", INVIO, "chiarisci", "x"]],
        [CLIENTE, [INVIO]], [CLIENTE, [INVIO, "invii"]],
    ]
    assert _percorsi(casi) == [None] * len(casi)


# ─── Cosa si puo' fare su una riga ───────────────────────────────────────────

@pytest.mark.parametrize("campi,atteso", [
    ({}, "attiva"),
    ({"attivo": True, "email": "s@x.it"}, "modifica"),
    ({"attivo": True, "sdi_attivo": False}, "modifica"),
    ({"attivo": True, "sospesa_motivo": "x"}, "modifica"),
    ({"arrivate": False}, "nessuna"),
    ({"sdi_attivo": False}, "nessuna"),
])
def test_azione_della_riga(campi, atteso):
    assert _chiama("azioneRiga", _voce(**campi)) == atteso


@pytest.mark.parametrize("campi,testo,tono", [
    ({}, "Non attivo.", "neutro"),
    ({"arrivate": False}, "Nessuna fattura è ancora arrivata via SDI: si potrà attivare dopo la prima.", "neutro"),
    ({"attivo": True, "email": "studio@x.it", "prossimo_invio": "2026-10-05"},
     "Attivo → studio@x.it, ogni lunedì. Prossimo invio: lunedì 5 ottobre.", "positivo"),
    ({"attivo": True, "email": "studio@x.it", "frequenza": "mensile"},
     "Attivo → studio@x.it, il 1° di ogni mese.", "positivo"),
    ({"attivo": True, "email": "studio@x.it", "sdi_attivo": False},
     "In pausa: nessuna sede di questa P.IVA riceve più via SDI.", "incerto"),
    ({"attivo": True, "email": "studio@x.it", "sospesa_motivo": "piva_non_solo_del_cliente"},
     "Fermo per un controllo di sicurezza: La P.IVA risulta anche su un altro account. "
     "Per ripartire premi Salva.", "negativo"),
    ({"attivo": True, "email": "studio@x.it",
      "da_chiarire": {"id": INVIO, "periodo_dal": "2026-09-28", "periodo_al": "2026-10-04"}},
     "Brevo non ha confermato l'ultima email: controlla nei suoi log se è arrivata. "
     "Finché non lo dici, non parte altro.", "incerto"),
])
def test_riga_di_stato(campi, testo, tono):
    assert _chiama("rigaStato", _voce(**campi), FREQUENZE) == {"testo": testo, "tono": tono}


@pytest.mark.parametrize("campi,atteso", [
    ({"attivo": True, "attivato_il": "2026-10-03T08:05:00Z", "attivato_da": "md@oneflux.it"},
     "Attivato il 03/10/2026 alle 10:05 da md@oneflux.it"),
    # a mezzanotte e mezza di Roma in UTC e' ancora il giorno prima
    ({"attivo": True, "attivato_il": "2026-12-31T23:30:00Z", "attivato_da": None},
     "Attivato il 01/01/2027 alle 00:30"),
    ({"attivo": False, "attivato_il": "2026-10-03T08:05:00Z"}, None),
    ({"attivo": True, "attivato_il": None}, None),
])
def test_chi_ha_attivato_e_quando(campi, atteso):
    assert _chiama("rigaAttivazione", _voce(**campi)) == atteso


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


@pytest.mark.parametrize("email,valida", [
    ("studio@esempio.it", True), (" studio@pec.esempio.it ", True), ("a@b", False),
    ("senza-chiocciola", False), ("due@@x.it", False), ("", False), ("con spazio@x.it", False),
])
def test_email_valida_come_il_worker(email, valida):
    assert _chiama("emailValida", email) is valida


@pytest.mark.parametrize("iso,atteso", [
    ("2026-10-05", "lunedì 5 ottobre"), ("2026-12-31", "giovedì 31 dicembre"), ("2027-03-28", "domenica 28 marzo"),
])
def test_giorno_esteso(iso, atteso):
    assert _chiama("giornoEsteso", iso) == atteso


def test_giorno_esteso_non_dipende_dal_fuso():
    for tz in ("America/Los_Angeles", "Pacific/Kiritimati"):
        assert esegui_ts(MODULO, "emit(m.giornoEsteso('2026-10-05'));", tz=tz) == "lunedì 5 ottobre"


def test_etichetta_della_piva():
    assert _chiama("etichettaPiva", _voce()) == "OFFSIDE, OVERTIME · P.IVA 07863990961"
    assert _chiama("etichettaPiva", _voce(sedi=[])) == "P.IVA 07863990961"


def test_i_motivi_diventano_frasi():
    motivi = ["invio_spento", "invoicetronic: HTTP 401", "brevo_rifiutata_http_400", "codice_mai_visto", None, ""]
    assert esegui_ts(MODULO, "emit(input.map(m.testoMotivo));", argomento=motivi, richiede=["testoMotivo"]) == [
        "Interruttore generale spento (INVIO_COMMERCIALISTA_ATTIVO sul queue-worker): non parte niente.",
        "Invoicetronic ha risposto con un errore. (HTTP 401)",
        "Brevo ha rifiutato l'email (HTTP 400): ricontrolla l'indirizzo.",
        "codice_mai_visto", "", "",
    ]


# ─── Cablaggio (i .tsx non si eseguono: si legge il sorgente normalizzato) ───

def _normalizzato(percorso):
    return " ".join((WEB / percorso).read_text(encoding="utf-8").split())


def test_la_card_attiva_solo_con_email_valida_e_manda_piva_email_frequenza():
    sorgente = _normalizzato("components/admin/invio-commercialista.tsx")
    assert ('<Button size="sm" disabled={occupato || !emailValida(email)} '
            'onClick={() => chiama("/attiva", { piva: v.piva, email, frequenza }, '
            'azione === "modifica" ? "Salvato" : "Invio attivato")}>') in sorgente
    assert "const azione = azioneRiga(v);" in sorgente


def test_da_attivo_il_form_resta_e_disattiva_sta_accanto_a_salva():
    """Cambiare email da attivo passa da Salva (la partenza resta): se servisse
    Disattiva + Attiva si perderebbero le fatture dei giorni in mezzo."""
    sorgente = _normalizzato("components/admin/invio-commercialista.tsx")
    blocco = sorgente.split('{azione !== "nessuna" && (', 1)[1].split("<ConfirmDialog", 1)[0]
    assert 'Email o PEC del commercialista' in blocco
    assert '{azione === "modifica" && (' in blocco and 'setConferma("disattiva")' in blocco
    assert sorgente.count('setConferma("disattiva")') == 1


def test_le_impostazioni_del_cliente_non_hanno_l_invio():
    """Lo attiva solo l'admin: il cliente non vede niente."""
    for percorso in ("app/(app)/impostazioni/account-client.tsx", "app/(app)/impostazioni/page.tsx"):
        assert "commercialista" not in (WEB / percorso).read_text(encoding="utf-8").lower()
    assert not (WEB / "app" / "api" / "account" / "invio-commercialista").exists()
