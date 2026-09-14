"""Isolamento fra clienti, PROVATO ESEGUENDO — lente trasversale L2 (14/09/2026).

Il difetto che questo file esiste per impedire
=============================================
Tre cicli di audit hanno certificato «216/216 endpoint protetti». Quel numero
misura che sono AUTENTICATI — non che il cliente A non possa leggere o
scrivere i dati del cliente B passando l'id di B. Con `auth.uid()` sempre NULL
e ogni client su `service_role` (che bypassa RLS), i filtri `user_id` /
`ristorante_id` scritti nel codice Python sono l'unica sicurezza multi-tenant
che esiste. Fino a oggi erano stati LETTI, mai eseguiti.

Come misura
===========
Due clienti veri su un Postgres vero (`tests/conftest_sql.py`, schema dallo
snapshot del DB live), ognuno con 2 sedi e una risorsa di ogni tipo (fattura,
tag, dipendente, turno, ricetta, riparto, coda...). Il worker FastAPI gira
in-process con `TestClient` e parla col DB attraverso
`tests/helpers_supabase_sql.py`, che traduce le catene del builder Supabase in
SQL: se un endpoint dimentica un filtro tenant, le righe dell'altro cliente
tornano davvero.

Per ogni operazione dell'OpenAPI che prende un id di risorsa (tag_id,
file_origine, dipendente_id, queue_id...) si chiama l'endpoint con la sessione
di A e l'id di B — e viceversa — e si classifica l'esito:

    403 / 404 / 400 / risposta vuota            -> ok
    la risposta contiene dati di B              -> LEAK
    una riga di B e' cambiata                   -> CRITICO
    una riga nuova di A punta a una risorsa di B -> RIFERIMENTO cross-tenant
    500                                         -> DA GUARDARE (non e' «protetto»)

«Dati di B» si riconoscono senza conoscere la forma della risposta: ogni
stringa seminata per B contiene `_B_SEGRETO`, e gli id di B sono noti.
«Una riga di B e' cambiata» si misura con un'impronta di TUTTE le tabelle
tenant (colonna `user_id` o `ristorante_id`, lette da information_schema)
prima e dopo la chiamata: un endpoint nuovo che scrive su una tabella nuova
resta dentro il perimetro senza toccare questo file.

La 241a operazione nasce coperta
================================
`test_ogni_operazione_con_id_di_risorsa_ha_una_ricetta` legge le rotte
dall'app e pretende una ricetta per ognuna che porta un id di risorsa. Chi
aggiunge un endpoint del genere deve aggiungere la riga qui — o motivare
l'esenzione in `SENZA_RICETTA_MOTIVATE`. Le GET che ricavano il tenant dalla
sessione (nessun id nel contratto) vengono comunque ESEGUITE come A dopo aver
seminato B: `test_get_a_tenant_di_sessione_non_mostra_l_altro_cliente`.

Cosa NON prova, e lo dice
=========================
- Le POST/PATCH/DELETE senza id di risorsa (scrivono sulla sede attiva del
  chiamante): non possono nominare B, quindi non vengono eseguite qui.
- Gli endpoint `/api/admin/*`: staff, gate `_verify_admin`
  (`test_route_api_auth_dichiarativa.py`).
- La sede attiva (`users.ultimo_ristorante_id`) e' fidata da
  `_resolve_ristorante_id`: il suo unico scrittore raggiungibile dal cliente e'
  `/api/account/cambia-sede`, che qui viene provato con la sede di B.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.helpers_supabase_sql import ClientSQL

pytestmark = pytest.mark.sql

CHIAVE_WORKER = "chiave-finta-isolamento"

# Un parametro con uno di questi nomi identifica una risorsa di un cliente.
# Stessa regola nel test strutturale in fondo: e' la definizione del perimetro.
NOME_DI_RISORSA = re.compile(
    r"(^|_)(id|ids|rid|sid)$|^(file_origine|file_origini|riga_ids)$"
)

# Operazioni con un parametro che sembra un id ma NON e' una risorsa tenant, o
# che non sono raggiungibili con una sessione cliente. Ogni riga dice perche'.
SENZA_RICETTA_MOTIVATE = {
    ("POST", "/api/classify"): (
        "Server-to-server (queue-worker), gate X-Worker-Key senza sessione; "
        "nessuna route Next.js lo espone al browser (misurato il 14/09/2026)."
    ),
    ("POST", "/api/parse"): (
        "Come /api/classify: chiamato dal queue-worker, non dal browser."
    ),
}


# ─── I due clienti ────────────────────────────────────────────────────────────
@dataclass
class Cliente:
    lettera: str
    token: str
    ids: Dict[str, Any] = field(default_factory=dict)

    @property
    def marker(self) -> str:
        return f"_{self.lettera}_SEGRETO"

    def id_noti(self) -> List[str]:
        """Gli identificatori (uuid e bigint) delle risorse seminate."""
        out = []
        for k, v in self.ids.items():
            if isinstance(v, (int, str)) and not str(v).endswith("SEGRETO") and not str(v).endswith(".xml"):
                out.append(str(v))
        return out


def _contiene_id(testo: str, identificatore: str) -> bool:
    if identificatore.isdigit():
        return re.search(rf"(?<![\w.]){identificatore}(?![\w.])", testo) is not None
    return identificatore in testo


def _uuid(lettera: str, n: int) -> str:
    l = lettera.lower() * 8
    return f"{l}-0000-4000-8000-{n:012d}"


def _semina(conn, lettera: str, base_bigint: int) -> Cliente:
    """Un cliente con 2 sedi e una risorsa di ogni tipo, tutte marcate."""
    L = lettera
    m = lambda nome: f"{nome}_{L}_SEGRETO"  # noqa: E731 - marker leggibile
    user = _uuid(L, 1)
    s1, s2 = _uuid(L, 11), _uuid(L, 12)
    d1, d2 = _uuid(L, 21), _uuid(L, 22)
    piva = {"A": "1", "B": "2"}[L] * 11
    token = f"sess-{L}-" + "x" * 30
    ids: Dict[str, Any] = {
        "user_id": user, "sede1": s1, "sede2": s2,
        "dipendente_id": d1, "target_id": d2,
        "file": f"FATT_{L}.xml", "file_cancellato": f"CANC_{L}.xml", "file_riparto": f"RIP_{L}.xml",
        "prodotto": m("PRODOTTO"), "fornitore": m("FORNITORE"),
    }

    def uno(sql: str, *params):
        cur = conn.execute(sql, params)
        riga = cur.fetchone()
        return riga[0] if riga else None

    # Gli id seriali partono da una base per cliente (700xxx / 800xxx): un id
    # come 458 comparirebbe in qualunque importo o conteggio e il controllo
    # «la risposta contiene un id dell'altro» griderebbe a vuoto.
    for seq in ("fatture_id_seq", "custom_tags_id_seq", "custom_tag_prodotti_id_seq",
                "custom_tag_suggestions_id_seq", "custom_tag_suggestion_items_id_seq",
                "prezzi_preferiti_id_seq"):
        conn.execute(f"SELECT setval('public.{seq}', %s)", (base_bigint + 100,))

    conn.execute(
        "INSERT INTO public.users (id, email, password_hash, nome_ristorante, attivo, piano, "
        "nome_gruppo) VALUES (%s, %s, 'x', %s, true, 'pro', %s)",
        (user, f"{L.lower()}@isolamento.test", m("RISTORANTE"), m("GRUPPO")),
    )
    for n, sede in ((1, s1), (2, s2)):
        conn.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, "
            "ragione_sociale) VALUES (%s, %s, %s, %s, true, %s)",
            (sede, user, m(f"SEDE{n}"), piva[:-1] + str(n), m("RAGIONE")),
        )
    # La sede attiva ha una FK verso ristoranti: si imposta dopo averle create.
    conn.execute("UPDATE public.users SET ultimo_ristorante_id = %s WHERE id = %s", (s1, user))
    conn.execute("INSERT INTO public.sessioni (user_id, token) VALUES (%s, %s)", (user, token))

    # Fatture: due righe vive e una cancellata (per il cestino), con documento.
    ids["riga_id"] = uno(
        "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, "
        "data_documento, fornitore, descrizione, categoria, quantita, prezzo_unitario, "
        "totale_riga, piva_cedente) VALUES (%s, %s, %s, 1, '2026-03-10', %s, %s, 'CARNE', 1, "
        "100, 100, '33333333333') RETURNING id",
        user, s1, ids["file"], m("FORNITORE"), m("PRODOTTO"),
    )
    ids["riga_id2"] = uno(
        "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, "
        "data_documento, fornitore, descrizione, categoria, quantita, prezzo_unitario, "
        "totale_riga, piva_cedente) VALUES (%s, %s, %s, 2, '2026-03-10', %s, %s, 'PESCE', 2, "
        "50, 100, '33333333333') RETURNING id",
        user, s1, ids["file"], m("FORNITORE"), m("PRODOTTO2"),
    )
    conn.execute(
        "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, "
        "data_documento, fornitore, descrizione, categoria, totale_riga, deleted_at) "
        "VALUES (%s, %s, %s, 1, '2026-02-10', %s, %s, 'CARNE', 70, now())",
        (user, s1, ids["file_cancellato"], m("FORNITORE"), m("PRODOTTO_CANC")),
    )
    for file, cancellato in ((ids["file"], False), (ids["file_cancellato"], True)):
        conn.execute(
            "INSERT INTO public.fatture_documenti (user_id, ristorante_id, file_origine, fornitore, "
            "piva_fornitore, numero_documento, data_documento, totale_documento, scadenza_xml, "
            "deleted_at) VALUES (%s, %s, %s, %s, '33333333333', %s, '2026-03-10', 200, '2026-04-10', %s)",
            (user, s1, file, m("FORNITORE"), m("NUMDOC"), "now()" if cancellato else None),
        )
        if cancellato:
            conn.execute(
                "UPDATE public.fatture_documenti SET deleted_at = now() WHERE user_id = %s AND file_origine = %s",
                (user, file),
            )

    # Tag di sede, associazione, suggerimento.
    ids["tag_id"] = uno(
        "INSERT INTO public.custom_tags (user_id, ristorante_id, nome) VALUES (%s, %s, %s) RETURNING id",
        user, s1, m("TAG"),
    )
    ids["assoc_id"] = uno(
        "INSERT INTO public.custom_tag_prodotti (tag_id, user_id, ristorante_id, descrizione, "
        "descrizione_key) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        ids["tag_id"], user, s1, m("PRODOTTO"), m("prodotto").lower(),
    )
    ids["sid"] = uno(
        "INSERT INTO public.custom_tag_suggestions (user_id, ristorante_id, suggestion_type, "
        "cluster_key, suggested_tag_name, status) VALUES (%s, %s, 'new_tag', %s, %s, 'pending') RETURNING id",
        user, s1, m("cluster").lower(), m("SUGGERIMENTO"),
    )
    conn.execute(
        "INSERT INTO public.custom_tag_suggestion_items (suggestion_id, user_id, ristorante_id, "
        "descrizione, descrizione_key) VALUES (%s, %s, %s, %s, %s)",
        (ids["sid"], user, s1, m("PRODOTTO"), m("prodotto").lower()),
    )
    # Tag di catena (id senza default nello schema).
    ids["gtag_id"] = base_bigint + 1
    ids["gassoc_id"] = base_bigint + 2
    conn.execute(
        "INSERT INTO public.gruppo_tags (id, user_id, nome) VALUES (%s, %s, %s)",
        (ids["gtag_id"], user, m("TAGCATENA")),
    )
    conn.execute(
        "INSERT INTO public.gruppo_tag_prodotti (id, tag_id, user_id, descrizione, descrizione_key) "
        "VALUES (%s, %s, %s, %s, %s)",
        (ids["gassoc_id"], ids["gtag_id"], user, m("PRODOTTO"), m("prodotto").lower()),
    )
    # Personale: due dipendenti, un turno, un mensile, una regola ricorrente.
    for did, nome in ((d1, m("DIPENDENTE")), (d2, m("DIPENDENTE2"))):
        conn.execute(
            "INSERT INTO public.dipendenti (id, ristorante_id, nome, costo_orario_default) "
            "VALUES (%s, %s, %s, 10)",
            (did, s1, nome),
        )
    ids["turno_id"] = uno(
        "INSERT INTO public.turni_personale (ristorante_id, user_id, dipendente_id, data_turno, "
        "ora_inizio, ora_fine, note) VALUES (%s, %s, %s, '2026-03-02', '09:00', '13:00', %s) RETURNING id",
        s1, user, d1, m("NOTA_TURNO"),
    )
    ids["turno_mensile_id"] = uno(
        "INSERT INTO public.turni_personale (ristorante_id, user_id, dipendente_id, data_turno, "
        "ora_inizio, ora_fine, mensile, ore_dichiarate, lordo_mensile, note) "
        "VALUES (%s, %s, %s, '2026-03-01', '00:00', '00:00', true, 160, 2000, %s) RETURNING id",
        s1, user, d1, m("NOTA_MENSILE"),
    )
    ids["regola_turni_id"] = uno(
        "INSERT INTO public.regole_turni_ricorrenti (ristorante_id, dipendente_id, giorno_settimana, "
        "tipo_giorno, ora_inizio, ora_fine) VALUES (%s, %s, 1, 'turno', '09:00', '13:00') RETURNING id",
        s1, d1,
    )
    ids["spesa_id"] = uno(
        "INSERT INTO public.spese_extra (ristorante_id, user_id, data_spesa, tipo, importo, descrizione) "
        "VALUES (%s, %s, '2026-03-05', 'generale', 50, %s) RETURNING id",
        s1, user, m("SPESA"),
    )
    # Workspace: ricetta, ingrediente manuale, voce inventario, evento diario.
    ids["ricetta_id"] = uno(
        "INSERT INTO public.ricette (user_id, ristorante_id, nome, categoria, note) "
        "VALUES (%s, %s, %s, 'CARNE', %s) RETURNING id",
        user, s1, m("RICETTA"), m("NOTA_RICETTA"),
    )
    ids["ing_id"] = uno(
        "INSERT INTO public.ingredienti_workspace (user_id, ristorante_id, nome, prezzo_per_um) "
        "VALUES (%s, %s, %s, 1.5) RETURNING id",
        user, s1, m("INGREDIENTE"),
    )
    ids["voce_id"] = uno(
        "INSERT INTO public.inventario_voci (user_id, ristorante_id, data_inventario, nome, quantita, "
        "prezzo_unitario) VALUES (%s, %s, '2026-03-31', %s, 2, 3) RETURNING id",
        user, s1, m("VOCE"),
    )
    ids["evento_id"] = uno(
        "INSERT INTO public.diario_eventi (ristorante_id, user_id, data_evento, titolo, descrizione) "
        "VALUES (%s, %s, '2026-03-15', %s, %s) RETURNING id",
        s1, user, m("EVENTO"), m("DESCRIZIONE_EVENTO"),
    )
    # Riparto di catena su una SECONDA fattura, con la riga marcata ripartita come
    # fa il prodotto (riga-categoria cerca il riparto per file e poi le righe di
    # `fatture` dello stesso file; da-fattura rifiuta con 409 una fattura gia'
    # ripartita, e su FATT_ deve poter passare). Due quote, regola fornitore.
    conn.execute(
        "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, "
        "data_documento, fornitore, descrizione, categoria, quantita, prezzo_unitario, "
        "totale_riga, ripartita_su_gruppo) VALUES (%s, %s, %s, 1, '2026-03-12', %s, %s, "
        "'UTENZE', 1, 300, 300, true)",
        (user, s1, ids["file_riparto"], m("FORNITORE"), m("PRODOTTO")),
    )
    ids["riparto_id"] = uno(
        "INSERT INTO public.riparto_costi_catena (user_id, origine, file_origine, fornitore, "
        "descrizione, importo_totale, anno, mese) VALUES (%s, 'fattura', %s, %s, %s, 300, 2026, 3) RETURNING id",
        user, ids["file_riparto"], m("FORNITORE"), m("RIPARTO"),
    )
    for sede in (s1, s2):
        conn.execute(
            "INSERT INTO public.riparto_costi_catena_quote (riparto_id, ristorante_id, quota_perc, "
            "quota_importo) VALUES (%s, %s, 50, 150)",
            (ids["riparto_id"], sede),
        )
    conn.execute(
        "INSERT INTO public.riparto_regole_fornitore (user_id, fornitore, regola) VALUES (%s, %s, 'equa')",
        (user, m("FORNITORE")),
    )
    # Coda fatture in attesa di sede (id senza default nello schema).
    ids["queue_id"] = base_bigint + 3
    conn.execute(
        "INSERT INTO public.fatture_queue (id, event_id, user_id, ristorante_id, piva_raw, status, "
        "xml_content, payload_meta) VALUES (%s, %s, %s, NULL, %s, 'da_assegnare', %s, %s)",
        (ids["queue_id"], f"evt-{L}", user, piva, f"<Fattura>{m('XML')}</Fattura>",
         json.dumps({"fornitore": m("FORNITORE")})),
    )
    ids["notifica_id"] = uno(
        "INSERT INTO public.notification_inbox (user_id, ristorante_id, topic_key, source_type, severity, "
        "title, body, dedupe_key) VALUES (%s, %s, 'prova', 'operativa', 'info', %s, %s, %s) RETURNING id",
        user, s1, m("NOTIFICA"), m("CORPO_NOTIFICA"), f"dk-{L}",
    )
    ids["regola_scadenziario_id"] = uno(
        "INSERT INTO public.fornitori_pagamenti_config (user_id, ristorante_id, piva_fornitore, "
        "fornitore_norm, giorni_pagamento, note) VALUES (%s, %s, '33333333333', %s, 30, %s) RETURNING id",
        user, s1, m("fornitore").lower(), m("NOTA_REGOLA"),
    )
    conn.execute(
        "INSERT INTO public.prezzi_preferiti (ristorante_id, user_id, descrizione_key, fornitore_key) "
        "VALUES (%s, %s, %s, %s)",
        (s1, user, m("prodotto").lower(), m("fornitore").lower()),
    )
    conn.execute(
        "INSERT INTO public.ricavi_giornalieri (user_id, ristorante_id, data, fatturato_iva10, coperti) "
        "VALUES (%s, %s, '2026-03-10', 500, 40)",
        (user, s1),
    )
    return Cliente(lettera=L, token=token, ids=ids)


# ─── Harness ──────────────────────────────────────────────────────────────────
class Scenario:
    def __init__(self, conn, sb: ClientSQL, client: TestClient, a: Cliente, b: Cliente):
        self.conn, self.sb, self.client, self.a, self.b = conn, sb, client, a, b
        self._tabelle = self._tabelle_tenant()

    def _tabelle_tenant(self) -> List[Tuple[str, str]]:
        righe = self.conn.execute(
            "SELECT table_name, bool_or(column_name = 'user_id'), bool_or(column_name = 'ristorante_id') "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "GROUP BY table_name ORDER BY table_name"
        ).fetchall()
        return [(t, "user_id" if u else "ristorante_id") for t, u, r in righe if u or r]

    def chiama(self, chi: Cliente, metodo: str, path: str, params=None, json_=None):
        return self.client.request(
            metodo, path, params=params, json=json_,
            headers={"Authorization": f"Bearer {chi.token}", "X-Worker-Key": CHIAVE_WORKER},
        )

    def impronta(self, chi: Cliente, escludi: Tuple[str, ...] = ()) -> Dict[str, List[str]]:
        """Tutte le righe del cliente, tabella per tabella, serializzate e ordinate."""
        out: Dict[str, List[str]] = {}
        sedi = [chi.ids["sede1"], chi.ids["sede2"]]
        for tabella, chiave in self._tabelle:
            if tabella in escludi:
                continue
            if chiave == "user_id":
                cur = self.conn.execute(
                    f'SELECT to_jsonb(t) FROM public."{tabella}" t WHERE t.user_id::text = %s',
                    (chi.ids["user_id"],),
                )
            else:
                cur = self.conn.execute(
                    f'SELECT to_jsonb(t) FROM public."{tabella}" t WHERE t.ristorante_id = ANY(%s::uuid[])',
                    (sedi,),
                )
            out[tabella] = sorted(json.dumps(r[0], sort_keys=True, default=str) for r in cur.fetchall())
        cur = self.conn.execute("SELECT to_jsonb(u) FROM public.users u WHERE u.id = %s", (chi.ids["user_id"],))
        out["users"] = [json.dumps(r[0], sort_keys=True, default=str) for r in cur.fetchall()]
        return out


@pytest.fixture
def worker():
    import os

    os.environ.setdefault("WORKER_DEV_MODE", "1")
    import services.fastapi_worker as fw

    return fw


@pytest.fixture
def scenario(db_sql, worker, monkeypatch) -> Scenario:
    conn = db_sql
    # Il worker parla col DB come `service_role`: le RPC con guardia
    # (`auth.role() <> 'service_role'` -> «Accesso negato») lo leggono dal GUC.
    # SET LOCAL apre anche la transazione della fixture: i savepoint del client
    # stanno dentro, e il rollback finale resta quello di `db_sql`.
    conn.execute("SET LOCAL request.jwt.claim.role = 'service_role'")
    # Lo snapshot dello schema ha perso `GENERATED BY DEFAULT AS IDENTITY` su
    # gruppo_tags e gruppo_tag_prodotti (migration 20260617230000_gruppo_tags.sql):
    # le sequenze ci sono, il default no. Senza, l'upsert di /api/gruppo/tag/{id}/
    # prodotti fallisce qui e non in produzione. Si ripristina nella transazione.
    for tabella in ("gruppo_tags", "gruppo_tag_prodotti"):
        conn.execute(
            f"ALTER TABLE public.{tabella} ALTER COLUMN id SET DEFAULT nextval('public.{tabella}_id_seq')"
        )
        conn.execute(f"SELECT setval('public.{tabella}_id_seq', 900000)")
    sb = ClientSQL(conn)
    import services

    # Tutti i modi in cui il codice si procura un client: il worker (e i router,
    # che gli delegano), l'alias modulo usato dagli endpoint admin, e il
    # singleton di `services` usato da db_service, auth_service, session_service.
    monkeypatch.setattr(worker, "_get_supabase_client", lambda: sb)
    monkeypatch.setattr(worker, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(services, "_cached_client", lambda: sb)
    monkeypatch.setattr(worker, "WORKER_SECRET_KEY", CHIAVE_WORKER)
    monkeypatch.setattr(worker, "WORKER_DEV_MODE", False)

    a = _semina(conn, "A", 700000)
    b = _semina(conn, "B", 800000)
    client = TestClient(worker.app, raise_server_exceptions=False)
    return Scenario(conn, sb, client, a, b)


# ─── Le ricette: come si chiama ogni operazione con l'id dell'altro ──────────
@dataclass(frozen=True)
class Ricetta:
    metodo: str
    path: str
    json_: Optional[Dict[str, Any]] = None
    params: Optional[Dict[str, Any]] = None
    nota: str = ""

    @property
    def etichetta(self) -> str:
        return f"{self.metodo} {self.path}" + (f" [{self.nota}]" if self.nota else "")


def R(metodo, path, json_=None, params=None, nota=""):
    return Ricetta(metodo, path, json_, params, nota)


_SEGNAPOSTO = re.compile(r"\{(?:(mio|altro)\.)?(\w+)\}")


def _risolvi(valore, mio: Cliente, altro: Cliente):
    """`{tag_id}` e `$altro.tag_id` -> id dell'altro; `{mio.x}` / `$mio.x` -> id proprio."""
    if isinstance(valore, str):
        if valore.startswith("$altro."):
            return altro.ids[valore[7:]]
        if valore.startswith("$mio."):
            return mio.ids[valore[5:]]
        return _SEGNAPOSTO.sub(
            lambda m: str((mio if m.group(1) == "mio" else altro).ids[m.group(2)]), valore
        )
    if isinstance(valore, list):
        return [_risolvi(v, mio, altro) for v in valore]
    if isinstance(valore, dict):
        return {k: _risolvi(v, mio, altro) for k, v in valore.items()}
    return valore


