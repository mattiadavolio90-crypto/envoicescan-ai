"""La logica pura della scheda «Invio al commercialista» (`lib/invio-commercialista.ts`).

Il pezzo che conta per la sicurezza e' `percorsoProxy`: il proxy Next.js
(app/api/admin/clienti/[id]/invio-commercialista/[[...percorso]]) inoltra al
worker SOLO cio' che questa funzione riconosce. Il resto dice all'admin le cose
giuste: cosa manca per accendere, perche' un invio non e' partito, quale periodo
partira' con «Invia ora» (lo stesso calcolo del worker).
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/invio-commercialista"
CLIENTE = "3e0e0000-0000-4000-8000-000000000001"
CONFIG = "3e0e0000-0000-4000-8000-0000000000c1"
INVIO = "3e0e0000-0000-4000-8000-0000000000d1"
BASE = f"/api/admin/clienti/{CLIENTE}/invio-commercialista"


def _percorsi(casi):
    return esegui_ts(
        MODULO,
        "emit(input.map(([id, seg, q]) => m.percorsoProxy(id, seg, new URLSearchParams(q))));",
        argomento=casi, richiede=["percorsoProxy"],
    )


def test_il_proxy_inoltra_i_percorsi_della_scheda():
    casi = [
        [CLIENTE, [], ""],
        [CLIENTE, ["azienda"], "piva=07863990961"],
        [CLIENTE, [CONFIG], ""],
        [CLIENTE, [CONFIG, "invii"], ""],
        [CLIENTE, [CONFIG, "invii", INVIO, "chiarisci"], ""],
        [CLIENTE, [CONFIG, "invii", INVIO, "annulla"], ""],
    ]
    assert _percorsi(casi) == [
        BASE,
        f"{BASE}/azienda?piva=07863990961",
        f"{BASE}/{CONFIG}",
        f"{BASE}/{CONFIG}/invii",
        f"{BASE}/{CONFIG}/invii/{INVIO}/chiarisci",
        f"{BASE}/{CONFIG}/invii/{INVIO}/annulla",
    ]


def test_il_proxy_non_inoltra_nient_altro():
    casi = [
        ["../../utenti", [], ""],
        ["../" + CLIENTE, [], ""],
        [f"{CLIENTE}/..", [], ""],
        [CLIENTE, ["..", "..", "flags"], ""],
        [CLIENTE, ["azienda"], ""],
        [CLIENTE, ["azienda"], "piva=0786399096"],
        [CLIENTE, ["azienda"], "piva=IT07863990961"],
        [CLIENTE, ["azienda", "x"], "piva=07863990961"],
        [CLIENTE, ["nonuuid"], ""],
        [CLIENTE, [CONFIG, "altro"], ""],
        [CLIENTE, [CONFIG, "invii", INVIO], ""],
        [CLIENTE, [CONFIG, "invii", INVIO, "cancella"], ""],
        [CLIENTE, [CONFIG, "invii", "x", "annulla"], ""],
        [CLIENTE, [CONFIG, "invii", INVIO, "annulla", "x"], ""],
    ]
    assert _percorsi(casi) == [None] * len(casi)


def test_della_query_passa_solo_la_piva():
    assert _percorsi([[CLIENTE, ["azienda"], "piva=07863990961&x=1&worker_key=abc"]]) == [
        f"{BASE}/azienda?piva=07863990961"
    ]


def test_i_motivi_diventano_frasi():
    motivi = [
        "invio_spento",
        "saldo_insufficiente (102 operazioni, 3 documenti)",
        "invoicetronic: HTTP 401",
        "brevo_rifiutata_http_400",
        "documento_con_altro_destinatario",
        "prova: documenti 3; saldo prima 500, dopo 497",
        "chiarito dall'admin: arrivata",
        "codice_mai_visto",
        None,
        "",
    ]
    assert esegui_ts(MODULO, "emit(input.map(m.testoMotivo));", argomento=motivi, richiede=["testoMotivo"]) == [
        "Interruttore generale spento (INVIO_COMMERCIALISTA_ATTIVO sul queue-worker): parte solo la prova a vuoto.",
        "Saldo Invoicetronic troppo basso per scaricare tutto senza lasciare a secco le fatture in arrivo. "
        "(102 operazioni, 3 documenti)",
        "Invoicetronic ha risposto con un errore. (HTTP 401)",
        "Brevo ha rifiutato l'email (HTTP 400): ricontrolla l'indirizzo.",
        "Nell'elenco c'è un documento per un'altra P.IVA.",
        "prova: documenti 3; saldo prima 500, dopo 497",
        "chiarito dall'admin: arrivata",
        "codice_mai_visto",
        "",
        "",
    ]


def _config(**campi):
    base = {
        "id": CONFIG, "piva": "07863990961", "invoicetronic_company_id": 1756, "invoicetronic_nome": "OFFSIDE SRL",
        "email_destinatario": "studio@x.test", "frequenza": "mensile", "data_partenza": "2026-07-15",
        "attivo": True, "consenso_ricevuto": True, "consenso_data": "2026-09-20", "consenso_email": "studio@x.test",
        "sospesa_at": None, "sospesa_motivo": None, "aggiornata_at": "2026-09-25T10:00:00Z",
        "sede_sdi_attiva": True, "ultimo_giorno_inviato": "2026-08-31", "invii": [],
    }
    base.update(campi)
    return base


def _stato(config):
    return esegui_ts(MODULO, "emit(m.statoConfigurazione(input));", argomento=config, richiede=["statoConfigurazione"])


@pytest.mark.parametrize("campi,testo,tono", [
    ({}, "Attiva — inviato fino al 31/08/2026", "positivo"),
    ({"ultimo_giorno_inviato": None}, "Attiva — il primo invio si lancia a mano", "incerto"),
    ({"sede_sdi_attiva": False}, "In pausa: nessuna sede con SDI attivo", "incerto"),
    ({"sospesa_at": "2026-09-25T02:10:00Z", "sospesa_motivo": "piva_non_solo_del_cliente"},
     "Sospesa dalla guardia: La P.IVA risulta anche su un altro account.", "negativo"),
    ({"invii": [{"stato": "esito_incerto"}]},
     "Esito incerto da chiarire: nessun altro invio finché non lo chiudi", "incerto"),
    ({"attivo": False}, "Spenta", "neutro"),
    ({"attivo": False, "consenso_email": "vecchio@x.test", "data_partenza": None},
     "Spenta — manca: consenso per questa email, data di partenza", "neutro"),
    ({"attivo": False, "invoicetronic_company_id": None, "email_destinatario": None, "consenso_ricevuto": False,
      "consenso_email": None},
     "Spenta — manca: collegamento a Invoicetronic, email del commercialista, consenso per questa email", "neutro"),
])
def test_lo_stato_della_configurazione(campi, testo, tono):
    assert _stato(_config(**campi)) == {"testo": testo, "tono": tono}


def test_il_limite_dei_due_anni_come_postgres():
    assert esegui_ts(MODULO, "emit(input.map(m.limiteDueAnni));", argomento=["2026-09-25", "2028-02-29", "2027-03-01"],
                     richiede=["limiteDueAnni"]) == ["2024-09-25", "2026-02-28", "2025-03-01"]


def test_il_periodo_scelto_dall_admin():
    casi = [
        ["2026-08-01", "2026-08-31"],
        ["2026-09-01", "2026-08-31"],
        ["2026-09-20", "2026-09-25"],
        ["2024-09-24", "2024-09-30"],
        ["2024-09-25", "2024-09-30"],
        ["", "2026-08-31"],
    ]
    risultati = esegui_ts(MODULO, "emit(input.map(([d, a]) => m.erroreDelPeriodo(d, a, '2026-09-25')));",
                          argomento=casi, richiede=["erroreDelPeriodo"])
    assert risultati[0] is None and risultati[4] is None
    assert risultati[1] == "La data di inizio viene dopo quella di fine."
    assert risultati[2] == "Il periodo deve finire al più tardi ieri."
    assert risultati[3].startswith("Invoicetronic conserva le fatture ricevute per 2 anni")
    assert risultati[5] == "Indica il periodo."


@pytest.mark.parametrize("config,atteso", [
    ({"data_partenza": "2026-07-15", "ultimo_giorno_inviato": None},
     {"tipo": "primo", "dal": "2026-07-15", "al": "2026-09-24"}),
    ({"data_partenza": "2026-07-15", "ultimo_giorno_inviato": "2026-08-31"},
     {"tipo": "ordinario", "dal": "2026-09-01", "al": "2026-09-24"}),
    ({"data_partenza": "2024-01-01", "ultimo_giorno_inviato": None},
     {"tipo": "primo", "dal": "2024-09-25", "al": "2026-09-24"}),
    ({"data_partenza": "2026-07-15", "ultimo_giorno_inviato": "2026-09-24"}, None),
    ({"data_partenza": None, "ultimo_giorno_inviato": None}, None),
])
def test_il_periodo_di_invia_ora_e_quello_del_worker(config, atteso):
    assert esegui_ts(MODULO, "emit(m.periodoInviaOra(input, '2026-09-25'));", argomento=config,
                     richiede=["periodoInviaOra"]) == atteso


def test_date_e_byte_in_italiano():
    assert esegui_ts(
        MODULO,
        "emit([m.formattaData('2026-09-05'), m.formattaData('2026-09-05T10:00:00Z'), m.formattaData(null),"
        " m.formattaByte(512), m.formattaByte(20480), m.formattaByte(3355443), m.formattaByte(null),"
        " m.spostaGiorni('2026-03-01', -1), m.spostaGiorni('2026-12-31', 1)]);",
        richiede=["formattaData", "formattaByte", "spostaGiorni"],
    ) == ["05/09/2026", "05/09/2026", "—", "512 byte", "20 KB", "3,2 MB", "—", "2026-02-28", "2027-01-01"]



def test_l_avviso_sulla_storia_di_una_configurazione_cancellata():
    assert esegui_ts(
        MODULO,
        "emit([m.avvisoStoricoOrfano({'07863990961': '2026-08-31'}, '07863990961'),"
        " m.avvisoStoricoOrfano({'07863990961': '2026-08-31'}, '12345678903'), m.avvisoStoricoOrfano(undefined, 'x')]);",
        richiede=["avvisoStoricoOrfano"],
    ) == [
        "Una configurazione cancellata ha già inviato le fatture di questa P.IVA fino al 31/08/2026: "
        "scegli la partenza dopo, o il commercialista le riceve due volte.",
        None,
        None,
    ]
