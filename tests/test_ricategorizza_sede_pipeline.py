"""La ricategorizzazione massiva non deve divergere dall'ingest, ne' sovrascrivere
cio' che un umano ha gia' deciso.

Contesto: lo script aveva iniziato a concatenare il nome fornitore alla
descrizione prima di applicare dizionario e regole forti, per far vedere il
carrier alle regole telecom. Effetto collaterale misurato su 3.376 coppie reali:
51 divergenze dal percorso di produzione — "LINEA MARE SRL" fa scattare
_SERVIZI_CANONI_RE su "LINEA" (gamberi in SERVIZI), "COMO ACQUA S.R.L" fa
scattare _ACQUA_CONFEZIONATA_RE (bolletta idrica fra le bevande), e all'opposto
la ragione sociale davanti alla descrizione rompe i match del dizionario.

Perche' questo file e' stato riscritto il 09/09/2026
===================================================
La versione precedente definiva una `_pipeline` LOCALE, che il suo stesso
docstring dichiarava "Replica di pipeline_deterministica": copiava a mano cinque
righe dello script. Un test cosi' resta verde qualunque cosa succeda al codice
vero — e infatti era gia' divergente (citava 19 divergenze quando lo script ne
dichiarava 51, e non riproduceva ne' `_applica_tutti_guardrail` ne'
`descrizione_e_dubbia`, che nello script vengono dopo).

Ora si esegue il modulo VERO. E' diventato possibile perche' lo script e' stato
messo dietro `main()`: prima `create_client` girava a import time e un `import`
esplodeva sui secrets.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ricategorizza_sede.py"


@pytest.fixture(scope="module")
def script():
    """Il modulo vero, importato senza eseguire main() ne' toccare la rete."""
    spec = importlib.util.spec_from_file_location("_ricategorizza_sede_test", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


# Righe reali di SUSHILAND VILLA GUARDIA, misurate sul DB live il 09/09/2026.
# La 128426 e' il caso del precedente: decisa a mano come CARNE il 25/06
# (reviewed_by='admin-pasta-ripiena-2026-06-25'), la pipeline la vuole in
# "PASTA E CEREALI".
RIGA_ARBITRATA = {
    "id": 128426,
    "descrizione": "INVOLTINO VIETNAM (POLLO) 7X1,9KGX50PZ",
    "fornitore": "H.D. ITALIA S.R.L",
    "categoria": "CARNE",
    "categoria_fonte": None,
    "reviewed_at": "2026-06-25T10:14:16.58098",
    "prezzo_unitario": 10.0,
    "totale_riga": 10.0,
    "iva_percentuale": 10.0,
}


def _riga(**extra):
    base = {
        "id": 1,
        "descrizione": "PETTO DI POLLO",
        "fornitore": "FORNITORE X",
        "categoria": "Da Classificare",
        "categoria_fonte": None,
        "reviewed_at": None,
        "prezzo_unitario": 5.0,
        "totale_riga": 5.0,
        "iva_percentuale": 10.0,
    }
    base.update(extra)
    return base


class TestFornitoreNonContaminaLaDescrizione:
    """Il LIVELLO 0 di produzione (ai_service.py:4564): hard override utility
    prima di tutto, descrizione lasciata pulita per dizionario e regole."""

    @pytest.mark.parametrize("desc", [
        "GAMBERO ROSSO MEDITERRANEO",
        "SCAMPO 20/30 BORDO CONG",
    ])
    def test_una_ragione_sociale_che_pare_un_servizio_non_sposta_il_pesce(self, script, desc):
        con_fornitore = script.pipeline_deterministica(desc, "Da Classificare", "LINEA MARE SRL")
        senza = script.pipeline_deterministica(desc, "Da Classificare", None)
        assert con_fornitore == senza, (
            "il fornitore e' entrato nel match: e' la regressione delle 51 divergenze"
        )

    @pytest.mark.parametrize("desc,fornitore,attesa", [
        # Se il fornitore entrasse nel match, "ACQUA" nella ragione sociale
        # manderebbe la birra fra le acque.
        ("BIRRA MORETTI 33CL", "ACQUA DI NEPI SRL", "BIRRE"),
        # E all'opposto: la ragione sociale davanti alla descrizione rompe il
        # match del dizionario e degrada a Da Classificare.
        ("QUATTRO FORMAGGI", "RISTORANTE MONOPOLI SRL", "LATTICINI"),
    ])
    def test_la_ragione_sociale_non_entra_nel_match(self, script, desc, fornitore, attesa):
        """Fornitori NON-utility: qui il nome non deve contare in nessun modo.

        Verificato che entrambi contaminerebbero se concatenati: la birra
        finirebbe in ACQUA, i formaggi in Da Classificare.
        """
        assert script.pipeline_deterministica(desc, "Da Classificare", fornitore) == attesa
        assert script.pipeline_deterministica(desc, "Da Classificare", None) == attesa

    def test_il_fornitore_utility_resta_un_override_esplicito(self, script):
        """L'unico uso legittimo del fornitore: non deve sparire nel fix opposto."""
        assert script.pipeline_deterministica(
            "CANONE MENSILE", "Da Classificare", "ENEL ENERGIA S.P.A."
        ) == "UTENZE E LOCALI"


class TestNonSovrascrivereCioCheUnUmanoHaDeciso:
    def test_la_riga_arbitrata_del_precedente_non_viene_toccata(self, script):
        """Il caso vivo del 09/09: senza guardia questa riga diventava PASTA."""
        proposta = script.pipeline_deterministica(
            RIGA_ARBITRATA["descrizione"], "CARNE", RIGA_ARBITRATA["fornitore"]
        )
        assert proposta != "CARNE", (
            "premessa del test: se la pipeline non proponesse piu' un cambio, "
            "questo test non misurerebbe piu' niente"
        )

        updates, saltate, _ = script.seleziona_aggiornamenti([RIGA_ARBITRATA])

        assert 128426 not in updates, "una riga decisa a mano non va riscritta"
        assert [s[0] for s in saltate] == [128426]

    def test_la_correzione_del_cliente_e_protetta_anche_senza_reviewed_at(self, script):
        """Le due condizioni sono disgiunte sul live (12 e 318, unione 330):
        coprirne una sola lascerebbe scoperta l'altra."""
        riga = _riga(
            id=2, descrizione="INVOLTINO VIETNAM (POLLO) 7X1,9KGX50PZ",
            categoria="CARNE", categoria_fonte="correzione_cliente",
        )
        updates, saltate, _ = script.seleziona_aggiornamenti([riga])
        assert updates == {}
        assert [s[0] for s in saltate] == [2]

    def test_le_righe_mai_arbitrate_passano(self, script):
        """La guardia non deve trasformarsi in un blocco: senza questo, una
        selezione che scarta TUTTO sarebbe verde sugli altri test."""
        riga = _riga(id=3, descrizione="INVOLTINO VIETNAM (POLLO) 7X1,9KGX50PZ",
                     categoria="CARNE")
        updates, saltate, _ = script.seleziona_aggiornamenti([riga])
        assert 3 in updates
        assert saltate == []

    def test_in_un_lotto_misto_passa_solo_la_riga_libera(self, script):
        libera = _riga(id=4, descrizione="INVOLTINO VIETNAM (POLLO) 7X1,9KGX50PZ",
                       categoria="CARNE")
        updates, saltate, _ = script.seleziona_aggiornamenti([libera, RIGA_ARBITRATA])
        assert set(updates) == {4}
        assert [s[0] for s in saltate] == [128426]


class TestLoScriptDichiaraChiE:
    def test_la_scrittura_passa_dal_chokepoint_attribuito(self, script):
        """Prima del 09/09 lo script scriveva con `.update()` diretto: ogni sua
        riga finiva nel registro come `db_trigger`, indistinguibile dal worker.
        E' cio' che ha reso il precedente del 26/08 impossibile da misurare."""
        sorgente = SCRIPT.read_text(encoding="utf-8")
        assert "aggiorna_categoria_fatture" in sorgente
        assert script.SOURCE == "script_ricategorizza_sede"

    def test_la_select_porta_le_colonne_che_la_guardia_legge(self, script):
        """Senza `categoria_fonte`/`reviewed_at` nella select, `e_arbitrata`
        leggerebbe sempre None e la guardia sarebbe inerte sui dati veri —
        restando verde su ogni test che costruisce le righe a mano."""
        import inspect
        sorgente = inspect.getsource(script.carica_righe)
        assert "categoria_fonte" in sorgente
        assert "reviewed_at" in sorgente
