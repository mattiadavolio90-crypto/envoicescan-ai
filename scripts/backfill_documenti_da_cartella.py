"""
Backfill documento header da cartella fatture locali (XML/P7M).

Obiettivo:
- recuperare numero_documento, scadenza_xml e giorni_termini_xml da file storici
- popolare/aggiornare `fatture_documenti` in modo idempotente

Uso:
    python -m scripts.backfill_documenti_da_cartella --folder data/backfill_fatture/land_dei_sapori
    python -m scripts.backfill_documenti_da_cartella --folder data/backfill_fatture/land_dei_sapori --apply

Note:
- In dry-run non scrive nulla su DB.
- Se user_id / ristorante_id non sono passati, prova auto-rilevamento via tabella `fatture`.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from services import get_supabase_client
from services.documenti_service import upsert_fattura_documento
from services.invoice_service import estrai_dati_da_xml, estrai_xml_da_p7m


SUPPORTED_EXT = {".xml", ".p7m"}


@dataclass
class Tenant:
    user_id: str
    ristorante_id: str


def _scan_files(folder: Path) -> List[Path]:
    return sorted(
        [
            p
            for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
        ]
    )


def _variants(filename: str) -> List[str]:
    name = filename.strip()
    low = name.lower()
    out = {low}
    if low.endswith(".p7m"):
        out.add(low[:-4] + ".xml")
    elif low.endswith(".xml"):
        out.add(low[:-4] + ".p7m")
    return list(out)


def _chunked(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _build_db_file_map_and_tenant(sb, local_files: List[Path]) -> Tuple[Dict[str, str], Optional[Tenant], Counter]:
    names = [p.name for p in local_files]
    all_targets: List[str] = []
    for n in names:
        all_targets.extend(_variants(n))
    all_targets = sorted(set(all_targets))

    rows: List[dict] = []
    for chunk in _chunked(all_targets, 200):
        resp = (
            sb.table("fatture")
            .select("user_id,ristorante_id,file_origine")
            .in_("file_origine", chunk)
            .is_("deleted_at", "null")
            .execute()
        )
        rows.extend(resp.data or [])

    pair_counter: Counter = Counter()
    db_file_map: Dict[str, str] = {}
    for r in rows:
        file_orig = str(r.get("file_origine") or "").strip()
        if not file_orig:
            continue
        db_file_map[file_orig.lower()] = file_orig
        pair = (str(r.get("user_id") or ""), str(r.get("ristorante_id") or ""))
        if pair[0] and pair[1]:
            pair_counter[pair] += 1

    if not pair_counter:
        return db_file_map, None, pair_counter

    ranked = pair_counter.most_common()
    top_pair, top_count = ranked[0]

    # auto-accept se c'e un solo tenant o il top e nettamente dominante
    if len(ranked) == 1:
        return db_file_map, Tenant(user_id=top_pair[0], ristorante_id=top_pair[1]), pair_counter

    second_count = ranked[1][1] if len(ranked) > 1 else 0
    total = sum(pair_counter.values())
    if top_count >= max(2 * second_count, 1) and (top_count / max(total, 1)) >= 0.7:
        return db_file_map, Tenant(user_id=top_pair[0], ristorante_id=top_pair[1]), pair_counter

    return db_file_map, None, pair_counter


def _resolve_file_origine(local_name: str, db_file_map: Dict[str, str]) -> str:
    low = local_name.lower().strip()
    if low in db_file_map:
        return db_file_map[low]

    for v in _variants(local_name):
        if v in db_file_map:
            return db_file_map[v]

    return local_name


def _extract_rows_from_file(path: Path, user_id: str) -> List[dict]:
    raw = path.read_bytes()

    if path.suffix.lower() == ".p7m":
        xml_stream = estrai_xml_da_p7m(io.BytesIO(raw))
        if xml_stream is None:
            return []
        xml_bytes = xml_stream.read() if hasattr(xml_stream, "read") else xml_stream
        file_like = io.BytesIO(xml_bytes)
        file_like.name = path.with_suffix(".xml").name  # type: ignore[attr-defined]
        return estrai_dati_da_xml(file_like, user_id=user_id)

    file_like = io.BytesIO(raw)
    file_like.name = path.name  # type: ignore[attr-defined]
    return estrai_dati_da_xml(file_like, user_id=user_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="Cartella con XML/P7M")
    ap.add_argument("--user-id", default=None, help="Override user_id")
    ap.add_argument("--ristorante-id", default=None, help="Override ristorante_id")
    ap.add_argument("--apply", action="store_true", help="Applica upsert su DB")
    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        print(f"❌ Cartella non valida: {folder}")
        return 1

    local_files = _scan_files(folder)
    print(f"📁 Cartella: {folder}")
    print(f"📄 File XML/P7M trovati: {len(local_files)}")
    if not local_files:
        return 1

    sb = get_supabase_client()

    db_file_map, detected_tenant, pair_counter = _build_db_file_map_and_tenant(sb, local_files)
    print(f"🔎 Match file in DB (fatture): {len(db_file_map)}")

    if pair_counter:
        print("👥 Distribuzione tenant rilevata:")
        for (u, r), c in pair_counter.most_common(5):
            print(f"   - user_id={u} | ristorante_id={r} -> {c} match")

    user_id = args.user_id
    ristorante_id = args.ristorante_id

    if not user_id or not ristorante_id:
        if detected_tenant is None:
            print("❌ Tenant ambiguo/non rilevabile automaticamente. Passa --user-id e --ristorante-id.")
            return 2
        user_id = user_id or detected_tenant.user_id
        ristorante_id = ristorante_id or detected_tenant.ristorante_id

    print(f"🎯 Tenant operativo: user_id={user_id} | ristorante_id={ristorante_id}")
    print(f"🧪 Modalita: {'APPLY' if args.apply else 'DRY-RUN'}")

    parsed_ok = 0
    parse_fail = 0
    upsert_ok = 0
    upsert_fail = 0
    found_numero = 0
    found_scadenza = 0

    for idx, fpath in enumerate(local_files, start=1):
        try:
            rows = _extract_rows_from_file(fpath, user_id=user_id)
            if not rows:
                parse_fail += 1
                print(f"[{idx}/{len(local_files)}] ⚠️ parsing vuoto: {fpath.name}")
                continue

            parsed_ok += 1
            header = rows[0]
            file_origine = _resolve_file_origine(fpath.name, db_file_map)

            payload = {
                "fornitore": header.get("Fornitore"),
                "piva_fornitore": header.get("piva_cedente"),
                "numero_documento": header.get("numero_documento"),
                "data_documento": header.get("Data_Documento") or header.get("data_documento"),
                "data_competenza": header.get("DataCompetenza") or header.get("data_competenza"),
                "tipo_documento": header.get("tipo_documento", "TD01"),
                "totale_documento": header.get("Totale_Documento") or header.get("TotaleDocumento"),
                "totale_imponibile": header.get("Totale_Imponibile") or header.get("TotaleImponibile"),
                "totale_iva": header.get("Totale_IVA") or header.get("TotaleIVA"),
                "scadenza_xml": header.get("scadenza_xml"),
                "giorni_termini_xml": header.get("giorni_termini_xml"),
                "source_origin": "manual",
            }

            if payload.get("numero_documento"):
                found_numero += 1
            if payload.get("scadenza_xml") or payload.get("giorni_termini_xml"):
                found_scadenza += 1

            if args.apply:
                res = upsert_fattura_documento(
                    user_id=user_id,
                    ristorante_id=ristorante_id,
                    file_origine=file_origine,
                    payload=payload,
                    supabase_client=sb,
                )
                if res.get("ok"):
                    upsert_ok += 1
                else:
                    upsert_fail += 1
                    print(f"[{idx}/{len(local_files)}] ❌ upsert fallito: {fpath.name}")
            else:
                upsert_ok += 1

        except Exception as e:
            if args.apply:
                upsert_fail += 1
            else:
                parse_fail += 1
            print(f"[{idx}/{len(local_files)}] ❌ errore su {fpath.name}: {e}")

    print("\n===== RISULTATO =====")
    print(f"✅ Parsing OK: {parsed_ok}")
    print(f"⚠️ Parsing KO/vuoto: {parse_fail}")
    print(f"✅ {'Upsert' if args.apply else 'Simulazioni'} OK: {upsert_ok}")
    if args.apply:
        print(f"❌ Upsert KO: {upsert_fail}")
    print(f"🧾 File con numero_documento trovato: {found_numero}")
    print(f"📅 File con info scadenza trovata: {found_scadenza}")

    return 0 if (args.apply and upsert_fail == 0) or (not args.apply) else 3


if __name__ == "__main__":
    sys.exit(main())
