"""Le tessere KPI di Ricavi e Margini seguono il tab aperto.

Fino al 23/09/2026 le sei tessere restavano identiche passando da Marginalita' a
Coperti ad Analisi Avanzate: `KpiBar` e' reso in `margini/page.tsx` SOPRA il
TabsSwitcher e non riceveva il tab. In Coperti si leggeva «Scontrino medio 29 €»
con sopra «MOL 2.678.419 €».

Il rischio vero di questa modifica non e' la logica di selezione — e' che le
etichette in `lib/kpi-margini-tab.ts` e quelle in `margini/kpi-bar.tsx` sono due
liste di stringhe scritte a mano. Rinominare una card nel `.tsx` senza toccare il
`.ts` non rompe niente a compilazione e **fa sparire la tessera invece di
rinominarla**: e' `test_le_etichette_esistono_davvero_nel_componente` a fermarlo.
"""
import re
from pathlib import Path

import pytest

from tests.helpers_ts import esegui_ts

_MODULO = "lib/kpi-margini-tab"
_KPI_BAR = Path("apps/web/src/app/(app)/margini/kpi-bar.tsx")
_PAGE = Path("apps/web/src/app/(app)/margini/page.tsx")


def _per_tab(tab):
    return esegui_ts(
        _MODULO,
        "emit(m.kpiPerTab(...input));",
        argomento=[tab],
        richiede=["kpiPerTab"],
    )


def test_marginalita_scende_a_tre_tessere():
    """Le altre tre sono gia' nella colonna TOTALE della tabella, riga per riga."""
    assert _per_tab("calcolo") == ["Fatturato Netto", "Margine Lordo", "MOL"]


def test_coperti_non_mostra_il_mol():
    """Il difetto osservato: «MOL 2.678.419 €» sopra lo scontrino medio."""
    assert "MOL" not in _per_tab("coperti")


def test_analisi_avanzate_mostra_i_costi_che_ripartisce():
    scelte = _per_tab("analisi")
    assert "Costi F&B" in scelte
    assert "MOL" not in scelte


@pytest.mark.parametrize("tab", [None, "", "un-tab-che-non-esiste"])
def test_tab_sconosciuto_mostra_tutto(tab):
    """Degradare mostrando di piu', non una barra vuota.

    Un tab nuovo (o la demo, che non ne ha uno vero) deve vedere le sei tessere
    di sempre. Il ripiego opposto — lista vuota — toglierebbe i KPI da una pagina
    senza che nessun errore lo segnali.
    """
    assert len(_per_tab(tab)) == 6


def test_ogni_tab_mostra_almeno_una_tessera():
    """Nessun tab resta con la barra vuota: sarebbe uno spazio bianco inspiegato."""
    for tab in ("calcolo", "coperti", "analisi"):
        assert len(_per_tab(tab)) >= 1, tab


def test_nessun_tab_mostra_tessere_inventate():
    """Ogni etichetta per-tab deve stare fra le sei che il componente sa rendere."""
    tutte = set(_per_tab(None))
    for tab in ("calcolo", "coperti", "analisi"):
        assert set(_per_tab(tab)) <= tutte, tab


# ─────────── il legame col componente: qui casca la rinomina ────────────────

def _etichette_del_componente() -> list[str]:
    """Le `label:` delle CardDef in kpi-bar.tsx, nell'ordine in cui sono scritte."""
    src = _KPI_BAR.read_text(encoding="utf-8")
    inizio = src.index("const cards: CardDef[] = [")
    fine = src.index("];", inizio)
    return re.findall(r'label:\s*"([^"]+)"', src[inizio:fine])


