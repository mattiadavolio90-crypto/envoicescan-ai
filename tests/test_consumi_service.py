"""Consumi mensili e soglia di piano — logica pura, nessun mock di Supabase.

I numeri usati qui sono quelli MISURATI sul DB di produzione il 1/9/2026, non
inventati: se la logica di soglia si rompe, questi test falliscono sugli stessi
casi che l'admin vede in pagina.

Volutamente niente mock del client: in questo progetto sei test sono passati per
mesi su una query che filtrava una colonna inesistente, perche' il mock rispondeva
comunque. Qui la decisione e' isolata in funzioni pure e si prova sui valori.
"""
from datetime import date

import pytest

from services.consumi_service import (
    conta_sopra_soglia,
    costruisci_righe,
    limite_piano,
    mesi_badge,
    piano_effettivo,
    primo_mese_finestra,
    sopra_soglia,
)


class TestPianoEffettivo:
    def test_piano_sede_vince_su_account(self):
        # Caso reale: account 'free', sede 'base' (2 clienti su 7 il 1/9/2026).
        # Leggere il piano dall'account darebbe la soglia sbagliata.
        assert piano_effettivo("base", "free") == "base"

    def test_eredita_da_account_se_sede_senza_piano(self):
        assert piano_effettivo(None, "pro") == "pro"

    def test_default_base_se_nessuno_dei_due(self):
        assert piano_effettivo(None, None) == "base"

    def test_stringa_vuota_non_conta_come_piano(self):
        assert piano_effettivo("   ", "pro") == "pro"

    def test_normalizza_maiuscole_e_spazi(self):
        assert piano_effettivo(" PRO ", None) == "pro"


class TestLimitePiano:
    @pytest.mark.parametrize("piano,atteso", [
        ("free", 50), ("base", 50), ("plus", 100), ("pro", 200),
    ])
    def test_limiti_dei_quattro_piani(self, piano, atteso):
        assert limite_piano(piano) == atteso

    def test_piano_sconosciuto_ricade_sul_default(self):
        assert limite_piano("enterprise") == 50

    def test_piano_none_ricade_sul_default(self):
        assert limite_piano(None) == 50


class TestSopraSoglia:
    def test_esattamente_al_limite_non_sfora(self):
        # Il monte incluso e' consumabile per intero: 200 su 200 e' dentro.
        assert sopra_soglia(200, 200) is False

    def test_uno_oltre_sfora(self):
        assert sopra_soglia(201, 200) is True

    def test_caso_reale_land_dei_sapori_agosto(self):
        # 214 caricate su piano pro (200) — sforamento in corso il 1/9/2026.
        assert sopra_soglia(214, limite_piano("pro")) is True

    def test_caso_reale_offside_luglio(self):
        # 160 caricate su piano base (50).
        assert sopra_soglia(160, limite_piano("base")) is True

    def test_caso_reale_sushiland_villa_guardia_agosto_non_sfora(self):
        # 151 su pro (200): sotto soglia, non deve comparire fra gli avvisi.
        assert sopra_soglia(151, limite_piano("pro")) is False

    def test_discriminante_51_su_50(self):
        assert sopra_soglia(50, 50) is False
        assert sopra_soglia(51, 50) is True


def _sede(rid, nome, piano=None, account_piano=None, email="cliente@example.com"):
    return {"id": rid, "nome_ristorante": nome, "piano": piano,
            "account_piano": account_piano, "email": email}