DESCRIZIONI = {"descrizioni": [{"descrizione": "$mio.prodotto"}]}

RICETTE: List[Ricetta] = [
    R("POST", "/api/notifiche/{notifica_id}/dismiss"),
    # tag di sede
    R("PUT", "/api/tag/{tag_id}", {"nome": "rinominato"}),
    R("DELETE", "/api/tag/{tag_id}"),
    R("GET", "/api/tag/{tag_id}/prodotti"),
    R("POST", "/api/tag/{tag_id}/prodotti", DESCRIZIONI),
    R("DELETE", "/api/tag/prodotti/{assoc_id}"),
    R("GET", "/api/tag/{tag_id}/analisi", params={"data_da": "2026-01-01", "data_a": "2026-12-31"}),
    R("GET", "/api/tag/{tag_id}/orfani"),
    R("POST", "/api/tag/suggestions/{sid}/accept", {"suggestion_type": "new_tag", "tag_name": "nuovo"}),
    R("POST", "/api/tag/suggestions/{mio.sid}/accept",
      {"suggestion_type": "extend_tag", "tag_id": "$altro.tag_id"}, nota="mio suggerimento sul tag altrui"),
    R("POST", "/api/tag/suggestions/{sid}/snooze", {"days": 7}),
    R("POST", "/api/tag/suggestions/{sid}/dismiss"),
    # scadenziario
    R("POST", "/api/scadenziario/pagata", {"file_origini": ["$altro.file"], "ristorante_id": "$altro.sede1"}),
    R("POST", "/api/scadenziario/pagata", {"file_origini": ["$altro.file"]}, nota="senza sede"),
    R("POST", "/api/scadenziario/pagata", {"file_origini": ["$mio.file"], "ristorante_id": "$altro.sede1"},
      nota="mio file, sede altrui"),
    R("POST", "/api/scadenziario/scadenza",
      {"file_origine": "$altro.file", "scadenza_override": "2026-05-01", "ristorante_id": "$altro.sede1"}),
    R("POST", "/api/scadenziario/scadenza", {"file_origine": "$altro.file", "scadenza_override": "2026-05-01"},
      nota="senza sede"),
    R("GET", "/api/scadenziario/anteprima", params={"file_origine": "$altro.file"}),
    R("DELETE", "/api/scadenziario/regole/{regola_scadenziario_id}"),
    # cestino e fatture
    R("POST", "/api/cestino/ripristina", {"file_origine": "$altro.file_cancellato"}),
    R("POST", "/api/cestino/elimina", {"file_origine": "$altro.file_cancellato"}),
    R("POST", "/api/fatture/elimina", {"file_origine": "$altro.file", "ristorante_id": "$altro.sede1"}),
    R("POST", "/api/fatture/elimina", {"file_origine": "$altro.file"}, nota="senza sede"),
    R("POST", "/api/fatture/oscura", {"file_origine": "$altro.file", "oscurata": True, "ristorante_id": "$altro.sede1"}),
    R("POST", "/api/fatture/oscura", {"file_origine": "$altro.file", "oscurata": True}, nota="senza sede"),
    R("POST", "/api/account/cambia-sede", {"ristorante_id": "$altro.sede1"}),
    R("POST", "/api/fatture/categoria-batch",
      {"descrizione": "$altro.prodotto", "nuova_categoria": "PESCE", "riga_ids": ["$altro.riga_id"]}),
    R("PATCH", "/api/fatture/{riga_id}/categoria", {"categoria": "PESCE"}),
    R("POST", "/api/fatture/scarta-da-coda", {"queue_id": "$altro.queue_id"}),
    R("POST", "/api/fatture/assegna-sede", {"queue_id": "$altro.queue_id", "ristorante_id": "$altro.sede1"}),
    R("POST", "/api/fatture/assegna-sede", {"queue_id": "$mio.queue_id", "ristorante_id": "$altro.sede1"},
      nota="mia coda, sede altrui"),
    R("POST", "/api/fatture/sposta-sede", {"file_origine": "$altro.file", "ristorante_id": "$altro.sede2"}),
    R("POST", "/api/fatture/sposta-sede", {"file_origine": "$mio.file", "ristorante_id": "$altro.sede1"},
      nota="mio file, sede altrui"),
    # workspace: foodcost, inventario, diario
    R("GET", "/api/workspace/foodcost/ricette/{ricetta_id}"),
    R("PATCH", "/api/workspace/foodcost/ricette/{ricetta_id}", {"nome": "x", "categoria": "CARNE", "righe": []}),
    R("DELETE", "/api/workspace/foodcost/ricette/{ricetta_id}"),
    R("PATCH", "/api/workspace/foodcost/ingredienti-manuali/{ing_id}", {"nome": "x"}),
    R("DELETE", "/api/workspace/foodcost/ingredienti-manuali/{ing_id}"),
    R("PATCH", "/api/workspace/inventario/{voce_id}", {"nome": "x"}),
    R("DELETE", "/api/workspace/inventario/{voce_id}"),
    R("PATCH", "/api/workspace/diario/{evento_id}", {"titolo": "x"}),
    R("DELETE", "/api/workspace/diario/{evento_id}"),
    # workspace: personale
    R("PATCH", "/api/workspace/dipendenti/{dipendente_id}", {"nome": "x"}),
    R("DELETE", "/api/workspace/dipendenti/{dipendente_id}"),
    R("PATCH", "/api/workspace/dipendenti/{dipendente_id}/disattiva"),
    R("PATCH", "/api/workspace/dipendenti/{dipendente_id}/riattiva"),
    R("POST", "/api/workspace/dipendenti/{dipendente_id}/merge-in/{target_id}"),
    R("POST", "/api/workspace/dipendenti/{mio.dipendente_id}/merge-in/{altro.target_id}",
      nota="mio dipendente nel dipendente altrui"),
    R("POST", "/api/workspace/personale",
      {"dipendente_id": "$altro.dipendente_id", "data_turno": "2026-03-03", "ora_inizio": "09:00", "ora_fine": "13:00"}),
    R("POST", "/api/workspace/personale/copia-mese", {"mese": "2026-03", "dipendente_ids": ["$altro.dipendente_id"]}),
    R("POST", "/api/workspace/personale/mensile",
      {"dipendente_id": "$altro.dipendente_id", "mese": "2026-04", "ore_totali": 100, "lordo": 1000}),
    R("PATCH", "/api/workspace/personale/mensile/{turno_mensile_id}", {"lordo": 1}),
    R("PATCH", "/api/workspace/personale/{turno_id}", {"note": "x"}),
    R("PATCH", "/api/workspace/personale/{mio.turno_id}", {"dipendente_id": "$altro.dipendente_id"},
      nota="mio turno sul dipendente altrui"),
    R("DELETE", "/api/workspace/personale/{turno_id}"),
    R("PATCH", "/api/workspace/personale/{turno_id}/stato-giorno", {"tipo_giorno": "riposo"}),
    R("POST", "/api/workspace/personale/stato-giorno-intervallo",
      {"dipendente_id": "$altro.dipendente_id", "data_da": "2026-03-01", "data_a": "2026-03-03", "tipo_giorno": "ferie"}),
    R("GET", "/api/workspace/regole-turni", params={"dipendente_id": "$altro.dipendente_id"}),
    R("POST", "/api/workspace/regole-turni",
      {"dipendente_id": "$altro.dipendente_id", "giorno_settimana": 2, "tipo_giorno": "turno",
       "ora_inizio": "09:00", "ora_fine": "13:00"}),
    R("PATCH", "/api/workspace/regole-turni/{regola_turni_id}", {"attiva": False}),
    R("DELETE", "/api/workspace/regole-turni/{regola_turni_id}"),
    R("POST", "/api/workspace/regole-turni/genera",
      {"data_da": "2026-03-01", "data_a": "2026-03-07", "dipendente_id": "$altro.dipendente_id"}),
    R("PATCH", "/api/workspace/spese/{spesa_id}", {"importo": 1}),
    R("DELETE", "/api/workspace/spese/{spesa_id}"),
    # tag di catena
    R("DELETE", "/api/gruppo/tag/{gtag_id}"),
    R("GET", "/api/gruppo/tag/{gtag_id}/prodotti"),
    R("POST", "/api/gruppo/tag/{gtag_id}/prodotti", DESCRIZIONI),
    R("DELETE", "/api/gruppo/tag/prodotti/{gassoc_id}"),
    R("GET", "/api/gruppo/tag/{gtag_id}/analisi", params={"mese": 3}),
    # riparto
    R("POST", "/api/riparto/da-fattura", {"file_origine": "$altro.file", "descrizione": "x"}),
    R("POST", "/api/riparto/da-coda", {"queue_id": "$altro.queue_id", "descrizione": "x"}),
    R("PATCH", "/api/riparto/riga-categoria",
      {"file_origine": "$altro.file_riparto", "descrizione": "$altro.prodotto", "nuova_categoria": "PESCE"}),
    R("PATCH", "/api/riparto/{riparto_id}", {"importo_totale": 1}),
    R("DELETE", "/api/riparto/{riparto_id}"),
    R("POST", "/api/riparto/{riparto_id}/duplica"),
    R("GET", "/api/riparto/anteprima-coda", params={"queue_id": "$altro.queue_id"}),
]

