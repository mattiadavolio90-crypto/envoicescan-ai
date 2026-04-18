"""Audit completo fatture + upload_events.

Esegue 7 check contro DB Supabase (paginazione in Python per aggirare
limiti del client REST) e stampa report tabellare.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Carica credenziali da .streamlit/secrets.toml verso env vars
try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

secrets_path = ROOT / ".streamlit" / "secrets.toml"
if secrets_path.exists():
    with open(secrets_path, "rb") as f:
        _secrets = tomllib.load(f)
    sb = _secrets.get("supabase", {})
    os.environ.setdefault("SUPABASE_URL", sb.get("url", ""))
    os.environ.setdefault(
        "SUPABASE_SERVICE_ROLE_KEY",
        sb.get("service_role_key") or sb.get("key", ""),
    )

from services import get_supabase_client  # noqa: E402

CATEGORIE_UFFICIALI = {
    "ACQUA", "AMARI/LIQUORI", "BEVANDE", "BIRRE", "CAFFÈ E THE",
    "CARNE", "DISTILLATI", "FRUTTA", "GELATI", "LATTICINI",
    "OLIO E CONDIMENTI", "PASTICCERIA", "PESCE", "PRODOTTI DA FORNO",
    "SALSE E CREME", "SALUMI", "SCATOLAME E CONSERVE", "SECCO", "SHOP",
    "SPEZIE E AROMI", "SUSHI VARIE", "UOVA", "VARIE BAR", "VERDURE",
    "VINI", "MATERIALE DI CONSUMO", "SERVIZI E CONSULENZE",
    "UTENZE E LOCALI", "MANUTENZIONE E ATTREZZATURE", "Da Classificare",
}


def _fetch_all(client, table: str, columns: str, page_size: int = 1000):
    """Paginazione manuale via .range()."""
    rows = []
    start = 0
    while True:
        end = start + page_size - 1
        resp = client.table(table).select(columns).range(start, end).execute()
        chunk = resp.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return rows


def _parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _fmt_eur(v):
    return f"€ {v:>14,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _print_table(title, headers, rows, max_rows=None):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    if not rows:
        print("  (nessun risultato)")
        return
    if max_rows:
        rows = rows[:max_rows]
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def main():
    client = get_supabase_client()
    print("Scarico fatture...")
    fatture = _fetch_all(
        client,
        "fatture",
        "user_id,ristorante_id,file_origine,fornitore,"
        "tipo_documento,data_documento,categoria,descrizione,totale_riga,"
        "created_at",
    )
    print(f"  fatture totali: {len(fatture)}")

    print("Scarico upload_events...")
    try:
        events = _fetch_all(
            client, "upload_events",
            "user_id,file_name,status,details,created_at",
        )
    except Exception as exc:
        print(f"  upload_events non leggibili: {exc}")
        events = []
    print(f"  eventi totali: {len(events)}")

    # ------------------------------------------------------------------
    # CHECK 1 — DOPPI IMPORT (batch temporali distinti > 1 ora diff)
    # ------------------------------------------------------------------
    groups1 = defaultdict(list)
    for r in fatture:
        key = (r.get("user_id"), r.get("file_origine"))
        if key[1]:
            groups1[key].append(r)

    check1 = []
    for (uid, fo), rs in groups1.items():
        ts = [_parse_ts(r["created_at"]) for r in rs]
        ts = [t for t in ts if t]
        if not ts:
            continue
        hours = {t.replace(minute=0, second=0, microsecond=0) for t in ts}
        if len(hours) > 1:
            tot = sum(float(r.get("totale_riga") or 0) for r in rs)
            minutes = {t.replace(second=0, microsecond=0) for t in ts}
            check1.append((
                (uid or "")[:8], (fo or "")[:50], len(rs), len(minutes),
                len(hours), min(ts).isoformat(timespec="minutes"),
                max(ts).isoformat(timespec="minutes"), round(tot, 2),
            ))
    check1.sort(key=lambda x: (-x[4], -x[7]))
    _print_table(
        f"CHECK 1 — DOPPI IMPORT (batch orari distinti) — trovati: {len(check1)}",
        ["user_id", "file_origine", "righe", "min_batch",
         "hour_batch", "primo", "ultimo", "totale_eur"],
        check1, max_rows=20,
    )

    # ------------------------------------------------------------------
    # CHECK 2 — FATTURE CON TOTALE > €10k
    # ------------------------------------------------------------------
    groups2 = defaultdict(list)
    for r in fatture:
        key = (
            r.get("user_id"), r.get("file_origine"), r.get("fornitore"),
        )
        groups2[key].append(r)

    check2 = []
    for (uid, fo, forn), rs in groups2.items():
        tot = sum(float(r.get("totale_riga") or 0) for r in rs)
        if tot > 10000:
            data = max((r.get("data_documento") or "") for r in rs)
            check2.append((
                (uid or "")[:8], (fo or "")[:45],
                (forn or "")[:30],
                len(rs), round(tot, 2), data,
            ))
    check2.sort(key=lambda x: -x[4])
    _print_table(
        f"CHECK 2 — FATTURE > €10k — trovate: {len(check2)}",
        ["user_id", "file_origine", "fornitore",
         "n_righe", "totale_db", "data_doc"],
        check2, max_rows=30,
    )

    # ------------------------------------------------------------------
    # CHECK 3 — TIPO DOCUMENTO (focus TD24)
    # ------------------------------------------------------------------
    groups3 = defaultdict(lambda: {"files": set(), "righe": 0, "tot": 0.0})
    for r in fatture:
        key = ((r.get("user_id") or "")[:8], r.get("tipo_documento") or "—")
        g = groups3[key]
        g["files"].add(r.get("file_origine"))
        g["righe"] += 1
        g["tot"] += float(r.get("totale_riga") or 0)

    check3 = [
        (uid, tipo, len(v["files"]), v["righe"], round(v["tot"], 2))
        for (uid, tipo), v in groups3.items()
    ]
    check3.sort(key=lambda x: (x[1], -x[2]))
    _print_table(
        f"CHECK 3 — TIPO DOCUMENTO per cliente — righe: {len(check3)}",
        ["user_id", "tipo_doc", "n_fatture", "n_righe", "totale_eur"],
        check3,
    )

    # ------------------------------------------------------------------
    # CHECK 4 — NOTE DI CREDITO (TD04)
    # ------------------------------------------------------------------
    groups4 = defaultdict(list)
    for r in fatture:
        if (r.get("tipo_documento") or "").upper() == "TD04":
            key = (
                r.get("user_id"), r.get("file_origine"), r.get("fornitore"),
            )
            groups4[key].append(r)

    check4 = []
    for (uid, fo, forn), rs in groups4.items():
        tots = [float(r.get("totale_riga") or 0) for r in rs]
        tot = sum(tots)
        check4.append((
            (uid or "")[:8], (fo or "")[:45], (forn or "")[:30],
            len(rs), round(tot, 2), round(min(tots), 2),
            round(max(tots), 2),
            "❌ POSITIVO" if tot >= 0 else "OK",
        ))
    check4.sort(key=lambda x: -x[4])
    _print_table(
        f"CHECK 4 — NOTE DI CREDITO TD04 — trovate: {len(check4)}",
        ["user_id", "file_origine", "fornitore", "righe",
         "totale", "min_riga", "max_riga", "flag"],
        check4,
    )
    n_pos = sum(1 for r in check4 if r[4] >= 0)
    print(f"   >> Note di credito con totale POSITIVO: {n_pos}")

    # ------------------------------------------------------------------
    # CHECK 5 — RIGHE "Da Classificare"
    # ------------------------------------------------------------------
    groups5 = defaultdict(lambda: {"n": 0, "tot": 0.0})
    for r in fatture:
        if (r.get("categoria") or "") == "Da Classificare":
            key = ((r.get("user_id") or "")[:8], (r.get("descrizione") or "")[:60])
            g = groups5[key]
            g["n"] += 1
            g["tot"] += float(r.get("totale_riga") or 0)

    check5 = [
        (uid, desc, v["n"], round(v["tot"], 2))
        for (uid, desc), v in groups5.items()
    ]
    check5.sort(key=lambda x: -x[2])
    tot_non_class = sum(x[3] for x in check5)
    _print_table(
        f"CHECK 5 — DA CLASSIFICARE — descrizioni distinte: {len(check5)}, "
        f"totale € non classificato: {tot_non_class:,.2f}",
        ["user_id", "descrizione", "n_righe", "totale"],
        check5, max_rows=40,
    )

    # ------------------------------------------------------------------
    # CHECK 6 — CATEGORIE FUORI ELENCO / NULL
    # ------------------------------------------------------------------
    groups6 = defaultdict(lambda: {"n": 0, "tot": 0.0})
    for r in fatture:
        cat = r.get("categoria")
        if cat is None or cat not in CATEGORIE_UFFICIALI:
            key = cat if cat is not None else "__NULL__"
            g = groups6[key]
            g["n"] += 1
            g["tot"] += float(r.get("totale_riga") or 0)

    check6 = [
        (cat, v["n"], round(v["tot"], 2)) for cat, v in groups6.items()
    ]
    check6.sort(key=lambda x: -x[1])
    _print_table(
        f"CHECK 6 — CATEGORIE SOSPETTE — anomalie: {len(check6)}",
        ["categoria", "n_righe", "totale_eur"],
        check6,
    )

    # ------------------------------------------------------------------
    # CHECK 7 — UPLOAD EVENTS con più SAVED_OK
    # ------------------------------------------------------------------
    groups7 = defaultdict(list)
    for e in events:
        key = (e.get("user_id"), e.get("file_name"))
        groups7[key].append(e)

    check7 = []
    for (uid, fn), es in groups7.items():
        if not fn:
            continue
        saved_ok = [e for e in es if e.get("status") == "SAVED_OK"]
        if len(saved_ok) > 1:
            ts = [_parse_ts(e["created_at"]) for e in saved_ok]
            ts = [t for t in ts if t]
            check7.append((
                (uid or "")[:8], (fn or "")[:55],
                len(es), len(saved_ok),
                min(ts).isoformat(timespec="minutes") if ts else "",
                max(ts).isoformat(timespec="minutes") if ts else "",
            ))
    check7.sort(key=lambda x: -x[3])
    _print_table(
        f"CHECK 7 — FILE CON >1 SAVED_OK — trovati: {len(check7)}",
        ["user_id", "file_name", "n_eventi", "n_saved_ok", "primo", "ultimo"],
        check7, max_rows=30,
    )

    # ------------------------------------------------------------------
    # SINTESI
    # ------------------------------------------------------------------
    print("\n" + "=" * 100)
    print("SINTESI ESECUTIVA")
    print("=" * 100)
    print(f"  Check 1 (doppi import)       : {len(check1):>4} casi")
    print(f"  Check 2 (fatture > €10k)     : {len(check2):>4} casi")
    print(f"  Check 3 (tipi documento)     : {len(check3):>4} combinazioni")
    print(f"  Check 4 (TD04 positive)      : {n_pos:>4} su {len(check4)} TD04 totali")
    print(f"  Check 5 (Da Classificare)    : {len(check5):>4} descrizioni, € {tot_non_class:,.2f}")
    print(f"  Check 6 (categorie sospette) : {len(check6):>4} categorie fuori elenco/NULL")
    print(f"  Check 7 (doppio SAVED_OK)    : {len(check7):>4} file")


if __name__ == "__main__":
    main()
