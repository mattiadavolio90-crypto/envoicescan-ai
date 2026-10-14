"""«Elimina account» e «Elimina sede» su Postgres vero (migration 20261014122000).

Con i due clienti del test di isolamento (A e B, due sedi ciascuno, col riparto
di catena su entrambe le sedi e i ricavi sulla prima). Fino al 14/10/2026:
- un account col riparto non si cancellava: le quote del riparto erano l'unica
  FK verso `ristoranti` senza CASCADE;
- un account (o una sede) coi ricavi nemmeno: la cascata sui ricavi faceva
  scattare il ricalcolo dei margini, che reinseriva `margini_mensili` per una
  sede gia' cancellata;
- otto tabelle con `user_id` restavano dopo la cancellazione dell'account, e
  tre con `ristorante_id` dopo quella della sede.

Il controllo «non resta niente» non elenca le tabelle: legge da
information_schema tutte quelle con `user_id` o `ristorante_id`
(`Scenario.impronta`). Trova pero' solo le righe che la semina ha messo: le
quattro tabelle che la semina comune non riempie si riempiono qui, per
entrambi i clienti. Una tabella NUOVA senza FK la prendono i due test sul
catalogo in fondo, che non dipendono dalla semina.
"""
from __future__ import annotations

import pytest

from tests.test_isolamento_per_risorsa import CHIAVE_WORKER, scenario, worker  # noqa: F401

pytestmark = pytest.mark.sql


def _uno(sc, query, *params):
    return sc.conn.execute(query, params).fetchone()


def _semina_le_tabelle_senza_fk(sc):
    for chi in (sc.a, sc.b):
        uid, s1 = chi.ids["user_id"], chi.ids["sede1"]
        sc.conn.execute(
            "INSERT INTO public.upload_events (user_id, user_email, file_name, status, ristorante_id) "
            "VALUES (%s, %s, %s, 'SAVED_OK', %s)",
            (uid, f"{chi.lettera.lower()}@prova.it", f"FATT_{chi.lettera}.xml", s1),
        )
        sc.conn.execute("INSERT INTO public.upload_locks (ristorante_id, user_id) VALUES (%s, %s)", (s1, uid))
        sc.conn.execute(
            "INSERT INTO public.classificazioni_manuali (descrizione, categoria_corretta, validato_da, user_id) "
            "VALUES (%s, 'CARNE', 'cliente', %s)",
            (f"PRODOTTO_{chi.lettera}", uid),
        )
        sc.conn.execute(
            "INSERT INTO public.gruppo_segnali_state (user_id, generated_for_date) VALUES (%s, '2026-10-14')",
            (uid,),
        )


def _non_resta_niente(sc, chi):
    rimaste = {t: righe for t, righe in sc.impronta(chi).items() if righe}
    assert rimaste == {}


def _margine(sc, sede, anno=2026, mese=3):
    riga = _uno(
        sc,
        "SELECT fatturato_iva10, coperti FROM public.margini_mensili WHERE ristorante_id = %s AND anno = %s AND mese = %s",
        sede, anno, mese,
    )
    return None if riga is None else (float(riga[0]), riga[1])


@pytest.fixture
def sc(scenario):
    _semina_le_tabelle_senza_fk(scenario)
    return scenario


# ─── Account intero ───────────────────────────────────────────────────────────
def test_la_semina_ha_i_due_blocchi_e_le_otto_tabelle(sc):
    """Senza riparto e ricavi i test sotto passerebbero anche col difetto."""
    a = sc.a
    assert _uno(sc, "SELECT count(*) FROM public.riparto_costi_catena_quote WHERE ristorante_id = %s", a.ids["sede1"])[0] > 0
    assert _uno(sc, "SELECT count(*) FROM public.ricavi_giornalieri WHERE ristorante_id = %s", a.ids["sede1"])[0] > 0
    impronta = sc.impronta(a)
    for tabella in ("classificazioni_manuali", "fatture_documenti", "gruppo_segnali_state", "prezzi_preferiti",
                    "riparto_costi_catena", "riparto_regole_fornitore", "upload_events", "upload_locks"):
        assert impronta[tabella], tabella


def test_cancellare_l_utente_porta_via_tutto_e_lascia_l_altro_cliente(sc):
    a, b = sc.a, sc.b
    prima_b = sc.impronta(b)

    sc.conn.execute("DELETE FROM public.users WHERE id = %s", (a.ids["user_id"],))

    _non_resta_niente(sc, a)
    assert sc.impronta(b) == prima_b


def test_elimina_account_dal_cliente(sc):
    a, b = sc.a, sc.b
    prima_b = sc.impronta(b)

    resp = sc.chiama(a, "POST", "/api/account/elimina", json_={"conferma": "ELIMINA"})

    assert resp.status_code == 200, resp.text
    _non_resta_niente(sc, a)
    assert sc.impronta(b) == prima_b


