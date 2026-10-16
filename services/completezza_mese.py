"""Quando un mese ha la merce che serve per giudicarne i conti.

Una sola regola per Home, Margini, Salute, catena, briefing e chat. Fino al
16/10/2026 ogni punto la ricopiava come «costi F&B <= 0», e bastavano 100 EUR
inseriti a mano su 386.000 EUR di incasso netto a dichiarare completo un mese
senza una fattura: MOL verde, food cost 0% (audit di ottobre 2026, K03).

Decisione di Mattia (16/10/2026, sera), sui 73 mesi chiusi misurati quel giorno:

- un mese chiuso con incasso e' **senza merce** (giallo) se fatture + merce
  inserita a mano + quote di riparto del gruppo sono meno del **20%** dell'incasso
  netto. Il costo noto: un bar reale sta al 17,8-19,3% con mesi pieni di fatture,
  e quei mesi diventano gialli;
- un mese chiuso sopra soglia e' **in attesa delle fatture di fine mese** (grigio,
  ne' verde ne' giallo) se ha fatture di merce ma nessuna datata negli ultimi
  **5 giorni** del mese. Al posto del criterio «merce arrivata nel mese dopo»,
  che teneva grigia ogni Home per i primi 5-7 giorni del mese nuovo.

Il mese in corso resta su «nessuna merce»: a meta' mese la merce arriva in
ritardo sull'incasso, e la percentuale lo farebbe giallo tre settimane al mese.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Optional

SOGLIA_MERCE_SU_NETTO = 0.20
GIORNI_FINE_MESE = 5


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


def inizio_fine_mese(anno: int, mese: int) -> date:
    """Il primo dei «5 giorni prima della fine del mese»: il 25 per un mese di
    30 giorni, il 26 per uno di 31, il 23 per febbraio."""
    return date(anno, mese, monthrange(anno, mese)[1] - GIORNI_FINE_MESE)


def in_attesa_fine_mese(
    netto: float, merce: float, *, merce_fatture: float,
    fine_mese_coperta: Optional[bool], in_corso: bool = False,
) -> bool:
    """True = mese chiuso con abbastanza merce, ma nessuna fattura di merce negli
    ultimi giorni (`inizio_fine_mese`): le fatture di fine mese possono mancare.

    Solo per un mese che ha fatture di merce (`merce_fatture` > 0): un mese fatto
    di merce a mano o di sole quote di gruppo non ha una data di fattura, e
    resterebbe grigio per sempre. `fine_mese_coperta` None (non letta) non mette
    in attesa: niente stato inventato.
    """
    if in_corso or fine_mese_coperta is None or fine_mese_coperta:
        return False
    if float(merce_fatture or 0) <= 0:
        return False
    return float(netto or 0) > 0 and not merce_insufficiente(netto, merce)