def test_le_etichette_esistono_davvero_nel_componente():
    """`kpiPerTab` filtra per stringa: un'etichetta che non esiste = tessera persa.

    E' il difetto silenzioso di questa modifica. Rinominando «Margine Lordo» in
    kpi-bar.tsx senza aggiornare lib/kpi-margini-tab.ts, `mostrate` ne trova due
    invece di tre: nessun errore, nessun avviso, una tessera in meno a schermo.
    """
    del_componente = set(_etichette_del_componente())
    assert del_componente, "non ho trovato le CardDef in kpi-bar.tsx"
    for tab in ("calcolo", "coperti", "analisi", None):
        mancanti = set(_per_tab(tab)) - del_componente
        assert not mancanti, f"tab {tab}: etichette che il componente non rende: {mancanti}"


def test_kpi_tutte_elenca_esattamente_le_card_del_componente():
    """Le due liste devono restare la stessa cosa, non due cose simili."""
    assert _per_tab(None) == _etichette_del_componente()


def test_la_pagina_passa_il_tab_alla_barra():
    """Senza questa prop la selezione e' codice morto: sei tessere come prima.

    E' l'errore gia' fatto due volte in questa fase (blocchi B e C): la funzione
    giusta, provata in isolamento, che nessuno chiama.
    """
    src = _PAGE.read_text(encoding="utf-8")
    assert re.search(r"<KpiBar\b[^>]*\btab=\{tab\}", src), (
        "margini/page.tsx non passa piu' `tab` a <KpiBar>: le tessere tornano fisse"
    )


# ─────────── la selezione ESEGUITA, non descritta ───────────────────────────

def _seleziona(tab):
    """Le etichette che restano dopo il filtro, sulle sei card vere del componente.

    Fa girare `selezionaKpi`, cioe' la funzione che il componente chiama davvero.
    La prima stesura di questo file provava solo `kpiPerTab` (la LISTA): con la
    `.filter()` ancora dentro il .tsx, disattivarla lasciava verdi tutti e 12 i
    test — il mutante piu' importante, quello che ripristina esattamente il
    difetto, sopravviveva. Provare la lista non prova la selezione.
    """
    carte = [{"label": etichetta} for etichetta in _etichette_del_componente()]
    scelte = esegui_ts(
        _MODULO,
        "emit(m.selezionaKpi(...input).map((c) => c.label));",
        argomento=[carte, tab],
        richiede=["selezionaKpi"],
    )
    return scelte


def test_la_selezione_toglie_davvero_le_tessere():
    """Il difetto in una riga: su Marginalita' si passa da sei tessere a tre."""
    assert len(_seleziona("calcolo")) == 3
    assert len(_seleziona(None)) == 6


def test_la_selezione_non_mostra_il_mol_in_coperti():
    assert "MOL" not in _seleziona("coperti")


def test_la_selezione_tiene_l_ordine_delle_card():
    """Le tessere spariscono, non si riordinano: l'occhio le ritrova dov'erano.

    L'ordine e' quello di `cards` nel componente, non quello della lista per-tab.
    """
    ordine_componente = _etichette_del_componente()
    for tab in ("calcolo", "coperti", "analisi", None):
        scelte = _seleziona(tab)
        posizioni = [ordine_componente.index(e) for e in scelte]
        assert posizioni == sorted(posizioni), f"tab {tab}: tessere riordinate"


def _griglia(n):
    return esegui_ts(
        _MODULO,
        "emit(m.colonneGriglia(...input));",
        argomento=[n],
        richiede=["colonneGriglia"],
    )


@pytest.mark.parametrize("n,attesa", [
    (1, "grid-cols-1 md:grid-cols-1 lg:grid-cols-1"),
    (3, "grid-cols-1 md:grid-cols-3 lg:grid-cols-3"),
    (6, "grid-cols-2 md:grid-cols-3 lg:grid-cols-6"),
])
def test_la_griglia_segue_il_numero_di_tessere(n, attesa):
    """Con 3 tessere su una griglia da 6 restavano mezze vuote, a sinistra."""
    assert _griglia(n) == attesa


