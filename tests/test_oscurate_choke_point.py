"""Ogni query su `fatture` decide, una volta per sempre, se conta soldi o no.

Perche' esiste
==============
`escludi_oscurate` non e' un choke point: non esiste un punto unico da cui
passano le query su `fatture`. Sono 119 siti su 19 file, e il filtro va scritto a
mano in quelli che contano.

Il precedente dice come va a finire senza una guardia: `filter_active` sta in
`db_service` dallo stesso identico scopo, e `fastapi_worker.py` — il file piu'
grande del progetto — **non la usa mai**, pur avendo 30 siti `table("fatture")`
che riscrivono il filtro a mano. L'helper e' rimasto, la disciplina no.

Cosa misura
===========
Per ogni coppia (file, funzione) che tocca `fatture`, il filtro c'e' oppure la
coppia sta in ELENCO_SENZA_FILTRO **con un motivo scritto**. Una funzione nuova
che nasce senza nessuna delle due cose fa fallire questo test: chi la scrive
deve fermarsi un attimo e decidere, che e' esattamente lo scopo.

Non e' un test sul comportamento, ed e' una scelta: il comportamento e'
presidiato da test_sql_oscura_fattura (le 13 RPC, eseguite) e da
test_oscura_fattura_endpoint. Questo presidia il DECADIMENTO, che nessun test di
comportamento puo' vedere perche' riguarda codice che ancora non esiste.
"""
from __future__ import annotations

import collections
import pathlib
import re

RADICE = pathlib.Path(__file__).resolve().parent.parent
SERVICES = RADICE / "services"

