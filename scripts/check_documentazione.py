#!/usr/bin/env python3
"""
scripts/check_documentazione.py — Trova documentazione candidata a pulizia.

Non elimina né archivia nulla: segnala. La decisione (elimina / archivia in
docs/storico/ / lascia) resta a chi legge l'output, perché solo chi conosce
il contenuto sa se un piano "chiuso" ha ancora valore predittivo (regola in
docs/storico/README.md) — questo script non lo può giudicare da solo.

Cerca sei cose:
1. Documenti fuori da docs/storico/ con marcatori di chiusura
   (CHIUSO/DEPLOYATO/COMPLETATO/SUPERATO) — candidati a eliminazione o
   archiviazione.
2. Link markdown [testo](file.md) rotti in TUTTI i .md del repo (non solo
   DOC_VIVI: quello lo fa già tests/test_documentazione_onesta.py).
3. File in docs/piani/ — dovrebbero esistere solo per lavoro davvero in
   corso (sono git-ignorati apposta, vedi docs/piani/README.md).
4. Documenti "vivi" (elencati nell'indice di DOCUMENTAZIONE/MAPPA_TECNICA.md)
   che l'indice stesso NON menziona più — segnale di indice andato fuori sync.
5. Cifre ri-misurabili dichiarate in CLAUDE.md/README.md che non corrispondono
   piu' alla realta' (test, righe di un file, migration, route). Aggiunto il
   2/9/2026: quel giorno lo script dava verde su 10 numeri sbagliati, di cui 4
   in CLAUDE.md — che entra in OGNI sessione, quindi li propagava ovunque.
6. Stato del ciclo di audit indietro rispetto ai propri verbali: se lo
   _STORICO.md cita date piu' recenti di quelle del file di stato, il file che
   deve dire "cosa manca" non le conosce. E' il difetto che ha reso necessario
   il riordino del 2/9: 10 verbali nello storico, 4 riflessi nello stato.

Uso:
    python scripts/check_documentazione.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

ESCLUDI_DIR = {".venv", "node_modules", ".git", ".next", "__pycache__", ".claude"}

MARCATORI_CHIUSURA = re.compile(
    r"✅\s*\**\s*(?:CHIUSO|DEPLOYAT[OA]|COMPLETAT[OA]|VERIFICAT[OA]|SUPERAT[OA])"
    r"|^>\s*\**\s*(?:CHIUSO|DEPLOYAT[OA]|COMPLETAT[OA]|SUPERAT[OA])\b",
    re.IGNORECASE | re.MULTILINE,
)

# Un documento di STATO elenca per mestiere cio' che e' chiuso: le sue righe
# "✅ chiusa" sono il suo contenuto, non un marcatore che si dichiara finito.
# Senza questa esclusione il file di stato del ciclo vivo veniva segnalato a
# ogni giro come "da archiviare" (2/9/2026) — e un allarme che suona sempre
# viene saltato per riflesso invece che letto.
STATO_CICLO = re.compile(r"AUDIT_ONEFLUX_STATO_\d{4}-\d{2}(?:-\d{2})?\.md$")

_LINK_MD = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)[^)]*\)")

# I percorsi scritti fra BACKTICK, non come link markdown. Sono il modo in cui
# l'indice di MAPPA_TECNICA §6 elenca i documenti — cioe' proprio il file che
# per mestiere non fa altro che nominare percorsi era l'unico che _LINK_MD non
# guardava. Il 26/09/2026 ci sono stati trovati 3 riferimenti rotti, fra cui un
# `PIANO_WEB_MARKETING.md` cancellato mesi prima e ancora descritto come "vivo".
_PATH_BACKTICK = re.compile(r"`([^`\n]+\.md)`")

# Un allarme che suona a vuoto viene disattivato mentalmente al terzo giro (e'
# la ragione per cui altrove qui si copre meno pur di non mentire mai). Questi
# non sono riferimenti a un file: sono forme con un segnaposto dentro.
_SEGNAPOSTO = re.compile(r"[<>*?]|\{|\}")


# Un documento vivo puo' nominare legittimamente un file che NON esiste piu':
# sta raccontando di averlo eliminato, rinominato o sostituito. E' il caso di
# "`X.md` eliminato alla Chiusura", "era una copia rimossa", "rinominato X -> Y".
# Senza questa distinzione restavano 10 segnalazioni di cui 8 di questo tipo.
_PASSATO = re.compile(
    r"\b(elimin|rimoss|rimuov|cancell|rinominat|sostituit|superat|spostat|"
    r"archiviat|era una|non esiste|stava in|assorbit)",
    re.IGNORECASE,
)


def _riga_di(testo: str, pos: int) -> str:
    inizio = testo.rfind("\n", 0, pos) + 1
    fine = testo.find("\n", pos)
    return testo[inizio:fine if fine != -1 else len(testo)]


def _e_riga_di_tabella(riga: str) -> bool:
    """Una riga di tabella markdown: `| percorso | a cosa serve |`.

    E' la forma dell'INDICE, e un indice non racconta: promette che il documento
    esiste. Quindi li' l'esenzione della narrazione non vale.
    """
    return riga.lstrip().startswith("|") and riga.count("|") >= 3


def _e_narrazione_al_passato(riga: str) -> bool:
    """La riga racconta che quel file e' stato tolto, invece di rimandarci.

    NON si applica dentro una riga di tabella. Provato il 26/9/2026 (rilievo del
    code-reviewer): la voce d'indice «| `DOCUMENTAZIONE/GUIDA_MARGINI.md` | Come
    si e' **spostata** la logica dei margini: guida viva |» — percorso
    inesistente — usciva pulita, e cambiando la sola parola in «calcola» il
    controllo tornava rosso: a silenziare era una parola di passaggio, non il
    senso della frase. Su celle lunghe pescare una delle 13 radici e' facile.

    Restringere a una finestra di caratteri attorno al backtick e' stato provato
    e **scartato**: misurando, la narrazione genuina sta fino a 50 caratteri dal
    riferimento e il falso negativo a 46 — la distanza non separa i due casi. La
    forma della riga si': dei 7 riferimenti oggi silenziati nei doc vivi, 7 su 7
    sono prosa e 0 sono righe di tabella.
    """
    if _e_riga_di_tabella(riga):
        return False
    return bool(_PASSATO.search(riga))


def _e_vivo(p: Path) -> bool:
    """Un documento e' vivo se non e' una fotografia archiviata.

    docs/storico/ contiene per definizione "fotografie datate di problemi
    chiusi" (la stessa esclusione che fa DOC_VIVI in test_documentazione_onesta).
    """
    rel = p.relative_to(ROOT).as_posix()
    return not rel.startswith("docs/storico/")


def _risolvi_nome_nudo(nome: str, md_files: list[Path]) -> Path | None:
    """Un nome citato senza percorso e' valido se il repo ha UN solo file cosi'.

    L'indice scrive a volte `README.md` o `WORKFLOW.md` senza cartella. Se il
    nome e' ambiguo (piu' file lo portano) non si decide: non e' un link rotto,
    e' una citazione generica.
    """
    candidati = [p for p in md_files if p.name == nome]
    return candidati[0] if len(candidati) == 1 else None


def _tutti_i_md() -> list[Path]:
    """I .md del repo, saltando le cartelle escluse SENZA discenderle.

    rglob("*.md") + filtro a posteriori attraversava comunque .venv e
    node_modules: 116 secondi per trovare 53 file (misurato il 2/9/2026). Uno
    script di controllo che costa due minuti viene lanciato meno, ed e' il
    motivo per cui i suoi allarmi arrivavano tardi. Ora e' una discesa
    esplicita che pota i rami: ~0,1s, stesso risultato.
    """
    out: list[Path] = []

    def scendi(d: Path) -> None:
        try:
            voci = list(d.iterdir())
        except OSError:
            return
        for v in voci:
            if v.is_dir():
                if v.name not in ESCLUDI_DIR:
                    scendi(v)
            elif v.suffix == ".md":
                out.append(v)

    scendi(ROOT)
    return out


def _leggi(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def check_marcatori_chiusura(md_files: list[Path]) -> list[str]:
    problemi = []
    for p in md_files:
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("docs/storico/"):
            continue  # lì i marcatori di chiusura sono attesi, è l'archivio
        if STATO_CICLO.search(rel):
            continue  # è un indice di stato: elencare cosa è chiuso è il suo lavoro
        testo = _leggi(p)
        if MARCATORI_CHIUSURA.search(testo):
            problemi.append(rel)
    return problemi


def check_link_rotti(md_files: list[Path]) -> list[tuple[str, str]]:
    problemi = []
    for p in md_files:
        testo = _leggi(p)
        for match in _LINK_MD.finditer(testo):
            target = match.group(1)
            if target.startswith(("http://", "https://")):
                continue
            if not (p.parent / target).resolve().exists():
                problemi.append((p.relative_to(ROOT).as_posix(), target))
    return problemi


def check_percorsi_backtick(md_files: list[Path]) -> list[tuple[str, str]]:
    """I percorsi .md fra backtick dei documenti VIVI esistono davvero?

    Complementare a check_link_rotti, che vede solo la sintassi markdown: l'indice
    di MAPPA_TECNICA §6 elenca i documenti fra backtick, quindi proprio il file
    che per mestiere non fa altro che nominare percorsi non era controllato da
    nessuno. Il 26/09/2026 ci sono stati trovati 3 riferimenti rotti, fra cui un
    `PIANO_WEB_MARKETING.md` cancellato mesi prima e ancora descritto come "vivo".

    **Solo i documenti vivi.** Un file sotto docs/storico/ e' una fotografia
    datata: nominare un documento poi cancellato e' il suo mestiere, non un
    difetto — docs/storico/README.md, per dirne uno, elenca apposta i file che
    ha rimosso. Provato senza questa distinzione: 45 segnalazioni di cui ~3
    vere. Un allarme che suona a vuoto viene disattivato mentalmente al terzo
    giro, ed e' la ragione per cui altrove qui si copre meno pur di non mentire.
    """
    problemi: list[tuple[str, str]] = []
    for p in md_files:
        if not _e_vivo(p):
            continue
        testo = _leggi(p)
        for match in _PATH_BACKTICK.finditer(testo):
            target = match.group(1).strip()
            if _SEGNAPOSTO.search(target) or target.startswith(("http://", "https://", "~")):
                continue
            # Abbreviazioni come `..._STORICO.md`: citano un file per suffisso,
            # non per percorso.
            if target.startswith(".."):
                continue
            # `_STORICO.md`: un suffisso generico usato in prosa per indicare la
            # famiglia dei file, non un percorso ("il `_STORICO.md` raccoglie i
            # verbali"). Un nome che comincia con "_" e non ha cartella non e'
            # un riferimento risolvibile.
            if "/" not in target and target.startswith("_"):
                continue
            if (ROOT / target).exists() or (p.parent / target).exists():
                continue
            if "/" not in target and _risolvi_nome_nudo(target, md_files):
                continue
            if _e_narrazione_al_passato(_riga_di(testo, match.start())):
                continue
            voce = (p.relative_to(ROOT).as_posix(), target)
            if voce not in problemi:
                problemi.append(voce)
    return problemi


def check_piani_orfani() -> list[str]:
    piani_dir = ROOT / "docs" / "piani"
    if not piani_dir.exists():
        return []
    # TUTTI i .md, non solo PIANO_*: il 2/9/2026 un PROMPT_PROSSIMA_SESSIONE.md
    # stantio e' rimasto qui invisibile a questo check (diceva "Fase 3 da fare"
    # di una fase deployata, e "51 commit in coda" quando erano 7) finche' una
    # sessione non ha ereditato da lui una cifra falsa. Il nome del file non e'
    # una garanzia: conta la cartella. README.md e' la documentazione della
    # cartella stessa, non un piano.
    return [
        p.relative_to(ROOT).as_posix()
        for p in sorted(piani_dir.glob("*.md"))
        if p.name != "README.md"
    ]


def check_indice_fuori_sync(md_files: list[Path]) -> list[str]:
    mappa = ROOT / "DOCUMENTAZIONE" / "MAPPA_TECNICA.md"
    if not mappa.exists():
        return []
    testo_mappa = _leggi(mappa)

    # Cartelle "vive" indicizzate esplicitamente: root, DOCUMENTAZIONE/,
    # DOCUMENTAZIONE/tecnica/, docs/ (non ricorsivo in docs/storico|piani,
    # che hanno le proprie regole/README dedicate).
    candidati = []
    for p in md_files:
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("docs/storico/", "docs/piani/", ".claude/")):
            continue
        if "/" in rel and not rel.startswith(("DOCUMENTAZIONE/", "docs/")):
            continue  # es. apps/web/README.md: indicizzato a parte, non qui
        candidati.append((rel, p.name))

    fuori_sync = []
    for rel, nome in candidati:
        if nome not in testo_mappa and rel not in testo_mappa:
            fuori_sync.append(rel)
    return fuori_sync


def _conta_righe(rel: str) -> int | None:
    f = ROOT / rel
    if not f.exists():
        return None
    try:
        return len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
    except OSError:
        return None


def check_cifre_dichiarate() -> list[str]:
    """Le cifre ri-misurabili scritte nei doc sempre-in-contesto sono ancora vere?

    Solo cifre che un comando puo' ricalcolare adesso. Niente stime, niente
    percentuali di copertura: quelle richiedono giudizio e stanno in
    AUDIT_COPERTURA.md, che questo script non sa (ne' deve) verificare.

    Tolleranza: le righe di un file crescono di continuo perche' piu' sessioni
    committano in parallelo. Si segnala solo uno scarto che nessuno spiegherebbe
    con il lavoro di una giornata (>5%), non la divergenza di poche righe.
    """
    problemi: list[str] = []

    attese: list[tuple[str, str, int | None, float]] = []

    righe_worker = _conta_righe("services/fastapi_worker.py")
    if righe_worker:
        attese.append(("CLAUDE.md", r"fastapi_worker\.py`?\s*\((\d[\d.]*) righe\)",
                       righe_worker, 0.05))

    mig = ROOT / "supabase" / "migrations"
    if mig.exists():
        attese.append(("CLAUDE.md", r"canonico,\s*(\d[\d.]*) file",
                       len(list(mig.glob("*.sql"))), 0.05))

    api = ROOT / "apps" / "web" / "src" / "app" / "api"
    if api.exists():
        attese.append(("CLAUDE.md", r"(\d[\d.]*) route API",
                       len(list(api.rglob("route.ts"))), 0.05))

    for doc, pattern, reale, tolleranza in attese:
        if reale is None:
            continue
        testo = _leggi(ROOT / doc)
        m = re.search(pattern, testo)
        if not m:
            continue
        try:
            dichiarato = int(m.group(1).replace(".", "").replace(",", ""))
        except ValueError:
            continue
        if dichiarato == 0:
            continue
        scarto = abs(dichiarato - reale) / reale
        if scarto > tolleranza:
            problemi.append(
                f"{doc}: dichiara {dichiarato:,}".replace(",", ".")
                + f", misurato ora {reale:,}".replace(",", ".")
                + f" (scarto {scarto:.0%}) — pattern: {pattern[:38]}"
            )
    return problemi


# Solo la forma ESTESA ("2/9/2026"). La forma corta "02/09" e' stata provata e
# scartata il 2/9/2026: in questi verbali "N/N" significa quasi sempre un
# rapporto, non una data — `mobile-catena.tsx:7-12` diventava il 7 dicembre e
# "9/9" (nove mutanti su nove) il 9 settembre. Due falsi allarmi in due prove.
# Un controllo che suona a vuoto viene disattivato mentalmente al terzo giro:
# meglio coprire meno e non mentire mai.
_DATA_ESTESA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d\d)\b")


def check_stato_ciclo_indietro() -> list[str]:
    """Il file di stato conosce le sessioni che il suo storico ha verbalizzato?

    Il difetto che ha reso necessario il riordino del 2/9/2026: lo storico aveva
    10 verbali, il file di stato ne rifletteva 4. Chi apriva lo stato per sapere
    "cosa manca" leggeva una roadmap ferma a tre giorni prima, e nessun controllo
    lo vedeva.

    Confronta le date in forma estesa dei due file. Copre poco per scelta (vedi
    il commento su _DATA_ESTESA), ma quando parla ha ragione.
    """
    problemi: list[str] = []
    doc_dir = ROOT / "DOCUMENTAZIONE"
    if not doc_dir.exists():
        return problemi

    def _date(p: Path) -> set[tuple[int, int, int]]:
        out: set[tuple[int, int, int]] = set()
        for g, m, a in _DATA_ESTESA.findall(_leggi(p)):
            gi, mi, ai = int(g), int(m), int(a)
            if 1 <= mi <= 12 and 1 <= gi <= 31:
                out.add((ai, mi, gi))
        return out

    for storico in sorted(doc_dir.glob("AUDIT_ONEFLUX_STATO_*_STORICO.md")):
        stato = storico.with_name(storico.name.replace("_STORICO.md", ".md"))
        if not stato.exists():
            continue
        d_storico, d_stato = _date(storico), _date(stato)
        if not d_storico or not d_stato:
            continue
        if max(d_storico) > max(d_stato):
            a, m, g = max(d_storico)
            ay, my, gy = max(d_stato)
            problemi.append(
                f"{stato.relative_to(ROOT).as_posix()}: lo storico verbalizza fino al "
                f"{g:02d}/{m:02d}/{a}, lo stato si ferma al {gy:02d}/{my:02d}/{ay} "
                f"-> aggiorna 'cosa manca', non solo il verbale"
            )
    return problemi


def main() -> int:
    md_files = _tutti_i_md()

    chiusi = check_marcatori_chiusura(md_files)
    link_rotti = check_link_rotti(md_files)
    backtick_rotti = check_percorsi_backtick(md_files)
    piani = check_piani_orfani()
    fuori_sync = check_indice_fuori_sync(md_files)
    cifre = check_cifre_dichiarate()
    stato_indietro = check_stato_ciclo_indietro()

    ha_problemi = False

    if chiusi:
        ha_problemi = True
        print(f"\n[MARCATORI DI CHIUSURA] {len(chiusi)} documento/i fuori da docs/storico/ si dichiarano chiusi:")
        for f in chiusi:
            print(f"  - {f}")
        print("  -> Se il contenuto e' gia' in memoria/git history: elimina.")
        print("  -> Se ha valore predittivo futuro: sposta in docs/storico/ (vedi docs/storico/README.md).")

    if link_rotti:
        ha_problemi = True
        print(f"\n[LINK ROTTI] {len(link_rotti)} link puntano a file inesistenti:")
        for doc, target in link_rotti:
            print(f"  - {doc} -> {target}")

    if backtick_rotti:
        ha_problemi = True
        print(f"\n[PERCORSI INESISTENTI] {len(backtick_rotti)} percorso/i citato/i fra backtick non esiste:")
        for doc, target in backtick_rotti:
            print(f"  - {doc} -> {target}")
        print("  -> L'indice promette un documento che non c'e': correggi il percorso o togli la riga.")

    if piani:
        print(f"\n[PIANI ATTIVI] {len(piani)} file in docs/piani/ (normale se lavoro in corso, verifica se orfani):")
        for f in piani:
            print(f"  - {f}")

    if fuori_sync:
        ha_problemi = True
        print(f"\n[INDICE FUORI SYNC] {len(fuori_sync)} documento/i non citati in DOCUMENTAZIONE/MAPPA_TECNICA.md §6:")
        for f in fuori_sync:
            print(f"  - {f}")
        print("  -> Aggiungi una riga all'indice, o e' un file che andrebbe eliminato.")

    if cifre:
        ha_problemi = True
        print(f"\n[CIFRE NON PIU' VERE] {len(cifre)} numero/i dichiarato/i diverge dalla misura:")
        for c in cifre:
            print(f"  - {c}")
        print("  -> Ri-misura e correggi. CLAUDE.md entra in ogni sessione: propaga i suoi errori.")

    if stato_indietro:
        ha_problemi = True
        print(f"\n[STATO INDIETRO] {len(stato_indietro)} ciclo/i ha verbali piu' recenti del proprio stato:")
        for c in stato_indietro:
            print(f"  - {c}")

    if not ha_problemi and not piani:
        print("Documentazione in ordine: nessun marcatore di chiusura fuori posto, nessun link rotto, indice allineato.")

    return 1 if ha_problemi else 0


if __name__ == "__main__":
    sys.exit(main())
