"""Presidio sulla GIUNZIONE fra i moduli puri di export e i componenti React.

Perche' esiste. I moduli `lib/*-export.ts` sono coperti da test che eseguono il
TypeScript vero, ma la riga che li **collega** al componente vive in un `.tsx`,
dove nessun runner arriva (`apps/web/` non ne ha uno per scelta:
`deploy-vercel.yml` scatta su `apps/web/**`). Quella riga e' la gamba scoperta
di ogni fix a piu' pezzi:

- 21/09/2026: la querystring dell'export Articoli senza il filtro "Nuovi
  caricati" — rimuoverla passava 492 test verdi.
- 22/09/2026: l'export della pivot che leggeva le righe non ordinate invece di
  quelle mostrate — rimettendo il difetto, 223 test restavano verdi.

Cosa misura e cosa no. Questi assert guardano il SORGENTE, non il
comportamento: provano che la giunzione sia scritta, non che funzioni. E' un
presidio di seconda scelta, accettato qui perche' l'alternativa e' nessun
presidio. Per non ricadere nei difetti noti dei test sul sorgente:

- si normalizzano gli spazi e si esclude cio' che sta dentro un commento, cosi'
  il bug scritto in un commento non passa per codice;
- si asserisce la RELAZIONE fra due punti del file (la stessa espressione
  alimenta tabella ed export), non la presenza di un letterale, che una
  rinomina innocua farebbe fallire a vuoto.
"""
import re
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
WEB = RADICE / "apps/web/src/app/(app)"


def _sorgente_senza_commenti(percorso: Path) -> str:
    """Il file con i commenti tolti e gli spazi normalizzati.

    Senza questo, un assert su una stringa passa anche quando la stringa sta in
    un commento che descrive il bug invece che nel codice che lo evita.
    """
    testo = percorso.read_text(encoding="utf-8")
    testo = re.sub(r"/\*.*?\*/", " ", testo, flags=re.S)
    testo = re.sub(r"(?m)^\s*//.*$", " ", testo)
    testo = re.sub(r"\s+", " ", testo)
    return testo


def _righe_di_codice(percorso: Path) -> list[str]:
    fuori = []
    dentro_blocco = False
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        spoglia = riga.strip()
        if dentro_blocco:
            if "*/" in spoglia:
                dentro_blocco = False
            continue
        if spoglia.startswith("/*"):
            dentro_blocco = "*/" not in spoglia
            continue
        if spoglia.startswith("//"):
            continue
        fuori.append(riga)
    return fuori


# ─── Pivot di Analisi Fatture: export e tabella ordinano uguale ─────────────

PIVOT = WEB / "analisi-fatture/pivot-tab.tsx"


def test_pivot_file_esiste():
    """Se il file viene rinominato questi assert diventerebbero vacui."""
    assert PIVOT.is_file(), PIVOT


def test_pivot_export_e_tabella_leggono_la_stessa_espressione():
    """Il difetto del 22/09/2026: la tabella mostrava le righe ordinate e
    l'export scriveva `pivot.rows` grezzo, cosi' il file usciva in un ordine
    diverso da quello a schermo.

    L'assert e' sulla relazione: qualunque sia il nome, la sorgente delle righe
    dell'export deve essere la stessa che alimenta il `.map` della tabella.
    """
    righe = _righe_di_codice(PIVOT)
    sorgenti_export = [
        m.group(1)
        for r in righe
        if (m := re.search(r"const dataRows = ([A-Za-z_$][\w.$]*)\.map\(", r))
    ]
    assert len(sorgenti_export) == 1, f"attesa una sola riga dataRows, trovate {sorgenti_export}"

    corpo = " ".join(righe)
    sorgenti_tabella = set(re.findall(r"\{([A-Za-z_$][\w.$]*)\.map\(\(row\)", corpo))
    assert sorgenti_tabella, "non trovo il .map che stampa le righe della tabella"

    assert sorgenti_export[0] in sorgenti_tabella, (
        f"l'export legge `{sorgenti_export[0]}` ma la tabella stampa "
        f"{sorgenti_tabella}: il file uscirebbe in un ordine diverso da quello "
        "che il cliente vede"
    )


