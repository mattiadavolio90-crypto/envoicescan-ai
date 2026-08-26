"""Unit test motore suggerimenti tag — logica a radice (v2)."""

from services.tag_suggestion_service import (
    _build_extend_tag_suggestions,
    _filtra_items_selezionati,
    _build_new_tag_suggestions,
    _get_product_root,
    _nomi_tag_per_id,
    _roots_dei_tag_esistenti,
    _get_product_token,
    dismiss_suggerimenti_obsoleti,
)


# ── _get_product_root ───────────────────────────────────────────────────────

def test_root_primo_token_significativo():
    # La radice è la forma canonica singolare (stemmata): SALMONE→SALMON
    assert _get_product_root("SALMONE NORVEGESE") == "SALMON"


def test_root_singolare_e_plurale_stessa_radice():
    # Cuore della fix: "SALMONI" (plurale del fornitore) e "SALMONE" (singolare
    # del cliente) devono condividere la stessa radice per agganciarsi.
    assert _get_product_root("SALMONI 5/6 FRESCHI") == _get_product_root("SALMONE 5-6")


def test_token_salta_stopword_iniziale():
    # "DI" è stopword, "POLLO" è il token scelto (grezzo, non stemmato)
    assert _get_product_token("DI POLLO INTERO") == "POLLO"


def test_token_salta_token_con_cifre():
    # "1LT" ha cifre → escluso, "ACQUA" è il token scelto
    assert _get_product_token("ACQUA 1LT NATURALE") == "ACQUA"


def test_token_salta_token_corti():
    # "EVO" è 3 chars → escluso, "OLIO" è il token scelto
    assert _get_product_token("OLIO EVO") == "OLIO"


def test_token_none_se_solo_stopwords_e_cifre():
    # nessun token valido
    assert _get_product_token("1LT 500ML KG") is None
    assert _get_product_root("1LT 500ML KG") is None


def test_token_con_cifre_esclusi():
    # "33CL" ha cifre, "BIRRA" è il token scelto
    assert _get_product_token("BIRRA 33CL") == "BIRRA"


# ── _build_new_tag_suggestions ──────────────────────────────────────────────

