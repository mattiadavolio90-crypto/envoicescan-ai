"""Test: il reset password non rivela quali email sono registrate.

Contesto (audit §3 su auth_service.py, 8/8/2026). `invia_codice_reset`
dichiarava a :1398-1400 "Risposta sempre generica per non rivelare se l'email è
registrata" e definiva `_MSG_GENERICO` per questo, ma il ramo di successo
ritornava `"Email inviata con successo"` — un testo DIVERSO. Il messaggio arriva
al client tal quale (`fastapi_worker.py:7991` fa `return {"ok": True,
"message": msg}`), quindi bastava confrontare la risposta di due richieste per
sapere quali email esistono nel sistema.

Il difetto era che la funzione contraddiceva la propria intenzione dichiarata:
il commento anti-enumerazione era presente e il costante `_MSG_GENERICO` pure,
ma il percorso felice non lo usava. Esiste un rate limit per IP a monte
(`fastapi_worker.py:7984`) che rallenta l'abuso, ma non chiude il canale: un
attaccante paziente enumerava comunque.

I test confrontano i due rami tra loro invece di controllare una stringa fissa:
un domani il testo può cambiare, ciò che non deve cambiare è che i due rami
dicano la STESSA cosa.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import services.auth_service as auth


def _client(utente_esiste: bool):
    """Client Supabase minimo: decide solo se l'email risulta registrata."""
    q = MagicMock()
    for m in ("select", "eq", "update", "insert", "maybe_single", "limit", "order"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(
        data={"id": "u1"} if utente_esiste else None
    )
    client = MagicMock()
    client.table.return_value = q
    return client


def _invia(utente_esiste: bool, brevo_status: int = 200):
    """Esegue invia_codice_reset isolando rete e cooldown."""
    resp = SimpleNamespace(status_code=brevo_status, text="")
    with patch.object(auth, "_check_reset_rate_limit", MagicMock(return_value=None)), \
         patch.object(auth, "_record_reset_request", MagicMock()), \
         patch.dict("os.environ", {"BREVO_API_KEY": "k", "BREVO_SENDER_EMAIL": "a@b.it"}), \
         patch("requests.post", MagicMock(return_value=resp)):
        return auth.invia_codice_reset(
            "tizio@esempio.it", supabase_client=_client(utente_esiste)
        )


class TestResetNonRivelaEmailRegistrate:

    def test_email_registrata_e_non_registrata_danno_lo_stesso_messaggio(self):
        """Il cuore del fix: le due risposte devono essere indistinguibili."""
        ok_esiste, msg_esiste = _invia(utente_esiste=True)
        ok_non_esiste, msg_non_esiste = _invia(utente_esiste=False)

        assert ok_esiste is True and ok_non_esiste is True
        assert msg_esiste == msg_non_esiste, (
            "I due rami restituiscono messaggi diversi: confrontando la risposta "
            "si scopre quali email sono registrate."
        )

    def test_il_messaggio_non_afferma_che_una_mail_e_stata_inviata(self):
        """'Email inviata con successo' e' un'affermazione che vale solo per gli
        utenti registrati: dirla a tutti sarebbe falso, dirla solo ad alcuni
        sarebbe il canale di enumerazione."""
        _, msg = _invia(utente_esiste=True)
        assert "inviata con successo" not in msg.lower()
        # Deve restare condizionale ("se l'email è registrata...")
        assert "se l'email" in msg.lower()

    def test_usa_la_costante_condivisa_non_un_literal_duplicato(self):
        """Due literal separati divergono alla prima modifica distratta."""
        import inspect
        src = inspect.getsource(auth.invia_codice_reset)
        assert src.count("_MSG_GENERICO") >= 3, (
            "Il messaggio generico non e' centralizzato: definizione + i due "
            "rami di uscita devono usare la stessa costante."
        )

    def test_fallimento_brevo_resta_distinguibile(self):
        """Un errore vero DEVE essere segnalato: nascondere anche i guasti
        lascerebbe l'utente in attesa di un'email che non arrivera' mai."""
        ok, msg = _invia(utente_esiste=True, brevo_status=500)
        assert ok is False
        assert msg != _invia(utente_esiste=True)[1]


class TestCooldownNonRivelaEmailRegistrate:
    """Il canale residuo trovato dal code-reviewer.

    `_record_reset_request` fa `UPDATE users ... WHERE email = ?`: e' un no-op
    per le email NON registrate, quindi `last_reset_requested_at` si valorizza
    solo per quelle vere e il cooldown scatta solo per loro. Rispondere "Attendi
    N minuti" soltanto a quelle sposta l'oracolo di UNA richiesta invece di
    chiuderlo. I test della classe sopra non lo vedevano perche' mockavano via
    `_check_reset_rate_limit`: qui NON lo mockiamo.
    """

    def _invia_con_cooldown(self, utente_esiste: bool, cooldown_attivo: bool):
        from datetime import datetime, timezone
        client = _client(utente_esiste)
        if utente_esiste and cooldown_attivo:
            # Cooldown reale: timestamp appena scritto, letto da _check_reset_rate_limit.
            client.table.return_value.execute.return_value = SimpleNamespace(
                data={"id": "u1", "last_reset_requested_at": datetime.now(timezone.utc).isoformat()}
            )
        resp = SimpleNamespace(status_code=200, text="")
        with patch.object(auth, "_record_reset_request", MagicMock()), \
             patch.dict("os.environ", {"BREVO_API_KEY": "k", "BREVO_SENDER_EMAIL": "a@b.it"}), \
             patch("requests.post", MagicMock(return_value=resp)):
            return auth.invia_codice_reset("tizio@esempio.it", supabase_client=client)

    def test_cooldown_su_email_registrata_non_si_distingue_da_email_inesistente(self):
        _, msg_cooldown = self._invia_con_cooldown(utente_esiste=True, cooldown_attivo=True)
        _, msg_inesistente = self._invia_con_cooldown(utente_esiste=False, cooldown_attivo=False)
        assert msg_cooldown == msg_inesistente, (
            "Il messaggio di cooldown rivela che l'email è registrata: le email "
            "inesistenti non entrano mai in cooldown (l'UPDATE è un no-op)."
        )

    def test_il_cooldown_resta_attivo_e_non_invia(self):
        """Mascherare il messaggio non deve disattivare la protezione."""
        with patch("requests.post") as post:
            resp = SimpleNamespace(status_code=200, text="")
            post.return_value = resp
            from datetime import datetime, timezone
            client = _client(True)
            client.table.return_value.execute.return_value = SimpleNamespace(
                data={"id": "u1", "last_reset_requested_at": datetime.now(timezone.utc).isoformat()}
            )
            with patch.object(auth, "_record_reset_request", MagicMock()), \
                 patch.dict("os.environ", {"BREVO_API_KEY": "k", "BREVO_SENDER_EMAIL": "a@b.it"}):
                auth.invia_codice_reset("tizio@esempio.it", supabase_client=client)
            post.assert_not_called()

    def test_guasto_del_servizio_resta_distinguibile(self):
        """Il fail-closed su errore DB (:227-228) NON va mascherato: lì l'utente
        deve sapere che il servizio è giù e che deve riprovare."""
        client = _client(True)
        client.table.return_value.execute.side_effect = RuntimeError("db giu")
        with patch.object(auth, "_record_reset_request", MagicMock()):
            ok, msg = auth.invia_codice_reset("tizio@esempio.it", supabase_client=client)
        assert ok is False
        assert "non disponibile" in msg.lower()
