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
        assert "valuta_fiducia (gate Fase 3)" in src


class TestCoerenzaFonteCategoria:
    """Findings B2 della review (1/9): la fonte veniva decisa PRIMA che la categoria
    fosse definitiva.

    Gli 11 return di L0-L6 fanno `_ret(_applica_guardrail_note_con_importo(...),
    fonte="...")`: il guardrail puo' riportare la riga a "Da Classificare" dopo che
    la fonte e' gia' stata scelta. Misurato sul catalogo reale prima del fix: 68
    combinazioni descrizione/importo in cui una riga finiva in coda dichiarando che
    L4_dicitura (52) o L1_5_non_negoziabile (16) l'aveva decisa.

    Una riga in coda non ha, per definizione, un livello che l'ha decisa.
    """

    @pytest.mark.parametrize("descrizione", [
        "ARROTONDAMENTO DOCUMENTO",
        "AVOCADO TRASPORTO AEREO",
        "DDT N. 449 DEL 11/06/2026",
        "PREMIO POSTICIPATO FINE PERIODO RIFERIMENTO: 4000305",
    ])
    def test_riga_riportata_in_coda_dal_guardrail_non_ha_fonte(
        self, _memoria_vuota, descrizione
    ):
        """prezzo=0 fa riconoscere la dicitura (L4), ma totale_riga != 0 viola la
        regola di dominio #2 e il guardrail la rimanda in coda. E' la combinazione
        esatta che produceva le 52 righe con fonte "L4_dicitura" a fronte di una
        categoria "Da Classificare". Niente skip: se un giorno questa combinazione
        smettesse di finire in coda, il test deve FALLIRE e farlo notare, non
        passare in silenzio."""
        cat = categorizza_con_memoria(
            descrizione=descrizione, prezzo=0.0, quantita=1, user_id="u1",
            supabase_client=None, fornitore="X SPA", iva_percentuale=22,
            totale_riga=10.0,
        )
        assert str(cat).strip() == "Da Classificare", (
            "il guardrail NOTE non ha rimandato in coda una dicitura con importo: "
            "e' la regola di dominio #2, non un dettaglio di questo test"
        )
        fonte, fiducia = ultima_provenienza()
        assert fonte == "nessuna", f"riga in coda ma fonte='{fonte}'"
        assert fiducia is None

    def test_invariante_su_tutti_i_livelli(self, _memoria_vuota):
        """L'invariante non vale per una descrizione fortunata ma per costruzione:
        qualunque riga finisca in coda dichiara 'nessuna'."""
        from services import ai_service

        for desc in ("ARROTONDAMENTO DOCUMENTO", "ZZQX 4471 RIF. CONTRATTO",
                     "SALMONE AFFUMICATO 200G", "CANONE TELEFONIA MOBILE"):
            for prezzo, totale in ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (10.0, 10.0)):
                cat = categorizza_con_memoria(
                    descrizione=desc, prezzo=prezzo, quantita=1, user_id="u1",
                    supabase_client=None, fornitore="X SPA", iva_percentuale=22,
                    totale_riga=totale,
                )
                fonte, fiducia = ai_service.ultima_provenienza()
                if str(cat).strip() == "Da Classificare":
                    assert fonte == "nessuna", f"'{desc}' ({prezzo}/{totale}): {fonte}"
                    assert fiducia is None
                else:
                    assert fonte not in (None, "nessuna"), f"'{desc}': categoria senza fonte"

    def test_invoice_service_riallinea_prima_di_scrivere(self):
        """Fra la lettura della provenienza e la scrittura della riga la categoria
        passa ancora da enforce_no_unclassified_category, special_row e guardrail
        NOTE: la coerenza va garantita sulla categoria DAVVERO scritta."""
        src = Path("services/invoice_service.py").read_text(encoding="utf-8")
        assert "'categoria_fonte': (" in src
        assert "if str(categoria_finale).strip() == 'Da Classificare'" in src


class TestCorrezioneUmanaEFonteCerta:
    """Finding B3: `correzione_cliente` non era in `_FONTI_CERTE`, quindi
    `_fiducia_per_fonte` la classificava `da_verificare`. Non esplodeva solo perche'
    i router hardcodavano "certa" accanto alla fonte — ma `upload_handler` gia' deriva
    la fiducia da questa funzione. Il giorno in cui un percorso di correzione facesse
    lo stesso, la Fase 4 escluderebbe dai margini le righe appena corrette a mano."""

    @pytest.mark.parametrize("fonte", ["correzione_cliente", "correzione_admin"])
    def test_una_decisione_umana_e_certa(self, fonte):
        assert _fiducia_per_fonte(fonte, "CARNE") == "certa"


