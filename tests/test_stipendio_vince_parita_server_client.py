"""Parita' server ↔ client della regola «lo stipendio del mese vince» (fase C2).

La regola vive in tre punti: `services/costo_personale_turni.py` (Recupera in
Margini, export Excel), `aggregaPerPersona` (tab Personale desktop) e
`riepilogoPerDipendente` (/m). Stessi turni di UN mese → stesso costo per
persona, stesse componenti, stesse ore. Casi generati con seme fisso, righe
mescolate e mensili «sporchi» (extra + chiamata oltre il lordo, ore_extra oltre
le ore). Unica differenza dichiarata: /m somma le assenze a carico di chi NON ha
lo stipendio (il server le tiene a parte, il desktop non le mostra).
"""
import random

from services.costo_personale_turni import aggrega_per_dipendente_mese
from tests.helpers_ts import esegui_ts


def _ore(t):
    return float(t.get("ore_dichiarate") or 0) if t.get("mensile") else float(t["ore"])


def _casi(n=60, seme=7):
    rnd = random.Random(seme)
    casi = []
    for _ in range(n):
        turni = []
        for dip in ("a", "b", "c"):
            for i in range(rnd.randint(0, 4)):
                tipo = rnd.choice(["turno", "turno", "turno", "ferie", "malattia", "riposo"])
                turni.append({
                    "dipendente_id": dip, "data_turno": f"2026-09-{i + 2:02d}", "mensile": False,
                    "tipo_giorno": tipo, "ore": rnd.choice([0, 4, 8, 7.5]),
                    "ore_extra": rnd.choice([None, 0, 2, 10]),
                    "costo_orario": rnd.choice([None, 10, 12.5]),
                    "costo_orario_extra": rnd.choice([None, 15]),
                    "importo_a_carico": rnd.choice([None, 50]) if tipo in ("ferie", "malattia") else None,
                })
            if rnd.random() < 0.5:
                turni.append({
                    "dipendente_id": dip, "data_turno": "2026-09-01", "mensile": True,
                    "tipo_giorno": "turno", "ore": 0,
                    "ore_dichiarate": rnd.choice([0, 160]), "ore_extra": rnd.choice([None, 10, 200]),
                    "lordo_mensile": rnd.choice([0, 1000, 1800]),
                    "importo_extra": rnd.choice([None, 200, 1500]),
                    "importo_chiamata": rnd.choice([None, 100, 900]),
                })
        rnd.shuffle(turni)
        casi.append(turni)
    return casi


def test_server_desktop_e_mobile_danno_lo_stesso_costo_e_le_stesse_ore():
    casi = _casi()
    client = esegui_ts("lib/ore-turno", """
const oreDi = (t) => t.mensile ? (t.ore_dichiarate ?? 0) : t.ore;
emit(input.casi.map(turni => ({
  a: m.aggregaPerPersona(turni, (t) => t.dipendente_id, oreDi),
  r: m.riepilogoPerDipendente(turni, oreDi),
})));
""", {"casi": casi}, richiede=["aggregaPerPersona", "riepilogoPerDipendente"])

    divergenze = []
    confronti = 0
    for k, (turni, res) in enumerate(zip(casi, client)):
        a = res["a"]
        mob = {x["dipendenteId"]: x for x in res["r"]}
        for (dip, _mese), c in aggrega_per_dipendente_mese(turni, _ore).items():
            costo = c["costo_ordinario"] + c["costo_extra"] + c["costo_chiamata"]
            assenze_mob = 0 if c["con_stipendio"] else c["costo_assenze"]
            coppie = [
                ("costo desktop", costo, a["costoTot"].get(dip, 0)),
                ("ordinario", c["costo_ordinario"], a["costoStd"].get(dip, 0)),
                ("extra", c["costo_extra"], a["costoExt"].get(dip, 0)),
                ("chiamata", c["costo_chiamata"], a["costoChi"].get(dip, 0)),
                ("ore desktop", c["ore"], a["oreStd"].get(dip, 0) + a["oreExt"].get(dip, 0)),
                ("ore /m", c["ore"], mob[dip]["oreLavorate"] if dip in mob else 0),
                ("costo /m", costo, (mob[dip]["costoTot"] if dip in mob else 0) - assenze_mob),
            ]
            for nome, server, schermo in coppie:
                confronti += 1
                if abs(server - schermo) > 0.011:
                    divergenze.append((k, dip, nome, server, schermo))
    assert confronti > 500
    assert divergenze == []
