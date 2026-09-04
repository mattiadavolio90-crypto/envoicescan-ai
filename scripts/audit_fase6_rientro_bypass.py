"""
Misura il rientro nel bypass dopo la Fase 6 (e il fix del 4/9).

Perche' esiste: la Fase 6 declassa le voci di prodotti_master mai confermate da
una persona e promette loro una via di rientro (CONFERME_PER_BYPASS conferme
dell'AI di fila). Fino al 4/9 quella via era chiusa da una guardia che usciva
prima di incrementare lo streak: le voci restavano a streak 0 per sempre.

Questo script serve a rispondere con un numero, non a memoria, alla domanda
"lo streak risale davvero?" — la domanda 3 di PROMPT_COSTO_AI_DOPO_FASE6.md.

Il segnale da leggere e' la DISTRIBUZIONE, non il totale: se le voci declassate
stanno tutte a 0 mentre il gruppo di controllo ('media', dove la guardia non
interveniva) distribuisce su 0/1/2, la via di rientro e' ancora chiusa. Era
esattamente il quadro del 4/9: 373/0/0 contro 720/128/16.

Sola lettura: nessuna scrittura su prodotti_master.

Uso:
    python -m scripts.audit_fase6_rientro_bypass
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List

from config.constants import CONFERME_PER_BYPASS, CONFIDENCE_ALTA
from services import get_supabase_client


def _fetch_all(sb) -> List[dict]:
    rows: List[dict] = []
    page = 0
    while True:
        res = (
            sb.table("prodotti_master")
            .select("descrizione, categoria, confidence, "
                    "consecutive_correct_classifications, verified")
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        page += 1


def _distribuzione(voci: List[dict]) -> Counter:
    c: Counter = Counter()
    for v in voci:
        s = v.get("consecutive_correct_classifications") or 0
        c[min(s, CONFERME_PER_BYPASS)] += 1
    return c


def _riga(nome: str, c: Counter, totale: int) -> str:
    celle = " ".join(
        f"{('>=' + str(CONFERME_PER_BYPASS)) if s == CONFERME_PER_BYPASS else s}:{c.get(s, 0):>5}"
        for s in range(CONFERME_PER_BYPASS + 1)
    )
    return f"  {nome:<34} {celle}   tot {totale}"


def main() -> int:
    sb = get_supabase_client()
    rows = _fetch_all(sb)

    non_verif = [r for r in rows if not r.get("verified")]
    declassate = [r for r in non_verif if r.get("confidence") in CONFIDENCE_ALTA]
    controllo = [r for r in non_verif if r.get("confidence") not in CONFIDENCE_ALTA]

    d_decl = _distribuzione(declassate)
    d_ctrl = _distribuzione(controllo)

    print(f"\nprodotti_master: {len(rows)} voci, "
          f"{len(rows) - len(non_verif)} verificate, {len(non_verif)} no\n")
    print("Distribuzione dello streak (soglia bypass = "
          f"{CONFERME_PER_BYPASS}):")
    print(_riga("declassate Fase 6 (alta, no umano)", d_decl, len(declassate)))
    print(_riga("controllo (media/bassa/NULL)", d_ctrl, len(controllo)))

    in_movimento = sum(d_decl.get(s, 0) for s in range(1, CONFERME_PER_BYPASS))
    rientrate = d_decl.get(CONFERME_PER_BYPASS, 0)
    bloccate = d_decl.get(0, 0)

    # Il segnale e' il MOVIMENTO, non il totale. Le voci gia' a >=CONFERME sono
    # un residuo storico (erano arrivate a soglia PRIMA di essere promosse ad
    # 'alta'): contarle come "rientri" fa dichiarare verde proprio lo stato
    # bloccato che questo script deve riconoscere.
    ctrl_mossi = sum(d_ctrl.get(s, 0) for s in range(1, CONFERME_PER_BYPASS + 1))

    print("\nVerdetto:")
    if not declassate:
        print("  Nessuna voce declassata: niente da misurare.")
    elif in_movimento:
        print(f"  VERDE — {in_movimento} voci in salita (streak fra 1 e "
              f"{CONFERME_PER_BYPASS - 1}), {bloccate} ancora a 0.")
        print("  La via di rientro e' aperta: il contatore si muove.")
    elif ctrl_mossi:
        print(f"  ROSSO — nessuna delle {len(declassate)} declassate si e' mossa da 0,")
        print(f"  ma il gruppo di controllo si muove ({ctrl_mossi} voci sopra 0).")
        print("  Il contatore funziona in generale ed e' bloccato SOLO per le")
        print("  declassate: guarda la guardia in aggiorna_streak_classificazione,")
        print("  esce prima dell'incremento. E' il quadro del 4/9 (373/0/0).")
    else:
        print("  INCONCLUSIVO — nessuna voce si muove, ne' declassate ne' controllo.")
        print("  Non distingue 'via chiusa' da 'nessuna fattura elaborata': serve")
        print("  traffico prima di concludere. Ri-misurare dopo il prossimo upload.")

    if rientrate:
        print(f"\n  ({rientrate} voci sono gia' a >={CONFERME_PER_BYPASS}: sono in")
        print("  bypass, non un movimento recente. Non provano nulla da sole.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