class TestCostruisciRighe:
    def test_unisce_fatture_ai_e_anagrafica(self):
        consumi = [{"ristorante_id": "r1", "mese": "2026-08",
                    "manuali": 214, "sdi": 0, "tot": 214}]
        ai = [{"ristorante_id": "r1", "mese": "2026-08",
               "richieste": 48, "token": 344851, "costo": 0.1422}]
        sedi = [_sede("r1", "LAND DEI SAPORI SRL", piano="pro")]

        righe = costruisci_righe(consumi, ai, sedi)

        assert len(righe) == 1
        r = righe[0]
        assert r["sede"] == "LAND DEI SAPORI SRL"
        assert (r["manuali"], r["sdi"], r["totale"]) == (214, 0, 214)
        assert (r["piano"], r["limite"]) == ("pro", 200)
        assert r["sopra_soglia"] is True
        assert (r["ai_richieste"], r["ai_costo"]) == (48, 0.1422)

    def test_split_canale_manuale_e_sdi(self):
        # OFFSIDE luglio: 144 manuali + 16 SDI = 160.
        consumi = [{"ristorante_id": "r2", "mese": "2026-07",
                    "manuali": 144, "sdi": 16, "tot": 160}]
        sedi = [_sede("r2", "OFFSIDE SPORTS PUB", piano="base")]

        r = costruisci_righe(consumi, [], sedi)[0]

        assert (r["manuali"], r["sdi"], r["totale"]) == (144, 16, 160)
        assert r["sopra_soglia"] is True

    def test_sede_non_ammessa_viene_scartata(self):
        # Una sede tecnica esclusa a monte non deve rientrare dalla finestra:
        # e' cosi' che "Costi comuni di gruppo" resta fuori dagli avvisi.
        consumi = [{"ristorante_id": "tecnica", "mese": "2026-07",
                    "manuali": 127, "sdi": 15, "tot": 142}]

        assert costruisci_righe(consumi, [], []) == []

    def test_mese_senza_consumo_ai_resta_a_zero(self):
        consumi = [{"ristorante_id": "r3", "mese": "2026-08",
                    "manuali": 3, "sdi": 0, "tot": 3}]
        sedi = [_sede("r3", "CASATI 14", piano="pro")]

        r = costruisci_righe(consumi, [], sedi)[0]

        assert (r["ai_richieste"], r["ai_token"], r["ai_costo"]) == (0, 0, 0.0)

    def test_ai_di_un_altro_mese_non_viene_attribuita(self):
        consumi = [{"ristorante_id": "r1", "mese": "2026-08",
                    "manuali": 10, "sdi": 0, "tot": 10}]
        ai = [{"ristorante_id": "r1", "mese": "2026-07", "richieste": 99,
               "token": 1, "costo": 1.0}]
        sedi = [_sede("r1", "LAND DEI SAPORI SRL", piano="pro")]

        assert costruisci_righe(consumi, ai, sedi)[0]["ai_richieste"] == 0

    def test_fallback_piano_account_quando_sede_senza_piano(self):
        consumi = [{"ristorante_id": "r4", "mese": "2026-08",
                    "manuali": 60, "sdi": 0, "tot": 60}]
        sedi = [_sede("r4", "TIME CAFE", piano=None, account_piano="pro")]

        r = costruisci_righe(consumi, [], sedi)[0]

        assert (r["piano"], r["limite"]) == ("pro", 200)
        assert r["sopra_soglia"] is False

    def test_caso_reale_account_free_sede_base(self):
        # 60 fatture: sotto soglia con 'base' (50)? No, sopra. Ma il punto e' che
        # il limite applicato dev'essere quello della SEDE, non dell'account.
        consumi = [{"ristorante_id": "r5", "mese": "2026-07",
                    "manuali": 40, "sdi": 0, "tot": 40}]
        sedi = [_sede("r5", "OVERTIME", piano="base", account_piano="free")]

        r = costruisci_righe(consumi, [], sedi)[0]

        assert r["piano"] == "base"
        assert r["sopra_soglia"] is False


