"""La scelta fra app desktop e PWA /m, eseguita sul modulo vero con node.

Perche' esiste: il 23/09/2026 `apps/web/src/lib/device.ts` non aveva alcun test.
La misura di quel giorno ha mostrato che `isPhoneViewport()` decide SOLO sulla
larghezza della finestra — `maxTouchPoints` non entra mai in gioco fuori da
iPad e Android — quindi un PC fisso **senza touch** con la finestra affiancata
sotto i 768px veniva spostato su /m a meta' lavoro, senza alcun modo di tornare
indietro (da /m non c'era un link al desktop, e riallargare non bastava perche'
/m e' escluso dal redirect stesso).

Il fix non tocca la soglia: i telefoni veri devono continuare ad andare su /m.
Sposta il rimbalzo all'INGRESSO e aggiunge una via d'uscita memorizzata.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers_ts import esegui_ts  # noqa: E402

MODULO = "lib/device"


def _json(v):
    """Le opzioni viaggiano come letterale JS dentro l'espressione."""
    return json.dumps(v)

UA_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
UA_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
UA_IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/604.1"
)

# `localStorage` non esiste in node: lo stub e' un vero oggetto con stato, non un
# mock generoso — `impostaPreferenzaDesktop` deve poterci scrivere e rileggere.
_AMBIENTE = """
Object.defineProperty(globalThis, "navigator", {
  value: { userAgent: input.ua, maxTouchPoints: input.touch },
  configurable: true, writable: true,
});
globalThis.window = { innerWidth: input.w };
const _store = new Map(Object.entries(input.storage ?? {}));
globalThis.localStorage = {
  getItem: (k) => (_store.has(k) ? _store.get(k) : null),
  setItem: (k, v) => _store.set(k, String(v)),
  removeItem: (k) => _store.delete(k),
};
"""


def _esegui(espressione, ua=UA_WINDOWS, touch=0, w=1400, storage=None, richiede=()):
    return esegui_ts(
        MODULO,
        _AMBIENTE + espressione,
        {"ua": ua, "touch": touch, "w": w, "storage": storage or {}},
        richiede=richiede,
    )


def test_il_telefono_vero_va_ancora_su_mobile():
    """Il fix non deve spegnere il comportamento per cui /m esiste."""
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_IPHONE, touch=5, w=390,
        richiede=("serviVistaMobile",),
    ) is True


def test_il_tablet_resta_su_desktop():
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_IPAD, touch=5, w=810,
        richiede=("serviVistaMobile",),
    ) is False


def test_desktop_senza_touch_con_finestra_stretta_non_viene_strappato_via():
    """Il caso misurato: NON e' un problema dei 2-in-1, il touch non c'entra.

    A parita' di larghezza, `maxTouchPoints` 0 e 10 danno lo stesso esito: e' la
    sola larghezza a decidere. Per questo il presidio gira su un desktop senza
    touch — se qualcuno "risolvesse" guardando il touch, questo test resterebbe
    rosso e direbbe perche'.
    """
    opts = {
        "isPhone": True,       # finestra < 768: isPhoneViewport() dice gia' true
        "pathname": "/margini",
        "giaDentro": True,     # stava gia' lavorando qui: ha solo ridimensionato
        "preferisceDesktop": False,
    }
    assert _esegui(
        f"emit(m.deveRimbalzareSuMobile({_json(opts)}));",
        touch=0, w=700,
        richiede=("deveRimbalzareSuMobile",),
    ) is False


def test_l_ingresso_su_una_pagina_desktop_da_telefono_rimbalza_ancora():
    """La controprova del test sopra: all'ingresso il rimbalzo deve restare."""
    opts = {
        "isPhone": True,
        "pathname": "/margini",
        "giaDentro": False,
        "preferisceDesktop": False,
    }
    assert _esegui(
        f"emit(m.deveRimbalzareSuMobile({_json(opts)}));",
        touch=0, w=700,
        richiede=("deveRimbalzareSuMobile",),
    ) is True


def test_la_scelta_versione_desktop_sopravvive_al_redirect():
    """Senza memoria il link "Versione desktop" non funzionerebbe affatto.

    Si atterra su /dashboard con la finestra ancora stretta e il redirect
    rispedisce su /m: il giro completo, non solo la scrittura della preferenza.
    """
    esito = _esegui(
        """
        m.impostaPreferenzaDesktop(true);
        emit(m.deveRimbalzareSuMobile({
          isPhone: true, pathname: "/dashboard",
          giaDentro: false, preferisceDesktop: m.preferisceDesktop(),
        }));
        """,
        touch=0, w=700,
        richiede=("impostaPreferenzaDesktop", "preferisceDesktop", "deveRimbalzareSuMobile"),
    )
    assert esito is False