# Il path OpenAPI di una ricetta: i segnaposto `{mio.x}` / `{altro.x}` tornano al
# nome del parametro di rotta, letto dall'app (vedi _rotte_con_id_di_risorsa).
def _path_openapi(ricetta: Ricetta, rotte: Dict[Tuple[str, str], str]) -> Optional[str]:
    generico = re.sub(r"\{(?:mio|altro)\.", "{", ricetta.path)
    for (metodo, path), _ in rotte.items():
        if metodo != ricetta.metodo:
            continue
        schema = re.sub(r"\{\w+\}", "{}", path)
        if schema == re.sub(r"\{\w+\}", "{}", generico):
            return path
    return None


# GET a tenant di sessione: nessun id nel contratto, il tenant e' quello della
# sessione. Si eseguono come A con B seminato: la risposta non deve contenere B.
_PERIODO = {"data_da": "2026-01-01", "data_a": "2026-12-31"}
_MESE = {"anno": 2026, "mese": 3}
GET_SESSIONE: Dict[str, Dict[str, Any]] = {
    "/api/auth/me": {}, "/api/dashboard/stats": {}, "/api/notifiche": {"include_dismissed": True},
    "/api/home/briefing": {}, "/api/home/salute": {}, "/api/home/alert-prezzi": {}, "/api/home/kpi": {},
    "/api/home/config": {}, "/api/tag": {}, "/api/tag/descrizioni": {}, "/api/tag/suggestions": {},
    "/api/scadenziario": {}, "/api/scadenziario/calendario": _MESE, "/api/scadenziario/fornitori": {},
    "/api/scadenziario/regole": {}, "/api/cestino": {}, "/api/account/me": {},
    "/api/account/esporta-dati": {}, "/api/account/sedi": {}, "/api/prezzi/soglia-alert": {},
    "/api/prezzi/variazioni": _PERIODO, "/api/prezzi/preferiti": {}, "/api/prezzi/sconti-omaggi": _PERIODO,
    "/api/prezzi/note-credito": _PERIODO, "/api/prezzi/storico-prodotto": {"prodotto": "PRODOTTO"},
    "/api/prezzi/score-fornitori": _PERIODO, "/api/ricavi/giornalieri": _PERIODO,
    "/api/ricavi/coperti-analisi": _PERIODO, "/api/ricavi/coperti-categorie": _PERIODO,
    "/api/ricavi/modalita": _MESE, "/api/fatture/mesi-disponibili": {}, "/api/fatture/kpi": _PERIODO,
    "/api/fatture/articoli-aggregati": {**_PERIODO, "search": "PRODOTTO"},
    "/api/fatture/righe-articolo": {"descrizione": "$mio.prodotto"}, "/api/fatture/pivot": _PERIODO,
    "/api/fatture/trend": _PERIODO, "/api/fatture/fornitori": {}, "/api/fatture/categorie": {},
    "/api/fatture": {**_PERIODO, "search": "PRODOTTO"}, "/api/fatture/da-assegnare": {},
    "/api/margini": {"anno": 2026}, "/api/margini/fatturato-centri": _MESE,
    "/api/margini/fatturato-centri-giorni": _MESE, "/api/margini/analisi-centri": _PERIODO,
    "/api/margini/analisi-avanzata": _PERIODO, "/api/margini/costo-personale-turni": _MESE,
    "/api/margini/costo-spese-extra": _MESE, "/api/margini/analisi": _PERIODO, "/api/margini/kpi": _PERIODO,
    "/api/workspace/foodcost/ingredienti": {}, "/api/workspace/foodcost/ricette": {},
    "/api/workspace/foodcost/ingredienti-manuali": {}, "/api/workspace/inventario/articoli": {},
    "/api/workspace/inventario/snapshot-dates": {}, "/api/workspace/inventario": {"data": "2026-03-31"},
    "/api/workspace/diario": {"mese": "2026-03"}, "/api/workspace/dipendenti": {},
    "/api/workspace/personale": {"da": "2026-03-01", "a": "2026-03-31"},
    "/api/workspace/personale/export-mensile": {"mese": "2026-03"},
    "/api/workspace/spese": {"da": "2026-03-01", "a": "2026-03-31"},
    "/api/gruppo/overview": {}, "/api/gruppo/spesa-pivot": _PERIODO, "/api/gruppo/margini-coperti": {"mese": 3},
    "/api/gruppo/spreco-categorie": {"mese": 3}, "/api/gruppo/scadenziario": {}, "/api/gruppo/cestino": {},
    "/api/gruppo/segnali": {"force": True}, "/api/gruppo/assistant-config": {}, "/api/gruppo/tag": {},
    "/api/gruppo/tag/descrizioni": {"q": "PRODOTTO"}, "/api/gruppo/chat-config": {},
    "/api/riparto/regola-fornitore": {"fornitore": "$mio.fornitore"}, "/api/gruppo/costi-comuni": _MESE,
}