# (file relativo a services/, funzione) -> perche' NON filtra `oscurata`.
# Il motivo e' obbligatorio: una riga qui senza spiegazione e' un filtro
# dimenticato che si e' travestito da scelta.
ELENCO_SENZA_FILTRO = {
    # ── Ciclo di vita del documento: cestino, ripristino, eliminazione, purge.
    # Agiscono SULLA fattura, non sui suoi importi: escludere le escluse le
    # renderebbe impossibili da cestinare o ripristinare.
    ("db_service.py", "elimina_fattura_completa"): "hard/soft delete del documento",
    ("db_service.py", "elimina_tutte_fatture"): "svuotamento account",
    ("db_service.py", "get_fatture_cestino"): "elenco cestino (filtra il contrario)",
    ("db_service.py", "ripristina_fattura"): "ripristino dal cestino",
    ("db_service.py", "svuota_cestino"): "svuotamento cestino",
    ("db_service.py", "purge_cestino_scaduto"): "retention cestino 30gg",
    ("db_service.py", "purge_fatture_retention"): "retention GDPR 2 anni",
    ("db_service.py", "_pulisci_riparto_orfano"): "conta righe VIVE dopo una delete",
    ("db_service.py", "_smarca_fatture_senza_riparto"): "ciclo di vita del riparto",
    ("db_service.py", "aggiorna_data_competenza_fattura"): "modifica del documento",
    ("db_service.py", "aggiorna_categoria_fatture"): "scrittura categoria",
    ("routers/cestino.py", "elimina_fattura_soft"): "sposta nel cestino",
    ("routers/cestino.py", "oscura_fattura"): "SCRIVE il flag: e' l'endpoint stesso",

    # ── Scritture e tooling di categorizzazione: lavorano sulle righe da
    # classificare. Una fattura esclusa dai conti va comunque categorizzata, o
    # tornando nei conti rientrerebbe come "Da Classificare".
    ("ai_service.py", "_importo"): "propagazione categoria admin cross-cliente",
    ("routers/fatture.py", "aggiorna_categoria_riga"): "correzione categoria",
    ("routers/fatture.py", "categoria_batch"): "correzione categoria in blocco",
    ("routers/fatture.py", "get_categorie_disponibili"): "elenco categorie esistenti",
    ("routers/fatture.py", "get_fornitori_disponibili"): "elenco fornitori esistenti",
    ("routers/fatture.py", "fatture_sposta_sede"): "spostamento fra sedi",
    ("routers/admin.py", "_categorie_da_controllare"): "tooling admin qualita'",
    ("routers/admin.py", "_compute_admin_overview"): "volumi per fatturazione",
    ("routers/admin.py", "_imp"): "tooling admin qualita'",
    ("routers/admin.py", "_promuovibile"): "tooling admin memoria AI",
    ("routers/admin.py", "admin_qualita_audit_annulla"): "tooling admin qualita'",
    ("routers/admin.py", "admin_qualita_auto_review"): "tooling admin qualita'",
    ("routers/admin.py", "admin_qualita_classifica"): "tooling admin qualita'",
    ("routers/admin.py", "admin_qualita_coda"): "tooling admin qualita'",
    ("routers/admin.py", "prepara_suggerimenti_ai"): "tooling admin memoria AI",
    ("db_service.py", "get_descrizioni_distinte"): "catalogo descrizioni per l'AI",

    # ── Ingestione: decidono se un file e' gia' stato caricato. Una fattura
    # esclusa E' stata caricata: ignorarla creerebbe duplicati veri.
    ("invoice_service.py", "salva_fattura_processata"): "scrittura righe in ingestione",
    ("upload_handler.py", "handle_uploaded_files"): "dedup upload",
    ("upload_handler.py", "_find_active_exact_files_for_targets"): "dedup upload",
    ("upload_handler.py", "_find_active_existing_files"): "dedup upload",
    ("upload_handler.py", "_collect_post_upload_quality_checks"): "qualita' post-upload",
    ("upload_handler.py", "_run_post_upload_ai_categorization"): "categorizzazione post-upload",
    ("auth_service.py", "_is_invoicetronic_event"): "instradamento evento SDI",
    ("fastapi_worker.py", "_strip_suffix_n"): "dedup upload per nome file",
    ("fastapi_worker.py", "_run_agent_notturno"): "classifica righe, non conta soldi",
    ("fastapi_worker.py", "_esegui"): "tooling admin",

    # ── Presenza e copertura temporale dei dati, non importi. Una fattura
    # esclusa resta un documento caricato: dire "non hai fatture" sarebbe falso.
    ("fastapi_worker.py", "_briefing_fatture_mancanti"): "segnale di ARRIVO fatture",
    ("fastapi_worker.py", "_briefing_onboarding"): "«ha almeno una fattura?»",
    ("tag_suggestion_service.py", "_latest_invoice_date"): "data ultimo caricamento",
    ("tag_suggestion_service.py", "_fetch_recent_rows"): "candidati tag, non spesa",
    ("routers/scadenziario.py", "get_anteprima_fattura"): "righe del documento in lista",
    ("routers/scadenziario.py", "get_fornitori_scadenziario"): "filtro fornitore della lista",

    # ── Riparto: e' l'endpoint a rifiutare (409), non la query a filtrare.
    # Filtrare qui sarebbe PEGGIO: senza righe reali `_proietta_riparto` cade sul
    # ramo sintetico e proietta le quote lo stesso — "esclusa alla fonte, viva a
    # valle". Vedi services/routers/cestino.py::oscura_fattura.
    ("riparto_service.py", "righe_ripartite_proiettate"): "il 409 la previene a monte",
    ("riparto_service.py", "_pesi_e_netto_categoria_fattura"): "idem",
    ("riparto_service.py", "verifica_documento_vivo"): "esistenza del documento",
    ("routers/riparto.py", "riparto_da_coda"): "creazione riparto dalla coda",
    ("routers/riparto.py", "riparto_elimina"): "ciclo di vita del riparto",
    ("routers/riparto.py", "riparto_riga_categoria"): "correzione categoria quota",
    ("routers/riparto.py", "gruppo_costi_comuni"): "elenco fatture di struttura",

    # ── Loader legacy senza chiamanti vivi (misurato 12/9/2026: 0).
    ("db_service.py", "carica_sconti_e_omaggi"): "nessun chiamante",
    ("db_service.py", "get_fatture_stats"): "nessun chiamante",
}

# Funzioni in cui SOLO ALCUNI dei siti filtrano, e va bene cosi'.
# Ogni voce dice quanti siti devono filtrare e perche' gli altri no.
PARZIALI = {
    ("fastapi_worker.py", "_build_chat_system_prompt"): (
        3, "3 conteggi di spesa filtrano; 2 leggono MIN/MAX(data_documento), "
           "cioe' il periodo coperto dai dati: una fattura esclusa e' comunque "
           "un documento caricato"),
    ("routers/riparto.py", "riparto_da_fattura"): (
        1, "la select porta `oscurata` per il 409; l'altro sito e' la marcatura "
           "delle righe come ripartite"),
}


