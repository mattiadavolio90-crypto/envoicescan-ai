"""Il primo interruttore dell'admin su un account mai configurato (fase H3, 09/10/2026).

`users.pagine_abilitate` NULL (o un dict senza chiavi-pagina) vale «tutte le
pagine aperte». Il pannello admin salva un interruttore alla volta, fondendolo
nel dict: spegnere UNA pagina su un account NULL salvava `{pagina: False}`, che
`_normalize_pagine` legge come «solo le pagine a True» — nessuna. Il cliente
perdeva l'intero menu. Ora le pagine si scrivono per esteso prima della fusione.

Sul live il 09/10/2026: 4 account su 9 hanno `pagine_abilitate` NULL.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("WORKER_DEV_MODE", "1")

UID = "11111111-1111-4111-8111-111111111111"
ADMIN = {"email": "md@oneflux.it"}


def _patch(monkeypatch, pagine_attuali, corpo):
    from services.routers import admin

    scritture = []
    sb = MagicMock()
    q = sb.table.return_value
    for m in ("select", "eq", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"email": "c@cliente.it", "pagine_abilitate": pagine_attuali}])
    q.update.side_effect = lambda d: scritture.append(d) or q
    monkeypatch.setattr(admin, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(admin, "_admin_emails_set", lambda: {"md@oneflux.it"})
    admin.admin_aggiorna_flags(UID, admin.FlagsBody(pagine_abilitate=corpo), admin_user=ADMIN)
    return scritture[-1]["pagine_abilitate"]


def test_spegnere_una_pagina_su_un_account_null_spegne_solo_quella(monkeypatch):
    import services.fastapi_worker as fw

    salvato = _patch(monkeypatch, None, {"analisi_e_tag": False})
    menu = fw._normalize_pagine(salvato)
    assert sorted(menu) == sorted(fw._PAGINE_FLAG - {"analisi_e_tag"})


def test_un_interruttore_di_catena_su_un_account_null_lascia_le_pagine(monkeypatch):
    import services.fastapi_worker as fw

    salvato = _patch(monkeypatch, None, {"tab_off_catena_coperti": True})
    assert sorted(fw._normalize_pagine(salvato)) == sorted([*fw._PAGINE_FLAG, "tab_off_catena_coperti"])


def test_un_account_gia_configurato_non_si_riscrive(monkeypatch):
    """Chi ha gia' le sue pagine (anche spente) le tiene: si fonde e basta."""
    attuali = {"margini": True, "prezzi": False, "tab_off_margini_coperti": True}
    salvato = _patch(monkeypatch, attuali, {"tab_off_catena_tag": True})
    assert salvato == {**attuali, "tab_off_catena_tag": True}
