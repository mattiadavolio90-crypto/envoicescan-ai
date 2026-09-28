"""I fornitori delle fatture senza scadenza, ordinati per quanto pesano.

Misurato sul DB di produzione il 25/09/2026: 1.073 fatture non pagate senza
scadenza per **959.319 EUR** — il 35% del non pagato, su tutte e 11 le sedi
(dal 5% al 74%) — sparse su 168 fornitori. Nessuna di quelle fatture aveva il
dato nell'XML (0 con `scadenza_xml`, 0 con `giorni_termini_xml`), ma tutte
avevano la data documento: si risolvono con una regola di pagamento per
fornitore. E **7 fornitori valgono meta' del problema, 33 ne valgono l'80%**.

Il banner diceva solo «1.073 fatture senza scadenza» e apriva una finestra con
168 nomi in ordine alfabetico, dove i 7 che contano sono indistinguibili dal
fornitore con una fattura sola.

**L'asserzione che vale piu' di tutte e' l'ordinamento per euro.** E' il punto
dove e' piu' facile scrivere codice che sembra giusto: ordinare per numero di
fatture e' altrettanto naturale da scrivere, sembra ragionevole a leggerlo, e
mette in cima il fornitore sbagliato. Senza il caso che li mette in conflitto
(molte fatture piccole contro poche grosse) il test resterebbe verde su quella
scelta.

**Perche' i senza-P.IVA sono esclusi e non in fondo.** Il match delle regole
avviene per P.IVA (`_applica_regole_fornitore` in documenti_service.py):
offrire un menu a chi non puo' essere agganciato e' una promessa che la
finestra non mantiene — oggi il dialog li accetta e poi li scarta con un
errore. Si contano a parte e si dice che vanno sistemate a mano.

Mutazioni provate (25/09/2026), tutte uccise:
1. ordinamento per `count` invece che per `totale` -> test_ordina_per_euro_non_per_numero
2. tolto il filtro sulla P.IVA vuota -> test_senza_piva_fuori_dall_elenco
3. tolto `!d.pagata` -> test_esclude_pagate_note_di_credito_e_oscurate
4. tolto `!d.is_nota_credito` -> idem
5. tolto `!d.oscurata` -> idem
6. etichetta presa dal primo nome invece che dal piu' frequente -> test_una_piva_una_voce_sola
"""
import re

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
_RICHIEDE = ["fornitoriSenzaScadenza", "bucketizeDocumenti"]


def _doc(**kw):
    base = {
        "id": "x",
        "file_origine": "f.xml",
        "fornitore": "Rossi Srl",
        "piva_fornitore": "01234567890",
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": 100.0,
        "data_documento": "2026-09-01",
        "numero_documento": "1",
        "scadenza_effettiva": None,
        "scadenza_source": "none",
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "oscurata": False,
    }
    base.update(kw)
    return base


def _riepilogo(docs, limite=5):
    return esegui_ts(
        MODULO,
        "emit(m.fornitoriSenzaScadenza(input.docs, input.limite));",
        {"docs": docs, "limite": limite},
        richiede=_RICHIEDE,
    )


def test_ordina_per_euro_non_per_numero():
    """Poche fatture grosse pesano piu' di molte piccole.

    Chi imposta i termini di pagamento decide quanto debito rendere
    prevedibile, non quante righe sistemare.
    """
    docs = (
        [_doc(id=f"a{i}", piva_fornitore="AAA", fornitore="Tante Piccole", totale_documento=10.0)
         for i in range(50)]
        + [_doc(id=f"b{i}", piva_fornitore="BBB", fornitore="Poche Grosse", totale_documento=1000.0)
           for i in range(3)]
    )
    r = _riepilogo(docs)
    assert [f["label"] for f in r["top"]] == ["Poche Grosse", "Tante Piccole"]
    assert r["top"][0]["totale"] == 3000.0
    assert r["top"][0]["count"] == 3


def test_esclude_pagate_note_di_credito_e_oscurate():
    """Stessa precedenza di `bucketizeDocumenti`: non sono debiti da pianificare."""
    docs = [
        _doc(id="viva", piva_fornitore="AAA", fornitore="Viva", totale_documento=100.0),
        _doc(id="pag", piva_fornitore="BBB", fornitore="Pagata", pagata=True, totale_documento=999.0),
        _doc(id="nc", piva_fornitore="CCC", fornitore="Nota", is_nota_credito=True, totale_documento=999.0),
        _doc(id="osc", piva_fornitore="DDD", fornitore="Esclusa", oscurata=True, totale_documento=999.0),
    ]
    r = _riepilogo(docs)
    assert [f["label"] for f in r["top"]] == ["Viva"]


def test_esclude_chi_ha_gia_una_scadenza():
    """La lista serve a chi la scadenza non ce l'ha: chi ce l'ha e' gia' a posto."""
    docs = [
        _doc(id="senza", piva_fornitore="AAA", fornitore="Senza", totale_documento=100.0),
        _doc(id="con", piva_fornitore="BBB", fornitore="Con", scadenza_effettiva="2026-10-01",
             totale_documento=999.0),
    ]
    r = _riepilogo(docs)
    assert [f["label"] for f in r["top"]] == ["Senza"]