def test_chi_ha_scelto_desktop_non_torna_su_m_rientrando_dal_login():
    """Il buco trovato per mutazione (M5), il caso che conta di piu'.

    `defaultNext()` del login usa `serviVistaMobile()`: se quella ignorasse la
    preferenza, la scelta "Versione desktop" durerebbe una sessione sola e al
    rientro si finirebbe di nuovo su /m — con la stessa sensazione di prima del
    fix. Il caso e' un TELEFONO vero, non una finestra stretta: e' l'unico in
    cui la preferenza deve battere il rilevamento.
    """
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_IPHONE, touch=5, w=390,
        storage={"oneflux_forza_desktop": "1"},
        richiede=("serviVistaMobile",),
    ) is False


def test_il_logout_riporta_alla_scelta_automatica():
    esito = _esegui(
        """
        m.impostaPreferenzaDesktop(false);
        emit({ pref: m.preferisceDesktop(), mobile: m.serviVistaMobile() });
        """,
        ua=UA_IPHONE, touch=5, w=390,
        storage={"oneflux_forza_desktop": "1"},
        richiede=("impostaPreferenzaDesktop", "preferisceDesktop", "serviVistaMobile"),
    )
    assert esito == {"pref": False, "mobile": True}


def test_storage_negato_non_blocca_l_app():
    """Modalita' privata: `localStorage` puo' lanciare. Non deve propagare."""
    esito = esegui_ts(
        MODULO,
        """
        Object.defineProperty(globalThis, "navigator", {
          value: { userAgent: input.ua, maxTouchPoints: 0 },
          configurable: true, writable: true,
        });
        globalThis.window = { innerWidth: 390 };
        globalThis.localStorage = {
          getItem: () => { throw new Error("storage negato"); },
          setItem: () => { throw new Error("storage negato"); },
          removeItem: () => { throw new Error("storage negato"); },
        };
        m.impostaPreferenzaDesktop(true);
        emit(m.preferisceDesktop());
        """,
        {"ua": UA_IPHONE},
        richiede=("preferisceDesktop", "impostaPreferenzaDesktop"),
    )
    assert esito is False


def test_admin_e_m_restano_esclusi_dal_rimbalzo():
    """/admin e' solo desktop, /m e' gia' mobile: rimbalzarli sarebbe un ciclo.

    `/margini` e' qui apposta: `startsWith("/m")` lo matcherebbe, e il confronto
    per segmento e' gia' costato un giro (vedi commento nel sorgente).
    """
    def rimbalza(pathname):
        return _esegui(
            f"emit(m.deveRimbalzareSuMobile({_json({'isPhone': True, 'pathname': pathname, 'giaDentro': False, 'preferisceDesktop': False})}));",
            touch=0, w=700,
            richiede=("deveRimbalzareSuMobile",),
        )

    assert rimbalza("/admin/utenti") is False
    assert rimbalza("/m") is False
    assert rimbalza("/m/diario") is False
    assert rimbalza("/margini") is True


# ── La SEQUENZA dei render, non la singola decisione ────────────────────────
#
# I test sopra provano `deveRimbalzareSuMobile` come funzione pura, passando
# `giaDentro` a mano. Il difetto trovato dalla review del 23/09/2026 non viveva
# li': viveva nell'ACCUMULO di stato fra un render e l'altro. `useIsMobile()`
# torna `!!isMobile` e al primo render vale sempre `false` (lo stato parte da
# `undefined`), quindi la decisione veniva segnata come presa su un falso e al
# secondo render — quello col valore vero — il rimbalzo non scattava piu'.

_SEQUENZA = """
Object.defineProperty(globalThis, "navigator", {
  value: { userAgent: input.ua, maxTouchPoints: input.touch },
  configurable: true, writable: true,
});
globalThis.window = { innerWidth: input.w };
const _store = new Map(Object.entries(input.storage ?? {}));
globalThis.localStorage = {
  getItem: (k) => (_store.has(k) ? _store.get(k) : null),
  setItem: (k, v) => _store.set(k, String(v)),
  removeItem: (k) => _store.delete(k),
};

// Riproduce l'effect di MobileRedirect su piu' render successivi.
let decisoPer = null;
let rimbalzi = 0;
for (const isPhone of input.renders) {
  if (!m.decisionePresa(isPhone)) continue;
  const giaDentro = decisoPer === input.pathname;
  decisoPer = input.pathname;
  if (m.deveRimbalzareSuMobile({
    isPhone, pathname: input.pathname,
    giaDentro, preferisceDesktop: m.preferisceDesktop(),
  })) rimbalzi++;
}
emit(rimbalzi);
"""


