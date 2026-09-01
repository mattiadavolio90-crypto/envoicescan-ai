"""Fase 2 — rendere visibile CHI ha deciso la categoria (audit 1/9/2026).

D1 era la causa radice di tutto il piano: `fatture` non aveva ALCUN campo che
registrasse quale livello avesse deciso. Su 39.143 righe non era ricostruibile se
una categoria venisse da una regola certa, dal dizionario, da memoria non verificata
o dall'AI. Senza quel dato non si puo' applicare la filosofia del progetto — non si
puo' dubitare di cio' di cui non si conosce l'origine — ne' misurare per fonte, ne'
fare rollback mirato di una regola sbagliata.

Il dato ESISTEVA gia' nel codice: ogni return di `categorizza_con_memoria` lo logga
con la sua emoji, e `applica_regole_categoria_forti` restituisce 196 motivi distinti
che quasi tutti i chiamanti scartavano con `_`. Non andava ricostruito, andava propagato.

Fase 2 REGISTRA soltanto. E' la Fase 3 a farne un gate e la Fase 4 a escludere le
`da_verificare` dai margini: la separazione e' voluta, cosi' si misura la
distribuzione reale prima di cambiare un solo numero mostrato al cliente.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.ai_service import (
    _fiducia_per_fonte,
    categorizza_con_memoria,
    ultima_provenienza,
)

MIGRATION = Path("supabase/migrations/20260901170000_fatture_provenienza_categoria.sql")


@pytest.fixture
def _memoria_vuota(monkeypatch):
    """Isola i livelli deterministici: senza memorie caricate, a rispondere sono
    L0/L1.5/L4/L5/L6/L7 — cioe' proprio quelli che la provenienza deve distinguere."""
    from services import ai_service

    monkeypatch.setattr(ai_service, "_disable_global_memory", True, raising=False)
    monkeypatch.setattr(ai_service, "carica_memoria_completa", lambda *a, **k: None)
    monkeypatch.setattr(ai_service, "_memoria_cache", {
        "loaded": True, "_loaded_user_ids": {"u1"}, "classificazioni_manuali": {},
        "prodotti_utente": {}, "prodotti_utente_norm": {}, "prodotti_master": {},
        "prodotti_master_canon": {},
    }, raising=False)
    return ai_service


def _categorizza(descrizione, fornitore="FORNITORE SPA", prezzo=10.0, um=None):
    return categorizza_con_memoria(
        descrizione=descrizione, prezzo=prezzo, quantita=1, user_id="u1",
        supabase_client=object(), fornitore=fornitore, unita_misura=um,
        iva_percentuale=22, totale_riga=prezzo,
    )


class TestOgniLivelloSiDichiara:
    """Il valore del campo non e' che esista: e' che dica il vero, livello per livello."""

    @pytest.mark.parametrize("descrizione,fornitore,fonte_attesa", [
        ("CANONE TELEFONIA MOBILE", "TIM SPA", "L0_fornitore"),
        ("BLACK BURGER 150G", "FORNITORE SPA", "L1_5_non_negoziabile"),
        ("SALMONE AFFUMICATO 200G", "FORNITORE SPA", "L7_dizionario"),
    ])
    def test_la_fonte_corrisponde_al_livello_che_ha_deciso(
        self, _memoria_vuota, descrizione, fornitore, fonte_attesa
    ):
        _categorizza(descrizione, fornitore=fornitore)
        fonte, _fiducia = ultima_provenienza()
        assert fonte == fonte_attesa

    def test_riga_non_riconosciuta_dichiara_nessuna_fonte(self, _memoria_vuota):
        cat = _categorizza("ZZQX 4471 RIF. CONTRATTO")
        assert cat == "Da Classificare"
        fonte, fiducia = ultima_provenienza()
        assert fonte == "nessuna"
        # Una riga in coda non ha fiducia: non c'e' nulla di cui fidarsi.
        assert fiducia is None

    def test_la_provenienza_non_e_ereditata_dalla_riga_precedente(self, _memoria_vuota):
        """Il difetto piu' insidioso di un canale laterale: se non si azzera a ogni
        chiamata, una riga sconosciuta eredita la fonte di quella prima e diventa
        'certa' senza che nessuno l'abbia decisa."""
        _categorizza("CANONE TELEFONIA MOBILE", fornitore="TIM SPA")
        assert ultima_provenienza()[0] == "L0_fornitore"

        _categorizza("ZZQX 4471 RIF. CONTRATTO")
        assert ultima_provenienza()[0] == "nessuna", (
            "la riga sconosciuta ha ereditato la provenienza della precedente"
        )


