"""/api/tts verifica la sessione prima di chiamare Google.

Perche' esiste
==============
Audit di ottobre 2026 (K26): la route controllava solo che il cookie
`oneflux_session` esistesse. Con un valore inventato chiunque la usava come
proxy verso il TTS di Google. La decisione sta in `lib/tts-accesso.ts` (eseguita
con node); il cablaggio nella route, che non ha un runner, e' una guardia sul
sorgente: la verifica deve stare prima della prima chiamata a Google.
"""
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

ROUTE = Path(__file__).resolve().parent.parent / "apps/web/src/app/api/tts/route.ts"


@pytest.mark.parametrize(
    "stato,atteso",
    [
        ("ok", None),
        ("invalid", {"status": 401, "error": "Non autenticato"}),
        ("unavailable", {"status": 503, "error": "Servizio temporaneamente non raggiungibile"}),
    ],
)
def test_solo_una_sessione_valida_passa(stato, atteso):
    out = esegui_ts("lib/tts-accesso", "emit(m.rifiutoTts({status: input}));", stato,
                    richiede=["rifiutoTts"])
    assert out == atteso


def test_la_route_verifica_la_sessione_prima_di_google():
    s = ROUTE.read_text(encoding="utf-8")
    verifica = s.index("const negato = rifiutoTts(await verifySession(token));")
    uscita = s.index("if (negato) return NextResponse.json({ error: negato.error }, { status: negato.status });")
    google = s.index("https://translate.google.com/translate_tts")
    assert verifica < uscita < google
