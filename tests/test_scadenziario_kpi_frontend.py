"""I KPI dello scadenziario contano i soldi giusti, e li contano in ogni fuso.

`computeKpi` decide le cifre che il cliente legge in cima allo scadenziario:
"Scadute", "Questa settimana", "Da pagare", "Pagate (mese)". Un errore qui non
rompe niente di visibile — mostra solo un numero sbagliato, che e' la classe di
difetto piu' costosa del progetto (F7, F1).

**Perche' le fixture sono ai confini.** Provato per mutazione prima di scrivere
il test: con fixture "ovvie" (una scaduta nel 2020, una pagata, una nota di
credito) su 4 mutanti ne moriva **uno solo**. Sopravvivevano `scad < today`
mutato in `<=`, la rimozione del filtro sul mese corrente, e `new Date()` al
posto di `parseLocalDate`. Le date lontane dai confini non distinguono i rami.

**Perche' le date sono relative a oggi.** Con date fisse il test invecchia: una
fixture scritta oggi come "scade oggi" fra tre mesi e' "scaduta da 90 giorni",
e i mutanti tornano a sopravvivere in silenzio.

**Perche' anche America/Los_Angeles.** Il mutante `new Date()` — cioe' proprio
il bug di fuso che il codice ha gia' corretto una volta — muore SOLO in un fuso
a ovest di Greenwich. Misurato: con Europe/Rome sopravvive, con
Pacific/Kiritimati (UTC+14) sopravvive, con Los Angeles muore. Non e' un fuso a
caso e non e' ridondante: e' l'unico che rende visibile la classe di difetto.
"""
import datetime
import random

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

# Rome = il fuso reale degli utenti. Los Angeles = l'unico che smaschera
# l'errore di mezzanotte UTC (vedi docstring). Non toglierlo.
FUSI = ["Europe/Rome", "America/Los_Angeles"]


def _doc(**kw):
    base = {
        "id": kw.get("id", "x"),
        "fornitore": "F",
        "is_nota_credito": False,
        "totale_documento": 0,
        "scadenza_effettiva": None,
        "pagata": False,
        "pagata_at": None,
    }
    base.update(kw)
    return base


def _kpi(documenti, tz):
    return esegui_ts(
        MODULO,
        "emit(m.computeKpi(input));",
        argomento=documenti,
        tz=tz,
        richiede=["computeKpi", "bucketizeDocumenti", "parseLocalDate"],
    )


def _buckets(documenti, tz):
    return esegui_ts(
        MODULO,
        "emit(Object.fromEntries(Object.entries(m.bucketizeDocumenti(input))"
        ".map(([k, v]) => [k, v.length])));",
        argomento=documenti,
        tz=tz,
        richiede=["bucketizeDocumenti"],
    )


def _oggi_in(tz):
    """La data che node vede in quel fuso: le fixture si costruiscono su questa.

    Non si usa `date.today()` di Python: a cavallo di mezzanotte, o con il
    processo Python in un fuso diverso, le due date divergono e il test
    fallirebbe per un motivo che non c'entra col codice sotto esame.
    """
    iso = esegui_ts(
        MODULO,
        "const d = new Date();"
        "emit([d.getFullYear(), d.getMonth() + 1, d.getDate()]);",
        tz=tz,
    )
    return datetime.date(*iso)


def _campione(tz):
    """Un documento per ogni confine che i mutanti sanno attraversare."""
    oggi = _oggi_in(tz)
    primo = oggi.replace(day=1)
    fine_mese_scorso = primo - datetime.timedelta(days=1)
    return oggi, [
        # scade oggi: NON scaduta, ma dentro i 7 giorni (uccide `scad <= today`)
        _doc(id="oggi", totale_documento=10, scadenza_effettiva=oggi.isoformat()),
        # confine alto della finestra settimana (uccide `scad < in7`)
        _doc(id="g7", totale_documento=20,
             scadenza_effettiva=(oggi + datetime.timedelta(days=7)).isoformat()),
        # appena fuori: non deve entrare in settimana
        _doc(id="g8", totale_documento=40,
             scadenza_effettiva=(oggi + datetime.timedelta(days=8)).isoformat()),
        # scaduta davvero
        _doc(id="scaduta", totale_documento=80,
             scadenza_effettiva=(oggi - datetime.timedelta(days=1)).isoformat()),
        # senza scadenza: da pagare, ma in nessuna finestra
        _doc(id="senza", totale_documento=160, scadenza_effettiva=None),
        # pagata il primo del mese: dentro "Pagate (mese)". E' il documento che
        # uccide sia il filtro-mese rimosso sia new Date() (nei fusi a ovest).
        _doc(id="primo", totale_documento=320, pagata=True,
             pagata_at=primo.isoformat(), scadenza_effettiva="2020-01-01"),
        # pagata il mese scorso: FUORI (uccide il filtro-mese rimosso)
        _doc(id="scorso", totale_documento=640, pagata=True,
             pagata_at=fine_mese_scorso.isoformat(), scadenza_effettiva="2020-01-01"),
        # nota di credito scaduta e non pagata: fuori da ogni secchio
        _doc(id="nc", totale_documento=1280, is_nota_credito=True,
             scadenza_effettiva=(oggi - datetime.timedelta(days=5)).isoformat()),
    ]


