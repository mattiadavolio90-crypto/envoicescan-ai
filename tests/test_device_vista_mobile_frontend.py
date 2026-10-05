"""La scelta fra app desktop e PWA /m, eseguita sul modulo vero con node.

Perche' esiste: il 23/09/2026 `apps/web/src/lib/device.ts` non aveva alcun test,
e un PC con la finestra affiancata sotto i 768px finiva su /m a meta' lavoro.

Il 5/10/2026 la regola e' cambiata (Mattia): **da telefono, iPhone o Android, i
clienti hanno solo la versione mobile**. Un cliente su iPhone era rimasto sulla
vista desktop, senza la barra in basso: o aveva scelto «Versione desktop» (scelta
memorizzata, e dal desktop non c'era un tasto per tornare), o Safari chiedeva il
«sito desktop» e l'iPhone, con lo user agent di un Mac e il touch, passava per un
iPad. La scelta non c'e' piu', e il telefono si riconosce anche dallo schermo.
"""
import json
import sys
from pathlib import Path

import pytest

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
# iPadOS 13+ E iPhone con «Richiedi sito desktop»: lo stesso user agent di un Mac.
UA_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
UA_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36"
)
UA_ANDROID_TABLET = (
    "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
# Chrome Android in «Sito desktop»: lo user agent di un PC Linux.
UA_LINUX = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# `screen` e' quello del dispositivo (lato corto e lungo), `w` la finestra. Il
# vecchio `localStorage` resta, con la preferenza desktop di chi l'aveva scelta:
# non deve contare piu'.
_AMBIENTE = """
Object.defineProperty(globalThis, "navigator", {
  value: { userAgent: input.ua, maxTouchPoints: input.touch },
  configurable: true, writable: true,
});
globalThis.window = { innerWidth: input.w, screen: input.screen };
const _store = new Map(Object.entries(input.storage ?? {}));
globalThis.localStorage = {
  getItem: (k) => (_store.has(k) ? _store.get(k) : null),
  setItem: (k, v) => _store.set(k, String(v)),
  removeItem: (k) => _store.delete(k),
};
"""

DESKTOP = {"ua": UA_WINDOWS, "touch": 0, "w": 1400, "screen": {"width": 1920, "height": 1080}}
IPHONE = {"ua": UA_IPHONE, "touch": 5, "w": 390, "screen": {"width": 390, "height": 844}}


def _esegui(espressione, ua=UA_WINDOWS, touch=0, w=1400, screen=None, storage=None, richiede=()):
    return esegui_ts(
        MODULO,
        _AMBIENTE + espressione,
        {"ua": ua, "touch": touch, "w": w, "screen": screen if screen is not None else {"width": 1920, "height": 1080},
         "storage": storage or {}},
        richiede=richiede,
    )


def _mobile(**disp):
    return _esegui("emit(m.serviVistaMobile());", richiede=("serviVistaMobile",), **disp)


# ─── Chi e' un telefono ───────────────────────────────────────────────────────
@pytest.mark.parametrize("disp", [
    IPHONE,
    {"ua": UA_ANDROID, "touch": 5, "w": 412, "screen": {"width": 412, "height": 915}},
    # «Richiedi sito desktop»: iPhone con lo user agent di un Mac e la finestra
    # larga 980 (il viewport desktop di Safari). Prima passava per un iPad.
    {"ua": UA_MAC, "touch": 5, "w": 980, "screen": {"width": 390, "height": 844}},
    {"ua": UA_MAC, "touch": 5, "w": 980, "screen": {"width": 440, "height": 956}},
    # Lo stesso in orizzontale: conta il lato corto.
    {"ua": UA_MAC, "touch": 5, "w": 980, "screen": {"width": 844, "height": 390}},
    # Android in «Sito desktop»: lo user agent di un PC Linux.
    {"ua": UA_LINUX, "touch": 5, "w": 980, "screen": {"width": 412, "height": 915}},
], ids=["iphone", "android", "iphone-sito-desktop", "iphone-pro-max-sito-desktop",
        "iphone-sito-desktop-orizzontale", "android-sito-desktop"])
def test_il_telefono_va_su_mobile_comunque_si_presenti(disp):
    assert _mobile(**disp) is True


@pytest.mark.parametrize("disp", [
    DESKTOP,
    {"ua": UA_IPAD, "touch": 5, "w": 810, "screen": {"width": 810, "height": 1080}},
    # Split View: la finestra e' stretta, ma e' un iPad (la guardia isTabletDevice).
    {"ua": UA_IPAD, "touch": 5, "w": 700, "screen": {"width": 810, "height": 1080}},
    {"ua": UA_MAC, "touch": 5, "w": 700, "screen": {"width": 1024, "height": 1366}},
    # iPad mini, il tablet piu' piccolo.
    {"ua": UA_MAC, "touch": 5, "w": 700, "screen": {"width": 744, "height": 1133}},
    {"ua": UA_ANDROID_TABLET, "touch": 10, "w": 700, "screen": {"width": 800, "height": 1280}},
    # Portatile col touch: schermo da computer.
    {"ua": UA_WINDOWS, "touch": 10, "w": 1400, "screen": {"width": 1366, "height": 768}},
    # 2-in-1 Windows da 10" al 150%: schermo piccolo in px CSS, ma non e' un telefono.
    {"ua": UA_WINDOWS, "touch": 10, "w": 853, "screen": {"width": 853, "height": 533}},
    # Il Mac vero non ha touch.
    {"ua": UA_MAC, "touch": 0, "w": 1400, "screen": {"width": 1440, "height": 900}},
], ids=["desktop", "ipad", "ipad-split-view", "ipados-mac", "ipad-mini", "tablet-android",
        "portatile-touch", "2in1-windows-150", "mac"])
def test_tablet_e_computer_restano_su_desktop(disp):
    assert _mobile(**disp) is False


def test_il_lato_corto_del_telefono_e_600_non_uno_qualunque():
    """Il caso va scelto dove i due mondi divergono: sotto e sopra la soglia, con
    lo user agent di un Mac (iPad o iPhone in «sito desktop») e la finestra larga."""
    mac = {"ua": UA_MAC, "touch": 5, "w": 980}
    assert _mobile(**mac, screen={"width": 599, "height": 900}) is True
    assert _mobile(**mac, screen={"width": 600, "height": 900}) is False


def test_lo_schermo_piccolo_senza_touch_non_e_un_telefono():
    """Un monitor piccolo di un computer non e' un telefono: serve anche il touch."""
    assert _mobile(ua=UA_WINDOWS, touch=0, w=980, screen={"width": 500, "height": 800}) is False


def test_senza_dati_sullo_schermo_si_decide_dal_resto():
    assert _mobile(ua=UA_MAC, touch=5, w=980, screen={}) is False
    assert _mobile(ua=UA_IPHONE, touch=5, w=390, screen={}) is True


def test_la_finestra_stretta_di_un_computer_e_ancora_mobile_all_ingresso():
    """La soglia dei 768 resta: un caso sopra e uno sotto, senza touch."""
    assert _mobile(ua=UA_WINDOWS, touch=0, w=768) is False
    assert _mobile(ua=UA_WINDOWS, touch=0, w=767) is True


def test_la_vecchia_preferenza_desktop_non_conta_piu():
    """Il cliente bloccato: aveva scelto «Versione desktop» dal menu di /m. Al
    prossimo accesso il telefono torna su mobile da solo."""
    assert _mobile(**IPHONE, storage={"oneflux_forza_desktop": "1"}) is True


# ─── Quando rimbalzare ────────────────────────────────────────────────────────
def _rimbalza(**opts):
    base = {"isPhone": True, "telefonoVero": False, "pathname": "/margini", "giaDentro": False}
    return _esegui(f"emit(m.deveRimbalzareSuMobile({_json({**base, **opts})}));",
                   richiede=("deveRimbalzareSuMobile",))


def test_il_telefono_vero_rimbalza_anche_se_e_gia_dentro():
    assert _rimbalza(telefonoVero=True, giaDentro=True) is True


def test_la_finestra_stretta_di_un_computer_rimbalza_solo_all_ingresso():
    """Il caso del 23/09: chi restringe la finestra mentre lavora non viene strappato via."""
    assert _rimbalza(giaDentro=True) is False
    assert _rimbalza(giaDentro=False) is True


@pytest.mark.parametrize("pathname,atteso", [
    ("/admin/utenti", False), ("/m", False), ("/m/diario", False), ("/margini", True),
])
def test_admin_e_m_restano_esclusi_dal_rimbalzo(pathname, atteso):
    """/admin e' solo desktop, /m e' gia' mobile: rimbalzarli sarebbe un ciclo.
    `/margini` e' qui apposta: `startsWith("/m")` lo matcherebbe."""
    assert _rimbalza(telefonoVero=True, pathname=pathname) is atteso


@pytest.mark.parametrize("indeterminato", [None, False])
def test_rilevamento_indeterminato_o_negativo_non_rimbalza(indeterminato):
    """Difesa per un chiamante che salti `decisionePresa`: anche col telefono vero."""
    assert _rimbalza(isPhone=indeterminato, telefonoVero=True) is False


# ── La SEQUENZA dei render, non la singola decisione ────────────────────────
# Il difetto della review del 23/09/2026 viveva nell'accumulo di stato fra un
# render e l'altro: al primo render il rilevamento e' indeterminato.

_SEQUENZA = _AMBIENTE + """
// L'effetto vero di MobileRedirect su piu' render successivi, col suo ref.
const decisoPer = { current: null };
let rimbalzi = 0;
for (const isPhone of input.renders) {
  if (m.rimbalzoAlRender(decisoPer, isPhone, input.pathname)) rimbalzi++;
}
emit(rimbalzi);
"""


def _rimbalzi(renders, disp=IPHONE, pathname="/margini"):
    return esegui_ts(
        MODULO, _SEQUENZA, {**disp, "pathname": pathname, "renders": renders, "storage": {}},
        richiede=("rimbalzoAlRender",),
    )


def test_il_telefono_rimbalza_anche_col_primo_render_indeterminato():
    assert _rimbalzi([None, True]) == 1


def test_render_indeterminati_ripetuti_non_consumano_la_decisione():
    """StrictMode monta due volte: l'indeterminato non deve "bruciare" il turno."""
    assert _rimbalzi([None, None, True]) == 1


def test_il_telefono_rimasto_su_una_pagina_desktop_rimbalza_a_ogni_render():
    assert _rimbalzi([True, True]) == 2


def test_il_ridimensionamento_dopo_l_ingresso_non_rimbalza_di_nuovo():
    """Desktop che restringe la finestra mentre lavora: si decide una volta sola."""
    assert _rimbalzi([False, True, True], disp={**DESKTOP, "w": 700}) == 0


def test_la_finestra_stretta_rimbalza_all_ingresso_anche_col_primo_render_indeterminato():
    """Il caso dove il primo render indeterminato conta davvero: il telefono vero
    rimbalza comunque, la finestra stretta di un computer solo se l'indeterminato
    non ha gia' «consumato» l'ingresso (il difetto del 23/09)."""
    assert _rimbalzi([None, True], disp={**DESKTOP, "w": 700}) == 1