# Le DUE forme valide del filtro. Cercare la sola stringa "oscurata" NON basta:
# `escludi_oscuratE` finisce per "e" e non la contiene — alla prima stesura questo
# test dava per non filtrati due siti che lo erano. Un presidio che cerca il
# termine sbagliato e' verde (o rosso) per il motivo sbagliato.
FORME_DEL_FILTRO = ('escludi_oscurate(', '"oscurata"', "'oscurata'")


def _filtra(contesto: str) -> bool:
    return any(forma in contesto for forma in FORME_DEL_FILTRO)


def _mappa_siti():
    """(file, funzione) -> lista di bool «questo sito filtra oscurata»."""
    siti = collections.defaultdict(list)
    for f in sorted(SERVICES.rglob("*.py")):
        righe = f.read_text(encoding="utf-8-sig").split("\n")
        funzione = "<modulo>"
        for i, riga in enumerate(righe):
            m = re.match(r"\s*(?:async )?def (\w+)", riga)
            if m:
                funzione = m.group(1)
            if 'table("fatture")' in riga or "table('fatture')" in riga:
                # Finestra generosa: la catena PostgREST si sviluppa su piu' righe,
                # e va guardata anche ALL'INDIETRO — `escludi_oscurate(query)`
                # avvolge la chiamata e compare PRIMA del `.table("fatture")`.
                # Cercare solo in avanti darebbe per non filtrati due siti che lo
                # sono: e' il difetto che questo test ha avuto alla prima stesura.
                contesto = "\n".join(righe[max(0, i - 3):i + 15])
                rel = str(f.relative_to(SERVICES))
                siti[(rel, funzione)].append(_filtra(contesto))
    return siti


def test_ogni_query_su_fatture_ha_deciso_se_conta_soldi():
    """Nessuna coppia (file, funzione) resta senza una decisione esplicita."""
    siti = _mappa_siti()
    non_dichiarate = []
    for chiave, flag in sorted(siti.items()):
        if chiave in PARZIALI:
            continue
        if all(flag):
            continue
        if chiave in ELENCO_SENZA_FILTRO:
            continue
        non_dichiarate.append(f"{chiave[0]}::{chiave[1]} ({len(flag)} siti)")

    assert not non_dichiarate, (
        "Query su `fatture` che non hanno deciso se contano soldi:\n  "
        + "\n  ".join(non_dichiarate)
        + "\n\nSe la funzione CONTA (importi, aggregati, KPI, costi): applica "
          "`escludi_oscurate` o `.eq(\"oscurata\", False)`.\n"
          "Se NON conta (ciclo di vita, ingestione, categorizzazione, presenza "
          "dati): aggiungila a ELENCO_SENZA_FILTRO con il motivo."
    )


def test_le_funzioni_parziali_filtrano_il_numero_atteso_di_siti():
    """Dove solo alcuni siti filtrano, il conteggio e' quello dichiarato.

    Senza questo, aggiungere una query che conta dentro una funzione gia'
    dichiarata parziale passerebbe inosservato.
    """
    siti = _mappa_siti()
    for chiave, (attesi, motivo) in PARZIALI.items():
        flag = siti.get(chiave)
        assert flag is not None, f"{chiave}: la funzione non esiste piu', togliere da PARZIALI"
        assert sum(flag) == attesi, (
            f"{chiave[0]}::{chiave[1]}: filtrano {sum(flag)} siti su {len(flag)}, "
            f"attesi {attesi}. Motivo dichiarato: {motivo}"
        )


def test_l_elenco_non_contiene_voci_morte():
    """Una voce che non corrisponde piu' a nessuna funzione e' rumore: nasconde
    il fatto che il codice e' cambiato sotto."""
    siti = _mappa_siti()
    morte = [f"{f}::{fn}" for (f, fn) in ELENCO_SENZA_FILTRO if (f, fn) not in siti]
    assert not morte, (
        "Voci di ELENCO_SENZA_FILTRO che non corrispondono a nessuna query su "
        "`fatture` (funzione rinominata o rimossa):\n  " + "\n  ".join(sorted(morte))
    )