class TestPrimoMeseFinestra:
    def test_una_finestra_di_un_mese_parte_dal_mese_corrente(self):
        assert primo_mese_finestra(date(2026, 9, 1), 1) == date(2026, 9, 1)

    def test_dodici_mesi_coprono_esattamente_dodici_mesi(self):
        # Il difetto originale (31 giorni fissi) ne restituiva 13: da ottobre 2025.
        assert primo_mese_finestra(date(2026, 9, 15), 12) == date(2025, 10, 1)

    def test_due_mesi_e_il_percorso_del_badge(self):
        assert primo_mese_finestra(date(2026, 9, 1), 2) == date(2026, 8, 1)

    def test_attraversa_il_capodanno(self):
        assert primo_mese_finestra(date(2026, 2, 10), 3) == date(2025, 12, 1)

    def test_torna_sempre_il_primo_del_mese(self):
        assert primo_mese_finestra(date(2026, 7, 31), 4).day == 1

    @pytest.mark.parametrize("mese", range(1, 13))
    def test_nessun_mese_dell_anno_sfora_la_finestra(self, mese):
        # Il difetto a 31 giorni si vedeva solo in certi mesi (marzo, maggio,
        # luglio, ottobre, dicembre con mesi=2): vanno provati tutti e 12.
        inizio = primo_mese_finestra(date(2026, mese, 1), 12)
        distanza = (2026 * 12 + mese - 1) - (inizio.year * 12 + inizio.month - 1)
        assert distanza == 11

    def test_mesi_zero_o_negativo_non_esplode(self):
        assert primo_mese_finestra(date(2026, 9, 1), 0) == date(2026, 9, 1)
        assert primo_mese_finestra(date(2026, 9, 1), -5) == date(2026, 9, 1)


class TestMesiBadge:
    def test_mese_corrente_e_precedente(self):
        assert mesi_badge("2026-09") == ["2026-09", "2026-08"]

    def test_rollover_gennaio_torna_a_dicembre_anno_prima(self):
        assert mesi_badge("2026-01") == ["2026-01", "2025-12"]

    def test_formato_a_due_cifre(self):
        assert mesi_badge("2026-10") == ["2026-10", "2026-09"]


class TestContaSopraSoglia:
    def test_conta_solo_i_mesi_richiesti(self):
        righe = [
            {"ristorante_id": "a", "mese": "2026-08", "sopra_soglia": True},
            {"ristorante_id": "b", "mese": "2026-07", "sopra_soglia": True},
            {"ristorante_id": "c", "mese": "2026-07", "sopra_soglia": True},
        ]
        assert conta_sopra_soglia(righe, ["2026-08"]) == 1
        assert conta_sopra_soglia(righe, ["2026-07"]) == 2
        assert conta_sopra_soglia(righe, ["2026-08", "2026-07"]) == 3

    def test_stessa_sede_su_due_mesi_conta_una_volta(self):
        # Il badge conta SEDI da controllare, non mesi sforati.
        righe = [
            {"ristorante_id": "a", "mese": "2026-08", "sopra_soglia": True},
            {"ristorante_id": "a", "mese": "2026-07", "sopra_soglia": True},
        ]
        assert conta_sopra_soglia(righe, ["2026-08", "2026-07"]) == 1

    def test_zero_quando_nessuno_sfora(self):
        righe = [{"ristorante_id": "a", "mese": "2026-08", "sopra_soglia": False}]
        assert conta_sopra_soglia(righe, ["2026-08"]) == 0

    def test_sforamento_del_mese_chiuso_resta_visibile(self):
        # Il 1/9/2026 il mese corrente era vuoto e LAND aveva chiuso agosto a
        # 214/200: guardando solo il mese corrente il badge direbbe 0 e lo
        # sforamento non verrebbe mai visto.
        righe = [{"ristorante_id": "land", "mese": "2026-08", "sopra_soglia": True}]

        assert conta_sopra_soglia(righe, ["2026-09"]) == 0
        assert conta_sopra_soglia(righe, mesi_badge("2026-09")) == 1

    def test_badge_coincide_con_le_righe_rosse_della_tabella(self):
        # Il vincolo che tiene allineati badge e pagina: stesso input, stesso conto.
        consumi = [
            {"ristorante_id": "r1", "mese": "2026-08", "manuali": 214, "sdi": 0, "tot": 214},
            {"ristorante_id": "r2", "mese": "2026-08", "manuali": 151, "sdi": 0, "tot": 151},
        ]
        sedi = [_sede("r1", "LAND", piano="pro"), _sede("r2", "VILLA GUARDIA", piano="pro")]

        righe = costruisci_righe(consumi, [], sedi)
        rosse = [r for r in righe if r["sopra_soglia"] and r["mese"] == "2026-08"]

        assert conta_sopra_soglia(righe, ["2026-08"]) == len(rosse) == 1
