"""Costo del personale dai turni: la regola «lo stipendio del mese vince».

Turni giornalieri e riga mensile (stipendio da busta paga) dello STESSO
dipendente nello STESSO mese convivono (fase C2, 04/10/2026). Per ogni coppia
(dipendente_id, mese YYYY-MM):

- **con riga mensile**: il costo viene SOLO dalla riga mensile. `lordo_mensile`
  e' il totale della busta, `importo_extra` e `importo_chiamata` sono «di cui»:
  ordinario = max(0, lordo − extra − chiamata). I turni giornalieri del mese
  contano come ORE, non come costo, e non finiscono fra i «senza costo orario».
  Le assenze a carico (ferie/malattia) non si sommano: sono gia' in busta.
- **ore del mese**: dai turni lavorati se ce ne sono, altrimenti
  `ore_dichiarate`/`ore_extra` della riga mensile. Mai le due insieme: le ore
  si conterebbero due volte.
- **senza riga mensile**: tariffa oraria come sempre. Senza `costo_orario` il
  turno non ha costo (nemmeno le extra) e si conta in `n_senza_costo`.

Unica fonte della regola per `ws_personale_list` (pagina Personale ed export
Excel) e `get_costo_personale_da_turni` (Margini). Funzione pura: nessun
accesso al DB; le ore di un turno arrivano da `ore_turno` (il `_ore_turno` del
worker), passato dal chiamante.
"""
from typing import Callable, Iterable


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _vuoto() -> dict:
    return {
        "ore": 0.0,
        "ore_extra": 0.0,
        "costo_ordinario": 0.0,
        "costo_extra": 0.0,
        "costo_chiamata": 0.0,
        "costo_assenze": 0.0,
        "n_turni": 0,
        "n_senza_costo": 0,
        "n_giorni_assenza": 0,
        "con_stipendio": False,
        "ha_ore": False,
        "costo_noto": False,
    }


def aggrega_per_dipendente_mese(turni: Iterable[dict], ore_turno: Callable[[dict], float]) -> dict:
    """{(dipendente_id, 'YYYY-MM'): componenti} con la regola applicata.

    Componenti: ore, ore_extra (sottoinsieme di ore), costo_ordinario,
    costo_extra, costo_chiamata, costo_assenze, n_turni, n_senza_costo,
    n_giorni_assenza, con_stipendio, ha_ore (c'e' almeno una fonte di ore),
    costo_noto (c'e' almeno un costo conosciuto: tariffa o stipendio).
    """
    gruppi: dict = {}
    for t in turni:
        chiave = (t.get("dipendente_id"), str(t.get("data_turno") or "")[:7])
        g = gruppi.setdefault(chiave, {"mensili": [], "lavorati": [], "assenze": []})
        if t.get("tipo_giorno", "turno") != "turno":
            g["assenze"].append(t)
        elif t.get("mensile"):
            g["mensili"].append(t)
        else:
            g["lavorati"].append(t)

    risultato: dict = {}
    for chiave, g in gruppi.items():
        c = _vuoto()
        c["n_giorni_assenza"] = len(g["assenze"])
        con_stipendio = bool(g["mensili"])
        c["con_stipendio"] = con_stipendio

        fonti_ore = g["lavorati"] if g["lavorati"] else g["mensili"]
        for t in fonti_ore:
            ore = ore_turno(t)
            # Le extra sono un sottoinsieme delle ore (modello 05/09/2026): senza
            # il clamp l'ordinario (ore - extra) uscirebbe negativo.
            extra = min(_f(t.get("ore_extra")), ore)
            c["ore"] += ore
            c["ore_extra"] += extra
            c["n_turni"] += 1
            c["ha_ore"] = True

        if con_stipendio:
            for m in g["mensili"]:
                lordo = _f(m.get("lordo_mensile"))
                imp_ext = _f(m.get("importo_extra"))
                imp_ch = _f(m.get("importo_chiamata"))
                c["costo_extra"] += imp_ext
                c["costo_chiamata"] += imp_ch
                c["costo_ordinario"] += max(0.0, lordo - imp_ext - imp_ch)
            c["costo_noto"] = True
        else:
            for t in g["lavorati"]:
                co = t.get("costo_orario")
                if co is None:
                    c["n_senza_costo"] += 1
                    continue
                co = float(co)
                # Le extra usano costo_orario_extra se impostato, altrimenti la
                # tariffa standard. Senza tariffa standard non si paga nemmeno lo
                # straordinario (ramo sopra): il costo del turno non e' noto.
                co_ext = t.get("costo_orario_extra")
                co_ext = float(co_ext) if co_ext is not None else co
                ore = ore_turno(t)
                extra = min(_f(t.get("ore_extra")), ore)
                c["costo_ordinario"] += (ore - extra) * co
                c["costo_extra"] += extra * co_ext
                c["costo_noto"] = True
            for a in g["assenze"]:
                c["costo_assenze"] += _f(a.get("importo_a_carico"))

        risultato[chiave] = c
    return risultato