class TestNessunaScritturaSenzaProvenienza:
    """Finding B1: il commit dichiarava «tutti i percorsi», ma tre scrivevano la
    categoria senza registrarla — incluso l'agent notturno, che la fonte ce l'aveva
    in mano (`decisione_deterministica` due righe sopra) e la buttava via."""

    def test_ogni_update_di_categoria_porta_la_provenienza(self):
        import re

        scoperti = []
        for f in list(Path("services").rglob("*.py")) + list(Path("worker").rglob("*.py")):
            src = f.read_text(encoding="utf-8")
            for m in re.finditer(
                r'table\([\'"]fatture[\'"]\)\s*\.\s*(update|upsert)\(\s*\{(.{0,900}?)\}\s*\)',
                src, re.S,
            ):
                body = m.group(2)
                if ('"categoria"' in body or "'categoria'" in body) \
                        and "categoria_fonte" not in body:
                    scoperti.append(f"{f}:{src[:m.start()].count(chr(10)) + 1}")
        assert not scoperti, (
            f"scrivono la categoria senza provenienza: {scoperti}. "
            "La Fase 4 escluderebbe dai margini una fetta di righe scelta a caso."
        )

    def test_l_annullamento_azzera_la_provenienza(self):
        """Annullare significa tornare a PRIMA di quella decisione: lasciare la
        fonte descriverebbe una decisione che non esiste piu'. NULL = 'non lo
        sappiamo', che e' la verita' (l'originaria non era stata conservata)."""
        src = Path("services/routers/admin.py").read_text(encoding="utf-8")
        assert '"categoria_fonte": None' in src
        assert '"categoria_fiducia": None' in src

    def test_l_agent_notturno_non_butta_via_la_fonte_che_ha(self):
        src = Path("services/fastapi_worker.py").read_text(encoding="utf-8")
        assert '"L7_regola_forte" if _motivo else "L7_dizionario"' in src


class TestIlCommentDelDbNonMente:
    """Il comment di `fatture.categoria_fonte` elencava `L3_globale_non_verificata`
    (mai emesso dal codice) e ometteva `correzione_cliente`/`correzione_admin` (i
    valori che i cinque percorsi di correzione manuale scrivono davvero).

    Un comment di colonna e' documentazione che vive nel DB: mente a chiunque ispezioni
    lo schema per capire cosa contiene quel campo, ed e' proprio il tipo di
    documentazione che nessun test copre. Questo la copre.
    """

    _FIX = Path("supabase/migrations/20260901183000_fix_comment_categoria_fonte.sql")

    def _comment_vigente(self) -> str:
        """Il testo del comment EFFETTIVAMENTE in vigore: l'ultima migration in
        ordine cronologico che lo definisce, e di quella solo la stringa SQL — non
        il file intero, o si leggerebbero anche i commenti `--` che spiegano quali
        valori sono stati RIMOSSI, contandoli come ancora documentati."""
        import re

        vigente = ""
        for f in sorted(Path("supabase/migrations").glob("*.sql")):
            src = f.read_text(encoding="utf-8")
            eseguibile = "\n".join(
                r for r in src.split("\n") if not r.strip().startswith("--")
            )
            # `.*?;` si fermerebbe al primo punto e virgola, che nel comment sta
            # DENTRO la stringa: si legge fino a `';` (chiusura della stringa SQL).
            m = re.search(
                r"comment\s+on\s+column\s+public\.fatture\.categoria_fonte\s+is\s+(.*?'\s*;)",
                eseguibile, re.S | re.I,
            )
            if m:
                vigente = m.group(1)
        assert vigente, "nessuna migration definisce il comment di categoria_fonte"
        return vigente

    def test_il_fix_esiste(self):
        assert self._FIX.exists()

    def test_ogni_fonte_emessa_dal_codice_e_documentata(self):
        from services.ai_service import _FONTI_CERTE, _FONTI_PROBABILI

        comment = self._comment_vigente()
        mancanti = [
            f for f in sorted(_FONTI_CERTE | _FONTI_PROBABILI | {"nessuna"})
            if f not in comment
        ]
        assert not mancanti, f"fonti emesse dal codice ma non documentate a DB: {mancanti}"

    def test_nessun_valore_fantasma_nel_comment(self):
        """Il verso opposto, che e' quello che era sfuggito: un valore documentato
        che il codice non emette piu' e' altrettanto fuorviante."""
        import re

        from services.ai_service import _FONTI_CERTE, _FONTI_PROBABILI

        reali = _FONTI_CERTE | _FONTI_PROBABILI | {"nessuna"}
        comment = self._comment_vigente()
        # I token con questa forma nel comment sono nomi di fonte, non prosa.
        citati = set(re.findall(r"\b(?:L\d[A-Za-z0-9_]*|AI_[a-z]+|correzione_[a-z]+)\b", comment))
        fantasmi = sorted(citati - reali)
        assert not fantasmi, (
            f"il comment documenta valori che il codice non emette: {fantasmi}"
        )
