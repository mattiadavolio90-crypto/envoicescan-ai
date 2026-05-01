"""
KPI operativo fallback/review su fatture attive.

Nota: non esiste un flag dedicato "fallback_forzato" in tabella fatture,
quindi usiamo needs_review come proxy operativo dei casi da revisione.
"""

from __future__ import annotations

from collections import Counter

from services import get_supabase_client


def _fetch_all_fatture_attive(sb):
    rows = []
    page = 0
    page_size = 1000
    while page < 200:
        resp = (
            sb.table("fatture")
            .select("id,user_id,fornitore,descrizione,categoria,needs_review")
            .is_("deleted_at", "null")
            .range(page * page_size, page * page_size + page_size - 1)
            .execute()
        )
        chunk = resp.data or []
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        page += 1
    return rows


def main() -> int:
    sb = get_supabase_client()
    rows = _fetch_all_fatture_attive(sb)

    total = len(rows)
    review_rows = [r for r in rows if bool(r.get("needs_review"))]
    review_count = len(review_rows)

    fallback_proxy_rows = [
        r for r in review_rows if str(r.get("categoria") or "").strip() == "SERVIZI E CONSULENZE"
    ]

    by_fornitore = Counter((r.get("fornitore") or "Sconosciuto").strip() for r in review_rows)
    by_categoria = Counter((r.get("categoria") or "<vuota>").strip() for r in review_rows)
    by_descrizione = Counter((r.get("descrizione") or "").strip()[:100] for r in review_rows)

    print("=== KPI REVIEW/FALLBACK ===")
    print(f"Righe attive totali: {total}")
    print(f"Righe in review (needs_review=True): {review_count}")
    print(f"% review su attive: {(review_count * 100 / total):.2f}%" if total else "% review su attive: 0.00%")
    print(
        f"Proxy fallback (review + categoria='SERVIZI E CONSULENZE'): {len(fallback_proxy_rows)} "
        f"({(len(fallback_proxy_rows) * 100 / review_count):.2f}% delle review)" if review_count else
        "Proxy fallback (review + categoria='SERVIZI E CONSULENZE'): 0 (0.00% delle review)"
    )

    print("\nTop 10 fornitori con review:")
    for name, n in by_fornitore.most_common(10):
        print(f"- {name}: {n}")

    print("\nTop 10 categorie in review:")
    for name, n in by_categoria.most_common(10):
        print(f"- {name}: {n}")

    print("\nTop 10 descrizioni in review:")
    for name, n in by_descrizione.most_common(10):
        print(f"- {name}: {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