# I totali sono potenze di 2: se un documento finisce nel secchio sbagliato la
# somma lo dice da sola, senza ambiguita' su quale sia entrato.
@pytest.mark.parametrize("tz", FUSI)
def test_kpi_sui_confini(tz):
    _, docs = _campione(tz)
    k = _kpi(docs, tz)

    assert (k["scadute_count"], k["scadute_totale"]) == (1, 80), (
        "scadute: solo il documento di ieri. Se c'e' anche 'oggi', il confronto "
        "e' `<=` invece di `<`"
    )
    assert (k["settimana_count"], k["settimana_totale"]) == (2, 30), (
        "settimana: 'oggi' (10) e 'g7' (20). Manca g7 -> confine `< in7`; "
        "c'e' g8 -> finestra allargata"
    )
    # da pagare = tutti i non pagati e non NC, scadenza o meno
    assert (k["da_pagare_count"], k["da_pagare_totale"]) == (5, 310)
    assert (k["pagate_mese_count"], k["pagate_mese_totale"]) == (1, 320), (
        "pagate nel mese: solo quella del primo. Se compare anche 640 il filtro "
        "sul mese corrente non c'e' piu'"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_le_note_di_credito_non_sono_debiti(tz):
    """L'importo della NC non deve entrare in NESSUN totale.

    Prima stesura sbagliata, trovata dal code-reviewer: asseriva
    `1280 not in (k[c],)`, cioe' che nessun totale valesse *esattamente* 1280.
    Ma una NC che entra in un secchio ci entra **sommata** agli altri: col
    mutante che toglie l'esclusione, `da_pagare_totale` diventa 1590 e quella
    riga passava lo stesso. Misurava un'uguaglianza che non poteva verificarsi,
    non la proprieta' che dichiarava.

    Qui si confronta con lo stesso campione **senza** la NC: se l'importo
    filtrasse in un totale qualsiasi, i due esiti divergerebbero.
    """
    _, docs = _campione(tz)
    senza_nc = [d for d in docs if not d["is_nota_credito"]]

    assert _kpi(docs, tz) == _kpi(senza_nc, tz), (
        "una nota di credito sta cambiando i KPI: non e' un'obbligazione di "
        "pagamento e non deve entrare in nessun secchio"
    )
    assert _kpi(docs, tz)["da_pagare_totale"] == 310


def test_i_kpi_non_dipendono_dal_fuso():
    """L'asserzione che cattura la classe intera, non il singolo campo.

    E' il test che sarebbe stato rosso prima del fix di `parseLocalDate`: un
    pagamento del primo del mese, letto come mezzanotte UTC, cadeva il giorno
    prima in un fuso a ovest e usciva da "Pagate (mese)".
    """
    oggi_rm, docs = _campione("Europe/Rome")
    oggi_la = _oggi_in("America/Los_Angeles")
    if oggi_rm != oggi_la:
        # Le due macchine virtuali sono a cavallo della mezzanotte: ricostruisco
        # sul fuso piu' indietro invece di skippare (uno skip qui riaprirebbe la
        # porta allo skip verde).
        _, docs = _campione("America/Los_Angeles")

    assert _kpi(docs, "Europe/Rome") == _kpi(docs, "America/Los_Angeles"), (
        "i KPI cambiano col fuso: una data nuda 'YYYY-MM-DD' e' stata letta con "
        "new Date() invece che con parseLocalDate()"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_parse_local_date_e_mezzanotte_locale(tz):
    """La primitiva su cui poggia tutto il resto, testata direttamente.

    Segnalata dal code-reviewer: era in `richiede` (quindi doveva esistere) ma
    non veniva mai esercitata da sola. E' usata in 11 punti di
    `scadenziario-client.tsx`: se tornasse `null` su un ISO valido i documenti
    finirebbero tutti in "senza scadenza" senza che nessun test lo dicesse.
    """
    esito = esegui_ts(
        MODULO,
        "const d = m.parseLocalDate(input);"
        "emit(d === null ? null : [d.getFullYear(), d.getMonth() + 1, d.getDate(),"
        " d.getHours(), d.getMinutes()]);",
        argomento="2026-03-01",
        tz=tz,
        richiede=["parseLocalDate"],
    )
    # Mezzanotte LOCALE: con new Date("2026-03-01") sarebbe mezzanotte UTC, che
    # a ovest di Greenwich cade il 28/2.
    assert esito == [2026, 3, 1, 0, 0], (
        "parseLocalDate non restituisce la mezzanotte locale del giorno chiesto"
    )


@pytest.mark.parametrize("valore", [None, "", "non-una-data"])
def test_parse_local_date_rifiuta_gli_input_non_validi(valore):
    esito = esegui_ts(
        MODULO,
        "const d = m.parseLocalDate(input); emit(d === null || isNaN(d.getTime()));",
        argomento=valore,
        richiede=["parseLocalDate"],
    )
    assert esito is True, f"parseLocalDate({valore!r}) doveva dare null o data invalida"


# Fusi agli estremi: qualunque sia l'ora in cui gira la suite, in almeno uno dei
# due la data LOCALE e' diversa da quella UTC (offset -11 e +14, cioe' 25 ore di
# distanza). Con i soli Rome/LA il test sarebbe passato o no a seconda dell'ora:
# alle 14:28 di LA la data UTC coincide, alle 23:28 di Roma no.
FUSI_ESTREMI = ["Pacific/Midway", "Pacific/Kiritimati"]


@pytest.mark.parametrize("tz", FUSI + FUSI_ESTREMI)
def test_today_local_iso_e_il_giorno_locale(tz):
    """Scrive `pagata_at` in produzione (scadenziario-client.tsx) e ha gia'
    avuto il bug di fuso descritto nel suo stesso docstring.

    Confrontare con `new Date()` letto nello stesso fuso non basterebbe: e' il
    confronto con **UTC** che smaschera `getUTCDate()`, e solo in un fuso dove
    oggi-locale e oggi-UTC differiscono davvero.
    """
    iso = esegui_ts(
        MODULO, "emit(m.todayLocalIso());", tz=tz, richiede=["todayLocalIso"]
    )
    assert iso == _oggi_in(tz).isoformat(), (
        "todayLocalIso non concorda col giorno locale: un pagamento registrato "
        "vicino a mezzanotte finirebbe nel giorno (e forse nel mese) sbagliato"
    )


def test_today_local_iso_non_e_la_data_utc():
    """In almeno un fuso estremo la data locale deve differire da quella UTC.

    E' l'asserzione che uccide `getUTCDate()`: senza di essa il test sopra
    passa o meno a seconda dell'ora in cui gira la suite.
    """
    utc = esegui_ts(MODULO, "emit(m.todayLocalIso());", tz="UTC",
                    richiede=["todayLocalIso"])
    locali = {
        tz: esegui_ts(MODULO, "emit(m.todayLocalIso());", tz=tz,
                      richiede=["todayLocalIso"])
        for tz in FUSI_ESTREMI
    }
    assert any(v != utc for v in locali.values()), (
        f"todayLocalIso da' la stessa data in UTC ({utc}) e nei fusi estremi "
        f"({locali}): sta leggendo l'istante UTC invece dell'ora locale"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_bucket_e_kpi_concordano(tz):
    """Due implementazioni degli stessi confini nello stesso file divergono.

    `computeKpi` e `bucketizeDocumenti` ricalcolano today/in7 ciascuna per conto
    suo: e' la coppia classica che si separa a un refactor di una sola delle due.
    """
    _, docs = _campione(tz)
    k, b = _kpi(docs, tz), _buckets(docs, tz)
    assert b["scadute"] == k["scadute_count"]
    assert b["settimana"] == k["settimana_count"]
    assert b["noteCredito"] == 1
    assert b["senzaScadenza"] == 1
    assert b["scadute"] + b["settimana"] + b["mese"] + b["oltre"] + b["senzaScadenza"] == k["da_pagare_count"]
    # `mese` e `oltre` vanno asseriti SEPARATAMENTE: dentro la somma sopra uno
    # spostamento fra i due si compensa e la finestra a 30 giorni potrebbe
    # valerne 7 senza che nulla fallisca (mutante sopravvissuto al primo giro).
    # g8 (fra 8 giorni) sta nel mese; nel campione niente cade oltre i 30.
    assert (b["mese"], b["oltre"]) == (1, 0), (
        "confine dei 30 giorni: g8 deve stare in `mese`, non in `oltre`"
    )


@pytest.mark.parametrize("tz", FUSI)
def test_concordano_anche_su_dataset_casuale(tz):
    """Seed fisso: riproducibile, ma copre combinazioni che non ho pensato."""
    oggi = _oggi_in(tz)
    rnd = random.Random(20260829)
    docs = []
    for i in range(120):
        scarto = rnd.randint(-60, 60)
        pagata = rnd.random() < 0.3
        docs.append(_doc(
            id=str(i),
            totale_documento=rnd.randint(1, 900),
            is_nota_credito=rnd.random() < 0.1,
            scadenza_effettiva=None if rnd.random() < 0.1
            else (oggi + datetime.timedelta(days=scarto)).isoformat(),
            pagata=pagata,
            pagata_at=(oggi - datetime.timedelta(days=rnd.randint(0, 60))).isoformat()
            if pagata else None,
        ))
    k, b = _kpi(docs, tz), _buckets(docs, tz)
    assert b["scadute"] == k["scadute_count"]
    assert b["settimana"] == k["settimana_count"]
    assert b["pagate"] >= k["pagate_mese_count"]