def test_pivot_ordinamento_viene_dal_modulo_presidiato():
    """L'ordinamento della tabella deve restare in `lib/pivot-ordinamento`, dove
    i test lo eseguono davvero. Reintrodurne una copia nel componente lo
    riporterebbe fuori dalla rete.

    Il divieto e' mirato: `sortRowsForPills` ordina alfabeticamente le pill del
    grafico di confronto e usa legittimamente `localeCompare` senza avere nulla
    a che fare con l'ordine delle righe. Un assert su tutto il file lo
    vieterebbe a torto — e un presidio che grida su codice sano viene disattivato.
    """
    testo = _sorgente_senza_commenti(PIVOT)
    assert "ordinaRighePivot" in testo
    assert '@/lib/pivot-ordinamento' in testo
    assert "sortRowsForPills" in testo, (
        "la funzione e' stata rinominata: l'esclusione qui sotto non la copre piu'"
    )

    corpo = " ".join(_righe_di_codice(PIVOT))
    inizio = corpo.find("function sortRowsForPills")
    fine = corpo.find("function TrendChart")
    assert inizio != -1 and fine > inizio, "non riesco a isolare sortRowsForPills"
    fuori_dalle_pill = corpo[:inizio] + corpo[fine:]
    assert "localeCompare" not in fuori_dalle_pill, (
        "il confronto e' tornato nel componente fuori da sortRowsForPills: se "
        "esiste una seconda copia dell'ordinamento delle righe, schermo ed "
        "export possono divergere di nuovo"
    )


# ─── Spese: la guardia e le righe guardano lo stesso elenco ────────────────

SPESE = WEB / "workspace/spese-view.tsx"


def test_spese_file_esiste():
    assert SPESE.is_file(), SPESE


def test_spese_export_usa_il_modulo_presidiato():
    testo = _sorgente_senza_commenti(SPESE)
    assert '@/lib/spese-export' in testo
    for nome in ("csvSpese", "puoEsportareSpese", "nomeFileSpese"):
        assert nome in testo, f"{nome} non e' piu' usato dal componente"


def test_spese_guardia_e_contenuto_guardano_lo_stesso_elenco():
    """Il difetto del 22/09/2026: la guardia controllava `risposta.voci` (il
    mese intero) e il file scriveva `voci` (il mese filtrato). Con un filtro
    che non seleziona nulla usciva un CSV senza righe con i totali del mese
    intero in fondo.

    Qui si asserisce che i due punti nominino la stessa variabile.
    """
    corpo = " ".join(_righe_di_codice(SPESE))
    guardia = re.search(r"puoEsportareSpese\(\s*([A-Za-z_$][\w.$]*)\s*\)", corpo)
    contenuto = re.search(r"csvSpese\(\s*([A-Za-z_$][\w.$]*)\s*,", corpo)
    assert guardia, "non trovo la chiamata a puoEsportareSpese"
    assert contenuto, "non trovo la chiamata a csvSpese"
    assert guardia.group(1) == contenuto.group(1), (
        f"la guardia guarda `{guardia.group(1)}` ma il file scrive "
        f"`{contenuto.group(1)}`: e' esattamente il difetto del 22/09/2026"
    )


def test_spese_totali_non_arrivano_piu_dalla_risposta_del_server():
    """I totali si ricalcolano sulle voci esportate. Rileggerli da `risposta`
    farebbe tornare il numero del mese intero in fondo a un file filtrato."""
    corpo = " ".join(_righe_di_codice(SPESE))
    inizio = corpo.find("function esportaCSV()")
    assert inizio != -1, "esportaCSV non trovata"
    funzione = corpo[inizio:inizio + 800]
    assert "totale_fb" not in funzione, (
        "l'export legge di nuovo il totale dal server invece di sommare le "
        "righe che scrive"
    )


@pytest.mark.parametrize("percorso", [PIVOT, SPESE])
def test_nessun_export_ricostruisce_il_csv_a_mano(percorso):
    """Una seconda copia della formattazione dentro il componente e' il modo in
    cui questi difetti sono nati: il modulo resta corretto e il file no."""
    testo = _sorgente_senza_commenti(percorso)
    assert 'replace(/"/g' not in testo, (
        "la quotatura CSV e' tornata nel componente: deve stare in "
        "lib/spese-export.ts, dove i test la eseguono"
    )
