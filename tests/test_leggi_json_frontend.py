"""Un 500 del worker non e' una risposta vuota.

**Il difetto, 8/10/2026 (CASATI 14).** Il tab Personale leggeva le due GET con
`fetch(url).then(r => r.json())`. Una GET e' andata in 500 e il suo body
(`{detail: ...}`) e' JSON valido: preso per buono, mancava `dipendenti`, e ogni
nome ricadeva sul `dipendente_id` con l'etichetta «disattivato». L'Agenda
generale aveva lo stesso schema con `allSettled`: un 500 sulle spese mostrava il
mese senza spese, in silenzio.

`leggiJson` fa fallire i non-2xx, `sorgentiNonCaricate` dice quali sorgenti di
un `allSettled` non sono arrivate. Si eseguono, non si leggono nel sorgente.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/esito-caricamento"


def _con_fetch(status: int, body: dict, corpo_js: str):
    import json

    return esegui_ts(
        MODULO,
        f"""
globalThis.fetch = async () => new Response({json.dumps(json.dumps(body))},
  {{ status: {status}, headers: {{ "Content-Type": "application/json" }} }});
{corpo_js}
""",
        richiede=["leggiJson"],
    )


LETTURA = """
try { emit({ ok: true, valore: await m.leggiJson("/api/x") }); }
catch (e) { emit({ ok: false, messaggio: String(e.message) }); }
"""


@pytest.mark.parametrize("status", [400, 403, 404, 500, 502])
def test_un_errore_del_worker_rigetta_anche_se_il_body_e_json(status):
    esito = _con_fetch(status, {"detail": "Internal Server Error"}, LETTURA)
    assert esito["ok"] is False, (
        f"HTTP {status} letto come risposta buona: il body d'errore passerebbe "
        "per un elenco vuoto (nomi -> id nel tab Personale)"
    )
    assert str(status) in esito["messaggio"]


def test_una_risposta_buona_restituisce_il_body():
    body = {"dipendenti": [{"id": "a", "nome": "LIUBIS"}], "turni": []}
    esito = _con_fetch(200, body, LETTURA)
    assert esito == {"ok": True, "valore": body}


def test_rete_giu_rigetta():
    esito = esegui_ts(
        MODULO,
        """
globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
try { await m.leggiJson("/api/x"); emit("risolta"); } catch { emit("rigettata"); }
""",
        richiede=["leggiJson"],
    )
    assert esito == "rigettata"


def _sorgenti(esiti_js: str):
    return esegui_ts(
        MODULO,
        f"emit(m.sorgentiNonCaricate({esiti_js}))",
        richiede=["sorgentiNonCaricate"],
    )


def test_elenca_solo_le_sorgenti_rigettate_nell_ordine_dato():
    esiti = """[
      ["Appuntamenti", { status: "fulfilled", value: { eventi: [] } }],
      ["Spese", { status: "rejected", reason: new Error("500") }],
      ["Personale", { status: "rejected", reason: new Error("502") }],
    ]"""
    assert _sorgenti(esiti) == ["Spese", "Personale"]


def test_una_sorgente_arrivata_vuota_non_e_non_caricata():
    """Il vuoto legittimo (risposta arrivata, zero righe) non deve far
    comparire l'avviso: quello e' per chi non ha risposto."""
    esiti = """[
      ["Appuntamenti", { status: "fulfilled", value: {} }],
      ["Spese", { status: "fulfilled", value: { voci: [] } }],
    ]"""
    assert _sorgenti(esiti) == []


# ── Le pagine ────────────────────────────────────────────────────────────────
# Qui si legge il sorgente: l'harness esegue `lib/`, non i `.tsx`. E' il limite
# dichiarato di questi presidi — provano il collegamento, non il rendering.

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)"
PAGINE = {
    "workspace/personale-tab.tsx": 4,  # due GET del mese + due del dialog dipendenti
    "agenda/agenda-overview.tsx": 3,   # diario, spese, personale
}


def _codice(rel: str) -> str:
    s = (WEB / rel).read_text(encoding="utf-8")
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return "\n".join(r for r in s.splitlines() if not r.lstrip().startswith("//"))


@pytest.mark.parametrize("rel", sorted(PAGINE))
def test_nessuna_lettura_che_ignora_lo_status(rel):
    codice = _codice(rel)
    ciechi = re.findall(r"\.then\(\s*\(?\s*\w+\s*\)?\s*=>\s*\w+\.json\(\)\s*\)", codice)
    assert not ciechi, (
        f"{rel}: {ciechi} legge il body senza guardare lo status — un 500 "
        "diventa un elenco vuoto. Usa leggiJson da @/lib/esito-caricamento"
    )


@pytest.mark.parametrize("rel,attese", sorted(PAGINE.items()))
def test_le_letture_passano_da_leggi_json(rel, attese):
    codice = _codice(rel)
    assert 'from "@/lib/esito-caricamento"' in codice
    chiamate = len(re.findall(r"\bleggiJson(?:<[^>]*>)?\(", codice))
    assert chiamate == attese, f"{rel}: {chiamate} chiamate a leggiJson, attese {attese}"



def _righe(rel: str) -> list[str]:
    return [" ".join(r.split()) for r in _codice(rel).splitlines()]


# Il collegamento fra flag e render si legge per RIGA ESATTA, non con `in`: al
# primo giro questi presidi cercavano frammenti e 7 mutanti su 7 del
# code-reviewer restavano verdi (`false && statoElenco === "guasto"`, flag
# riazzerato nel `finally`, costante al posto del flag, `if (res)` al posto di
# `res?.ok`). Stessa lezione di L9 sui client mobile.
RIGHE_ESATTE = {
    "workspace/personale-tab.tsx": [
        # tab: il guasto entra nella decisione e la decisione nel render
        "const [caricamentoFallito, setCaricamentoFallito] = useState(false);",
        "const statoElenco = statoLista({ caricamento: loading, caricamentoFallito, righeCaricate: turni.length });",
        '{statoElenco === "caricamento" ? (',
        ') : statoElenco === "guasto" ? (',
        # a mese non caricato non si inserisce: `dipendenti` e' vuoto -> doppioni
        '<Button disabled={statoElenco === "guasto"} onClick={() => { setEditTurno(null); setDataDefault(giornoDefaultDialogo); setDipendenteIdDefaultTurno(undefined); setDialogOpen(true); }}>',
        '<Button variant="outline" disabled={statoElenco === "guasto"} onClick={() => { setEditMensile(null); setDipendenteIdMensile(undefined); setMensileDialogOpen(true); }}>',
        # il ramo del guasto dice il guasto, non il vuoto
        "Non sono riuscito a caricare {fmtMese(meseBase)}.",
        "<p className=\"text-sm text-muted-foreground\">Non sono riuscito a caricare i dipendenti.</p>",
        # dialog Gestisci dipendenti: niente «Nessun dipendente» su un errore
        "const [elencoFallito, setElencoFallito] = useState(false);",
        "const statoDipendenti = statoLista({ caricamento: loading, caricamentoFallito: elencoFallito, righeCaricate: attivi.length + disattivati.length });",
        '{statoDipendenti === "caricamento" ? (',
        ') : statoDipendenti === "guasto" ? (',
        # eliminazione: il successo si dice solo se c'e' stato
        'if (res?.ok) toast.success("Eliminato");',
        'if (res?.ok) toast.success("Mese eliminato");',
    ],
    "agenda/agenda-overview.tsx": [
        "setNonCaricate(sorgentiNonCaricate([",
        "[FONTI.appuntamento.label, evRes],",
        "[FONTI.spesa.label, spRes],",
        "[FONTI.turno.label, tuRes],",
        "{!loading && nonCaricate.length > 0 && (",
    ],
}


@pytest.mark.parametrize(
    "rel,riga", [(rel, r) for rel, righe in sorted(RIGHE_ESATTE.items()) for r in righe]
)
def test_riga_esatta_presente(rel, riga):
    assert riga in _righe(rel), f"{rel}: manca la riga esatta {riga!r}"


@pytest.mark.parametrize(
    "rel,setter",
    [("workspace/personale-tab.tsx", "setCaricamentoFallito"),
     ("workspace/personale-tab.tsx", "setElencoFallito")],
)
def test_il_flag_si_alza_nel_catch_e_si_abbassa_nel_try(rel, setter):
    """Alzato e abbassato UNA volta ciascuno, e mai nel `finally`: il finally
    gira sempre e cancellerebbe il `true` del catch."""
    righe = _righe(rel)
    assert righe.count(f"{setter}(true);") == 1, f"{setter}(true) non e' piu' nel catch"
    assert righe.count(f"{setter}(false);") == 1, f"{setter}(false) non e' piu' nel try"
    dentro_finally = False
    for r in righe:
        if r.startswith("} finally {"):
            dentro_finally = True
            continue
        if dentro_finally:
            if r in ("}", "});", "}, []);"):
                dentro_finally = False
                continue
            assert f"{setter}(" not in r, f"{rel}: {setter} dentro un finally ({r!r})"


@pytest.mark.parametrize("rel", sorted(RIGHE_ESATTE))
def test_nessun_ramo_spento_da_una_costante(rel):
    for r in _righe(rel):
        if any(t in r for t in ('=== "guasto"', "nonCaricate", "res?.ok", "setNonCaricate(")):
            assert "false &&" not in r and "&& false" not in r and "[] &&" not in r, (
                f"{rel}: ramo spento da una costante ({r!r})"
            )


def test_il_personale_dopo_un_errore_non_tiene_il_mese_precedente():
    """Dopo un cambio mese fallito i turni del mese prima restavano sotto
    l'etichetta del mese nuovo (rilievo NB3 del code-reviewer, 8/10)."""
    codice = _codice("workspace/personale-tab.tsx")
    m = re.search(r"const load = useCallback\(async.*?\n  \}, \[\]\);", codice, flags=re.S)
    assert m, "load() del tab Personale non trovata: rinominata?"
    ramo_catch = m.group(0).split("} catch {", 1)[1].split("} finally {", 1)[0]
    assert "setRisposta(null);" in ramo_catch
    assert "setCaricamentoFallito(true);" in ramo_catch


def test_il_dialog_dipendenti_dopo_un_errore_non_tiene_le_liste_vecchie():
    """Alla seconda apertura fallita le liste della prima resterebbero, e
    `statoLista` le presenterebbe come dati validi."""
    codice = _codice("workspace/personale-tab.tsx")
    m = re.search(r"const carica = useCallback\(async.*?\n  \}, \[\]\);", codice, flags=re.S)
    assert m, "carica() del dialog dipendenti non trovata: rinominata?"
    corpo_try, resto = m.group(0).split("} catch {", 1)
    ramo_catch = resto.split("} finally {", 1)[0]
    for riga in ("setAttivi([]);", "setDisattivati([]);", "setElencoFallito(true);"):
        assert riga in ramo_catch, f"manca {riga} nel catch del dialog"
    assert "setElencoFallito(false);" in corpo_try
    assert "setElencoFallito(true);" not in corpo_try
