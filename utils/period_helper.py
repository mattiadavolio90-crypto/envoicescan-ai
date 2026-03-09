"""
Helper centralizzato per calcolo date periodo.
Evita duplicazione della logica mese/trimestre/semestre/anno in ogni pagina.
"""
from datetime import date


# Opzioni dropdown condivise
PERIODO_OPTIONS = [
    "📅 Mese in Corso",
    "📊 Trimestre in Corso",
    "📈 Semestre in Corso",
    "🗓️ Anno in Corso",
    "⚙️ Periodo Personalizzato"
]


def calcola_date_periodo():
    """
    Calcola le date di inizio per ogni periodo standard.
    
    Returns:
        dict con chiavi: oggi, inizio_mese, inizio_trimestre, inizio_semestre, inizio_anno
    """
    oggi = date.today()
    mese_trim = ((oggi.month - 1) // 3) * 3 + 1
    mese_sem = 1 if oggi.month <= 6 else 7
    
    return {
        'oggi': oggi,
        'inizio_mese': oggi.replace(day=1),
        'inizio_trimestre': oggi.replace(month=mese_trim, day=1),
        'inizio_semestre': oggi.replace(month=mese_sem, day=1),
        'inizio_anno': oggi.replace(month=1, day=1),
    }


def risolvi_periodo(periodo_selezionato: str, date_periodo: dict) -> tuple:
    """
    Dato il periodo selezionato e le date calcolate, restituisce (data_inizio, data_fine, label).
    
    Per "Periodo Personalizzato" restituisce (None, oggi, None) — il chiamante gestisce i date_input.
    """
    oggi = date_periodo['oggi']
    
    if periodo_selezionato == "📅 Mese in Corso":
        d = date_periodo['inizio_mese']
        return d, oggi, f"Mese in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📊 Trimestre in Corso":
        d = date_periodo['inizio_trimestre']
        return d, oggi, f"Trimestre in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "📈 Semestre in Corso":
        d = date_periodo['inizio_semestre']
        return d, oggi, f"Semestre in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    elif periodo_selezionato == "🗓️ Anno in Corso":
        d = date_periodo['inizio_anno']
        return d, oggi, f"Anno in corso ({d.strftime('%d/%m/%Y')} → {oggi.strftime('%d/%m/%Y')})"
    
    else:  # Periodo Personalizzato
        return None, oggi, None
