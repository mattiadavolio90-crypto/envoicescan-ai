"""I flag per-tab decidono quali tab il cliente vede: eseguono il TS vero.

`tab-flags.ts` governa **cosa sparisce dall'interfaccia di un cliente pagante**.
La classe di difetto e' la peggiore: se sbaglia verso, nessun errore compare —
le tab semplicemente non ci sono piu', e il cliente lo scopre prima di noi.

**Perche' la convenzione e' INVERSA** (chiave presente = tab SPENTA). I flag
arrivano al client come lista delle sole chiavi ATTIVE, quindi "assente" e "mai
configurato" sono lo stesso valore. Con la convenzione diretta i clienti in
produzione — che non hanno nessuna chiave tab — si vedrebbero sparire tutte le
tab al primo deploy: e' il bug OFFSIDE, un piano piu' in basso.
`test_cliente_senza_chiavi_vede_tutte_le_tab` e' il presidio di quel disastro.

**Perche' il test di coerenza TS<->Python.** Il formato della chiave e' scritto
due volte: `tabOffKey` qui e `_is_tab_off_key` nel worker (che valida per
prefisso, per non duplicare l'elenco delle tab). Sono due sorgenti che possono
driftare in silenzio: una tab spenta dall'admin che il worker non riconosce non
viaggia al client, e l'interruttore non fa niente — esattamente il difetto
`trigger_servizi_off` appena corretto. Il test genera le chiavi con il TS vero e
le fa validare dal Python vero, che e' l'unico modo di vederlo senza leggere il
sorgente.
"""
import os

import pytest

from tests.helpers_ts import esegui_ts

os.environ.setdefault("WORKER_DEV_MODE", "1")

MODULO = "lib/tab-flags"

_RICHIEDE = [
    "tabOffKey", "tabAbilitata", "tabAttive", "primaTabAttiva",
    "sezioneHaTabAttive", "risolviTab",
]


def _chiama(espressione: str, argomento=None):
    return esegui_ts(MODULO, espressione, argomento, richiede=_RICHIEDE)


class TestTabAbilitata:
    def test_admin_vede_tutto(self):
        # pagine == null = nessuna restrizione: e' la semantica di page-guard.
        assert _chiama('emit(m.tabAbilitata(null, "margini", "coperti"))') is True

    def test_cliente_senza_chiavi_vede_tutte_le_tab(self):
        """Il presidio della convenzione inversa.

        Un cliente esistente ha `pagine_abilitate` con le pagine e NESSUNA chiave
        tab. Se qualcuno invertisse la convenzione, qui tutte le tab sparirebbero
        in produzione al primo deploy.
        """
        esito = _chiama("""
          const pagine = ["margini", "prezzi", "analisi_fatture"];
          const out = {};
          for (const [sez, tabs] of Object.entries(m.TAB_SEZIONI)) {
            for (const t of tabs) out[sez + "/" + t.key] = m.tabAbilitata(pagine, sez, t.key);
          }
          emit(out);
        """)
        assert all(esito.values()), [k for k, v in esito.items() if not v]
        assert len(esito) == 18  # 18 tab su 6 sezioni: se cambia, aggiorna il piano

    def test_chiave_presente_spegne_la_tab(self):
        assert _chiama(
            'emit(m.tabAbilitata(["tab_off_margini_coperti"], "margini", "coperti"))'
        ) is False

    def test_spegnere_una_tab_non_tocca_le_sorelle(self):
        esito = _chiama("""
          const p = ["tab_off_margini_coperti"];
          emit({
            calcolo: m.tabAbilitata(p, "margini", "calcolo"),
            analisi: m.tabAbilitata(p, "margini", "analisi"),
            altra_sezione: m.tabAbilitata(p, "prezzi", "coperti"),
          });
        """)
        assert esito == {"calcolo": True, "analisi": True, "altra_sezione": True}


class TestPrimaTabAttiva:
    def test_salta_la_prima_se_spenta(self):
        # Uccide il mutante "ritorna sempre TAB_SEZIONI[s][0]".
        assert _chiama(
            'emit(m.primaTabAttiva(["tab_off_margini_calcolo"], "margini"))'
        ) == "coperti"

    def test_tutte_spente_da_null(self):
        assert _chiama("""
          const p = ["tab_off_margini_calcolo", "tab_off_margini_coperti", "tab_off_margini_analisi"];
          emit(m.primaTabAttiva(p, "margini"));
        """) is None

    def test_sezione_senza_tab_resta_visibile(self):
        # analisi_e_tag e' pagina unica: non deve mai sparire dalla sidebar.
        assert _chiama('emit(m.sezioneHaTabAttive([], "analisi_e_tag"))') is True


