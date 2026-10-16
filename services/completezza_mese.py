"""Quando un mese ha la merce che serve per giudicarne i conti.

Una sola regola per Home, Margini, Salute, catena, briefing e chat. Fino al
16/10/2026 ogni punto la ricopiava come «costi F&B <= 0», e bastavano 100 EUR
inseriti a mano su 386.000 EUR di incasso netto a dichiarare completo un mese
senza una fattura: MOL verde, food cost 0% (audit di ottobre 2026, K03).

Decisione di Mattia (16/10/2026), sui 73 mesi chiusi misurati quel giorno:
un mese chiuso con incasso e' senza merce se i costi della merce (fatture +
inseriti a mano + quote di riparto del gruppo) sono meno del 15% dell'incasso
netto. Il 15% e non il 20%: un bar reale sta stabilmente al 17,8-19,3% con mesi
pieni di fatture, e al 20% diventava giallo; tutti i mesi davvero vuoti stanno
sotto il 10%. Niente criterio sulla data dell'ultima fattura: sui dati non
distingue niente (51 mesi completi su 54 hanno una fattura dell'ultimo giorno)
e lascerebbe gialli per sempre i mesi fatti di sole quote o di merce a mano.

Il mese in corso resta sulla regola di prima (nessuna merce): a meta' mese la
merce arriva in ritardo sull'incasso, e il 15% lo farebbe giallo tre settimane
al mese.
"""
from __future__ import annotations

SOGLIA_MERCE_SU_NETTO = 0.15


def merce_insufficiente(netto: float, merce: float, *, in_corso: bool = False) -> bool:
    """True = il mese ha incasso ma non abbastanza merce per giudicarne i conti.

    `merce` e' il totale F&B del mese: fatture + `altri_costi_fb` + quote di
    riparto F&B. Senza incasso non si giudica niente (False): e' un altro caso,
    quello dei ricavi mancanti.
    """
    netto = float(netto or 0)
    merce = float(merce or 0)
    if netto <= 0:
        return False
    if in_corso:
        return merce <= 0
    return merce < SOGLIA_MERCE_SU_NETTO * netto