# 0 e 7 sono il RIPIEGO (fuori mappa): oggi irraggiungibili — il codice produce
# solo 1, 3 o 6 — ma e' la rete per una settima tessera aggiunta domani, ed e'
# esattamente li' che il difetto tornerebbe senza che nessuno se ne accorga.
# Senza questi due casi il mutante «ripiego senza base» sopravviveva.
@pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 5, 6, 7])
def test_la_griglia_dichiara_anche_la_base_non_solo_md_e_lg(n):
    """`md:` parte da 768px: sotto, senza una base, vale il default a 1 colonna.

    Il componente scriveva `grid-cols-2` fisso: con sei tessere andava sempre
    bene, ma da quando seguono il tab il caso n=1 (Coperti) rendeva UNA card a
    meta' larghezza con meta' riga vuota accanto. Trovato in revisione il
    23/09/2026. Il numero di tessere lo decide il tab, quindi la griglia deve
    seguirlo a OGNI larghezza, non solo da 768px in su.
    """
    classi = _griglia(n).split()
    base = [c for c in classi if not c.startswith(("md:", "lg:"))]
    assert base, f"n={n}: nessuna colonna dichiarata sotto i 768px ({classi})"


def test_una_sola_tessera_occupa_tutta_la_riga_anche_su_telefono():
    """Il caso concreto di Coperti: una card, nessun buco accanto."""
    assert "grid-cols-1" in _griglia(1).split()


def test_il_componente_non_scrive_una_base_fissa():
    """Una base fissa nel .tsx vincerebbe o competerebbe con quella della mappa."""
    righe = [
        r for r in _KPI_BAR.read_text(encoding="utf-8").splitlines()
        if not r.lstrip().startswith(("//", "*", "/*"))
    ]
    colpevoli = [
        r.strip() for r in righe
        if re.search(r"className=.*\bgrid\b.*\bgrid-cols-\d", r)
    ]
    assert not colpevoli, f"base di griglia fissa nel componente: {colpevoli}"


def test_le_liste_per_tab_sono_scritte_nell_ordine_delle_card():
    """Oggi filtrare o mappare da' lo stesso risultato: e' un caso, non una regola.

    Misurato il 23/09: sostituendo la `.filter()` con una `.map()` sulla lista
    per-tab, tutti e 19 i test restavano verdi — il mutante era REDUNDANTE (le
    tre liste sono gia' scritte nell'ordine di `cards`), non il test debole.
    Questo presidio inchioda quella coincidenza: scrivendo domani una lista in
    ordine diverso, le due implementazioni divergerebbero e l'ordine delle
    tessere dipenderebbe da un dettaglio che nessuno ha scelto.
    """
    ordine = _etichette_del_componente()
    for tab in ("calcolo", "coperti", "analisi"):
        lista = list(_per_tab(tab))
        posizioni = [ordine.index(e) for e in lista]
        assert posizioni == sorted(posizioni), (
            f"la lista di «{tab}» non segue l'ordine delle card: {lista}"
        )


def test_il_componente_usa_le_funzioni_della_lib():
    """Se il .tsx tornasse a filtrare per conto suo, i test sopra non lo vedrebbero."""
    src = _KPI_BAR.read_text(encoding="utf-8")
    assert "selezionaKpi(cards, tab)" in src, "kpi-bar.tsx non usa piu' selezionaKpi"
    assert "colonneGriglia(" in src, "kpi-bar.tsx non usa piu' colonneGriglia"


def test_le_colonne_della_griglia_sono_classi_intere():
    """Tailwind legge i sorgenti come TESTO: una classe interpolata non esiste.

    `lg:grid-cols-` seguito da un'interpolazione non finisce nel CSS generato e la
    griglia collassa a una colonna — senza errori, senza warning, solo le tessere
    in fila verticale.

    Le righe di COMMENTO sono escluse: la prima stesura di questo test falliva
    sulla riga che spiega il divieto citandolo: `grep` non distingue una regola
    dal codice che la viola (trappola gia' pagata due volte in questo progetto).
    """
    sorgenti = _KPI_BAR.read_text(encoding="utf-8") + Path(
        "apps/web/src/lib/kpi-margini-tab.ts"
    ).read_text(encoding="utf-8")
    righe = [
        r for r in sorgenti.splitlines()
        if not r.lstrip().startswith(("//", "*", "/*"))
    ]
    colpevoli = [r.strip() for r in righe if re.search(r"grid-cols-\$\{", r)]
    assert not colpevoli, f"classe grid-cols interpolata: {colpevoli}"


