"""La % di righe classificate non si calcola su un campione troncato.

`home_salute` leggeva le righe del mese con `.execute()` diretto: PostgREST
tronca a 1000 righe **senza errore**, quindi la percentuale mostrata al cliente
era calcolata sulle prime 1000 invece che su tutte.

Misurato sulla produzione il 2/9/2026:
  - LAND DEI SAPORI  3.344 righe -> 1.000: diceva **100%** invece di 99%.
    Cioe' "tutte le righe sono classificate" mentre non lo erano.
  - SUSHILAND VILLA GUARDIA 1.564 -> 1.000: 97% invece di 96%.

L'impatto sull'indice era sotto la risoluzione dell'arrotondamento (la voce pesa
25 punti su 100, quindi 1 punto di % ne sposta 0,25) e nessun colore cambiava:
il difetto non era il valore di oggi, era che **cresce in silenzio** man mano che
i `needs_review` si spostano oltre le prime 1000 righe.

Il gemello `_salute_indice_rosso` paginava gia', con un commento che diceva
esplicitamente «troncare qui falserebbe la % di righe classificate»: le due
superfici calcolavano la stessa formula su due campioni diversi.

NOTA SUL FAKE — il mock DEVE simulare il cap del server, altrimenti il test
passa anche col bug: un client che restituisce tutte le righe a un `.execute()`
senza `.range()` non e' PostgREST, e' un mock generoso. Qui senza `.range()`
tornano solo le prime PAGE_SIZE righe, esattamente come fa il server vero.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

CAP_POSTGREST = 1000


def _fake_sb_con_cap(righe_fatture):
    """Client che TRONCA come PostgREST: `.execute()` senza `.range()` ritorna
    al massimo CAP_POSTGREST righe; con `.range(a, b)` ritorna quella fetta."""

    def _table(nome):
        stato = {"range": None}
        q = MagicMock()

        for attr in ("select", "eq", "is_", "gte", "lte", "order", "limit", "single"):
            getattr(q, attr).return_value = q

        def _range(inizio, fine):
            stato["range"] = (inizio, fine)
            return q

        q.range.side_effect = _range

        def _execute():
            if nome != "fatture":
                return MagicMock(data=[], count=0)
            if stato["range"] is None:
                # Il cap del server: nessun errore, solo meno righe.
                return MagicMock(data=righe_fatture[:CAP_POSTGREST],
                                 count=len(righe_fatture))
            inizio, fine = stato["range"]
            stato["range"] = None
            return MagicMock(data=righe_fatture[inizio:fine + 1],
                             count=len(righe_fatture))

        q.execute.side_effect = _execute
        return q

    sb = MagicMock()
    sb.table.side_effect = _table
    sb.rpc.return_value = MagicMock(
        execute=MagicMock(return_value=MagicMock(data=[]))
    )
    return sb


def _righe(totali, da_rivedere):
    """`da_rivedere` righe needs_review messe IN FONDO: sono quelle che il
    troncamento nasconde. E' il caso reale — le righe piu' recenti sono le meno
    classificate, e stanno oltre le prime 1000."""
    righe = [{"needs_review": False, "categoria": "CARNE", "descrizione": f"P{i}"}
             for i in range(totali - da_rivedere)]
    righe += [{"needs_review": True, "categoria": "Da Classificare",
               "descrizione": f"REV{i}"} for i in range(da_rivedere)]
    return righe


def _pct_classificate(resp):
    """La % non e' esposta come campo a se': entra nell'indice, che e' la media
    delle 4 voci a peso uguale.

    Nel fake, VERIFICATO chiamando la funzione e leggendo le voci (non dedotto):
    'fatture' risulta ok (ripiega su len(righe_mese) > 0, e le righe ci sono),
    mentre 'fatturato' e 'personale' sono a 0 perche' margini_mensili e' vuoto.
    Quindi indice == round((100 + 0 + 0 + pct) / 4) e la percentuale si rilegge
    come indice * 4 - 100.

    L'arrotondamento a intero dell'indice perde risoluzione: 4 punti di % ne
    valgono 1 di indice. Per questo i casi qui sotto usano percentuali attese
    multiple di 4 rispetto alla base, e c'e' un test dedicato che verifica
    l'assunzione sulle altre tre voci: se un domani cambia, fallisce li' e si
    legge il perche', invece di far fallire i casi con un numero misterioso.
    """
    return resp.indice * 4 - 100


def _chiama_home_salute(monkeypatch, sb):
    import services.fastapi_worker as fw

    monkeypatch.setattr(fw, "_resolve_user_from_token", lambda _a: {"id": "u1"})
    monkeypatch.setattr(fw, "_get_supabase_client", lambda: sb)
    monkeypatch.setattr(fw, "_resolve_ristorante_id", lambda _u, _s: "rid-1")
    monkeypatch.setattr(fw, "_costi_automatici_mese", lambda *a, **k: None)
    monkeypatch.setattr(
        fw, "_briefing_nome_referente", lambda *a, **k: (None, []), raising=False
    )
    return fw.home_salute(authorization="Bearer x")


class TestPercentualeSuTutteLeRighe:
    """I casi sono scelti dove il troncamento e' OSSERVABILE nell'indice.

    L'indice e' un intero e la voce pesa 1/4: 4 punti di percentuale valgono 1
    punto di indice. I numeri veri di produzione (99% vs 100%) cadono DENTRO
    quell'arrotondamento — un test costruito su di essi passerebbe anche col bug,
    come il primo tentativo di questa stessa sessione. Servono percentuali che si
    separino davvero.
    """

    def test_il_troncamento_nasconde_il_lavoro_arretrato(self, monkeypatch):
        """4.000 righe: le prime 1.000 pulite, le altre 3.000 da rivedere.

        Vera: 25% classificate -> indice 31 (rosso).
        Troncata: legge solo le prime 1.000, tutte pulite -> 100% -> indice 50.
        E' il caso peggiore del difetto: piu' arretrato c'e' oltre il cap, piu'
        la card dice che va tutto bene.
        """
        sb = _fake_sb_con_cap(_righe(4000, 3000))
        resp = _chiama_home_salute(monkeypatch, sb)

        assert resp.indice == 31, (
            f"atteso indice 31 (25% su 4.000 righe), ottenuto {resp.indice}. "
            "50 = ha letto solo le prime 1.000, tutte classificate"
        )
        assert _pct_classificate(resp) == 24

    def test_il_colore_cambia(self, monkeypatch):
        """Lo stesso caso, visto come lo vede il cliente: il colore della card."""
        sb = _fake_sb_con_cap(_righe(4000, 3000))
        resp = _chiama_home_salute(monkeypatch, sb)
        assert resp.colore == "rosso", (
            f"con 3.000 righe da rivedere la card non puo' essere {resp.colore}"
        )

    def test_meta_arretrato_oltre_il_cap(self, monkeypatch):
        """2.000 righe, 1.000 da rivedere -> 50%, indice 38. Troncato direbbe 50."""
        sb = _fake_sb_con_cap(_righe(2000, 1000))
        resp = _chiama_home_salute(monkeypatch, sb)
        assert _pct_classificate(resp) == 52

    def test_sotto_il_cap_resta_invariato(self, monkeypatch):
        """Le sedi piccole non cambiano comportamento: 800 righe, 400 aperte."""
        sb = _fake_sb_con_cap(_righe(800, 400))
        resp = _chiama_home_salute(monkeypatch, sb)
        assert _pct_classificate(resp) == 52

    def test_tutte_le_righe_vengono_lette(self, monkeypatch):
        """Controprova diretta: 3.344 righe (il volume vero di LAND), tutte da
        rivedere. Se paginasse solo la prima pagina l'indice non sarebbe 25."""
        sb = _fake_sb_con_cap(_righe(3344, 3344))
        resp = _chiama_home_salute(monkeypatch, sb)
        assert resp.indice == 25, (
            f"3.344 righe tutte da rivedere -> 0% classificate -> indice 25, "
            f"ottenuto {resp.indice}"
        )


class TestIlFakeMisuraDavvero:
    """Se il fake non troncasse, i test sopra passerebbero anche col bug."""

    def test_senza_range_il_fake_tronca_come_il_server(self):
        sb = _fake_sb_con_cap(_righe(3344, 34))
        q = sb.table("fatture").select("needs_review,categoria")
        assert len(q.execute().data) == CAP_POSTGREST, (
            "il fake deve troncare come PostgREST, o non prova niente"
        )

    def test_con_range_il_fake_restituisce_la_fetta(self):
        sb = _fake_sb_con_cap(_righe(3344, 34))
        q = sb.table("fatture").select("needs_review,categoria")
        assert len(q.range(1000, 1999).execute().data) == 1000
        q2 = sb.table("fatture").select("needs_review,categoria")
        assert len(q2.range(3000, 3999).execute().data) == 344
