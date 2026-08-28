"""Test guardia: i tool della chat di catena passano l'auth al parametro giusto.

Difetto trovato in review il 28/08/2026: `g.gruppo_margini_coperti(authorization)`
passava il token nel primo parametro posizionale, che e' `mese: Optional[int]`
(l'authorization e' il SECONDO). Il confronto `1 <= mese <= 12` sollevava
TypeError, ingoiato dall'except Exception del dispatcher: la chat rispondeva
"strumento non disponibile" senza che nulla comparisse come errore.

`gruppo_overview` invece ha `authorization` come primo parametro, quindi li' il
posizionale e' corretto: e' proprio l'asimmetria fra le due firme che rende
facile sbagliare, e il motivo per cui questi test guardano la firma.
"""
import inspect

from services.routers import gruppo as g


class TestFirmeToolCatena:
    def test_margini_coperti_ha_mese_per_primo(self):
        """Se qualcuno riordinasse la firma, il chiamante keyword resta corretto
        ma questo test documenta perche' il posizionale era sbagliato."""
        params = list(inspect.signature(g.gruppo_margini_coperti).parameters)
        assert params[0] == "mese"
        assert "authorization" in params

    def test_overview_ha_authorization_per_primo(self):
        params = list(inspect.signature(g.gruppo_overview).parameters)
        assert params[0] == "authorization"


class TestDispatcherUsaKeyword:
    def test_il_dispatcher_non_passa_l_auth_posizionale_a_margini_coperti(self):
        """Il difetto in forma diretta: leggere il sorgente del dispatcher.

        Un mutante che torna al posizionale viene ucciso qui, mentre un test
        che invocasse il tool con supabase mockato mostrerebbe solo
        {"errore": ...} — lo stesso output che dava il codice rotto.
        """
        from services import fastapi_worker

        src = inspect.getsource(fastapi_worker._chat_esegui_tool_gruppo)
        assert "g.gruppo_margini_coperti(authorization=authorization)" in src
        assert "g.gruppo_margini_coperti(authorization)" not in src