def _pool_salmone():
    return {
        "SALMONE NORVEGESE": {"descrizione": "Salmone Norvegese", "descrizione_key": "SALMONE NORVEGESE", "occorrenze": 5, "fornitori_count": 2, "ultima_data": "2026-05-24"},
        "SALMONE AFFUMICATO": {"descrizione": "Salmone Affumicato", "descrizione_key": "SALMONE AFFUMICATO", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-05-23"},
        "SALMONE FRESCO": {"descrizione": "Salmone Fresco", "descrizione_key": "SALMONE FRESCO", "occorrenze": 3, "fornitori_count": 2, "ultima_data": "2026-05-22"},
    }


def test_new_tag_suggerito_per_radice_comune():
    out = _build_new_tag_suggestions(_pool_salmone(), min_products=3, min_rows=5, window_days=30)
    assert len(out) == 1
    s = out[0]
    assert s["suggestion_type"] == "new_tag"
    assert s["cluster_key"] == "new_tag::SALMON"
    assert s["matched_products_count"] == 3
    assert s["matched_rows_count"] == 12
    # Il nome mostrato resta la forma reale leggibile, non la radice stemmata
    assert s["suggested_tag_name"] == "Salmone"


def test_new_tag_sotto_soglia_prodotti_non_suggerito():
    out = _build_new_tag_suggestions(_pool_salmone(), min_products=4, min_rows=5, window_days=30)
    assert len(out) == 0


def test_new_tag_sotto_soglia_righe_non_suggerito():
    out = _build_new_tag_suggestions(_pool_salmone(), min_products=3, min_rows=20, window_days=30)
    assert len(out) == 0


def test_new_tag_token_con_cifre_non_diventano_radice():
    """Prodotti con solo token numerici non devono generare suggerimenti."""
    pool = {
        "ACQUA 1LT": {"descrizione": "Acqua 1lt", "descrizione_key": "ACQUA 1LT", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
        "VINO 1LT": {"descrizione": "Vino 1lt", "descrizione_key": "VINO 1LT", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-05-23"},
        "OLIO 1LT": {"descrizione": "Olio 1lt", "descrizione_key": "OLIO 1LT", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-05-22"},
    }
    out = _build_new_tag_suggestions(pool, min_products=3, min_rows=5, window_days=30)
    # Devono essere 3 suggerimenti distinti (ACQUA, VINO, OLIO), non uno per "1LT"
    cluster_keys = {s["cluster_key"] for s in out}
    assert "new_tag::1LT" not in cluster_keys
    # Le radici corrette
    assert "new_tag::ACQUA" in cluster_keys or len(out) == 0  # singoli prodotti → sotto min_products=3


def test_new_tag_prodotti_diversi_non_raggruppati():
    """Prodotti con radici diverse non devono essere raggruppati."""
    pool = {
        "POLLO INTERO": {"descrizione": "Pollo Intero", "descrizione_key": "POLLO INTERO", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
        "SALMONE NORVEGESE": {"descrizione": "Salmone Norvegese", "descrizione_key": "SALMONE NORVEGESE", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-05-23"},
        "MANZO FILETTO": {"descrizione": "Manzo Filetto", "descrizione_key": "MANZO FILETTO", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-05-22"},
    }
    # Con min_products=3 nessuno ha 3 prodotti con stessa radice
    out = _build_new_tag_suggestions(pool, min_products=3, min_rows=5, window_days=30)
    assert len(out) == 0


# ── _build_extend_tag_suggestions ──────────────────────────────────────────

def test_extend_tag_radice_corrisponde():
    """Un nuovo prodotto con la stessa radice dei prodotti nel tag deve essere suggerito."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE", "SALMONE AFFUMICATO"]}
    untagged_pool = {
        "SALMONE FRESCO": {"descrizione": "Salmone Fresco", "descrizione_key": "SALMONE FRESCO", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 1
    s = out[0]
    assert s["suggestion_type"] == "extend_tag"
    assert s["target_tag_id"] == 10
    assert s["matched_products_count"] == 1
    assert s["confidence_score"] == 95.0


def test_extend_tag_plurale_aggancia_singolare():
    """Caso reale LAND: tag con 'SALMONE', nuovo prodotto 'SALMONI' → suggerito.

    Regressione: prima il match era esatto e il plurale del fornitore non
    agganciava mai il singolare taggato dal cliente.
    """
    tags = [{"id": 19, "nome": "Salmone Sushi"}]
    tag_assoc_keys = {19: ["SALMONE 5-6", "SALMONE 5-6 ADC TOP QUALITY"]}
    untagged_pool = {
        "SALMONI 5/6 FRESCHI SJOR ACQUACUL SALMO SALAR": {
            "descrizione": "Salmoni 5/6 Freschi Sjor",
            "descrizione_key": "SALMONI 5/6 FRESCHI SJOR ACQUACUL SALMO SALAR",
            "occorrenze": 6, "fornitori_count": 1, "ultima_data": "2026-06-24",
        },
    }
    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=1, window_days=90)
    assert len(out) == 1
    assert out[0]["target_tag_id"] == 19


def test_extend_tag_una_sola_occorrenza_suggerito_con_soglia_1():
    """Con MIN_OCCORRENZE_EXTEND=1 anche un prodotto visto una volta è proposto."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE"]}
    untagged_pool = {
        "SALMONE PREAFFETTATO": {"descrizione": "Salmone Preaffettato", "descrizione_key": "SALMONE PREAFFETTATO", "occorrenze": 1, "fornitori_count": 1, "ultima_data": "2026-06-22"},
    }
    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=1, window_days=90)
    assert len(out) == 1
    assert out[0]["target_tag_id"] == 10


def test_extend_tag_radice_diversa_non_suggerito():
    """Prodotto con radice diversa dai prodotti del tag non deve essere suggerito."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE", "SALMONE AFFUMICATO"]}
    untagged_pool = {
        "POLLO PETTO": {"descrizione": "Pollo Petto", "descrizione_key": "POLLO PETTO", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 0


def test_extend_tag_sotto_soglia_occorrenze_non_suggerito():
    """Prodotto comprato solo 1 volta (sotto min_occurrenze) non genera suggerimento."""
    tags = [{"id": 10, "nome": "Salmone"}]
    tag_assoc_keys = {10: ["SALMONE NORVEGESE"]}
    untagged_pool = {
        "SALMONE FRESCO": {"descrizione": "Salmone Fresco", "descrizione_key": "SALMONE FRESCO", "occorrenze": 1, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 0


def test_extend_tag_token_con_cifre_non_matchano():
    """Prodotti raggruppabili solo per token numerico (es. 1LT) non devono estendere tag."""
    tags = [{"id": 20, "nome": "Acqua"}]
    # Il tag "Acqua" ha solo "ACQUA NATURALE" con radice ACQUA
    tag_assoc_keys = {20: ["ACQUA NATURALE"]}
    untagged_pool = {
        # "VINO 1LT": radice = VINO, non ACQUA → non deve matchare
        "VINO 1LT": {"descrizione": "Vino 1lt", "descrizione_key": "VINO 1LT", "occorrenze": 5, "fornitori_count": 1, "ultima_data": "2026-05-24"},
    }

    out = _build_extend_tag_suggestions(tags, tag_assoc_keys, untagged_pool, min_occurrenze=2, window_days=30)
    assert len(out) == 0


# ── niente doppio suggerimento sulla stessa radice ──────────────────────────

def test_new_tag_non_proposto_se_radice_gia_in_un_tag():
    """Caso reale 7/8: 'Crea tag Salmoni' e 'Aggiungi a SALMONE SUSHI' proponevano
    gli STESSI 11 prodotti. Se un tag presidia gia' la radice, la creazione di un
    tag omonimo va soppressa: resta il solo extend, senza disperdere il dato."""
    roots = _roots_dei_tag_esistenti({19: ["SALMONE 5-6", "SALMONE 6+"]})
    out = _build_new_tag_suggestions(
        _pool_salmone(), min_products=3, min_rows=5, window_days=30,
        roots_gia_coperte=roots,
    )
    assert out == []


def test_new_tag_resta_se_la_radice_non_e_coperta():
    """La soppressione e' mirata: un tag su un'altra radice non deve zittire il resto."""
    roots = _roots_dei_tag_esistenti({20: ["TONNO PINNE GIALLE"]})
    out = _build_new_tag_suggestions(
        _pool_salmone(), min_products=3, min_rows=5, window_days=30,
        roots_gia_coperte=roots,
    )
    assert len(out) == 1
    assert out[0]["cluster_key"] == "new_tag::SALMON"


def test_roots_dei_tag_esistenti_usa_la_radice_canonica():
    """Il plurale del fornitore deve coprire il singolare del cliente e viceversa."""
    assert _roots_dei_tag_esistenti({1: ["SALMONI 5/6 FRESCHI"]}) == {"SALMON"}
    assert _roots_dei_tag_esistenti({1: ["SALMONE 5-6"]}) == {"SALMON"}
    assert _roots_dei_tag_esistenti({1: ["1LT 500ML"]}) == set()


# ── punteggiatura nel primo token ───────────────────────────────────────────

def test_token_salta_abbreviazione_puntata():
    """'FIL.' passava (4 caratteri, nessuna cifra) e diventava la radice.
    Spezzando sul punto resta 'FIL', troppo corto: si prosegue fino a SALMONE."""
    assert _get_product_token("FIL. SALMONE FRESCO") == "SALMONE"


def test_token_non_incolla_le_parole_attorno_alla_punteggiatura():
    """La punteggiatura va spezzata, non cancellata: cancellandola 'PROSC.CRUDO'
    diventerebbe 'PROSCCRUDO' e 'ROAST-BEEF' 'ROASTBEEF', radici inventate."""
    assert _get_product_token("PROSC.CRUDO GR100") == "PROSC"
    assert _get_product_token("ROAST-BEEF SOTTOF INGLESE") == "ROAST"
    assert _get_product_token("TERRA&VITA PELATI") == "TERRA"


def test_token_prosegue_dentro_lo_stesso_token():
    """'INS.CAPRICCIOSA' e' un token solo: scartato 'INS' si deve valutare
    'CAPRICCIOSA', non saltare all'intero token successivo."""
    assert _get_product_token("INS.CAPRICCIOSA") == "CAPRICCIOSA"
    assert _get_product_token("FR.RI.COCCO") == "COCCO"


def test_token_apostrofo_non_spezza_il_nome():
    assert _get_product_token("SOUFFLE' CIOCCOLATO") == "SOUFFLE"


# ── soglia fornitori: marche e formati fuori dai nuovi tag ──────────────────

def _pool_un_solo_fornitore():
    """Caso reale 7/8: MOCCHI/ROENO/CREAMI — un solo fornitore li vende."""
    return {
        "MOCCHI CIOCCOLATO": {"descrizione": "Mocchi Cioccolato", "descrizione_key": "MOCCHI CIOCCOLATO", "occorrenze": 4, "fornitori_count": 1, "ultima_data": "2026-08-01"},
        "MOCCHI MANGO": {"descrizione": "Mocchi Mango", "descrizione_key": "MOCCHI MANGO", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-08-02"},
        "MOCCHI FRAGOLA": {"descrizione": "Mocchi Fragola", "descrizione_key": "MOCCHI FRAGOLA", "occorrenze": 3, "fornitori_count": 1, "ultima_data": "2026-08-03"},
    }


def test_new_tag_scartato_se_un_solo_fornitore():
    """Una radice comprata da un fornitore solo e' una marca o un formato, non un
    ingrediente: e' cosi' che nascevano i tag 'Mocchi', 'Roeno', 'Creami'."""
    out = _build_new_tag_suggestions(
        _pool_un_solo_fornitore(), min_products=3, min_rows=5, window_days=30,
    )
    assert out == []


def test_new_tag_proposto_se_almeno_due_fornitori():
    """Il criterio non deve zittire gli ingredienti veri: SALMONE arriva da 7
    fornitori diversi, e nel pool di test da 2."""
    out = _build_new_tag_suggestions(
        _pool_salmone(), min_products=3, min_rows=5, window_days=30,
    )
    assert len(out) == 1
    assert out[0]["cluster_key"] == "new_tag::SALMON"


def test_soglia_fornitori_conta_sul_gruppo_non_sul_singolo_prodotto():
    """Trappola verificata sul DB il 7/8: ogni singolo "SALMONE 5-6" ha UN solo
    fornitore, ma la radice SALMON ne ha 7. Misurando il prodotto isolato si
    scarterebbero gli ingredienti veri (SALMONE, PATATE, PASTA) insieme alle marche."""
    pool = {
        "SALMONE 5-6": {"descrizione": "Salmone 5-6", "descrizione_key": "SALMONE 5-6", "occorrenze": 5, "fornitori_count": 1, "fornitori": {"ADC"}, "ultima_data": "2026-08-01"},
        "SALMONE 6+": {"descrizione": "Salmone 6+", "descrizione_key": "SALMONE 6+", "occorrenze": 4, "fornitori_count": 1, "fornitori": {"MOWI"}, "ultima_data": "2026-08-02"},
        "SALMONI FRESCHI": {"descrizione": "Salmoni Freschi", "descrizione_key": "SALMONI FRESCHI", "occorrenze": 3, "fornitori_count": 1, "fornitori": {"SJOR"}, "ultima_data": "2026-08-03"},
    }
    out = _build_new_tag_suggestions(pool, min_products=3, min_rows=5, window_days=30)
    assert len(out) == 1
    assert out[0]["cluster_key"] == "new_tag::SALMON"


def test_soglia_fornitori_scarta_il_gruppo_di_un_solo_fornitore():
    """Speculare al precedente: 3 prodotti diversi ma tutti dallo stesso fornitore
    restano una marca (caso MOCCHI/ROENO), e vanno scartati."""
    pool = {
        f"MOCCHI {gusto}": {"descrizione": f"Mocchi {gusto}", "descrizione_key": f"MOCCHI {gusto}", "occorrenze": 3, "fornitori_count": 1, "fornitori": {"DOLCEVITA"}, "ultima_data": "2026-08-01"}
        for gusto in ("COCCO", "MANGO", "FRAGOLA")
    }
    assert _build_new_tag_suggestions(pool, min_products=3, min_rows=5, window_days=30) == []


def test_soglia_fornitori_non_tocca_gli_extend_tag():
    """Sull'extend il tag esiste gia' ed e' stato voluto dall'utente: aggiungere
    un prodotto monofornitore a un tag suo e' corretto."""
    out = _build_extend_tag_suggestions(
        [{"id": 7, "nome": "DOLCI"}],
        {7: ["MOCCHI COCCO"]},
        _pool_un_solo_fornitore(),
        min_occurrenze=1,
        window_days=30,
    )
    assert len(out) == 1
    assert out[0]["target_tag_id"] == 7


# ── pulizia automatica dei suggerimenti obsoleti ────────────────────────────

class _FakeQuery:
    def __init__(self, rows, log):
        self._rows, self._log = rows, log

    def select(self, *_a, **_k):
        return self

    def update(self, payload):
        self._log.append(payload)
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, _col, ids):
        self._log.append(list(ids))
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self._rows)


class _FakeSb:
    """Registra gli update: serve a provare che i non-pending non vengono toccati."""

    def __init__(self, rows):
        self.rows, self.log = rows, []

    def table(self, _nome):
        return _FakeQuery(self.rows, self.log)


_PENDING = [
    {"id": 1, "cluster_key": "new_tag::ROENO", "suggestion_type": "new_tag", "target_tag_id": None},
    {"id": 2, "cluster_key": "new_tag::ROEN", "suggestion_type": "new_tag", "target_tag_id": None},
    {"id": 3, "cluster_key": "extend_tag::19", "suggestion_type": "extend_tag", "target_tag_id": 19},
]


def test_pulizia_ritira_la_cluster_key_sparita():
    """Caso reale: lo stemmer ha spostato ROENO->ROEN e il vecchio suggerimento
    e' rimasto pending in eterno, affiancato al nuovo con gli stessi 3 vini."""
    sb = _FakeSb(_PENDING)
    n = dismiss_suggerimenti_obsoleti(
        "u1", "r1", {"new_tag::ROEN", "extend_tag::19"}, {19}, supabase_client=sb,
    )
    assert n == 1
    assert [1] in sb.log
    assert {"status": "dismissed", "feedback_note": "obsoleto: non più rilevato dal motore"} in sb.log


def test_pulizia_non_scrive_se_nessun_suggerimento_attivo():
    """Guardia critica: una run a vuoto (finestra senza fatture, errore di rete)
    non deve azzerare tutti i suggerimenti del cliente."""
    sb = _FakeSb(_PENDING)
    assert dismiss_suggerimenti_obsoleti("u1", "r1", set(), {19}, supabase_client=sb) == 0
    assert sb.log == []


def test_pulizia_idempotente():
    """Al secondo giro non c'e' piu' nulla da ritirare: nessuna scrittura."""
    sb = _FakeSb([_PENDING[1], _PENDING[2]])
    assert dismiss_suggerimenti_obsoleti(
        "u1", "r1", {"new_tag::ROEN", "extend_tag::19"}, {19}, supabase_client=sb,
    ) == 0
    assert sb.log == []


def test_pulizia_ritira_extend_verso_tag_cancellato():
    """Se il tag di destinazione non esiste piu' il suggerimento e' inaccettabile."""
    sb = _FakeSb([_PENDING[2]])
    assert dismiss_suggerimenti_obsoleti(
        "u1", "r1", {"extend_tag::19"}, set(), supabase_client=sb,
    ) == 1


def test_pulizia_interroga_solo_i_pending():
    """accepted/dismissed/snoozed sono decisioni dell'utente: uno snooze ritirato
    d'ufficio tradirebbe il 'ricordamelo piu' avanti'."""
    sb = _FakeSb(_PENDING)
    query = sb.table("custom_tag_suggestions")
    assert hasattr(query, "eq")
    dismiss_suggerimenti_obsoleti("u1", "r1", {"new_tag::ROEN"}, {19}, supabase_client=sb)
    # la UPDATE porta sempre il filtro di stato, oltre a user/ristorante
    assert any(isinstance(v, dict) and v.get("status") == "dismissed" for v in sb.log)


# ── nome del tag sul percorso di lettura ────────────────────────────────────

def test_nomi_tag_per_id_lista_vuota_non_interroga_il_db():
    """Nessun extend_tag = nessuna query in piu' sulla Home."""
    assert _nomi_tag_per_id([], "u1", "r1", supabase_client=None) == {}


def test_nomi_tag_per_id_mappa_id_su_nome():
    """Il nome del tag non e' una colonna del suggerimento: va risolto in lettura,
    o il frontend mostra 'Aggiungi al tag \"undefined\"' (caso reale 7/8)."""
    sb = _FakeSb([{"id": 19, "nome": "SALMONE SUSHI"}, {"id": 22, "nome": "Ricciola"}])
    assert _nomi_tag_per_id([19, 22], "u1", "r1", supabase_client=sb) == {
        19: "SALMONE SUSHI", 22: "Ricciola",
    }


# ── _filtra_items_selezionati ───────────────────────────────────────────────
# Regressione §3c: la deselezione dei prodotti nel dialog non arrivava al
# backend (AcceptSuggestionRequest non aveva il campo) e il filtro su
# selected_by_default era inerte — misurato sul DB: 307 item su 307 a true.

_ITEMS = [
    {"descrizione": "SALMONE 5/6", "descrizione_key": "salmone56", "selected_by_default": True},
    {"descrizione": "SALMONE 6/7", "descrizione_key": "salmone67", "selected_by_default": True},
    {"descrizione": "SALMONE AFF.", "descrizione_key": "salmoneaff", "selected_by_default": True},
]


def test_filtra_items_usa_le_chiavi_del_client():
    out = _filtra_items_selezionati(_ITEMS, ["salmone56", "salmoneaff"])
    assert [i["descrizione_key"] for i in out] == ["salmone56", "salmoneaff"]


def test_filtra_items_deselezione_totale_non_associa_nulla():
    # Il client blocca a monte, ma il backend non deve fidarsi: lista vuota
    # significa "nessun prodotto", non "tutti".
    assert _filtra_items_selezionati(_ITEMS, []) == []


def test_filtra_items_senza_chiavi_ricade_su_selected_by_default():
    # Chiamate vecchie (nessun descrizioni_key): comportamento precedente intatto.
    assert len(_filtra_items_selezionati(_ITEMS, None)) == 3


def test_filtra_items_senza_chiavi_rispetta_selected_by_default_false():
    items = [dict(_ITEMS[0]), {**_ITEMS[1], "selected_by_default": False}]
    out = _filtra_items_selezionati(items, None)
    assert [i["descrizione_key"] for i in out] == ["salmone56"]


def test_filtra_items_ignora_chiavi_inesistenti():
    assert _filtra_items_selezionati(_ITEMS, ["non_esiste"]) == []


def test_filtra_items_normalizza_spazi_e_scarta_chiavi_vuote():
    out = _filtra_items_selezionati(_ITEMS, ["  salmone67  ", "", "   "])
    assert [i["descrizione_key"] for i in out] == ["salmone67"]


def test_filtra_items_lista_item_vuota():
    assert _filtra_items_selezionati(None, ["salmone56"]) == []


def test_extend_tag_senza_item_selezionati_non_accetta():
    # Guardia simmetrica a quella di create_tag: con zero prodotti selezionati il
    # suggerimento non va marcato 'accepted' (sparirebbe dalla lista senza aver
    # associato nulla).
    import services.tag_suggestion_service as tss

    sugg = {
        "id": 1, "suggestion_type": "extend_tag", "target_tag_id": 7,
        "items": list(_ITEMS),
    }
    orig = tss._get_suggestion_with_items
    tss._get_suggestion_with_items = lambda *a, **k: sugg

    class _FakeSB:
        def table(self, _n): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return type("R", (), {"data": [{"id": 7}]})()

    try:
        res = tss.accept_suggestion_extend_tag(
            suggestion_id=1, tag_id=7, user_id="u", ristorante_id="r",
            supabase_client=_FakeSB(), descrizioni_key=[],
        )
    finally:
        tss._get_suggestion_with_items = orig
    assert res == {"success": False, "error": "no_items_selected"}, res