# ─── Il verdetto ──────────────────────────────────────────────────────────────
def _valori_inviati(richiesta: Dict[str, Any]) -> set:
    """Le stringhe che il chiamante ha messo nella richiesta: un endpoint che le
    rimanda indietro (es. la descrizione di categoria-batch) non sta trapelando."""
    out = set()

    def raccogli(v):
        if isinstance(v, dict):
            for x in v.values():
                raccogli(x)
        elif isinstance(v, list):
            for x in v:
                raccogli(x)
        elif isinstance(v, (str, int)) and not isinstance(v, bool) and len(str(v)) >= 4:
            out.add(str(v))

    raccogli([richiesta.get("path"), richiesta.get("params"), richiesta.get("json")])
    return out


def _verdetto(resp, mio: Cliente, altro: Cliente, prima_altro, dopo_altro, prima_mio, dopo_mio,
              inviati: set) -> List[str]:
    problemi: List[str] = []
    corpo = resp.text or ""
    for inviato in sorted(inviati, key=len, reverse=True):
        corpo = corpo.replace(inviato, "")
    if resp.status_code == 401:
        problemi.append(f"harness: 401 — la sessione di prova non e' riconosciuta ({corpo[:200]})")
    elif resp.status_code == 422:
        problemi.append(f"ricetta: 422 — il corpo della prova non e' valido ({corpo[:300]})")
    elif resp.status_code >= 500:
        problemi.append(f"DA GUARDARE: {resp.status_code} — un errore non e' un rifiuto ({corpo[:300]})")

    cambiate = [t for t in dopo_altro if dopo_altro[t] != prima_altro.get(t)]
    if cambiate:
        problemi.append(f"CRITICO: righe dell'altro cliente cambiate in {cambiate}")

    if altro.marker in corpo:
        problemi.append("LEAK: la risposta contiene dati dell'altro cliente (marker)")
    trapelati = [i for i in altro.id_noti() if _contiene_id(corpo, i)]
    if trapelati:
        problemi.append(f"LEAK: la risposta contiene id dell'altro cliente non inviati: {trapelati}")

    nuove = {r for t in dopo_mio for r in dopo_mio[t]} - {r for t in prima_mio for r in prima_mio[t]}
    ids_altro = set(altro.id_noti()) - {altro.ids["user_id"]}
    riferimenti = [i for i in ids_altro if any(_contiene_id(r, i) for r in nuove)]
    if riferimenti:
        problemi.append(f"RIFERIMENTO: righe nuove del chiamante puntano a risorse dell'altro cliente: {riferimenti}")
    return problemi