def _rimbalzi(renders, ua=UA_IPHONE, touch=5, w=390, pathname="/margini", storage=None):
    return esegui_ts(
        MODULO,
        _SEQUENZA,
        {"ua": ua, "touch": touch, "w": w, "pathname": pathname,
         "renders": renders, "storage": storage or {}},
        richiede=("decisionePresa", "deveRimbalzareSuMobile", "preferisceDesktop"),
    )


def test_il_telefono_rimbalza_anche_col_primo_render_indeterminato():
    """Il blocco della review: `undefined` poi `true` e' la sequenza REALE.

    Prima del fix dava 0 rimbalzi — i telefoni veri restavano sulla vista
    desktop, cioe' la regressione che il lavoro dichiarava di non introdurre.
    """
    assert _rimbalzi([None, True]) == 1


def test_il_ridimensionamento_dopo_l_ingresso_non_rimbalza_di_nuovo():
    """La ragione per cui il ref esiste: si decide una volta sola.

    Desktop che restringe la finestra mentre lavora: il primo render sa gia'
    che non e' un telefono, i successivi non devono strapparlo via.
    """
    assert _rimbalzi([False, True, True], ua=UA_WINDOWS, touch=0, w=700) == 0


def test_render_indeterminati_ripetuti_non_consumano_la_decisione():
    """StrictMode monta due volte: l'indeterminato non deve "bruciare" il turno."""
    assert _rimbalzi([None, None, True]) == 1


def test_il_tablet_in_split_view_non_finisce_su_mobile():
    """Uccide il mutante RM1 della review: la guardia `isTabletDevice()`.

    Il caso va scelto dove i due mondi DIVERGONO. A 810px `810 < 768` e' gia'
    false, quindi togliere la guardia non cambierebbe nulla: il test passerebbe
    anche sul codice rotto. In Split View (700px) la guardia e' l'unica cosa che
    tiene l'iPad sull'app completa — ed e' la regola scritta in cima a device.ts.
    """
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_IPAD, touch=5, w=700,
        richiede=("serviVistaMobile",),
    ) is False

    UA_IPADOS_MAC = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    )
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_IPADOS_MAC, touch=5, w=700,
        richiede=("serviVistaMobile",),
    ) is False


def test_la_soglia_dei_telefoni_e_768_non_una_qualunque():
    """Uccide il mutante RM2: soglia allargata (es. `<= 1400`).

    Senza un caso SOPRA la soglia su un dispositivo non-telefono, allargarla
    resterebbe invisibile: un desktop a schermo pieno finirebbe su /m.
    """
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_WINDOWS, touch=0, w=1400,
        richiede=("serviVistaMobile",),
    ) is False
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_WINDOWS, touch=0, w=768,
        richiede=("serviVistaMobile",),
    ) is False
    assert _esegui(
        "emit(m.serviVistaMobile());",
        ua=UA_WINDOWS, touch=0, w=767,
        richiede=("serviVistaMobile",),
    ) is True


def test_la_funzione_da_sola_non_rimbalza_su_un_rilevamento_indeterminato():
    """Difesa in profondita' per un chiamante che salti `decisionePresa`.

    Nel flusso vero MobileRedirect filtra prima, quindi qui `isPhone` e' sempre
    booleano e `!opts.isPhone` e `opts.isPhone !== true` coincidono (il mutante
    che li scambia sopravvive, ed e' ridondanza, non un buco). Il giorno in cui
    un secondo chiamante chiamasse la funzione senza filtrare, `undefined` non
    deve valere "e' un telefono".
    """
    for indeterminato in ("null", "undefined"):
        assert _esegui(
            f"""emit(m.deveRimbalzareSuMobile({{
              isPhone: {indeterminato}, pathname: "/margini",
              giaDentro: false, preferisceDesktop: false,
            }}));""",
            touch=0, w=390,
            richiede=("deveRimbalzareSuMobile",),
        ) is False


def test_le_due_transizioni_della_preferenza_vanno_in_direzioni_opposte():
    """Estratte dal .tsx perche' li' nessun test le vedeva.

    Invertire i due booleani non faceva fallire niente, e l'effetto e' visibile:
    chi fa logout da /m resterebbe bloccato sulla vista desktop al rientro, e
    chi chiede la versione desktop verrebbe rispedito su /m. Si asseriscono
    ENTRAMBE le transizioni, non la sola chiamata (rilievo della re-review del
    23/09/2026).
    """
    esito = _esegui(
        """
        m.scegliVersioneDesktop();
        const dopoScelta = m.preferisceDesktop();
        m.dimenticaPreferenzaAlLogout();
        const dopoLogout = m.preferisceDesktop();
        emit({ dopoScelta, dopoLogout });
        """,
        ua=UA_IPHONE, touch=5, w=390,
        richiede=("scegliVersioneDesktop", "dimenticaPreferenzaAlLogout", "preferisceDesktop"),
    )
    assert esito == {"dopoScelta": True, "dopoLogout": False}
