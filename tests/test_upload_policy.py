"""Policy sulle date di upload (services/upload_policy.py).

Contesto: i flag `blocco_anno_precedente` / `blocco_mesi_precedenti` erano
applicati solo nel percorso Streamlit, ormai irraggiungibile — interruttori
spenti in produzione. Questi test fissano il comportamento della regola ora che
vive in un modulo proprio e la applica il worker.

`oggi` e' sempre esplicito: un test che dipende da date.today() cambierebbe
verdetto a seconda del giorno in cui gira.
"""

from datetime import date

import pytest

from services.upload_policy import (
    BLOCCO_ANNO,
    BLOCCO_MESE,
    messaggio_blocco,
    valuta_policy_data,
)

OGGI = date(2026, 8, 26)


class TestBloccoMesiPrecedenti:
    def test_mese_vecchio_bloccato_quando_flag_attivo(self):
        assert valuta_policy_data(
            "2026-06-15", {"blocco_mesi_precedenti": True}, oggi=OGGI
        ) == BLOCCO_MESE

    def test_mese_corrente_passa(self):
        assert valuta_policy_data(
            "2026-08-01", {"blocco_mesi_precedenti": True}, oggi=OGGI
        ) is None

    def test_mese_precedente_passa(self):
        assert valuta_policy_data(
            "2026-07-31", {"blocco_mesi_precedenti": True}, oggi=OGGI
        ) is None

    def test_flag_spento_lascia_passare(self):
        assert valuta_policy_data(
            "2026-06-15", {"blocco_mesi_precedenti": False}, oggi=OGGI
        ) is None

    def test_flag_assente_lascia_passare(self):
        """Default False: il blocco mesi si attiva esplicitamente, al contrario
        del blocco anno."""
        assert valuta_policy_data("2026-06-15", {}, oggi=OGGI) is None

    def test_cambio_anno_il_mese_precedente_e_dicembre(self):
        """A gennaio il mese precedente sta nell'anno prima: senza questo il
        blocco anno lo intercetterebbe comunque, ma per il motivo sbagliato."""
        gennaio = date(2027, 1, 15)
        assert valuta_policy_data(
            "2026-12-20",
            {"blocco_mesi_precedenti": True, "blocco_anno_precedente": False},
            oggi=gennaio,
        ) is None


class TestBloccoAnnoPrecedente:
    def test_anno_precedente_bloccato_per_default(self):
        assert valuta_policy_data("2025-12-31", {}, oggi=OGGI) == BLOCCO_ANNO

    def test_disattivabile_esplicitamente(self):
        assert valuta_policy_data(
            "2025-12-31", {"blocco_anno_precedente": False}, oggi=OGGI
        ) is None

    def test_gennaio_dicembre_precedente_passa(self):
        """Il caso normale di inizio anno: le fatture di dicembre arrivano a
        gennaio. Con `data.year < oggi.year` secco (l'indice storico) sarebbero
        state rifiutate a TUTTI i clienti, perche' nessuno configura la chiave e
        il default e' True."""
        gennaio = date(2027, 1, 10)
        assert valuta_policy_data("2026-12-28", {}, oggi=gennaio) is None

    def test_gennaio_novembre_resta_bloccato(self):
        """Il mese precedente e' ammesso, non tutto l'anno prima: novembre da
        gennaio resta fuori."""
        gennaio = date(2027, 1, 10)
        assert valuta_policy_data("2026-11-28", {}, oggi=gennaio) == BLOCCO_ANNO

    def test_febbraio_dicembre_torna_bloccato(self):
        """A febbraio dicembre non e' piu' il mese precedente: la deroga si
        chiude da sola, senza date speciali cablate."""
        assert valuta_policy_data(
            "2026-12-28", {}, oggi=date(2027, 2, 10)
        ) == BLOCCO_ANNO

    def test_anno_ha_precedenza_sul_mese(self):
        """Con entrambi i flag attivi una fattura dell'anno scorso deve dire
        'anno precedente': e' il messaggio che spiega davvero il rifiuto."""
        assert valuta_policy_data(
            "2025-06-15",
            {"blocco_anno_precedente": True, "blocco_mesi_precedenti": True},
            oggi=OGGI,
        ) == BLOCCO_ANNO


class TestBypass:
    def test_admin_bypassa_sempre(self):
        assert valuta_policy_data(
            "2020-01-01",
            {"blocco_anno_precedente": True, "blocco_mesi_precedenti": True},
            is_admin=True,
            oggi=OGGI,
        ) is None

    def test_trial_limitato_a_corrente_e_precedente(self):
        """Il trial ha la sua policy anche senza il flag: mese corrente o
        precedente, come _is_trial_invoice_date_allowed nel percorso storico."""
        assert valuta_policy_data(
            "2026-06-15", {}, is_trial=True, oggi=OGGI
        ) == BLOCCO_MESE
        assert valuta_policy_data(
            "2026-07-15", {}, is_trial=True, oggi=OGGI
        ) is None