def _esegui_ricetta(sc: Scenario, ricetta: Ricetta, mio: Cliente, altro: Cliente):
    richiesta = {
        "path": _risolvi(ricetta.path, mio, altro),
        "params": _risolvi(ricetta.params, mio, altro),
        "json": _risolvi(ricetta.json_, mio, altro),
    }
    prima_altro, prima_mio = sc.impronta(altro), sc.impronta(mio, escludi=("sessioni",))
    resp = sc.chiama(mio, ricetta.metodo, richiesta["path"], params=richiesta["params"], json_=richiesta["json"])
    dopo_altro, dopo_mio = sc.impronta(altro), sc.impronta(mio, escludi=("sessioni",))
    problemi = _verdetto(resp, mio, altro, prima_altro, dopo_altro, prima_mio, dopo_mio, _valori_inviati(richiesta))
    dettaglio = "" if resp.status_code < 400 else f" {resp.text[:100]}"
    print(f"ESITO {mio.lettera}->{altro.lettera} {ricetta.etichetta} -> {resp.status_code} {'; '.join(problemi) or 'ok'}{dettaglio}")
    return resp, problemi


# ─── I test ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("verso", ["A_su_B", "B_su_A"])
@pytest.mark.parametrize("ricetta", RICETTE, ids=lambda r: r.etichetta)
def test_operazione_con_id_altrui_non_raggiunge_l_altro_cliente(scenario, ricetta, verso):
    mio, altro = (scenario.a, scenario.b) if verso == "A_su_B" else (scenario.b, scenario.a)
    resp, problemi = _esegui_ricetta(scenario, ricetta, mio, altro)
    assert not problemi, (
        f"{ricetta.etichetta} chiamata da {mio.lettera} con gli id di {altro.lettera}: "
        f"HTTP {resp.status_code}\n  " + "\n  ".join(problemi)
    )