class TestMappaturaFiducia:
    @pytest.mark.parametrize("fonte,attesa", [
        ("L1_admin", "certa"),
        ("L1_5_non_negoziabile", "certa"),
        ("L7_regola_forte", "certa"),
        ("AI_confermata", "certa"),
        ("L3_globale", "probabile"),
        ("L7_dizionario", "probabile"),
        ("AI_alta", "probabile"),
    ])
    def test_fonte_nota_ha_la_fiducia_attesa(self, fonte, attesa):
        assert _fiducia_per_fonte(fonte, "PESCE") == attesa

    def test_fonte_sconosciuta_e_da_verificare(self):
        """Prudenza: una fonte non prevista non puo' passare per certa."""
        assert _fiducia_per_fonte("fonte_inventata_domani", "PESCE") == "da_verificare"

    def test_legacy_non_ha_fiducia_e_non_e_da_verificare(self):
        """Vincolo S3 del piano: provenienza assente = `legacy` = si tratta come
        certa. Se `None` diventasse `da_verificare`, l'intero storico (39.143 righe)
        uscirebbe dai margini da un giorno all'altro, cambiando il MOL di aprile
        tre mesi dopo che il cliente l'ha letto."""
        assert _fiducia_per_fonte(None, "PESCE") is None

    def test_riga_in_coda_non_ha_fiducia(self):
        assert _fiducia_per_fonte("L7_dizionario", "Da Classificare") is None


class TestMigrationRispettaIVincoli:
    def test_la_migration_esiste(self):
        assert MIGRATION.exists()

    def test_aggiunge_le_due_colonne_senza_default(self):
        """ADD COLUMN senza DEFAULT e' metadata-only da PG11: nessun rewrite delle
        39.155 righe, nessun lock lungo su una tabella di produzione."""
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        assert "add column if not exists categoria_fonte" in sql
        assert "add column if not exists categoria_fiducia" in sql
        # Solo le righe ESEGUIBILI: la parola "default" compare nel commento che
        # ne spiega l'assenza, e cercarla nel testo grezzo misurerebbe la prosa.
        eseguibile = "\n".join(
            r for r in sql.split("\n") if r.strip() and not r.strip().startswith("--")
        )
        assert "default" not in eseguibile, (
            "un DEFAULT forzerebbe il rewrite della tabella E darebbe una "
            "provenienza inventata alle righe legacy"
        )

    def test_nessun_backfill_retroattivo(self):
        """Assegnare una fonte a righe scritte da un codice che non la registrava
        sarebbe un'invenzione, non un dato."""
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        assert "update public.fatture" not in sql
        assert "update fatture" not in sql

    def test_il_constraint_ammette_null(self):
        """NULL = legacy deve restare scrivibile, o lo storico diventa invalido."""
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        assert "categoria_fiducia is null" in sql


class TestTuttiIPercorsiDiCorrezioneRegistranoLUmano:
    """D5 — le correzioni manuali passano da QUATTRO endpoint diversi. Se anche uno
    solo non registrasse la fonte, una riga corretta a mano conserverebbe la
    provenienza automatica che l'aveva sbagliata, e la Fase 4 potrebbe escluderla
    dai margini proprio dopo che il cliente l'ha sistemata."""

    @pytest.mark.parametrize("percorso", [
        "services/routers/fatture.py",
        "services/routers/riparto.py",
    ])
    def test_nessun_update_di_categoria_senza_provenienza(self, percorso):
        src = Path(percorso).read_text(encoding="utf-8")
        # La forma compatta `.update({"categoria": X, "needs_review": False})` e'
        # esattamente quella che dimenticava la provenienza.
        assert '.update({"categoria": nuova_cat, "needs_review": False})' not in src
        assert '{"categoria": categoria, "needs_review": False}' not in src

    def test_la_correzione_manuale_e_certa(self):
        """Un umano che guarda la riga e' la fonte piu' attendibile che esista, e
        i tre update di questo file la scrivono esplicitamente `certa` — non la
        derivano da `_fiducia_per_fonte`, che di "correzione_cliente" non sa nulla."""
        src = Path("services/routers/fatture.py").read_text(encoding="utf-8")
        assert src.count('"categoria_fonte": "correzione_cliente"') == 3
        assert src.count('"categoria_fiducia": "certa"') == 3


class TestScrittureAutomaticheRegistranoLaFonte:
    def test_upload_handler_raggruppa_anche_per_fonte(self):
        """La chiave di raggruppamento deve includere fonte e fiducia: con la chiave
        vecchia due righe con la stessa categoria ma provenienza diversa finivano
        nello stesso UPDATE, e una delle due riceveva la provenienza dell'altra."""
        src = Path("services/upload_handler.py").read_text(encoding="utf-8")
        assert "(categoria_target, needs_review_target, fonte_target, fiducia_target)" in src
        assert "'categoria_fonte': fonte_target" in src

    def test_il_worker_distingue_ai_confermata_da_ai_sola(self):
        """Due fonti indipendenti concordi non sono la stessa cosa della sola
        parola dell'AI: la Fase 3 dovra' poterle trattare diversamente."""
        src = Path("worker/queue_processor.py").read_text(encoding="utf-8")
        assert '"AI_confermata" if _confermata_runtime else "AI_alta"' in src
        assert '"categoria_fonte": fonte' in src

    def test_il_worker_degrada_senza_mentire(self):
        """Se l'import della tracciabilita' fallisce, la colonna resta NULL (=legacy,
        =certa) e il degrado viene LOGGATO: non si scrive una fiducia inventata."""
        src = Path("worker/queue_processor.py").read_text(encoding="utf-8")
        assert "_fiducia_per_fonte (tracciabilita' Fase 2)" in src
