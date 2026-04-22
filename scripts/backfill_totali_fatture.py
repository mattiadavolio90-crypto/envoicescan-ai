#!/usr/bin/env python3
"""Backfill totale_documento, totale_imponibile, totale_iva su fatture esistenti.

Per ogni XML in --input-dir:
1. Estrae ImportoTotaleDocumento, somma ImponibileImporto e Imposta da DatiRiepilogo
2. Trova in Supabase le righe con file_origine ILIKE '%<nome_senza_estensione>%'
3. Aggiorna tutte le righe trovate con i 3 valori
4. Stampa riepilogo: aggiornate / non trovate / errori
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, List, Optional
import xml.etree.ElementTree as ET

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Bootstrap credenziali Supabase da .streamlit/secrets.toml (uso CLI)
# ---------------------------------------------------------------------------

def _bootstrap_supabase_env_from_secrets() -> None:
    secrets_path = ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return
    try:
        with secrets_path.open("rb") as f:
            secrets = tomllib.load(f)
    except Exception:
        return
    cfg = secrets.get("supabase", {})
    if cfg.get("url"):
        os.environ["SUPABASE_URL"] = cfg["url"]
    if cfg.get("service_role_key"):
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = cfg["service_role_key"]
    if cfg.get("key"):
        os.environ.setdefault("SUPABASE_KEY", cfg["key"])


_bootstrap_supabase_env_from_secrets()

from services import get_supabase_client  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers XML (riproduco la stessa logica di verifica_lotto.py)
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    if ":" in tag:
        return tag.rsplit(":", 1)[1]
    return tag


def _find_first(root: ET.Element, path: List[str]) -> Optional[ET.Element]:
    current = root
    for expected in path:
        found = None
        for child in current:
            if _local(child.tag) == expected:
                found = child
                break
        if found is None:
            return None
        current = found
    return current


def _find_all_by_local(root: ET.Element, local_name: str) -> List[ET.Element]:
    return [node for node in root.iter() if _local(node.tag) == local_name]


def _text(node: Optional[ET.Element]) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Parsing XML
# ---------------------------------------------------------------------------

def _estrai_totali(xml_path: Path) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Restituisce (totale_documento, totale_imponibile, totale_iva)."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as exc:
        raise ValueError(f"XML non parsabile: {exc}") from exc

    # ImportoTotaleDocumento
    totale_documento = _to_float(
        _text(
            _find_first(
                root,
                [
                    "FatturaElettronicaBody",
                    "DatiGenerali",
                    "DatiGeneraliDocumento",
                    "ImportoTotaleDocumento",
                ],
            )
        ) or None
    )

    # Somma ImponibileImporto e Imposta da tutti i DatiRiepilogo
    totale_imponibile = 0.0
    totale_iva = 0.0

    riepilogo_nodes = _find_all_by_local(root, "DatiRiepilogo")
    for node in riepilogo_nodes:
        imponibile_node = None
        imposta_node = None
        for child in node:
            local = _local(child.tag)
            if local == "ImponibileImporto":
                imponibile_node = child
            elif local == "Imposta":
                imposta_node = child
        totale_imponibile += _to_float(_text(imponibile_node)) or 0.0
        totale_iva += _to_float(_text(imposta_node)) or 0.0

    # Se DatiRiepilogo non trovato, rimango a None per non sovrascrivere con 0
    if not riepilogo_nodes:
        totale_imponibile_out: Optional[float] = None
        totale_iva_out: Optional[float] = None
    else:
        totale_imponibile_out = round(totale_imponibile, 6)
        totale_iva_out = round(totale_iva, 6)

    return totale_documento, totale_imponibile_out, totale_iva_out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill totale_documento/totale_imponibile/totale_iva da XML su Supabase."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Cartella contenente i file XML delle fatture elettroniche.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Filtra le righe Supabase per questo user_id (opzionale).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula le operazioni senza eseguire UPDATE su Supabase.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"ERRORE: --input-dir '{input_dir}' non è una cartella valida.")
        sys.exit(1)

    # Usa un dict per deduplicare (su Windows glob case-insensitive restituisce duplicati)
    xml_files_map = {p.name.lower(): p for p in input_dir.glob("*.xml")}
    xml_files_map.update({p.name.lower(): p for p in input_dir.glob("*.XML")})
    xml_files = sorted(xml_files_map.values(), key=lambda p: p.name.lower())
    if not xml_files:
        print(f"Nessun file XML trovato in '{input_dir}'.")
        sys.exit(0)

    print(f"File XML trovati: {len(xml_files)}")
    if args.dry_run:
        print("MODALITÀ DRY-RUN: nessuna modifica verrà applicata.\n")
    else:
        print()

    supabase = get_supabase_client()

    aggiornate = 0
    non_trovate = 0
    errori = 0

    for xml_path in xml_files:
        nome_file = xml_path.stem  # nome senza estensione

        # 1. Parsing XML
        try:
            totale_documento, totale_imponibile, totale_iva = _estrai_totali(xml_path)
        except ValueError as exc:
            print(f"  [ERRORE PARSING] {xml_path.name}: {exc}")
            errori += 1
            continue

        # 2. Cerca righe in Supabase
        try:
            query = (
                supabase.table("fatture")
                .select("id,file_origine")
                .ilike("file_origine", f"%{nome_file}%")
            )
            if args.user_id:
                query = query.eq("user_id", args.user_id)

            response = query.execute()
            righe = response.data or []
        except Exception as exc:
            print(f"  [ERRORE QUERY] {xml_path.name}: {exc}")
            errori += 1
            continue

        if not righe:
            print(f"  [NON TROVATA] {xml_path.name} — nessuna riga in DB (file_origine ILIKE '%{nome_file}%')")
            non_trovate += 1
            continue

        # 3. Prepara payload UPDATE (esclude i None per non sovrascrivere valori)
        payload: dict = {}
        if totale_documento is not None:
            payload["totale_documento"] = totale_documento
        if totale_imponibile is not None:
            payload["totale_imponibile"] = totale_imponibile
        if totale_iva is not None:
            payload["totale_iva"] = totale_iva

        if not payload:
            print(f"  [SKIP] {xml_path.name} — nessun valore estraibile dall'XML (DatiRiepilogo assente?)")
            non_trovate += 1
            continue

        # 4. UPDATE
        if args.dry_run:
            td = f"{totale_documento:.2f}" if totale_documento is not None else "N/A"
            ti = f"{totale_imponibile:.2f}" if totale_imponibile is not None else "N/A"
            tiva = f"{totale_iva:.2f}" if totale_iva is not None else "N/A"
            print(
                f"  [DRY-RUN] {xml_path.name} — {len(righe)} righe | "
                f"tot_doc={td} tot_imp={ti} tot_iva={tiva}"
            )
            aggiornate += 1
            continue

        try:
            update_query = (
                supabase.table("fatture")
                .update(payload)
                .ilike("file_origine", f"%{nome_file}%")
            )
            if args.user_id:
                update_query = update_query.eq("user_id", args.user_id)

            update_query.execute()

            td = f"{totale_documento:.2f}" if totale_documento is not None else "N/A"
            ti = f"{totale_imponibile:.2f}" if totale_imponibile is not None else "N/A"
            tiva = f"{totale_iva:.2f}" if totale_iva is not None else "N/A"
            print(
                f"  [OK] {xml_path.name} — {len(righe)} righe aggiornate | "
                f"tot_doc={td} tot_imp={ti} tot_iva={tiva}"
            )
            aggiornate += 1
        except Exception as exc:
            print(f"  [ERRORE UPDATE] {xml_path.name}: {exc}")
            errori += 1

    # 5. Riepilogo
    print()
    print("=" * 60)
    print(f"  Aggiornate : {aggiornate}")
    print(f"  Non trovate: {non_trovate}")
    print(f"  Errori     : {errori}")
    print(f"  Totale XML : {len(xml_files)}")
    print("=" * 60)
    if args.dry_run:
        print("(dry-run: nessuna modifica applicata)")


if __name__ == "__main__":
    main()