@pytest.mark.parametrize("ricetta", RICETTE, ids=lambda r: r.etichetta)
def test_controllo_la_stessa_ricetta_sui_propri_id_trova_la_risorsa(scenario, ricetta):
    """Il controllo che rende credibili i 404 qui sopra: la stessa chiamata con i
    PROPRI id non deve dare 404. Se lo desse, il 404 sull'id altrui non
    proverebbe l'ownership ma solo che la risorsa non e' stata seminata — e il
    test sarebbe verde senza misurare niente."""
    a = scenario.a
    richiesta = {
        "path": _risolvi(ricetta.path, a, a),
        "params": _risolvi(ricetta.params, a, a),
        "json": _risolvi(ricetta.json_, a, a),
    }
    resp = scenario.chiama(a, ricetta.metodo, richiesta["path"], params=richiesta["params"], json_=richiesta["json"])
    print(f"CONTROLLO {ricetta.etichetta} -> {resp.status_code} {resp.text[:120]}")
    assert resp.status_code not in (404, 500, 401, 422), (
        f"{ricetta.etichetta} sui propri id: HTTP {resp.status_code} {resp.text[:300]} — "
        "la risorsa seminata non viene trovata, quindi il 404 sull'id altrui non misura l'ownership"
    )


# Le GET che, con A seminato, DEVONO nominare qualcosa di A: il controllo
# positivo delle letture. Senza, «la risposta non contiene B» e' banalmente vero
# su un 200 vuoto, e il test sarebbe verde anche se l'endpoint non leggesse
# niente (stessa trappola del 404 che non prova l'ownership).
# Fuori dall'elenco le letture che per costruzione non possono nominare una
# risorsa seminata: categorie di dominio, id di coda, KPI e aggregati numerici, e
# `/api/riparto/regola-fornitore`, che trova la regola di A (verificato: risponde
# `{"regola":"equa"}`) ma non rimanda il nome del fornitore che gli e' stato dato.
GET_CHE_MOSTRANO_IL_PROPRIO = {
    "/api/auth/me", "/api/account/me", "/api/account/sedi", "/api/account/esporta-dati",
    "/api/tag", "/api/tag/descrizioni", "/api/fatture", "/api/fatture/fornitori",
    "/api/fatture/articoli-aggregati", "/api/fatture/righe-articolo",
    "/api/scadenziario", "/api/scadenziario/fornitori",
    "/api/scadenziario/regole", "/api/cestino", "/api/prezzi/preferiti",
    "/api/workspace/foodcost/ricette", "/api/workspace/foodcost/ingredienti-manuali",
    "/api/workspace/inventario", "/api/workspace/diario", "/api/workspace/dipendenti",
    "/api/workspace/personale", "/api/workspace/spese", "/api/gruppo/overview",
    "/api/gruppo/tag", "/api/gruppo/tag/descrizioni", "/api/gruppo/scadenziario",
    "/api/gruppo/cestino", "/api/notifiche",
}