class TestRisolviTab:
    def test_tab_valida_e_attiva_resta_identica(self):
        # Niente redirect spurio: il guard confronta richiesta vs risolta.
        assert _chiama('emit(m.risolviTab([], "margini", "coperti"))') == "coperti"

    def test_tab_spenta_ricade_sulla_prima_attiva(self):
        assert _chiama(
            'emit(m.risolviTab(["tab_off_margini_calcolo"], "margini", "calcolo"))'
        ) == "coperti"

    def test_param_ignoto_ricade_sul_default(self):
        """`?tab=pippo` su /workspace deve dare foodcost.

        Prima esisteva una normalizzazione simile SOLO in workspace/page.tsx: le
        altre quattro sezioni accettavano qualsiasi stringa e renderizzavano il
        corpo vuoto.
        """
        assert _chiama('emit(m.risolviTab([], "workspace", "pippo"))') == "foodcost"
        assert _chiama('emit(m.risolviTab([], "analisi_fatture", "pippo"))') == "articoli"

    def test_param_assente_da_il_default(self):
        assert _chiama('emit(m.risolviTab([], "prezzi", null))') == "variazioni"

    def test_tutte_spente_da_null(self):
        assert _chiama("""
          const p = ["tab_off_workspace_foodcost", "tab_off_workspace_inventario"];
          emit(m.risolviTab(p, "workspace", "foodcost"));
        """) is None

    def test_idempotente(self):
        """Il guard redirige solo se risolta !== richiesta: se risolviTab non
        fosse idempotente sarebbe un ciclo di redirect infinito sul cliente."""
        esito = _chiama("""
          const casi = [
            [[], "margini", "pippo"],
            [["tab_off_margini_calcolo"], "margini", "calcolo"],
            [["tab_off_prezzi_variazioni", "tab_off_prezzi_sconti"], "prezzi", "variazioni"],
            [[], "agenda", null],
          ];
          emit(casi.map(([p, s, r]) => {
            const uno = m.risolviTab(p, s, r);
            return uno === m.risolviTab(p, s, uno);
          }));
        """)
        assert all(esito), esito


def test_formato_chiave_riconosciuto_dal_worker():
    """Coerenza TS<->Python su tutte e 18 le tab.

    Il TS genera le chiavi, il Python le valida. Uccide il mutante "cambio il
    prefisso (o il separatore) da una parte sola", che nessun test su un singolo
    lato puo' vedere: di la' resterebbe verde.
    """
    import services.fastapi_worker as fw

    chiavi = _chiama("""
      const out = [];
      for (const [sez, tabs] of Object.entries(m.TAB_SEZIONI)) {
        for (const t of tabs) out.push(m.tabOffKey(sez, t.key));
      }
      emit(out);
    """)
    assert len(chiavi) == 18
    non_riconosciute = [k for k in chiavi if not fw._is_tab_off_key(k)]
    assert not non_riconosciute, (
        f"il worker non riconosce {non_riconosciute}: il formato di tabOffKey e "
        "quello di _is_tab_off_key sono driftati. Una tab spenta dall'admin non "
        "arriverebbe al client e l'interruttore non farebbe niente."
    )


def test_le_chiavi_tab_sopravvivono_a_normalize_pagine():
    """L'anello completo: chiave generata dal TS -> trasporto worker -> lettura TS.

    E' il giro che il difetto `trigger_servizi_off` aveva rotto nel mezzo, con
    entrambi gli estremi corretti e nessun test a coprire la giunzione.
    """
    import services.fastapi_worker as fw

    chiave = _chiama('emit(m.tabOffKey("margini", "coperti"))')
    trasportate = fw._normalize_pagine({"margini": True, chiave: True})
    assert trasportate is not None and chiave in trasportate

    esito = _chiama(
        'emit({ coperti: m.tabAbilitata(input, "margini", "coperti"),'
        '        calcolo: m.tabAbilitata(input, "margini", "calcolo") })',
        argomento=trasportate,
    )
    assert esito == {"coperti": False, "calcolo": True}