def test_senza_piva_fuori_dall_elenco():
    """Una regola non puo' agganciarli: si contano a parte, non si promettono."""
    docs = [
        _doc(id="ok", piva_fornitore="AAA", fornitore="Con Piva", totale_documento=100.0),
        _doc(id="no1", piva_fornitore=None, fornitore="Senza Piva", totale_documento=70.0),
        _doc(id="no2", piva_fornitore="  ", fornitore="Piva Vuota", totale_documento=30.0),
    ]
    r = _riepilogo(docs)
    assert [f["label"] for f in r["top"]] == ["Con Piva"]
    assert r["senzaPivaCount"] == 2
    assert r["senzaPivaTotale"] == 100.0


def test_una_piva_una_voce_sola():
    """Due grafie della stessa ragione sociale non fanno due righe.

    L'etichetta e' il nome piu' FREQUENTE, come in `elencaFornitori`: quella
    ricorrente e' la grafia che il cliente riconosce.
    """
    docs = [
        _doc(id="1", piva_fornitore="AAA", fornitore="Rossi S.r.l.", totale_documento=10.0),
        _doc(id="2", piva_fornitore="AAA", fornitore="ROSSI SRL", totale_documento=10.0),
        _doc(id="3", piva_fornitore="AAA", fornitore="ROSSI SRL", totale_documento=10.0),
    ]
    r = _riepilogo(docs)
    assert len(r["top"]) == 1
    assert r["top"][0]["label"] == "ROSSI SRL"
    assert r["top"][0]["count"] == 3
    assert r["top"][0]["totale"] == 30.0


def test_il_resto_e_contato_non_perso():
    """Chi non entra nell'elenco resta nel conteggio: la somma deve tornare."""
    docs = [
        _doc(id=f"f{i}", piva_fornitore=f"P{i}", fornitore=f"F{i}", totale_documento=float(100 - i))
        for i in range(8)
    ]
    r = _riepilogo(docs, limite=3)
    assert len(r["top"]) == 3
    assert r["restoCount"] == 5
    totale_tutti = sum(float(100 - i) for i in range(8))
    assert r["top"][0]["totale"] + sum(f["totale"] for f in r["top"][1:]) + r["restoTotale"] == totale_tutti


def test_nessuna_fattura_senza_scadenza_da_elenco_vuoto():
    docs = [_doc(id="con", scadenza_effettiva="2026-10-01")]
    r = _riepilogo(docs)
    assert r["top"] == []
    assert r["restoCount"] == 0
    assert r["senzaPivaCount"] == 0


def test_importo_mancante_non_rompe_la_somma():
    """`totale_documento` a null non deve produrre NaN nella classifica."""
    doc = _doc(id="x", piva_fornitore="AAA", fornitore="Senza Importo")
    doc["totale_documento"] = None
    r = _riepilogo([doc])
    assert r["top"][0]["totale"] == 0
    assert r["top"][0]["count"] == 1


# ── Il cablaggio nel client ──────────────────────────────────────────────────
#
# La funzione puo' essere giusta e non essere chiamata, o essere chiamata e non
# portare a nulla. Assert sul sorgente: debole da solo, ma copre le regressioni
# concrete di questa fase, che i test sopra non vedrebbero.

from pathlib import Path  # noqa: E402

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


@pytest.fixture(scope="module")
def sorgente() -> str:
    return CLIENT.read_text(encoding="utf-8")


def test_il_banner_usa_la_classifica(sorgente: str):
    assert "fornitoriSenzaScadenza(buckets.senzaScadenza" in sorgente, (
        "il riquadro non costruisce piu' la classifica dei fornitori"
    )


def test_salvare_una_regola_ricarica_la_lista(sorgente: str):
    """Prima il dialog ricaricava solo se stesso: la regola veniva creata e le
    scadenze a video restavano quelle di prima, fino a un «Aggiorna» a mano."""
    assert "onSalvato={loadData}" in sorgente, (
        "dopo il salvataggio la lista non viene piu' ricaricata"
    )
    assert "if (salvate > 0) onSalvato?.();" in sorgente, (
        "RegoleDialog non avvisa piu' il genitore dopo un salvataggio"
    )


def test_il_riquadro_preseleziona_il_fornitore(sorgente: str):
    """Un clic sulla riga deve lasciare un solo gesto: scegliere i termini."""
    # Il NOME, non la P.IVA: `selectedNomi` dentro RegoleDialog e' keyed su
    # `f.fornitore` (sei punti). Passando la P.IVA il set non matchava nessuno e
    # il dialog si apriva con zero selezionati e il Salva disabilitato — la
    # preselezione non esisteva, pur essendo dichiarata nel commit.
    assert "setRegolaNome(f.label)" in sorgente, (
        "la preselezione non passa piu' il nome del fornitore"
    )
    assert "nomeIniziale={regolaNome}" in sorgente
    assert "pivaIniziale" not in sorgente, (
        "tornata la preselezione per P.IVA: non matcha selectedNomi"
    )
    # E il dialog deve USARE `nomeIniziale` all'apertura: ignorarlo (selezione
    # sempre vuota) e' la stessa regressione e restava verde (mutante del 26/09).
    testo = re.sub(r"\s+", " ", sorgente)
    assert "setSelectedNomi(nomeIniziale ? new Set([nomeIniziale]) : new Set());" in testo, (
        "RegoleDialog non preseleziona piu' il fornitore che riceve"
    )