@pytest.mark.parametrize("path", sorted(GET_SESSIONE), ids=lambda p: p)
def test_get_a_tenant_di_sessione_non_mostra_l_altro_cliente(scenario, path):
    """Le GET senza id nel contratto leggono la sede attiva della sessione: con B
    seminato, la risposta ad A non deve contenere niente di B — e dove la lettura
    ha per forza qualcosa da dire, deve contenere qualcosa di A."""
    a, b = scenario.a, scenario.b
    params = _risolvi(GET_SESSIONE[path], a, b)
    prima_b = scenario.impronta(b)
    resp = scenario.chiama(a, "GET", path, params=params)
    dopo_b = scenario.impronta(b)
    problemi = _verdetto(resp, a, b, prima_b, dopo_b, {}, {}, set())
    if path in GET_CHE_MOSTRANO_IL_PROPRIO and a.marker.lower() not in (resp.text or "").lower():
        problemi.append(
            "CONTROLLO: la risposta non nomina nessuna risorsa del chiamante — "
            "«non contiene B» qui non misura niente"
        )
    print(f"ESITO GET {path} -> {resp.status_code} {'; '.join(problemi) or 'ok'}")
    assert not problemi, f"GET {path} come A: HTTP {resp.status_code}\n  " + "\n  ".join(problemi)


def test_le_get_del_controllo_positivo_esistono(worker):
    """L'elenco del controllo positivo non deve nominare rotte sparite: una voce
    morta e' una lettura che nessuno verifica piu'."""
    fantasmi = sorted(GET_CHE_MOSTRANO_IL_PROPRIO - set(GET_SESSIONE))
    assert not fantasmi, f"voci di GET_CHE_MOSTRANO_IL_PROPRIO fuori da GET_SESSIONE: {fantasmi}"


# ─── Le RPC di catena e della chat, chiamate direttamente ─────────────────────
RPC_GRUPPO = {
    "gruppo_peso_categoria": {"p_data_da": "2026-01-01", "p_data_a": "2026-12-31"},
    "gruppo_salute_componenti": {"p_inizio": "2026-01-01T00:00:00+00:00", "p_anno": 2026, "p_mese": 3},
    "gruppo_spesa_pivot": {"p_dimensione": "categoria", "p_data_da": "2026-01-01", "p_data_a": "2026-12-31"},
    "gruppo_spreco_fb_categorie": {"p_data_da": "2026-01-01", "p_data_a": "2026-12-31"},
    "gruppo_tag_analisi": {"p_descrizione_keys": ["PRODOTTO_A_SEGRETO", "PRODOTTO_B_SEGRETO"],
                           "p_data_da": "2026-01-01", "p_data_a": "2026-12-31"},
    "gruppo_tag_descrizioni": {"p_q": None, "p_limit": 500},
    "gruppo_tag_fornitori": {"p_descrizione_keys": ["PRODOTTO_A_SEGRETO", "PRODOTTO_B_SEGRETO"],
                             "p_data_da": "2026-01-01", "p_data_a": "2026-12-31"},
    "gruppo_tag_trend": {"p_descrizione_keys": ["PRODOTTO_A_SEGRETO", "PRODOTTO_B_SEGRETO"],
                         "p_data_da": "2026-01-01", "p_data_a": "2026-12-31"},
}


