"""Fra le scadute, la piu' recente sta in cima: il tempo va all'indietro.

In ogni altra fascia la scadenza cresce verso il futuro e la piu' vicina e' la
piu' urgente. Fra le SCADUTE il verso si rovescia: la piu' vicina a oggi e'
quella appena scaduta — ancora recuperabile con una telefonata — mentre in
fondo c'e' l'arretrato storico. `ordinaDocumenti` ordinava crescente anche
qui, cioe' apriva la lista sulla fattura piu' vecchia.

Quanto pesa, misurato sul DB di produzione il 25/09/2026: 1.909 scadute in
totale, di cui **1.313 (69%) oltre i 90 giorni**, contro 53 in scadenza entro
7 giorni. Sulla sede maggiore: 456 relitti oltre i 90 giorni e 20 fatture
urgenti. La sezione si apriva sui relitti.

**Perche' le date sono relative a oggi.** Con date fisse il test invecchia: una
fixture scritta come «scaduta ieri» fra sei mesi e' «scaduta da 180 giorni» e
smette di distinguere i rami (stessa ragione documentata in
test_scadenziario_kpi_frontend.py).

**Perche' si prova anche il verso NON rovesciato.** Il rischio speculare di
questo fix e' rovesciare tutto: per importo o per fornitore il verso non cambia
di significato e deve restare quello di `ordinaDocumenti`. Senza quei casi, un
`ordinaScadute` che inverte sempre passerebbe il test principale.

Mutazioni provate (25/09/2026), tutte uccise:
1. `db - da` -> `da - db` (torna crescente) -> test_la_piu_recente_in_cima
2. rovesciare anche il criterio importo -> test_per_importo_resta_decrescente
3. rovesciare anche il criterio fornitore -> test_per_fornitore_resta_alfabetico
4. bucket `scadute` che torna a `ordinaDocumenti` nel client -> test_il_client_usa_ordinaScadute
"""
import datetime
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
_RICHIEDE = ["ordinaScadute", "ordinaDocumenti"]

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


def _doc(id_, giorni_fa, importo=100.0, fornitore="F"):
    """Una scaduta `giorni_fa` giorni fa, con data costruita da oggi."""
    d = datetime.date.today() - datetime.timedelta(days=giorni_fa)
    return {
        "id": id_,
        "file_origine": f"{id_}.xml",
        "fornitore": fornitore,
        "totale_documento": importo,
        "scadenza_effettiva": d.isoformat(),
        "pagata": False,
        "is_nota_credito": False,
    }


def _ordina(docs, ordine):
    return esegui_ts(
        MODULO,
        "emit(m.ordinaScadute(input.docs, input.ordine).map(d => d.id));",
        {"docs": docs, "ordine": ordine},
        richiede=_RICHIEDE,
    )


def test_la_piu_recente_in_cima():
    """Il caso che conta: 10 giorni fa prima di 400 giorni fa."""
    docs = [_doc("vecchia", 400), _doc("recente", 10), _doc("media", 100)]
    assert _ordina(docs, "scadenza") == ["recente", "media", "vecchia"]


def test_una_sola_scaduta_non_rompe():
    assert _ordina([_doc("sola", 30)], "scadenza") == ["sola"]


def test_stessa_data_non_perde_documenti():
    """Due scadute lo stesso giorno restano entrambe in lista."""
    docs = [_doc("a", 15), _doc("b", 15)]
    assert sorted(_ordina(docs, "scadenza")) == ["a", "b"]


def test_per_importo_resta_decrescente():
    """Il verso per importo non cambia: il piu' grosso in cima, come altrove."""
    docs = [_doc("piccola", 10, importo=50.0), _doc("grossa", 400, importo=9000.0)]
    assert _ordina(docs, "importo") == ["grossa", "piccola"]


def test_per_fornitore_resta_alfabetico():
    docs = [_doc("z", 10, fornitore="Zeta"), _doc("a", 400, fornitore="Alfa")]
    assert _ordina(docs, "fornitore") == ["a", "z"]


def test_senza_data_in_coda():
    """Il bucket scadute ha per definizione una data, ma l'invariante non si
    appoggia alla garanzia di un'altra funzione."""
    docs = [_doc("con_data", 30)]
    senza = _doc("senza", 0)
    senza["scadenza_effettiva"] = None
    assert _ordina(docs + [senza], "scadenza") == ["con_data", "senza"]


def test_non_modifica_la_lista_in_ingresso():
    """`ordinaDocumenti` copia prima di ordinare: la nuova deve fare lo stesso,
    o l'ordine di un bucket cambierebbe quello di un altro."""
    docs = [_doc("vecchia", 400), _doc("recente", 10)]
    primo = esegui_ts(
        MODULO,
        "const prima = input.docs.map(d => d.id);"
        "m.ordinaScadute(input.docs, 'scadenza');"
        "emit([prima, input.docs.map(d => d.id)]);",
        {"docs": docs},
        richiede=_RICHIEDE,
    )
    assert primo[0] == primo[1], "ordinaScadute ha riordinato l'array originale"


def test_il_client_usa_ordinaScadute():
    """Il cablaggio: la funzione puo' essere giusta e non essere chiamata.

    Assert sul sorgente — debole da solo, ma qui copre la regressione concreta
    (il bucket che torna a `ordinaDocumenti`) che i test sopra non vedrebbero.
    """
    src = CLIENT.read_text(encoding="utf-8")
    assert "scadute: ordinaScadute(b.scadute, ordine)," in src, (
        "il bucket scadute non passa piu' da ordinaScadute"
    )
    # Gli altri bucket NON devono usarla: l'ordine rovesciato vale solo qui.
    for bucket in ("settimana", "mese", "oltre", "pagate"):
        assert f"{bucket}: ordinaDocumenti(b.{bucket}, ordine)," in src, (
            f"il bucket {bucket} ha cambiato ordinamento: il verso rovesciato "
            "vale solo per le scadute"
        )