class TestDateNonDecidibili:
    @pytest.mark.parametrize("valore", [None, "", "N/A", "None", "non-una-data"])
    def test_data_illeggibile_lascia_passare(self, valore):
        """Bloccare su una data non parsabile trasformerebbe un difetto di
        parsing in una fattura rifiutata."""
        assert valuta_policy_data(
            valore,
            {"blocco_anno_precedente": True, "blocco_mesi_precedenti": True},
            oggi=OGGI,
        ) is None

    def test_accetta_oggetto_date(self):
        assert valuta_policy_data(
            date(2026, 6, 15), {"blocco_mesi_precedenti": True}, oggi=OGGI
        ) == BLOCCO_MESE

    def test_pagine_abilitate_none_non_esplode(self):
        assert valuta_policy_data("2026-08-15", None, oggi=OGGI) is None

    @pytest.mark.parametrize("cfg", [[], "", "blocco_mesi_precedenti", 0, True])
    def test_pagine_abilitate_non_dict_ricade_sui_default(self, cfg):
        """La guardia e' `isinstance(..., dict)`, non `or {}`: un valore non-dict
        (lista, stringa) supererebbe `or {}` e poi esploderebbe su `.get`, oppure
        — per una stringa — si comporterebbe come un contenitore sbagliato.
        Il default che deve valere e' quello del dict vuoto."""
        assert valuta_policy_data("2026-08-15", cfg, oggi=OGGI) is None
        assert valuta_policy_data("2025-08-15", cfg, oggi=OGGI) == BLOCCO_ANNO


class TestMessaggi:
    def test_prefissi_riconosciuti_dal_frontend(self):
        assert messaggio_blocco(BLOCCO_ANNO, "2025-06-15", oggi=OGGI).startswith(
            "ANNO PRECEDENTE"
        )
        assert messaggio_blocco(BLOCCO_MESE, "2026-06-15", oggi=OGGI).startswith(
            "MESE NON CONSENTITO"
        )

    def test_messaggio_mese_nomina_i_mesi_ammessi(self):
        msg = messaggio_blocco(BLOCCO_MESE, "2026-06-15", oggi=OGGI)
        assert "Luglio 2026" in msg and "Agosto 2026" in msg

    def test_messaggio_mese_non_nomina_il_mese_sbagliato(self):
        """MESI_ITA e' 1-indexed: con l'indice storico (month - 1) il messaggio
        diceva 'Giugno o Luglio' mentre i mesi ammessi erano Luglio e Agosto."""
        msg = messaggio_blocco(BLOCCO_MESE, "2026-06-15", oggi=OGGI)
        assert "Giugno" not in msg

    def test_messaggio_gennaio_da_l_anno_giusto_a_dicembre(self):
        """A cavallo d'anno i due mesi ammessi stanno in anni diversi: un anno
        solo in fondo alla frase ne datava uno in modo falso."""
        msg = messaggio_blocco(BLOCCO_MESE, "2026-11-05", oggi=date(2027, 1, 15))
        assert "Dicembre 2026" in msg and "Gennaio 2027" in msg


class TestDefaultAsimmetriciDeiBlocchi:
    """I due blocchi hanno default OPPOSTI: e' voluto, ed e' facile allinearli per errore.

    `blocco_anno_precedente` e' attivo di default (fail-open), `blocco_mesi_precedenti`
    e' spento di default (fail-closed). Il pannello admin usava un fail-open uniforme
    e mostrava quindi ACCESO un blocco mesi che il backend non applicava: l'admin
    credeva di aver ristretto i caricamenti e non era vero. La correzione e' stata
    fatta nella UI, che ora legge un `defaultOn` per voce; questi default NON vanno
    toccati (vedi i commenti su gennaio/dicembre in upload_policy.py).
    """

    def test_blocco_mesi_spento_senza_configurazione(self):
        # Giugno con oggi=agosto: passa solo perche' il blocco mesi NON e' attivo.
        assert valuta_policy_data("2026-06-15", {}, oggi=OGGI) is None

    def test_blocco_anno_acceso_senza_configurazione(self):
        assert valuta_policy_data("2025-06-15", {}, oggi=OGGI) == BLOCCO_ANNO

    def test_i_due_default_non_coincidono(self):
        """Uccide il mutante "uniformo i due default": se qualcuno portasse il
        blocco mesi a True per simmetria, una fattura di giugno verrebbe
        rifiutata ad agosto a TUTTI i clienti, nessuno dei quali ha la chiave."""
        mesi = valuta_policy_data("2026-06-15", {}, oggi=OGGI)
        anno = valuta_policy_data("2025-06-15", {}, oggi=OGGI)
        assert (mesi, anno) == (None, BLOCCO_ANNO)
