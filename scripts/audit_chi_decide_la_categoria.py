"""Chi decide davvero la categoria di una riga: le regole, la memoria o l'AI?

Perche' esiste
==============
La lente L4 dell'audit doveva misurare "l'esito statistico dell'AI". La misura
del 14/09/2026 ha rovesciato la domanda: sulle righe con provenienza registrata,
l'AI decide l'**1,3%**. Il 94,8% e' gia' deciso prima che il modello venga
interpellato — memoria locale del cliente, regole non negoziabili, dizionario.

Misurare "quanto sbaglia l'AI" avrebbe quindi descritto una frazione minuscola di
cio' che il cliente vede in pagina. Questo script risponde alla domanda giusta, e
con un numero invece che a memoria: **di chi e' la categoria che il cliente
legge?**

Come leggerlo
=============
- La distribuzione per fonte vale solo sulle righe che HANNO una provenienza:
  `categoria_fonte` esiste dalla Fase 2 (01/09/2026) e le righe precedenti sono
  NULL per scelta (nessun backfill: attribuire una fonte a righe scritte da un
  codice che non la registrava sarebbe un'invenzione). Lo script stampa sempre
  la base, perche' una percentuale senza la sua base non e' una misura.
- Se la quota AI resta bassa NON e' un guasto: significa che regole e memoria
  stanno rispondendo per prime, ed e' il disegno del sistema. Diventa un segnale
  quando cambia bruscamente in un verso o nell'altro.

Sola lettura: nessuna scrittura.

Uso:
    python -m scripts.audit_chi_decide_la_categoria
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import get_supabase_client  # noqa: E402

PAGINA = 1000


def _fetch_con_fonte(sb) -> list[dict]:
    """Tutte le righe attive che dichiarano una provenienza.

    `.order("id")`: una paginazione con `range()` senza ordinamento esplicito
    ripete e perde righe in silenzio, col totale che torna lo stesso (misurato il
    10/09/2026: 653 id mancanti su 3.067, rimpiazzati da duplicati).
    """
    righe: list[dict] = []
    pagina = 0
    while True:
        res = (
            sb.table("fatture")
            .select("id, categoria, categoria_fonte, categoria_fiducia")
            .is_("deleted_at", "null")
            .not_.is_("categoria_fonte", "null")
            .order("id")
            .range(pagina * PAGINA, pagina * PAGINA + PAGINA - 1)
            .execute()
        )
        blocco = res.data or []
        righe.extend(blocco)
        if len(blocco) < PAGINA:
            return righe
        pagina += 1


def _conta_attive(sb) -> int:
    res = (
        sb.table("fatture")
        .select("id", count="exact")
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    return int(res.count or 0)


def _famiglia(fonte: str | None) -> str:
    if not fonte:
        return "senza provenienza"
    if fonte.startswith("AI"):
        return "AI"
    if fonte == "correzione_cliente":
        return "umano"
    return "deciso prima del modello"


def main() -> int:
    sb = get_supabase_client()

    attive = _conta_attive(sb)
    righe = _fetch_con_fonte(sb)
    con_fonte = len(righe)

    print("=" * 74)
    print("CHI DECIDE LA CATEGORIA")
    print("=" * 74)
    print(f"  righe attive:            {attive:>7}")
    print(f"  con provenienza:         {con_fonte:>7}"
          f"   ({100.0 * con_fonte / attive:.1f}% del totale)" if attive else "")
    print("  Le righe senza provenienza sono anteriori alla Fase 2 (01/09/2026):")
    print("  NULL significa 'legacy', non 'sconosciuto per errore'.")

    if not con_fonte:
        print("\n  Nessuna riga con provenienza: la distribuzione non e' misurabile.")
        return 0

    famiglie = Counter(_famiglia(r.get("categoria_fonte")) for r in righe)
    print(f"\n  Su {con_fonte} righe con provenienza:")
    for nome, n in famiglie.most_common():
        print(f"    {nome:<28} {n:>6}   {100.0 * n / con_fonte:>5.1f}%")

    print("\n  Dettaglio per livello:")
    for fonte, n in Counter(r.get("categoria_fonte") for r in righe).most_common():
        print(f"    {str(fonte):<28} {n:>6}   {100.0 * n / con_fonte:>5.1f}%")

    fiducia = Counter(r.get("categoria_fiducia") or "(nessuna)" for r in righe)
    print("\n  Per fiducia dichiarata:")
    for nome, n in fiducia.most_common():
        print(f"    {str(nome):<28} {n:>6}   {100.0 * n / con_fonte:>5.1f}%")

    quota_ai = 100.0 * famiglie.get("AI", 0) / con_fonte
    print("\n" + "-" * 74)
    print(f"  Quota decisa dall'AI: {quota_ai:.1f}% ({famiglie.get('AI', 0)} righe)")
    print("  Una quota bassa NON e' un guasto: regole e memoria rispondono prima.")
    print("  Il segnale e' il CAMBIAMENTO nel tempo, non il valore assoluto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