@pytest.mark.parametrize("nome", sorted(RPC_GRUPPO))
def test_rpc_di_catena_restituisce_solo_le_sedi_passate(scenario, nome):
    """Le RPC `gruppo_*` non conoscono il chiamante: prendono `p_ristorante_ids`
    e SECURITY DEFINER. L'isolamento sta nel call site Python (`_resolve_gruppo`
    passa solo le sedi dell'account) — qui si prova che la funzione, ricevute
    le sedi di A, non restituisca righe di B."""
    a, b = scenario.a, scenario.b
    params = {"p_ristorante_ids": [a.ids["sede1"], a.ids["sede2"]], **RPC_GRUPPO[nome]}
    righe = scenario.sb.rpc(nome, params).execute().data
    testo = json.dumps(righe, default=str)
    assert righe, f"{nome}: nessuna riga per A — il test non sta misurando niente"
    assert b.marker not in testo and b.ids["sede1"] not in testo and b.ids["sede2"] not in testo, (
        f"{nome} con le sedi di A ha restituito dati di B: {testo[:500]}"
    )


def test_rpc_chat_top_categoria_fornitore_filtra_utente_e_sede(scenario):
    a, b = scenario.a, scenario.b
    incrociato = scenario.sb.rpc(
        "chat_top_categoria_fornitore",
        {"p_user_id": a.ids["user_id"], "p_ristorante_id": b.ids["sede1"], "p_giorni": 3650, "p_top": 5},
    ).execute().data
    assert incrociato == [], f"utente A + sede B non deve restituire nulla: {incrociato}"
    proprio = scenario.sb.rpc(
        "chat_top_categoria_fornitore",
        {"p_user_id": a.ids["user_id"], "p_ristorante_id": a.ids["sede1"], "p_giorni": 3650, "p_top": 5},
    ).execute().data
    assert proprio and b.marker not in json.dumps(proprio), proprio


def test_rpc_chat_usage_conta_per_sede(scenario):
    """Il contatore della chat e' per (utente, sede): la sede di B non deve
    consumare — ne' leggere — il contatore di A."""
    a, b = scenario.a, scenario.b
    sb = scenario.sb
    n1 = sb.rpc("chat_usage_check_and_log", {"p_user_id": a.ids["user_id"], "p_ristorante_id": a.ids["sede1"], "p_limite": 10}).execute().data
    n2 = sb.rpc("chat_usage_check_and_log", {"p_user_id": a.ids["user_id"], "p_ristorante_id": a.ids["sede1"], "p_limite": 10}).execute().data
    altrui = sb.rpc("chat_usage_check_and_log", {"p_user_id": b.ids["user_id"], "p_ristorante_id": b.ids["sede1"], "p_limite": 10}).execute().data
    assert (n1, n2) == (1, 2), (n1, n2)
    assert altrui == 1, f"il contatore di B parte da zero, non da quello di A: {altrui}"


# ─── La 241a operazione nasce coperta ─────────────────────────────────────────
def _rotte_con_id_di_risorsa(app) -> Dict[Tuple[str, str], str]:
    """(METODO, path) -> nomi dei parametri di risorsa, per le rotte cliente."""
    schema = app.openapi()
    comps = schema.get("components", {}).get("schemas", {})

    def proprieta(s):
        if "$ref" in s:
            return proprieta(comps.get(s["$ref"].split("/")[-1], {}))
        out = dict(s.get("properties", {}))
        for k in ("allOf", "anyOf", "oneOf"):
            for sub in s.get(k, []) or []:
                out.update(proprieta(sub))
        return out

    out = {}
    for path, metodi in schema["paths"].items():
        for metodo, op in metodi.items():
            if metodo not in ("get", "post", "put", "patch", "delete") or path.startswith("/api/admin/"):
                continue
            nomi = [p["name"] for p in op.get("parameters", [])]
            for c in op.get("requestBody", {}).get("content", {}).values():
                nomi += list(proprieta(c.get("schema", {})))
            risorse = sorted({n for n in nomi if NOME_DI_RISORSA.search(n)})
            if risorse:
                out[(metodo.upper(), path)] = ", ".join(risorse)
    return out


def test_ogni_operazione_con_id_di_risorsa_ha_una_ricetta(worker):
    rotte = _rotte_con_id_di_risorsa(worker.app)
    coperte = set()
    senza_rotta = []
    for r in RICETTE:
        path = _path_openapi(r, rotte)
        if path is None:
            senza_rotta.append(r.etichetta)
        else:
            coperte.add((r.metodo, path))
    assert not senza_rotta, f"ricette che non corrispondono a nessuna rotta con id di risorsa: {senza_rotta}"

    scoperte = sorted(k for k in rotte if k not in coperte and k not in SENZA_RICETTA_MOTIVATE)
    assert not scoperte, (
        "Operazioni che prendono l'id di una risorsa e non hanno una ricetta in RICETTE:\n  "
        + "\n  ".join(f"{m} {p}  (parametri: {rotte[(m, p)]})" for m, p in scoperte)
        + "\n\nAggiungi una riga a RICETTE (chiamata con gli id dell'altro cliente) "
        "oppure motiva l'esenzione in SENZA_RICETTA_MOTIVATE."
    )
    morte = sorted(k for k in SENZA_RICETTA_MOTIVATE if k not in rotte)
    assert not morte, f"esenzioni che non corrispondono piu' a nessuna rotta: {morte}"
    povere = sorted(k for k, v in SENZA_RICETTA_MOTIVATE.items() if len(v.strip()) < 25)
    assert not povere, f"esenzioni senza motivazione leggibile: {povere}"


def test_ogni_get_a_tenant_di_sessione_e_eseguita(worker):
    """Le GET cliente senza id di risorsa vanno in GET_SESSIONE: e' cosi' che una
    lettura nuova viene eseguita con B seminato senza che nessuno se ne ricordi."""
    con_id = _rotte_con_id_di_risorsa(worker.app)
    attese = set()
    for r in worker.app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods:
            continue
        if r.path.startswith("/api/admin/") or ("GET", r.path) in con_id:
            continue
        if r.path in ("/health",):
            continue
        attese.add(r.path)
    mancanti = sorted(attese - set(GET_SESSIONE))
    assert not mancanti, "GET a tenant di sessione senza voce in GET_SESSIONE:\n  " + "\n  ".join(mancanti)
    morte = sorted(set(GET_SESSIONE) - attese)
    assert not morte, f"voci di GET_SESSIONE che non sono piu' rotte GET cliente: {morte}"
