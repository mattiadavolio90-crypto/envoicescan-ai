"""L'emoji scelta accettando un suggerimento deve arrivare fino al tag.

Il difetto (misurato il 23/09/2026 sui dati veri): un tag creato accettando un
suggerimento nasceva SEMPRE senza emoji. `accept_suggestion_create_tag` passava
`emoji=None` cablato a `crea_tag`, e il selettore esisteva solo nel dialog di
creazione manuale — quindi dalla card del suggerimento non c'era modo di
sceglierla. A DB: 3 tag nati da suggerimento, di cui 2 con l'emoji aggiunta
dopo a mano (il cliente rimediava riaprendo il tag).

Il presidio e' sull'ARGOMENTO RICEVUTO DA `crea_tag`, non sul ritorno: e'
esattamente li' che il valore si perdeva, e un assert sul dizionario tornato da
un finto `crea_tag` sarebbe una tautologia (verificherebbe il test, non il
codice).
"""
import services.tag_suggestion_service as tss


class _Exec:
    def __init__(self, data):
        self.data = data


class _Query:
    """Catena builder di Supabase: ogni metodo torna se stesso."""

    def __init__(self, data=None):
        self._data = data if data is not None else []

    def __getattr__(self, _nome):
        return lambda *a, **k: self

    def execute(self):
        return _Exec(self._data)


class _Sb:
    def table(self, _nome):
        return _Query()


SUGGERIMENTO = {
    "id": 1,
    "suggestion_type": "new_tag",
    "suggested_tag_name": "Yogurt",
    "items": [
        {
            "descrizione": "Yogurt greco 1kg",
            "descrizione_key": "YOGURT GRECO 1KG",
            "selected_by_default": True,
        }
    ],
}


def _accetta(monkeypatch, emoji, **extra):
    """Esegue l'accettazione e restituisce i kwargs ricevuti da `crea_tag`."""
    visti = {}

    def finto_crea_tag(**kwargs):
        visti.update(kwargs)
        return {"id": 42}

    monkeypatch.setattr(tss, "crea_tag", finto_crea_tag)
    monkeypatch.setattr(tss, "aggiungi_associazioni", lambda *a, **k: None)
    monkeypatch.setattr(
        tss, "_get_suggestion_with_items", lambda *a, **k: dict(SUGGERIMENTO)
    )

    esito = tss.accept_suggestion_create_tag(
        suggestion_id=1,
        tag_name="Yogurt",
        user_id="u1",
        ristorante_id="r1",
        supabase_client=_Sb(),
        emoji=emoji,
        **extra,
    )
    assert esito.get("success") is not False, esito
    assert visti, "crea_tag non e' stata chiamata"
    return visti


def test_l_emoji_scelta_arriva_al_tag(monkeypatch):
    """Il caso del difetto: prima arrivava sempre None."""
    assert _accetta(monkeypatch, "🥛")["emoji"] == "🥛"


def test_senza_emoji_il_tag_nasce_senza(monkeypatch):
    """L'emoji resta opzionale: non si inventa un default."""
    assert _accetta(monkeypatch, None)["emoji"] is None


def test_emoji_di_soli_spazi_equivale_ad_assente(monkeypatch):
    """`""` e `"  "` non devono finire a DB come emoji vuota.

    A DB la colonna distingue NULL da stringa vuota, e il frontend rende
    `{tag.emoji && ...}`: una stringa di spazi stamperebbe uno spazio muto
    accanto al nome invece di non stampare nulla.
    """
    assert _accetta(monkeypatch, "   ")["emoji"] is None
    assert _accetta(monkeypatch, "")["emoji"] is None


def test_il_nome_del_tag_resta_quello_scelto(monkeypatch):
    """Controprova: aggiungere l'emoji non ha spostato gli altri argomenti."""
    visti = _accetta(monkeypatch, "🥛")
    assert visti["nome"] == "Yogurt"
    assert visti["user_id"] == "u1"
    assert visti["ristorante_id"] == "r1"


def test_chiamata_senza_emoji_resta_valida(monkeypatch):
    """Retrocompatibilita': un chiamante che non passa `emoji` non deve rompersi.

    L'endpoint vecchio non manda il campo; il parametro ha un default apposta.
    """
    visti = {}

    def finto_crea_tag(**kwargs):
        visti.update(kwargs)
        return {"id": 42}

    monkeypatch.setattr(tss, "crea_tag", finto_crea_tag)
    monkeypatch.setattr(tss, "aggiungi_associazioni", lambda *a, **k: None)
    monkeypatch.setattr(
        tss, "_get_suggestion_with_items", lambda *a, **k: dict(SUGGERIMENTO)
    )

    tss.accept_suggestion_create_tag(
        suggestion_id=1,
        tag_name="Yogurt",
        user_id="u1",
        ristorante_id="r1",
        supabase_client=_Sb(),
    )
    assert visti["emoji"] is None


def test_il_modello_dell_endpoint_accetta_l_emoji():
    """L'anello che il frontend riempie davvero.

    Senza il campo nel modello Pydantic il body verrebbe accettato e l'emoji
    scartata in silenzio: il fix nel service resterebbe irraggiungibile.
    """
    from services.routers.tag import AcceptSuggestionRequest

    body = AcceptSuggestionRequest(
        suggestion_type="new_tag", tag_name="Yogurt", emoji="🥛"
    )
    assert body.emoji == "🥛"
    assert AcceptSuggestionRequest(suggestion_type="new_tag").emoji is None


def test_l_endpoint_passa_l_emoji_al_service(monkeypatch):
    """L'anello che il primo giro di mutazione aveva lasciato scoperto.

    Togliendo `emoji=body.emoji` dall'endpoint gli altri test restavano tutti
    verdi (il service lo riceve dal test, non dall'endpoint) e l'emoji si
    perdeva di nuovo per strada. Qui si chiama la funzione dell'endpoint vera.
    """
    import services.routers.tag as rt

    visti = {}

    def finto_create(**kwargs):
        visti.update(kwargs)
        return {"success": True, "tag_id": 42}

    monkeypatch.setattr(tss, "accept_suggestion_create_tag", finto_create)
    monkeypatch.setattr(rt, "_resolve_user_from_token", lambda *a, **k: {"id": "u1"})
    monkeypatch.setattr(rt, "_get_supabase_client", lambda *a, **k: _Sb())
    monkeypatch.setattr(rt, "_resolve_ristorante_id", lambda *a, **k: "r1")

    rt.accept_tag_suggestion(
        sid=1,
        body=rt.AcceptSuggestionRequest(
            suggestion_type="new_tag", tag_name="Yogurt", emoji="🥛"
        ),
        authorization="Bearer x",
    )
    assert visti.get("emoji") == "🥛", (
        "l'endpoint non ha inoltrato l'emoji al service: si perde fra HTTP e DB"
    )