def test_elimina_cliente_dall_admin(sc):
    from services.routers import admin

    a, b = sc.a, sc.b
    prima_b = sc.impronta(b)

    assert admin.admin_elimina_cliente(a.ids["user_id"], admin_user={"email": "staff@oneflux.it"})["ok"] is True

    _non_resta_niente(sc, a)
    assert sc.impronta(b) == prima_b


# ─── Una sede sola ────────────────────────────────────────────────────────────
def _righe_della_sede(sc, sede):
    tabelle = [r[0] for r in sc.conn.execute(
        "SELECT c.table_name FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = 'public' AND c.column_name = 'ristorante_id' AND t.table_type = 'BASE TABLE'"
    ).fetchall()]
    conti = {t: _uno(sc, f'SELECT count(*) FROM public."{t}" WHERE ristorante_id = %s', sede)[0] for t in tabelle}
    return {t: n for t, n in conti.items() if n}


def _elimina_sede(sc, chi, sede):
    from services.routers import admin

    return admin.admin_elimina_sede(chi.ids["user_id"], sede, admin_user={"email": "staff@oneflux.it"})


def test_elimina_sede_col_riparto_e_rifiutata_senza_toccare_niente(sc):
    """Le quote se ne andrebbero con la sede e il riparto resterebbe senza
    pareggio: al primo ricalcolo «l'ultima sede assorbe» sposterebbe il costo
    sull'altra sede. Prima si rifanno i riparti."""
    from fastapi import HTTPException

    a, b = sc.a, sc.b
    prima_a, prima_b = sc.impronta(a), sc.impronta(b)

    with pytest.raises(HTTPException) as err:
        _elimina_sede(sc, a, a.ids["sede1"])

    assert err.value.status_code == 409
    assert "1 riparti" in err.value.detail
    assert sc.impronta(a) == prima_a
    assert sc.impronta(b) == prima_b


def test_elimina_sede_nelle_percentuali_di_una_regola_e_rifiutata(sc):
    """Senza quote, ma la regola del fornitore la nomina: il prossimo riparto
    di quel fornitore risponderebbe 400 «Sede non appartenente all'account»."""
    import json

    from fastapi import HTTPException

    a = sc.a
    s1, s2 = a.ids["sede1"], a.ids["sede2"]
    sc.conn.execute("DELETE FROM public.riparto_costi_catena_quote WHERE ristorante_id = %s", (s1,))
    sc.conn.execute(
        "UPDATE public.riparto_regole_fornitore SET regola = 'percentuali', percentuali = %s::jsonb WHERE user_id = %s",
        (json.dumps({s1: 30, s2: 70}), a.ids["user_id"]),
    )

    with pytest.raises(HTTPException) as err:
        _elimina_sede(sc, a, s1)

    assert err.value.status_code == 409
    assert "1 fornitori" in err.value.detail
    assert _uno(sc, "SELECT count(*) FROM public.ristoranti WHERE id = %s", s1)[0] == 1


def test_una_regola_che_nomina_solo_l_altra_sede_non_blocca(sc):
    import json

    a = sc.a
    s1, s2 = a.ids["sede1"], a.ids["sede2"]
    sc.conn.execute("DELETE FROM public.riparto_costi_catena_quote WHERE ristorante_id = %s", (s1,))
    sc.conn.execute(
        "UPDATE public.riparto_regole_fornitore SET regola = 'percentuali', percentuali = %s::jsonb WHERE user_id = %s",
        (json.dumps({s2: 100}), a.ids["user_id"]),
    )

    assert _elimina_sede(sc, a, s1)["ok"] is True


def test_elimina_sede_senza_riparto_porta_via_la_sede_e_lascia_il_resto(sc):
    """Coi ricavi (il ricalcolo dei margini) e con le tre tabelle che non
    avevano la FK verso `ristoranti`."""
    a, b = sc.a, sc.b
    s1, s2 = a.ids["sede1"], a.ids["sede2"]
    sc.conn.execute("DELETE FROM public.riparto_costi_catena_quote WHERE ristorante_id = %s", (s1,))
    da_togliere = _righe_della_sede(sc, s1)
    for tabella in ("ricavi_giornalieri", "margini_mensili", "fatture_documenti", "upload_events", "upload_locks"):
        assert da_togliere.get(tabella), tabella
    prima_s2, prima_b = _righe_della_sede(sc, s2), sc.impronta(b)

    assert _elimina_sede(sc, a, s1)["ok"] is True

    assert _righe_della_sede(sc, s1) == {}
    assert _righe_della_sede(sc, s2) == prima_s2
    assert _uno(sc, "SELECT count(*) FROM public.users WHERE id = %s", a.ids["user_id"])[0] == 1
    assert sc.impronta(b) == prima_b


