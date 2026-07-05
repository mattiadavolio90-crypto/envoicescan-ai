"""A/B test gpt-4o-mini vs gpt-4.1-mini sulla categorizzazione, su ground truth reale.

Ground truth: correzioni MANUALI di clienti reali in prodotti_utente
(classificato_da LIKE 'Manuale (%@%'), NON db_trigger/AI/keyword-auto (quelle
sono automatiche, non un giudizio umano verificato).

Uso:
    railway run --service worker -- python scripts/ab_test_modello_categorizzazione.py

Richiede OPENAI_API_KEY nell'ambiente (railway run la inietta da Railway).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402
from services import get_supabase_client  # noqa: E402
from services.ai_service import _chiama_gpt_classificazione  # noqa: E402

BATCH_SIZE = 30
MODELLI = ["gpt-4o-mini", "gpt-4.1-mini"]


def carica_ground_truth() -> list[tuple[str, str]]:
    sb = get_supabase_client()
    resp = (
        sb.table("prodotti_utente")
        .select("descrizione,categoria,classificato_da")
        .like("classificato_da", "Manuale (%@%")
        .execute()
    )
    rows = resp.data or []
    return [(r["descrizione"], r["categoria"]) for r in rows if r.get("descrizione") and r.get("categoria")]


def valuta_modello(modello: str, casi: list[tuple[str, str]], client: OpenAI) -> dict:
    os.environ["ONEFLUX_AI_MODEL"] = modello
    descrizioni = [c[0] for c in casi]
    attese = [c[1] for c in casi]

    predette: list[str] = []
    prompt_tok = 0
    completion_tok = 0
    t0 = time.monotonic()

    for i in range(0, len(descrizioni), BATCH_SIZE):
        chunk = descrizioni[i:i + BATCH_SIZE]
        try:
            cats, _conf = _chiama_gpt_classificazione(chunk, client, return_confidenze=True)
        except Exception as exc:
            print(f"  [{modello}] batch {i}-{i+len(chunk)} errore: {exc}", file=sys.stderr)
            cats = ["Da Classificare"] * len(chunk)
        predette.extend(cats)

    elapsed = time.monotonic() - t0
    corrette = sum(1 for p, a in zip(predette, attese) if p == a)
    # tariffe da ai_cost_service._MODEL_TARIFFE (hardcoded qui per non dipendere
    # dal tracking-costi reale, che richiede ristorante_id)
    tariffe = {"gpt-4o-mini": (0.15, 0.60), "gpt-4.1-mini": (0.40, 1.60)}
    in_rate, out_rate = tariffe[modello]

    return {
        "modello": modello,
        "n_casi": len(casi),
        "corrette": corrette,
        "accuratezza": round(corrette / len(casi), 4) if casi else 0.0,
        "elapsed_sec": round(elapsed, 1),
        "predette": predette,
        "attese": attese,
        "descrizioni": descrizioni,
        "in_rate_per_m": in_rate,
        "out_rate_per_m": out_rate,
    }


def main():
    casi = carica_ground_truth()
    print(f"Ground truth: {len(casi)} correzioni manuali reali")
    if not casi:
        print("Nessun caso trovato, esco.")
        return

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    risultati = []
    for modello in MODELLI:
        print(f"\n--- Valutazione {modello} ---")
        r = valuta_modello(modello, casi, client)
        print(f"  accuratezza: {r['corrette']}/{r['n_casi']} ({r['accuratezza']*100:.1f}%) in {r['elapsed_sec']}s")
        risultati.append(r)

    print("\n" + "=" * 70)
    print("RIEPILOGO")
    print("=" * 70)
    for r in risultati:
        print(f"{r['modello']:16s} accuratezza={r['accuratezza']*100:5.1f}%  "
              f"({r['corrette']}/{r['n_casi']})  "
              f"tariffa=${r['in_rate_per_m']}/${r['out_rate_per_m']} per M token")

    # Disaccordi: casi dove i due modelli danno risposte diverse
    out_path = ROOT / "scripts" / "_ab_test_disaccordi.json"
    disaccordi = []
    r0, r1 = risultati[0], risultati[1]
    for desc, attesa, p0, p1 in zip(r0["descrizioni"], r0["attese"], r0["predette"], r1["predette"]):
        if p0 != p1:
            disaccordi.append({
                "descrizione": desc,
                "attesa_cliente": attesa,
                r0["modello"]: p0,
                r1["modello"]: p1,
            })
    out_path.write_text(json.dumps(disaccordi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(disaccordi)} disaccordi salvati in {out_path}")


if __name__ == "__main__":
    main()
