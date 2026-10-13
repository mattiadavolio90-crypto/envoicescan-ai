"""Lista clienti e scheda cliente dell'admin (riordino del 13/10/2026): filtri,
ordine, «da quanti giorni» e tab dall'URL."""
from __future__ import annotations

from tests.helpers_ts import esegui_ts

MODULO = "lib/admin-clienti"
FUNZIONI = ["voceAttiva", "giorniDa", "testoGiorni", "eFermo", "contaFiltri", "clientiVisibili", "tabDaUrl", "eliminazioneConfermata"]

# 13/10/2026 12:00 UTC
ADESSO = 1791892800000
GIORNO = 86_400_000


def _iso(giorni_fa: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp((ADESSO - giorni_fa * GIORNO) / 1000, tz=timezone.utc).isoformat()


def _c(nome, *, attivo=True, giorni=1.0, trial=False, piva=None, gruppo=None, problemi=0):
    return {
        "n_problemi": problemi,
        "email": f"{nome.lower()}@x.it", "nome_ristorante": nome, "nome_gruppo": gruppo,
        "partita_iva": None, "attivo": attivo, "trial": {"active": True} if trial else None,
        "ultimo_caricamento_at": None if giorni is None else _iso(giorni),
        "sedi": [{"partita_iva": piva}],
    }


def _f(espressione, arg):
    return esegui_ts(MODULO, f"emit({espressione});", argomento=arg, richiede=FUNZIONI)


def _nomi(clienti, cerca="", filtro="tutti"):
    out = _f(f"m.clientiVisibili(input.c, input.q, input.f, {ADESSO})",
             {"c": clienti, "q": cerca, "f": filtro})
    return [c["nome_ristorante"] for c in out]


def test_giorni_e_testo():
    assert _f(f"m.giorniDa(input, {ADESSO})", _iso(6.9)) == 6
    assert _f(f"m.giorniDa(input, {ADESSO})", None) is None
    assert _f(f"m.giorniDa(input, {ADESSO})", "non-una-data") is None
    assert _f(f"m.testoGiorni(input, {ADESSO})", _iso(0.2)) == "Oggi"
    assert _f(f"m.testoGiorni(input, {ADESSO})", _iso(1.5)) == "Ieri"
    assert _f(f"m.testoGiorni(input, {ADESSO})", _iso(12)) == "12 giorni fa"
    assert _f(f"m.testoGiorni(input, {ADESSO})", None) == "Mai"


def test_fermo_dal_settimo_giorno_e_mai_caricato_conta_come_fermo():
    assert _f(f"m.eFermo(input, {ADESSO})", _c("A", giorni=6.9)) is False
    assert _f(f"m.eFermo(input, {ADESSO})", _c("A", giorni=7)) is True
    assert _f(f"m.eFermo(input, {ADESSO})", _c("A", giorni=None)) is True


def test_un_account_disattivo_non_e_fermo():
    assert _f(f"m.eFermo(input, {ADESSO})", _c("A", attivo=False, giorni=30)) is False


def test_ordine_fermi_in_cima_dal_piu_vecchio_poi_attivi_per_nome_poi_disattivi():
    clienti = [
        _c("Zeta", giorni=1), _c("Spento", attivo=False, giorni=90), _c("Alfa", giorni=2),
        _c("Fermo10", giorni=10), _c("Mai", giorni=None), _c("Fermo8", giorni=8),
    ]
    assert _nomi(clienti) == ["Mai", "Fermo10", "Fermo8", "Alfa", "Zeta", "Spento"]


def test_chi_ha_problemi_aperti_sta_in_cima_i_piu_numerosi_prima():
    clienti = [
        _c("Fermo", giorni=20), _c("Uno", problemi=1), _c("Tre", problemi=3, giorni=30),
        _c("Sano"), _c("SpentoConProblemi", attivo=False, problemi=5),
    ]
    assert _nomi(clienti) == ["Tre", "Uno", "Fermo", "Sano", "SpentoConProblemi"]
    assert _nomi(clienti, filtro="problemi") == ["Tre", "Uno", "SpentoConProblemi"]


def test_filtri_e_conteggi():
    clienti = [_c("A", giorni=1), _c("B", giorni=9), _c("C", attivo=False), _c("D", giorni=1, trial=True)]
    assert _nomi(clienti, filtro="fermi") == ["B"]
    assert _nomi(clienti, filtro="trial") == ["D"]
    assert _nomi(clienti, filtro="disattivi") == ["C"]
    assert _f(f"m.contaFiltri(input, {ADESSO})", clienti) == {"tutti": 4, "problemi": 0, "fermi": 1, "trial": 1, "disattivi": 1}


def test_ricerca_su_nome_gruppo_email_e_piva_delle_sedi():
    clienti = [_c("Trattoria", piva="01234567890"), _c("Pizzeria", gruppo="SUSHILAND")]
    assert _nomi(clienti, cerca="sushi") == ["Pizzeria"]
    assert _nomi(clienti, cerca="0123456") == ["Trattoria"]
    assert _nomi(clienti, cerca="PIZZERIA@") == ["Pizzeria"]


def test_tab_dall_url():
    assert _f("m.tabDaUrl(input)", "sedi") == "sedi"
    assert _f("m.tabDaUrl(input)", "invii") == "invii"
    assert _f("m.tabDaUrl(input)", "inesistente") == "panoramica"
    assert _f("m.tabDaUrl(input)", None) == "panoramica"


def test_voce_di_menu_attiva():
    casi = [
        ("/admin", "/admin", True), ("/admin/", "/admin", True), ("/admin/clienti", "/admin", False),
        ("/admin/clienti", "/admin/clienti", True), ("/admin/clienti/abc", "/admin/clienti", True),
        ("/admin/clientixyz", "/admin/clienti", False), ("/admin/categorie", "/admin/clienti", False),
    ]
    for pathname, href, atteso in casi:
        assert _f("m.voceAttiva(input[0], input[1])", [pathname, href]) is atteso, (pathname, href)


def test_l_eliminazione_si_sblocca_solo_con_l_email_esatta():
    def ok(scritta, email="Mario@Trattoria.it"):
        return _f("m.eliminazioneConfermata(input[0], input[1])", [scritta, email])
    assert ok(" mario@trattoria.it ") is True
    assert ok("mario@trattoria") is False
    assert ok("") is False
    assert ok("", "") is False