# ─── Svuota dati (admin): le sedi se ne vanno, l'account resta ───────────────
def test_svuota_dati_non_lascia_riparti_senza_quote(sc):
    """Lo svuotamento cancella le sedi, non l'utente: il CASCADE da `users` non
    scatta, e i riparti (che stanno sull'account) vanno tolti a mano, o
    resterebbero intestazioni senza quote."""
    from services.routers import account

    a, b = sc.a, sc.b
    prima_b = sc.impronta(b)

    esito = account.account_svuota_dati(account.SvuotaDatiBody(conferma="SVUOTA"), admin_user={"id": a.ids["user_id"]})

    assert esito["ok"] is True
    for tabella in ("riparto_costi_catena", "riparto_regole_fornitore", "riparto_costi_catena_quote", "ristoranti"):
        colonna = "ristorante_id" if tabella == "riparto_costi_catena_quote" else "user_id"
        valore = [a.ids["sede1"], a.ids["sede2"]] if colonna == "ristorante_id" else [a.ids["user_id"]]
        assert _uno(sc, f"SELECT count(*) FROM public.{tabella} WHERE {colonna} = ANY(%s::uuid[])", valore)[0] == 0, tabella
    assert _uno(sc, "SELECT count(*) FROM public.users WHERE id = %s", a.ids["user_id"])[0] == 1
    assert sc.impronta(b) == prima_b


# ─── Il ricalcolo dei margini resta vivo per le cancellazioni normali ────────
def test_togliere_un_giorno_di_ricavi_ricalcola_ancora_il_mese(sc):
    """La guardia salta il ricalcolo solo se la sede non c'e' piu'."""
    a = sc.a
    s1 = a.ids["sede1"]
    sc.conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10, coperti) "
        "VALUES (%s, %s, '2026-03-11', 200, 10)",
        (a.ids["user_id"], s1),
    )
    assert _margine(sc, s1) == (700.0, 50)

    sc.conn.execute("DELETE FROM public.ricavi_giornalieri WHERE ristorante_id = %s AND data = '2026-03-11'", (s1,))

    assert _margine(sc, s1) == (500.0, 40)


# ─── Lo schema dopo la migration ──────────────────────────────────────────────
@pytest.mark.parametrize("tabella", [
    "classificazioni_manuali", "fatture_documenti", "gruppo_segnali_state", "prezzi_preferiti",
    "riparto_costi_catena", "riparto_regole_fornitore", "upload_events", "upload_locks",
])
def test_le_otto_tabelle_hanno_la_fk_verso_users_con_cascade(sc, tabella):
    assert _uno(
        sc,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s AND conrelid = %s::regclass",
        f"{tabella}_user_id_fkey", f"public.{tabella}",
    )[0] == "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"


@pytest.mark.parametrize("colonna, verso", [("user_id", "users"), ("ristorante_id", "ristoranti")])
def test_ogni_tabella_con_la_colonna_ha_la_fk(sc, colonna, verso):
    """Il presidio per le tabelle future: una tabella nuova con `user_id` o
    `ristorante_id` senza FK fa fallire questo test, semina o no."""
    senza_fk = [r[0] for r in sc.conn.execute(
        "SELECT c.table_name FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = 'public' AND c.column_name = %s AND t.table_type = 'BASE TABLE' "
        "AND NOT EXISTS (SELECT 1 FROM pg_constraint k JOIN pg_attribute a "
        "  ON a.attrelid = k.conrelid AND a.attnum = ANY(k.conkey) "
        "  WHERE k.contype = 'f' AND k.conrelid = ('public.' || c.table_name)::regclass "
        "  AND k.confrelid = ('public.' || %s)::regclass AND a.attname = %s) "
        "ORDER BY 1",
        (colonna, verso, colonna),
    ).fetchall()]
    assert senza_fk == []


def test_nessuna_fk_verso_users_o_ristoranti_blocca_la_cancellazione(sc):
    bloccanti = sc.conn.execute(
        "SELECT conrelid::regclass::text, conname FROM pg_constraint "
        "WHERE contype = 'f' AND confrelid IN ('public.users'::regclass, 'public.ristoranti'::regclass) "
        "AND confdeltype NOT IN ('c', 'n')"
    ).fetchall()
    assert bloccanti == []


def test_la_migration_si_riapplica_senza_errori(sc):
    from pathlib import Path

    migration = (Path(__file__).resolve().parent.parent / "supabase" / "migrations"
                 / "20261014122000_elimina_account_cascata_completa.sql")
    sc.conn.execute(migration.read_text(encoding="utf-8"))
    assert _uno(
        sc,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'riparto_costi_catena_quote_ristorante_id_fkey'",
    )[0] == "FOREIGN KEY (ristorante_id) REFERENCES ristoranti(id) ON DELETE CASCADE"