def test_eliminare_una_regola_ricarica_la_lista_solo_se_riuscita(sorgente: str):
    """Togliere una regola ricalcola le scadenze delle sue fatture: senza
    `onSalvato` la lista restava quella di prima (mutante sopravvissuto il
    26/09). E senza guardare la risposta diceva «Regola eliminata» anche quando
    il server aveva rifiutato."""
    # Due handleDelete nel file: questa e' quella delle regole (l'altra elimina
    # la fattura dal dettaglio).
    i = sorgente.index("async function handleDelete(id: string)")
    corpo = re.sub(r"\s+", " ", sorgente[i:sorgente.index("const pivaToNome", i)])
    ordine = [
        'const res = await fetch(`/api/scadenziario/regole/${id}`, { method: "DELETE" });',
        'if (!res.ok) { toast.error("Errore eliminazione"); return; }',
        "setRegole(r => r.filter(x => x.id !== id));",
        'toast.success("Regola eliminata");',
        "onSalvato?.();",
    ]
    posizioni = [corpo.find(riga) for riga in ordine]
    assert -1 not in posizioni, f"manca un passo dell'eliminazione: {list(zip(ordine, posizioni))}"
    assert posizioni == sorted(posizioni), f"passi dell'eliminazione fuori ordine: {corpo}"


def _blocco_riquadro(src: str) -> str:
    """Il solo blocco del riquadro fornitori, dalla classifica alla sua chiusura.

    Cercare un letterale in TUTTO il file non dice che stia nel punto giusto: il
    reviewer ha bucato la prima stesura spostando `modalitaCatena ? (` in un
    punto scollegato e il test restava verde.
    """
    i = src.index("fornitoriSenzaScadenza(buckets.senzaScadenza")
    j = src.index("{/* Toolbar */}", i)
    return src[i:j]


def _mostra(catena, filtri, n):
    return esegui_ts(
        MODULO,
        "emit(m.mostraRiquadroSenzaScadenza(input));",
        {"modalitaCatena": catena, "filtriAttivi": filtri, "senzaScadenza": n},
        richiede=["mostraRiquadroSenzaScadenza"],
    )


def test_il_riquadro_c_e_nella_sede_senza_filtri():
    assert _mostra(False, False, 1) is True


@pytest.mark.parametrize(
    "catena, filtri, n",
    [
        # In catena no (Mattia, 28/9): le regole sono per-sede, e la classifica
        # in sola lettura ripeteva la sezione «Senza scadenza» dell'elenco.
        (True, False, 723),
        # Con un filtro il conteggio non e' piu' quello di tutto il debito.
        (False, True, 5),
        (False, False, 0),
    ],
)
def test_il_riquadro_non_c_e(catena, filtri, n):
    assert _mostra(catena, filtri, n) is False


def test_il_render_usa_la_regola_della_lib(sorgente: str):
    """La regola in lib non serve se il .tsx non la chiama sul riquadro."""
    testo = re.sub(r"\s+", " ", sorgente)
    i = testo.index("{mostraRiquadroSenzaScadenza({")
    j = testo.index("fornitoriSenzaScadenza(buckets.senzaScadenza", i)
    # Fra la condizione e la classifica c'e' un solo blocco: il suo.
    assert testo[i:j].count("&& (() => {") == 1, "la condizione non e' piu' quella del riquadro"
    assert "modalitaCatena: !!modalitaCatena," in testo[i:j]


def test_nel_riquadro_ogni_fornitore_apre_le_sue_regole(sorgente: str):
    blocco = re.sub(r"\s+", " ", _blocco_riquadro(sorgente))
    assert "<button" in blocco
    assert "setRegolaNome(f.label); setRegoleOpen(true);" in blocco, (
        "la riga del fornitore non apre piu' le regole"
    )


def test_il_riquadro_viene_davvero_renderizzato(sorgente: str):
    """Calcolare la classifica e non mostrarla e' il difetto gemello.

    Il docstring di questo file dichiara di coprire anche «essere chiamata e non
    portare a nulla»: il reviewer ha sostituito la condizione di render con
    `false &&` e tutti i test restavano verdi. Ora la condizione e' ancorata.
    """
    blocco = _blocco_riquadro(sorgente)
    assert "{riepilogo.top.length > 0 && (" in blocco, (
        "il riquadro non e' piu' condizionato alla classifica non vuota: se la "
        "condizione e' stata cambiata in qualcosa di sempre falso, la "
        "classifica viene calcolata e mai mostrata"
    )
    assert "riepilogo.top.map(" in blocco, (
        "le voci della classifica non vengono piu' iterate a video"
    )