def test_il_punto_finale_della_sparkline_non_e_un_cerchio():
    """Con `preserveAspectRatio="none"` un <circle> esce come un'ellisse.

    La viewBox e' 100x24 su una card di ~200px: x viene stirato circa il doppio
    di y. Il primo tentativo usava `<circle ... vectorEffect="non-scaling-stroke">`
    credendo di rimediare, ma quella proprieta' agisce solo sullo STROKE e il
    punto ha solo il `fill`: era inerte, e il commento accanto dichiarava una
    protezione che il codice non dava — il difetto peggiore, perche' nessuno
    torna a guardare una cosa gia' dichiarata risolta (trovato in revisione il
    23/09/2026). Ora e' un <rect> con la larghezza divisa per la stessa scala.
    """
    # Finestra = TUTTO il file, non il solo corpo di `Sparkline`.
    #
    # La prima stesura partiva da `src.index("function Sparkline(")`, ma le
    # costanti del modulo stanno SOPRA la funzione: una costante di scala
    # ri-dichiarata li' — cioe' esattamente dove stava `ASPETTO` — passava
    # inosservata, e con essa il difetto vero (punto ovale a meta' larghezza).
    # Trovato dalla seconda revisione, 23/09/2026: il presidio scritto per
    # difendere la correzione non copriva il punto in cui il difetto era nato.
    #
    # Righe di commento escluse: senza, il test falliva sul commento che spiega
    # di NON usare <circle>.
    src = _KPI_BAR.read_text(encoding="utf-8")
    corpo = "\n".join(
        r for r in src.splitlines()
        if not r.lstrip().startswith(("//", "*", "/*"))
    )
    assert "<circle" not in corpo, (
        "il punto finale e' tornato un <circle>: con preserveAspectRatio='none' "
        "esce ovale"
    )
    assert "non-scaling-stroke" not in corpo, (
        "vectorEffect non ha effetto su una forma con il solo fill: e' una "
        "protezione dichiarata e inesistente"
    )
    # E ora il COMPORTAMENTO, non il nome di una costante.
    #
    # La stesura precedente asseriva `"ASPETTO" not in corpo`: difendeva una
    # PAROLA. Bastava chiamarla `SCALA_X` per rimettere il difetto — punto ovale
    # a meta' larghezza — con tutti i test verdi (mutante M15 della seconda
    # revisione, sopravvissuto). Quello che rende il punto tondo e' che le sue
    # due dimensioni siano la STESSA espressione: qualunque divisore su una
    # delle due lo deforma, comunque lo si chiami.
    larghezza = re.search(r"width:\s*([^,\n]+),", corpo)
    altezza = re.search(r"height:\s*([^,\n]+),", corpo)
    assert larghezza and altezza, "non trovo le dimensioni del punto finale"
    assert larghezza.group(1).strip() == altezza.group(1).strip(), (
        f"il punto non e' tondo: width={larghezza.group(1).strip()} "
        f"height={altezza.group(1).strip()} — con preserveAspectRatio='none' "
        "una dimensione scalata esce ovale, e il fattore dipende dalla "
        "larghezza della card, che cambia col tab"
    )
    # E che quella misura sia in PIXEL (un numero), non in unita' della viewBox.
    assert re.search(r"const PUNTO_PX\s*=\s*\d", corpo), (
        "il punto finale non e' piu' dimensionato in pixel"
    )
