"""
AI Service - Classificazione Intelligente e Gestione Memoria Prodotti

Gestisce:
- Classificazione automatica prodotti con OpenAI
- Sistema memoria ibrida (admin + locale utente + globale)
- Cache in-memory per eliminare N+1 queries
- Correzioni basate su dizionario keyword
- Retry logic per API OpenAI

ARCHITETTURA MEMORIA (3 livelli):
==============================

1️⃣ MEMORIA ADMIN (classificazioni_manuali)
   - Priorità: MASSIMA
   - Uso: Correzioni manuali amministratore
   - Scope: Globale

2️⃣ MEMORIA LOCALE (prodotti_utente)
   - Priorità: ALTA (dopo admin)
   - Uso: Personalizzazioni cliente specifico
   - Scope: Solo per l'utente proprietario
   - ⭐ QUANDO: Cliente modifica manualmente una categoria

3️⃣ MEMORIA GLOBALE (prodotti_master)
   - Priorità: MEDIA (dopo locale e admin)
   - Uso: Categorizzazioni automatiche condivise
   - Scope: TUTTI i clienti
   - ⭐ QUANDO: AI/Dizionario/Keyword categorizza automaticamente

FLUSSI PRINCIPALI:
==================

📥 CATEGORIZZAZIONE AUTOMATICA (nuovo articolo):
   1. Check memoria admin → se trovato, usa quello
   2. Check memoria locale cliente → se trovato, usa quello
   3. Check memoria globale → se trovato, usa quello
   4. Keyword/Dizionario → categorizza + SALVA in memoria GLOBALE
   5. AI GPT → categorizza + SALVA in memoria GLOBALE

✏️ MODIFICA MANUALE CLIENTE:
   - Salva in memoria LOCALE (prodotti_utente)
   - NON tocca memoria globale
   - Solo il cliente vede la sua personalizzazione
   - Altri clienti continuano a usare memoria globale

🔧 MODIFICA ADMIN (TAB "Memoria Globale"):
   - Salva in memoria GLOBALE (prodotti_master)
   - Propaga a TUTTE le fatture nel database
   - Tutti i clienti futuri vedono la modifica
   - ⚠️ Rispetta personalizzazioni locali esistenti

👁️ ADMIN IMPERSONIFICATO:
   - Comportamento come CLIENTE normale
   - Modifiche salvate in memoria LOCALE del cliente
   - Non impatta altri clienti

Pattern: Dependency Injection per testabilità
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple
import streamlit as st
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, APIError

# Import da moduli interni
from config.constants import DIZIONARIO_CORREZIONI, BRAND_AMBIGUI_NO_DICT, TUTTE_LE_CATEGORIE, MEMORIA_SESSION_CAP, MAX_DESC_LENGTH_DB, MAX_AI_CALLS_PER_DAY, LEGACY_CATEGORY_ALIASES
from utils.text_utils import get_descrizione_normalizzata_e_originale, normalizza_stringa
from utils.validation import is_dicitura_sicura

# Logger centralizzato
from config.logger_setup import get_logger
logger = get_logger('ai')

# ============================================================
# COSTANTI
# ============================================================
MEMORIA_AI_FILE = "memoria_ai_correzioni.json"
RETRIABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, APIError)
MAX_TOKENS_PER_BATCH = 12000  # Limite sicuro per evitare timeout

# ============================================================
# CACHE GLOBALE IN-MEMORY (ELIMINA N+1 QUERY)
# ============================================================
_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 3600  # Ricarica la cache globale dopo 1 ora (evita memory leak a lungo termine)
_memoria_cache = {
    'prodotti_utente': {},         # {user_id: {descrizione: categoria}}
    'prodotti_master': {},         # {descrizione: categoria} — solo confidence alta/altissima → bypass AI
    'prodotti_master_hint': {},    # {descrizione: categoria} — confidence media/None → hint per AI
    'classificazioni_manuali': {},  # {descrizione: {categoria, is_dicitura}}
    'brand_ambigui': set(),        # set di brand dinamici da Supabase (UNION con BRAND_AMBIGUI_NO_DICT)
    'version': 0,               # Incrementato ad ogni invalidazione
    'loaded': False,
    '_loaded_at': 0.0,          # Timestamp ultimo caricamento globale (TTL eviction)
    '_loaded_user_ids': set()   # user_id già caricati (isola dati per utente)
}

# Flag per disabilitare la memoria globale (solo sessione)
_disable_global_memory = False


def _normalize_category_name(categoria: str | None) -> str | None:
    """Converte alias storici cliente nella categoria canonica attuale."""
    if categoria is None:
        return None
    cat = str(categoria).strip()
    if not cat:
        return None
    return LEGACY_CATEGORY_ALIASES.get(cat, cat)


# Regole forti: proteggono da errori grossolani AI/dizionario.
# ORDINE IMPORTANTE: le regole in cima hanno priorità più alta.
# Es. BICCHIER/CALICE deve stare prima di AMARI per non catturare "BICCHIERI AMARO BRAULIO".
# Es. ODK/DE KUYPER (VARIE BAR) deve stare prima di BEVANDE per non catturare "ODK SCIROPPO".
_CATEGORIA_REGEX_FORTI: list[tuple[str, str]] = [
    (
        "MANUTENZIONE E ATTREZZATURE",
        r"\bCAUZIONE\s+FUSTI\b",
    ),
    # --- Priorità alta: oggetti fisici/attrezzature (override AMARI/LIQUORI se contiene BICCHIER/CALICE) ---
    (
        "MANUTENZIONE E ATTREZZATURE",
        r"\b(BICCHIER[EI]?|CALICE|CALICI)\b",
    ),
    # --- Ingredienti/sciroppi da bar (brand specifici) ---
    (
        "VARIE BAR",
        r"\b(ODK|DE KUYPER|DEKUYPER|FABBRI MIXYBAR|DOLCIFICANTE)\b",
    ),
    # --- Alcolici ---
    (
        "DISTILLATI",
        r"\b(GIN|VODKA|WHISKY|WHISKEY|RHUM|RUM|TEQUILA|GRAPPA|BOURBON|COGNAC|MEZCAL|CACHACA|CACHAÇA|ASSENZIO|BRANDY)\b",
    ),
    (
        "AMARI/LIQUORI",
        r"\b(AMARO|LIQUORE|LIMONCELLO|SAMBUCA|JAGERMEISTER|AVERNA|MONTENEGRO|NONINO|KAHLUA|BAILEYS|CYNAR|BRANCAMENTA|FERNET|MIRTO|"
        r"MARASCHINO|APEROL|CAMPARI|ANGOSTURA|PASSOA|CURACAO|TRIPLE SEC|BOLS|PORTO|LILLET|VERMOUTH)\b",
    ),
    (
        "VINI",
        r"\b(VINO|CHIANTI|MONTEPULCIANO|FRANCIACORTA|PROSECCO|MOSCATO|FALANGHINA|GEWURZTRAMINER|PINOT|RIESLING|MERLOT|SYRAH|CABERNET|"
        r"BRUT|CUVEE|LANGHE|BAROLO|BARBARESCO|AMARONE|PRIMITIVO|NEBBIOLO|SANGIOVESE|LAMBRUSCO|DOCG|DOC|IGT|"
        r"PASSERINA|RIBOLLA|VALDOB\w*|PLUM\s+WINE)\b",
    ),
    # --- Birre (BEER escluso: in italiano si usa BIRRA; evita catturare GINGER BEER = BEVANDE) ---
    (
        "BIRRE",
        r"\b(BIRRA|BIRRE|HEINEKEN|ICHNUSA|PERONI|MORETTI|MENABREA|TENNENT|TSINGTAO|NASTRO\s*AZZURRO)\b",
    ),
    # --- Bevande analcoliche (SCIROPPO rimosso: gli sciroppi da bar sono VARIE BAR) ---
    (
        "BEVANDE",
        r"\b(COCA\-COLA|COCA COLA|FANTA|SPRITE|SCHWEPPES|TONICA|GINGER|CEDRATA|ESTATHE|CRODINO|SIFONE|DERBY|ARANCIATA|CHINOTTO|RED BULL|YOGA|BRAVO|PFANNER|NETTARE|NETT\.?|SUCCO)\b",
    ),
    (
        "LATTICINI",
        r"\b(LATTE|MOZZARELLA|BRIE|EDAMER|FETA|OVOLINE)\b",
    ),
    (
        "PASTICCERIA",
        r"\b(PASTICCERIA|CORNETTO|CROISSANT|SFOGLIATELLA|BOMBOLONE|CANNONCINO|KRAPFEN|BIGNE|BRIOCHE)\b",
    ),
    # --- Pesce e frutti di mare (incluso tonno; lo stato di conservazione non cambia la categoria) ---
    (
        "PESCE",
        r"\b(PESCE|SALMON[EI]|TONNO|GAMBERI|GAMBERETTI|GAMBERONE|GAMBERONI|MAZZANCOLL[AE]|ORATA|ORATE|BRANZIN[OI]|SPIGOLA|"
        r"CALAMARI|CALAMARO|POLPO|POLPI|COZZ[AE]|SEPPI[AE]|ACCIUGH[AE]|ALIC[EI]|MERLUZZO|SCAMPI|SCAMPO|"
        r"VONGOL[AE]|BACCALA|ASTICE|ARAGOSTA|FRUTTI\s*DI\s*MARE|RICCI\s*DI\s*MARE|CERNIA|TROTA|DENTICE|"
        r"ROMBO|SOGLIOLA|PLATESSA|PESCE\s*SPADA|SURIMI|CANNOLICCHI[OA]?|RICCIOLA|SCOFANO|CORVINA|CAPPASANTA|OSTRICH\w*|HOKKIGAI|SPUMILIA)\b",
    ),
    # --- Salumi (solo keyword ultra-specifici; COPPA/LONZA/PANCETTA esclusi: troppo ambigui) ---
    (
        "SALUMI",
        r"\b(PROSCIUTT[OI]|PROSC\.|BRESAOLA|MORTADELLA|SPECK|GUANCIALE|NDUJA|SALAME|SALAMI|CULATELLO|LARDO|COPPA\s*DI\s*TESTA)\b",
    ),
]

_CATEGORIE_PLACEHOLDER = {"", "DA CLASSIFICARE"}

# Eccezioni: pattern nel descrizione che BLOCCANO una specifica regola forte.
# Se (desc matcha eccezione_pattern) E (regola target == regola_bloccata) → skip.
_ECCEZIONI_REGOLE: list[tuple[str, str]] = [
    # ACETO DI VINO non è un VINO
    (r"\bACETO\b", "VINI"),
    # CAUZIONE FUSTI non è VINO/BIRRE/BEVANDE
    (r"\bCAUZIONE\b", "VINI"),
    (r"\bCAUZIONE\b", "BIRRE"),
    (r"\bCAUZIONE\b", "BEVANDE"),
    # GIN CO è un brand di caffè/ginseng, non GIN distillato
    (r"\bGIN CO\b", "DISTILLATI"),
    # TAZZA GIN CO = stoviglie, non distillato
    (r"\bTAZZA.+GIN CO\b", "DISTILLATI"),
    # CORSO sul VINO non è un VINO
    (r"\bCORSO\b", "VINI"),
    # CONCHIGLIA/CREMA con LATTE = pasticceria, non latticino
    (r"\bCONCHIGLIA.+LATTE\b", "LATTICINI"),
    (r"\bCREMA.+LATTE\b", "LATTICINI"),
    # VINO DI RISO (condimento asiatico) non è VINO
    (r"\bVINO\s+(DI\s+)?RISO\b", "VINI"),
    # TEA/THE con GINGER = CAFFE E THE, non BEVANDE
    (r"\b(TEA|THE|TE)\b.*\bGINGER\b", "BEVANDE"),
    (r"\bGINGER\b.*\b(TEA|THE|TE)\b", "BEVANDE"),
    # BAILEYS è un liquore cremoso, non DISTILLATI (anche se contiene WHISKY)
    (r"\bBAILEYS\b", "DISTILLATI"),
    # GINGER BEER/ALE non è BIRRE (è bevanda analcolica da bar)
    (r"\bGINGER\b", "BIRRE"),
    # Utensili da cucina (forbici, coltelli) con nomi pesce → MATERIALE/MANUTENZIONE, non PESCE
    (r"\b(FORBICE|FORBICI|COLTELLO|COLTELLI|PINZA|PINZE)\b", "PESCE"),
    # SALMONI/SALMONE con "BRAVO" (brand fornitore pesce) non è una BEVANDA
    (r"\bSALMON\w*\b", "BEVANDE"),
    # INSALATA DI MARE non è VERDURE
    (r"\bINSALATA\s+DI\s+MARE\b", "VERDURE"),
    # Pasta ripiena / dim sum (congelati/secchi) con ingredienti pesce → SECCO, non PESCE
    (r"\b(RAVIOLI|TORTELLI|TORTELLONI|AGNOLOTTI|GIRASOLI|MEZZELUNE|DIMSUM|DIM\s*SUM)\b", "PESCE"),
    # Pasta ripiena (congelata/secca) con ingredienti salumi → SECCO, non SALUMI
    (r"\b(RAVIOLI|TORTELLI|TORTELLONI|AGNOLOTTI|GIRASOLI|MEZZELUNE)\b", "SALUMI"),
    # SALAME DI CIOCCOLATO = PASTICCERIA, non SALUMI
    (r"\bSALAME\b.*\bCIOCCOLAT", "SALUMI"),
]

_MATERIALE_CONSUMO_RE = re.compile(
    r"\b(MONOUSO|USA\s*E\s*GETTA|ASPORTO|TAKEAWAY|TOVAGLIOLI?|POSATE|PIATTI|COPERCHI|CANNUCCE|PALETTE|"
    r"STUZZICADENTI|PELLICOLA|FILM|ALLUMINIO|CARTA\s*FORNO|SACCHETTI?|SACCHI|BUSTE?|"
    r"VASCHE?TTE?|CONTENITORI?|GUANTI|SPUGNE?|DETERSIV\w*|BRILL\w*|LAVASTOV\w*|MOUSSE\s*MANI|"
    r"SALE\s*PASTIGLIE|POMPETTA|TAPPO)\b"
)
_MANUTENZIONE_ATTREZZATURE_RE = re.compile(
    r"\b(MOP|LAVAPAVIMENTI|SECCHIO|CARRELLO|ATTREZZ\w*|MACCHIN\w*|AFFETTATRICE|FRULLATOR\w*|"
    r"ROBOT|PIASTRA|GRIGLIA|LAMA|DISCO|PINZA|PINZE|COLTELLO|COLTELLI|FORBICE|FORBICI|"
    r"PADELLA|PENTOLA|BILANCIA|TERMOMETRO|SPREMIAGRUMI|ERGO|CARAFFA|CARAFFE|BROCCA|BROCCHE)\b"
)
_BICCHIERI_MONOUSO_RE = re.compile(
    r"\b(BICCHIER[EI]?|CALICE|CALICI|TAZZA|TAZZE|COPPA|COPPE)\b.*\b(PLASTICA|CARTA|CARTONE|MONOUSO|ASPORTO|USA\s*E\s*GETTA)\b|"
    r"\b(PLASTICA|CARTA|CARTONE|MONOUSO|ASPORTO|USA\s*E\s*GETTA)\b.*\b(BICCHIER[EI]?|CALICE|CALICI|TAZZA|TAZZE|COPPA|COPPE)\b"
)
_BICCHIERI_DUREVOLI_RE = re.compile(r"\b(BICCHIER[EI]?|CALICE|CALICI|TAZZA|TAZZE|CARAFFA|CARAFFE|BROCCA|BROCCHE)\b")
_COPPA_DUREVOLE_RE = re.compile(
    r"\b(COPPA|COPPE)\b.*\b(MARTINI|VETRO|TIMELESS|ELISIA|BRESK|AMBRA)\b|\b(MARTINI|VETRO|TIMELESS|ELISIA|BRESK|AMBRA)\b.*\b(COPPA|COPPE)\b"
)
_CAFFE_ASPORTO_RE = re.compile(r"\b(COP|BICCH)\w*\b.*\bCAFFE\b.*\bCARTA\b|\bCARTA\b.*\bCAFFE\b")
_TAPPI_FORMATO_RE = re.compile(r"\b(TAPPI?|TAPPO)\b.*\b\d{1,3}\s*[Xx]\s*\d{1,3}\b|\b\d{1,3}\s*[Xx]\s*\d{1,3}\b.*\b(TAPPI?|TAPPO)\b")
_PASTICCERIA_RE = re.compile(
    r"\b(PASTICCERIA|CORNETT[OI]|CROISSANT|SFOGLIATELL[AE]|BOMBOLON[EI]|CANNONCIN[OI]|KRAPFEN|BIGNE|"
    r"BRIOCHE|BRIOCHES|ARAGOSTIN[EI]|CANNOLO|CANNOLI|PAIN\s+AU\s+CHOCOLAT|CONCHIGLIA|FROLLA|SFOGLIA|"
    r"TRECCIA|GIRELLA|CREME\s*BRULEE|CREME\s*BRULE\b|CR[EÈ]ME\s*BR[UÛ]L[EÉ]E|BAO\s+CREMA)\b"
)
_PESCE_RE = re.compile(
    r"\b(PESCE|SALMON[EI]|TONNO|GAMBERI|GAMBERETTI|GAMBERONE|GAMBERONI|MAZZANCOLL[AE]|ORATA|"
    r"ORATE|BRANZIN[OI]|SPIGOLA|CALAMARI|CALAMARO|POLPO|POLPI|COZZ[AE]|SEPPI[AE]|ACCIUGH[AE]|"
    r"ALIC[EI]|MERLUZZO|SCAMPI|SCAMPO|VONGOL[AE]|BACCALA|ASTICE|ARAGOSTA|FRUTTI\s*DI\s*MARE|"
    r"RICCI\s*DI\s*MARE|CERNIA|TROTA|DENTICE|ROMBO|SOGLIOLA|PLATESSA|PESCE\s*SPADA|SURIMI|"
    r"CANNOLICCHI[OA]?|CAVIALE|RICCIOLA|SCOFANO|CORVINA|CAPPASANTA|OSTRICH\w*|HOKKIGAI|SPUMILIA)\b"
)
_SALSA_CREMA_RE = re.compile(
    r"\b(SALSA|SALSE|SUGO|SUGHI|RAGU|RAGÙ|PESTO|BESCIAMELLA|ROUX|CREMA|CREME|FARCITURA|FARCITURE)\b"
)
_PASTA_DI_RE = re.compile(r"\bPASTA\s+DI\b")
_PASTA_CREMA_RE = re.compile(r"\bPASTA\s+(PISTACCHIO|PISTACCHI|NOCCIOLA|NOCCIOLE|NOCI|NOCE|MANDORLA|MANDORLE)\b")
_LIQUORE_CREMA_RE = re.compile(
    r"\b(BAILEYS|LIQUORE|AMARO|WHISKY|WHISKEY|GIN|VODKA|RHUM|RUM|TEQUILA|GRAPPA|BRANDY|COGNAC|"
    r"VERMOUTH|APEROL|CAMPARI|CYNAR|FERNET|MIRTO|SAMBUCA|LIMONCELLO)\b"
)
_VARIE_BAR_RE = re.compile(
    r"\b(ODK|DE\s*KUYPER|DEKUYPER|FABBRI\s*MIXYBAR|MIXYBAR|SCIROPPO\s+ODK|SCIROPPO\s+DE\s*KUYPER|"
    r"SCIROPPO\s+(?:DI\s+)?MANDORL\w*)\b"
)
_CONSERVA_RE = re.compile(
    r"\b(SCATOL\w*|LATTIN\w*|LATTA|BARATTOLO|VASO|CONSERV\w*|SOTT'?OLIO|SOTTACETO|SOTTACETI|"
    r"SALAMOIA|SOTTO\s*SALE|PELATI|POLPA|PASSATA)\b"
)
_VERDURE_PROCESSATE_RE = re.compile(r"\b(IN\s*OLIO|SECCH[IOEA]|CARAMELL\w*|RUSTIC[IOEA]|GRIGLIAT\w*|TRIFOLAT\w*)\b")
_SURGELATO_RE = re.compile(r"\b(SURGELAT\w*|SURG\.?|GELO|CONGELAT\w*|CONG\b)\b")
_AROMI_RE = re.compile(
    r"\b(BASILICO|ROSMARINO|PEPERONCINO|PREZZEMOLO|SALVIA|TIMO|ALLORO|ORIGANO|FINOCCHIETTO|SHISO|CRESS|"
    r"MICRO\s*(?:GREEN|GREENS|HERB|HERBS|LEAF|LEAVES))\b"
)
_DIMSUM_RE = re.compile(r"\b(DIMSUM|DIM\s*SUM)\b")
_YOGURT_RE = re.compile(r"\b(YOGURT|YOGHURT)\b")
_FECOLA_RE = re.compile(r"\bFECOLA\b")
_CAFFE_THE_RE = re.compile(r"\b(TEA|THE|TE\b|TISANA|TISANE|INFUSO|INFUSI)\b")
_BEVANDA_VEGETALE_RE = re.compile(
    r"\b(BEVANDA\s+(?:DI\s+)?)\b.*\b(MANDORL\w*|SOI[AJ]\w*|RISO|AVENA|COCCO|NOCCIOL\w*)\b|"
    r"\b(LATTE\s+DI)\b.*\b(MANDORL\w*|SOI[AJ]\w*|RISO|AVENA|COCCO|NOCCIOL\w*)\b"
)
_LEGUMI_RE = re.compile(r"\b(CECI|LENTICCHIE|FAGIOLI|MAIS|CANNELLINI|BORLOTTI|PISELLI|EDAMAME|FAVE|SOIA)\b")
_VERDURE_RE = re.compile(
    r"\b(PISELLI|PANNOCCHI[EA]|POMODOR\w*|PORRI|SPINACI|VERDUR\w*|CARCIOFI|MELANZAN\w*|ZUCCHIN\w*|PATATE|"
    r"FAGIOLINI|CAVOLFIORE|BROCCOLI|BROCCOLETTI|PEPERONI|CAROTE|ERBETTE|INSALATA|RUCOLA|FUNGH\w*|CIPOLL\w*)\b"
)
_SECCO_RE = re.compile(r"\b(SECC[HOIA]\w*|ESSICCAT\w*|DECORTICAT\w*|BUSTA|BUSTE|SACCHETT\w*|SACCHI|FARINA)\b")
_FORNO_RE = re.compile(r"\b(PIZZA|FOCACCIA|BAGUETTE|CIABATTA|PANE|GRISSINI)\b")
_BEVANDE_ANALCOLICHE_RE = re.compile(
    r"\b(CHINOTTO|ARANCIATA|LIMONATA|CEDRATA|COLA|TONICA|GINGER|SCHWEPPES|CRODINO|ESTATHE|SUCCO|SPREMUTA|"
    r"NETTARE|NETT|YOGA|BRAVO|PFANNER)\b"
)
_ACQUA_CONFEZIONATA_RE = re.compile(
    r"\b((?:ACQ|ACQUA)(?:\s+(?:NATURALE|FRIZZANTE|EFFERVESCENTE|LISCIA))?|(?:ACQ|ACQUA)\s+PANNA|S\.?\s*BENEDETTO|SAN\s*BENEDETTO|"
    r"LEVISSIMA|VERA\b|SAN\s*PELLEGRINO|PAGNACCO|GAUDIANELLO|FERRARELLE|LURISIA|ROCCHETTA|ULIVETO|"
    r"LAURETANA|SANTANNA|S\.?\s*ANNA)\b"
)
_UTENZE_IDRICHE_RE = re.compile(
    r"\b(SERVIZIO\s*IDRICO|FORNITURA\s*IDRICA|ACQUEDOTTO|DEPURAZIONE|FOGNATURA|MATERIA\s*ACQUA|QUOTA\s*FISSA\s*ACQUA|"
    r"CONSUMO\s*IDRICO|ACQUA\s*POTABILE)\b"
)
_UTENZE_LOCALI_RE = re.compile(
    r"\b(ENEL|LUCE|ENERGIA\s*ELETTRICA|GAS|METANO|IDRICO|BOLLETTA|UTENZA|UTENZE|AFFITTO|LOCAZION[EI]|IMMOBILE|"
    r"MUTUO|CONDOMINIO|TARI|IMU|QUOTA\s*FISSA|MATERIA\s*GAS|ONERI\s*DI\s*SISTEMA|SPESA\s*PER\s*LA\s*VENDITA|"
    r"SPESA\s*PER\s*LA\s*TARIFFA|RISCALDAMENTO|CLIMATIZZAZIONE)\b"
)
_CANONE_LOCALE_RE = re.compile(r"\b(CANONE|LOCAZION[EI]|AFFITTO)\b.*\b(LOCALE|LOCALI|IMMOBILE|NEGOZIO|BOX|MAGAZZINO|CONDOMINIO)\b|\b(CANONE\s+LOCAZIONE|AFFITTO\s+LOCALE)\b")
_SERVIZI_CANONI_RE = re.compile(
    r"\b(CANONE|ABBONAMENTO|SERVIZIO|LINEA|FIBRA|ADSL|INTERNET|TELEFONO|TELEFONIA|MOBILE|SIM|VOCE|DATI|POS|RAI|"
    r"VODAFONE|TIM\b|TELECOM|WIND|ILIAD|FASTWEB|VERISURE)\b"
)
_SERVIZI_EXTRA_RE = re.compile(
    r"\b(ARROTONDAMENTO|TRASPORTO|ASSICURAZIONE|PREMIO\s+ASSICURATIVO|AGG\s*ISTAT|ADEGUAMENTO\s*ISTAT|ISTAT)\b"
)
_RIVALSA_BOLLO_RE = re.compile(r"\b(RIVALSA\s+(?:IMPOSTA\s+DI\s+)?BOLLO|IMPOSTA\s+DI\s+BOLLO|RIVALSA\s+BOLLO)\b")
_MANUTENZIONE_CONTRATTO_RE = re.compile(
    r"\b(CANONE\s+MANUTENZIONE|TELEASSISTENZA|CONTRATTO\s+MANUTENZIONE|MANUTENZIONE\s+ORDINARIA)\b"
)
_MANUTENZIONE_GAS_RE = re.compile(
    r"\b(BOMBOLA|BRUCIATORE|ADATTATORE|RIDUTTORE|VALVOLA|CONTENITORI?)\b.*\bGAS\b|\bGAS\b.*\b(BOMBOLA|BRUCIATORE|ADATTATORE|RIDUTTORE|VALVOLA|CONTENITORI?)\b"
)
_INTERVENTO_TECNICO_ATTREZZATURE_RE = re.compile(
    r"\b(RIPARAZION\w*|MANUTENZION\w*|SOSTITUZION\w*|GUASTO|RICAMBIO|ASSISTENZA\s+TECNICA|INTERVENTO\s+TECNICO)\b"
)
_APPARECCHI_CUCINA_RE = re.compile(
    r"\b(CUOCIRAVIOLI|CUCINA|WOK|FORNO|CAPPA|FRIGGITRICE|FRIGGITRIC[EI]|FRIGO|FRIGORIFERO|CELLA|LAVASTOVIGLIE|PIASTRA|BRUCIATORE|UGELLO|PILOTA|TERMOCOPPIA|RUBINETTO\s+GAS)\b"
)
_MANUTENZIONE_LIGHT_RE = re.compile(r"\b(ACCENDIGAS|ZOCCOLINO)\b")
_VARIE_BAR_SERVICE_RE = re.compile(
    r"\b(ZUCCH(?:ERO)?\s*BUSTIN\w*|BUSTIN\w*\s*ZUCCH(?:ERO)?|CIOK\d+\b|CIOCCOLATA\s+(COCCO|PISTACCHIO|FONDENTE))\b"
)
_SANTHE_RE = re.compile(r"\bSAN\s*TH[EÉ']\b|\bSANTHE['’]?\b")
_SUSHI_VARIE_RE = re.compile(r"\b(BAMBU|BAMBOO|NORI|WASABI|PANKO|MASAGO|TOBIKO)\b")
_TAZZE_PIATTI_RE = re.compile(r"\bTAZZE?\b.*\bPIAT\w*\b|\bPIAT\w*\b.*\bTAZZE?\b")
_ACCESSORI_PRODUZIONE_CREMA_RE = re.compile(r"\b(SAC\s*A\s*POCHE|COPPETTA\s*BICAMERA)\b")
_SERVIZI_NORMATIVI_RE = re.compile(r"\b(HACCP|ADEMPIMENTI\s*NORMATIVI|SICUREZZA\s*SUL\s*LAVORO|FORMAZIONE|CERTIFICAT\w*|RINNOVI?)\b")
_AGLIO_CIPOLLA_TRECCIA_RE = re.compile(r"\b(AGLIO|CIP(?:OLLA|OLLE|\.?))\b.*\bTRECCIA\b|\bTRECCIA\b.*\b(AGLIO|CIP(?:OLLA|OLLE|\.?))\b")
_VERDURA_IN_VASCHETTA_RE = re.compile(r"\b(VALERIANA|RUCOLA|INSALATA|SPINACI|ERBETTE)\b.*\b(VASCHE?TTA|VASCHE?TTE|VASC)\b|\b(VASCHE?TTA|VASCHE?TTE|VASC)\b.*\b(VALERIANA|RUCOLA|INSALATA|SPINACI|ERBETTE)\b")
_ARANCE_SPREMUTA_RE = re.compile(r"\bARANC\w*\b.*\bSPREMUTA\b|\bSPREMUTA\b.*\bARANC\w*\b")
_FRUTTA_TROPICALE_RE = re.compile(r"\b(FRUTTA\s+(?:DELLA\s+)?PASION\w*|PASSION\s*FRUIT|MARACU(JA|YA))\b")
_GERMOGLI_SOIA_RE = re.compile(r"\bGERMOGLI\b.*\bSOIA\b|\bSOIA\b.*\bGERMOGLI\b")
_AVOCADO_TRASPORTO_RE = re.compile(r"\bAVOCADO\b.*\bTRASPORTO\s+AEREO\b|\bTRASPORTO\s+AEREO\b.*\bAVOCADO\b")
_CASTAGNE_ACQUA_RE = re.compile(r"\bCASTAGN\w*\b.*\bD\s*[' ]?ACQUA\b|\bD\s*[' ]?ACQUA\b.*\bCASTAGN\w*\b")
_CINGHIALE_RE = re.compile(r"\bCINGHIALE\b")
_PASTA_SFOGLIA_RE = re.compile(r"\bPASTA\s*SFOGLIA\b|\bPASTASFOGLIA\b")
_POLPA_AVOCADO_RE = re.compile(r"\bPOLPA\b.*\bAVOCADO\b|\bAVOCADO\b.*\bPOLPA\b")
_SCIROPPATO_RE = re.compile(r"\bSCIROPPAT\w*\b")
_COPPA_META_RE = re.compile(r"\bCOPPA\b.*\bA\s+META\b|\bA\s+META\b.*\bCOPPA\b")
_DAYGUM_RE = re.compile(r"\bDAYGUM\b")
_DETERGENTE_BRAND_RE = re.compile(r"\b(CIF|CANDEG\w*)\b")
_CROIS_RE = re.compile(r"\bCROIS\b")
_CREMA_CATALANA_RE = re.compile(r"\bCREMA\s+CATALANA\b")
_CASTAGNE_D_ACQUA_RE = re.compile(r"\bCASTAGN\w*\b.*\bD[' ]\s*ACQUA\b|\bD[' ]\s*ACQUA\b.*\bCASTAGN\w*\b")
_LMA_VASC_RE = re.compile(r"\bLMA\b.*\bVASC\b|\bVASC\b.*\bLMA\b")
_COPPA_GELATO_GUSTO_RE = re.compile(r"\bCOPPA\b.*\b(RABBIT|PAN\s*DAN|CIP\s*CIOK)\b|\b(RABBIT|PAN\s*DAN|CIP\s*CIOK)\b.*\bCOPPA\b")
_PRODUCTS_REPORT_RE = re.compile(r"\bPRODUCTS\b\s*\(::")
_PEPE_MACINATO_RE = re.compile(r"PEPE\s+BIANCO\s+MACIN")
_LAMPONI_FORMATO_RE = re.compile(r"\bLAMPONI\b\s*GR\d+")
_FUMO_SHOP_RE = re.compile(r"\b(ELFBAR|LOST\s*MARY|OCB|SMOKING\s+FILTRI|PREFILLED\s+POD|TOCA\s+AIR\s+POD|TP800)\b")
_GINSENG_PREPARATO_RE = re.compile(r"\bPREPARAT\w*\b.*\bGINSENG\b|\bGINSENG\b.*\bPREPARAT\w*\b")
_ALCOHOL_FREE_RE = re.compile(r"\b(ALCOHOL\s*FREE|ANALCOLIC\w*)\b")
_ALCOHOL_FREE_BIRRE_RE = re.compile(r"\b(BIRRA|BIRRE|HEINEKEN|ICHNUSA|PERONI|MORETTI|MENABREA|TENNENT|TSINGTAO|NASTRO\s*AZZURRO)\b")
_ALCOHOL_FREE_VINI_RE = re.compile(r"\b(VINO|CHIANTI|MONTEPULCIANO|FRANCIACORTA|PROSECCO|MOSCATO|FALANGHINA|GEWURZTRAMINER|PINOT|RIESLING|MERLOT|SYRAH|CABERNET|BRUT|CUVEE|LANGHE|BAROLO|BARBARESCO|AMARONE|PRIMITIVO|NEBBIOLO|SANGIOVESE|LAMBRUSCO|DOCG)\b")
_ALCOHOL_FREE_DISTILLATI_RE = re.compile(r"\b(GIN|TANQUERAY|VODKA|WHISKY|WHISKEY|RHUM|RUM|TEQUILA|GRAPPA|BOURBON|COGNAC|MEZCAL|CACHACA|CACHAÇA|ASSENZIO|BRANDY)\b")
_ALCOHOL_FREE_AMARI_RE = re.compile(r"\b(AMARO|LIQUORE|LIMONCELLO|SAMBUCA|JAGERMEISTER|AVERNA|MONTENEGRO|NONINO|KAHLUA|BAILEYS|CYNAR|BRANCAMENTA|FERNET|MIRTO|MARASCHINO|APEROL|CAMPARI|ANGOSTURA|PASSOA|CURACAO|TRIPLE\s+SEC|BOLS|PORTO|LILLET|VERMOUTH)\b")
_CREAMI_RICARICA_RE = re.compile(r"\bCREAMI\b.*\bRICARICA\b|\bRICARICA\b.*\bCREAMI\b")
_CREAMI_DISPENSER_RE = re.compile(r"\bCREAMI\b.*\bDISPENSER\b|\bDISPENSER\b.*\bCREAMI\b")
_BLEND_T_FILTRI_RE = re.compile(r"\bBLEND\b.*\bT\b.*\bFILTRI?\b|\bFILTRI?\b.*\bBLEND\b.*\bT\b")
_LATTIERA_RE = re.compile(r"\bLATTIERA\b")
_TOPPING_CACAO_RE = re.compile(r"\bTOPPING\b.*\b(CIOCCOLAT\w*|CACAO)\b|\b(CIOCCOLAT\w*|CACAO)\b.*\bTOPPING\b")
_TOPPING_BAR_RE = re.compile(
    r"\bTOPPING\b.*\b(TOSCHI|FRUTTI?\s+DI\s+BOSCO|FRUTT\w*\s+BOSCO|PISTACCH\w*|CARAMELL\w*|VANIGL\w*)\b|"
    r"\b(TOSCHI|FRUTTI?\s+DI\s+BOSCO|FRUTT\w*\s+BOSCO|PISTACCH\w*|CARAMELL\w*|VANIGL\w*)\b.*\bTOPPING\b"
)
_VASSOIO_ESPOSIZIONE_RE = re.compile(r"\bVASSOIO\b.*\bESPOSIZION\w*\b|\bESPOSIZION\w*\b.*\bVASSOIO\b")
_ORZO_BAR_RE = re.compile(r"\bORZO\b.*\b(\d+\s*GR|GR\s*\d+|SOLUBILE)\b|\b(\d+\s*GR|GR\s*\d+|SOLUBILE)\b.*\bORZO\b")
_VERISURE_HARDWARE_RE = re.compile(
    r"\b(KIT\s*BASE|UPGRADE\s+AD\s+ALTA\s+SICUREZZA|ZEROVISION|PACK\s+PROTEZIONE|PACK\s+SOS|SENSORE\s+DI\s+MOVIMENTO\s+CERTIFICATO)\b"
)

# --- Regole prodotti comuni che l'AI spesso sbaglia ---
_TERRA_VITA_RE = re.compile(r"\bTERRA\s*&\s*VITA\b")
_PROVOLONE_ABBREV_RE = re.compile(r"\bPROVOL\.?\b")
_GALBANINO_BIRAGHI_RE = re.compile(r"\b(GALBANINO|BIRAGHINI|GRANBIRAGHI|BIRAGHI)\b")
_FORMAGGIO_SPALMABILE_RE = re.compile(r"\bFORM\.?\s*(FRESCO|SPALMABILE)\b|\bSPALMABILE\b.*\b(FORM|FORMAGG)")
_GRATTUGGIATO_RE = re.compile(r"\bGRATTUGGIAT[OA]\b")
_ORTOFRUTTA_RE = re.compile(r"\bORTOFRUTTA\b")
_BONDUELLE_RE = re.compile(r"\bBONDUELLE\b")
_MAIS_PISELLI_RE = re.compile(r"\b(MAIS|PISELLI)\b.*\b(BONDUELLE|SIGMA|TRIS|LATTINA)\b|\b(BONDUELLE|SIGMA)\b.*\b(MAIS|PISELLI)\b")
_CIPOLLINE_CONSERVA_RE = re.compile(r"\bCIPOLLINE\b.*\b(SACLA|BARATTOL|GR\.?\d|AGRODOLC)\b|\b(SACLA|BARATTOL)\b.*\bCIPOLLINE\b")
_ERBETTE_RE = re.compile(r"\bERBETTE\b")
_PULYCAFF_RE = re.compile(r"\bPULY\s*(CAFF|MILK)\b")
_BRITA_FILTRO_RE = re.compile(r"\bBRITA\b|\bPURITY\b.*\bCARTUCCIA\b|\bCARTUCCIA\b.*\bFILTR")
_STOPPER_RE = re.compile(r"\bSTOPPER\b")
_PENNA_LATTE_ART_RE = re.compile(r"\bPENNA\b.*\bLATTE\s*ART\b")
_TEIERA_TAZZONE_RE = re.compile(r"\b(TEIERA|TAZZONE)\b")
_COPPA_MAROCCHINO_RE = re.compile(r"\bCOPPA\b.*\bMAROCCHINO\b|\bMAROCCHINO\b.*\bCOPPA\b")
_TORTILLA_RE = re.compile(r"\bTORTILLA\b")
_CACAO_POLVERE_RE = re.compile(r"\bCACAO\b.*\b(KG|GR|POLV|\d)\b|\bCACAO\b\s+\d")
_FRUTTI_BOSCO_RE = re.compile(r"\bFRUTTI\s+DI\s+BOSCO\b|\bFRUTT\w*\s+BOSCO\b")
_SPIANATA_RE = re.compile(r"\bSPIANATA\b")
_MIELE_BUSTINE_RE = re.compile(r"\bMIELE\b.*\bBUSTIN\w*\b|\bBUSTIN\w*\b.*\bMIELE\b|\bCONFEZIONE\s+MIELE\b")
_CIOCCOLATA_CALDA_RE = re.compile(r"\bCIOCCOLATA\b.*\b(MONODOS|CALDA|LATTE|PREPARATO)\b|\bMONODOS\w*\b.*\bCIOCCOLAT")
_VINO_DOC_RE = re.compile(r"\b(DOC|DOCG|IGT)\b.*\b(CL\s*75|75\s*CL)\b|\b(CL\s*75|75\s*CL)\b.*\b(DOC|DOCG|IGT)\b")
_PIADA_RE = re.compile(r"\bPIAD[AE]\b")
_SALE_ALIMENTARE_RE = re.compile(r"\bSALE\b.*\b(IODATO|FINO|GROSSO|MARINO)\b")
_VANIGLIA_BACCA_RE = re.compile(r"\b(VANIGLIA|BACCA\s+VANIGLIA)\b")
_NOCI_PISTACCHIO_SECCO_RE = re.compile(r"\b(NOCI\s+SGUSCIAT|PISTACCHI\w*\s+(CALIF|TOST|SGUS|INTERO))\b")
_NON_FOOD_RE = re.compile(r"\bNON\s*FOOD\b")

# --- Regole audit anomalie categorizzazione ---
_SALVIETTA_TNT_RE = re.compile(r"\bSALV\w*\b.*\bTNT\b|\bTNT\b.*\bSALV\w*\b")
_MOCCHI_MOCHI_RE = re.compile(r"\b(MOCCHI|MOCHI)\b")
_BURRATA_RE = re.compile(r"\bBURRAT[AE]\b")
_OLIO_EXV_RE = re.compile(r"\bOLIO\s+EX(TRA)?V\w*\b")
_RAVIOLI_GRIGLIA_CARNE_RE = re.compile(r"\bRAVIOLI\b.*\bGRIGLIA\b.*\b(CARNE|MAIALE)\b")
_CONTRIBUTO_CONSEGNA_RE = re.compile(r"\bCONTRIBUTO\s+SPESE\b.*\bCONSEGNA\b|\bSPESE\s+DI\s+CONSEGNA\b")
_CAPRICCIOSA_SECCHIO_RE = re.compile(r"\bCAPRICCIOSA\b.*\bSECCHIO\b|\bSECCHIO\b.*\bCAPRICCIOSA\b")
_YOUTIAO_RE = re.compile(r"\bYOUTIAO\b")
_WOSUN_RE = re.compile(r"\bWOSUN\b")
_GUACAMOLE_RE = re.compile(r"\bGUACA\w*\b")
_CONCENTRATO_POMODORO_RE = re.compile(r"\b(DOPPIO\s+)?CONCENTRATO\b.*\bMUTTI\b|\bMUTTI\b.*\bCONCENTRATO\b")
_OVINO_RE = re.compile(r"\b(OVINO|AGNELLO|AGNELL\w*)\b")
_INSALATA_MARE_RE = re.compile(r"\bINSALATA\s+DI\s+MARE\b")
_CODA_SMARIA_RE = re.compile(r"\bCODA\b.*\bS\.?\s*MARIA\b")
_GRANELLA_PISTACCHIO_RE = re.compile(r"\bGRANELLA\b.*\bPISTACCH\w*\b")
_TOFU_GENERICO_RE = re.compile(r"\b(TOFU|TOUFU|DOUFU)\b")
_TOFU_PESCE_RE = re.compile(r"\b(SEAFOOD|FISH|PESCE)\b.*\b(TOFU|TOUFU)\b|\b(TOFU|TOUFU)\b.*\b(SEAFOOD|FISH|PESCE|DI\s+PESCE)\b")
_CIMI_BIMBA_RE = re.compile(r"\bCIMI\s+DI\s+BIMBA\b")

# Regole forti che devono battere cache locali/globali automatiche errate.
# Non include la memoria admin, che resta prioritaria e intenzionale.
_NON_NEGOZIABILI_CACHE_OVERRIDE = {
    "ingrediente_bar_specifico",
    "capricciosa_secchio_conserva",
    "topping_bar_specifico",
}


def applica_regole_categoria_forti(descrizione: str, categoria_predetta: str) -> Tuple[str, Optional[str]]:
    """
    Applica regole deterministiche ad alta confidenza per evitare errori grossolani.

    Returns:
        (categoria_finale, motivo_override)
    """
    desc = (descrizione or "").strip()
    cat = (categoria_predetta or "Da Classificare").strip()
    desc_u = desc.upper()
    cat_u = cat.upper()

    if not desc:
        return cat, None

    if desc_u in {"OMAGGIO", "SPESE FISSE"}:
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, f"termine_ambiguo:{desc_u}"
        return cat, None

    if _CASTAGNE_ACQUA_RE.search(desc_u) or _CASTAGNE_D_ACQUA_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "castagne_d_acqua_conserva"
        return cat, None

    if _ACQUA_CONFEZIONATA_RE.search(desc_u) and not _UTENZE_IDRICHE_RE.search(desc_u) and not _BEVANDE_ANALCOLICHE_RE.search(desc_u):
        mapped = "ACQUA"
        if cat != mapped:
            return mapped, "acqua_confezionata"
        return cat, None

    if _UTENZE_IDRICHE_RE.search(desc_u):
        mapped = "UTENZE E LOCALI"
        if cat != mapped:
            return mapped, "utenza_idrica"
        return cat, None

    if _MANUTENZIONE_GAS_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "gas_come_attrezzatura"
        return cat, None

    if _MANUTENZIONE_LIGHT_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "attrezzatura_leggera"
        return cat, None

    # Hardware sicurezza: deve battere la keyword generica "CERTIFICATO" usata in ambito normativo.
    if _VERISURE_HARDWARE_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "hardware_sicurezza"
        return cat, None

    # --- Regole audit: correzioni anomalie categorizzazione ---

    # Salviette/tovaglioli TNT → materiale di consumo (non frutta per "LIMONE")
    if _SALVIETTA_TNT_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "salvietta_tnt_consumo"
        return cat, None

    # MOCCHI/MOCHI (gelato/dessert) → pasticceria
    if _MOCCHI_MOCHI_RE.search(desc_u):
        mapped = "PASTICCERIA"
        if cat != mapped:
            return mapped, "mochi_pasticceria"
        return cat, None

    # Burrate → latticini (non servizi/materiale)
    if _BURRATA_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "burrata_latticino"
        return cat, None

    # Santhe/SanThé pesca-limone → bevande (non frutta)
    if _SANTHE_RE.search(desc_u):
        mapped = "BEVANDE"
        if cat != mapped:
            return mapped, "santhe_bevanda"
        return cat, None

    # Olio extravergine → olio e condimenti (non materiale di consumo)
    if _OLIO_EXV_RE.search(desc_u):
        mapped = "OLIO E CONDIMENTI"
        if cat != mapped:
            return mapped, "olio_extravergine"
        return cat, None

    # Ravioli alla griglia di carne/maiale → carne (non manutenzione)
    if _RAVIOLI_GRIGLIA_CARNE_RE.search(desc_u):
        mapped = "CARNE"
        if cat != mapped:
            return mapped, "ravioli_griglia_carne"
        return cat, None

    # Contributo/spese di consegna → servizi (non gelati)
    if _CONTRIBUTO_CONSEGNA_RE.search(desc_u):
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, "contributo_consegna_servizio"
        return cat, None

    # Insalata capricciosa in secchio → scatolame (non manutenzione)
    if _CAPRICCIOSA_SECCHIO_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "capricciosa_secchio_conserva"
        return cat, None

    # Concentrato di pomodoro Mutti → scatolame (non pasticceria)
    if _CONCENTRATO_POMODORO_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "concentrato_mutti_conserva"
        return cat, None

    # Youtiao (frittella cinese) → prodotti da forno
    if _YOUTIAO_RE.search(desc_u):
        mapped = "PRODOTTI DA FORNO"
        if cat != mapped:
            return mapped, "youtiao_forno"
        return cat, None

    # Wosun (verdura cinese) → verdure
    if _WOSUN_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "wosun_verdura"
        return cat, None

    # Cimi di bimba (cime di rapa, typo) → verdure
    if _CIMI_BIMBA_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "cimi_bimba_verdura"
        return cat, None

    # Guacamole/salsa guaca → salse e creme
    if _GUACAMOLE_RE.search(desc_u):
        mapped = "SALSE E CREME"
        if cat != mapped:
            return mapped, "guacamole_salsa"
        return cat, None

    # Ovino/agnello → carne (non pesce)
    if _OVINO_RE.search(desc_u):
        mapped = "CARNE"
        if cat != mapped:
            return mapped, "ovino_agnello_carne"
        return cat, None

    # Insalata di mare → pesce (non verdure)
    if _INSALATA_MARE_RE.search(desc_u):
        mapped = "PESCE"
        if cat != mapped:
            return mapped, "insalata_mare_pesce"
        return cat, None

    # Coda S.Maria (code mazzancolle) → pesce (non carne)
    if _CODA_SMARIA_RE.search(desc_u):
        mapped = "PESCE"
        if cat != mapped:
            return mapped, "coda_smaria_pesce"
        return cat, None

    # Granella di pistacchio → spezie e aromi (non materiale)
    if _GRANELLA_PISTACCHIO_RE.search(desc_u):
        mapped = "SPEZIE E AROMI"
        if cat != mapped:
            return mapped, "granella_pistacchio_spezia"
        return cat, None

    # Tofu/toufu/doufu generico → latticini (ma NON se è seafood/fish tofu)
    if _TOFU_GENERICO_RE.search(desc_u) and not _TOFU_PESCE_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "tofu_latticino"
        return cat, None

    # --- Fine regole audit ---

    if _SERVIZI_NORMATIVI_RE.search(desc_u):
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, "servizio_normativo"
        return cat, None

    if _DAYGUM_RE.search(desc_u):
        mapped = "SHOP"
        if cat != mapped:
            return mapped, "gomma_confezionata_shop"
        return cat, None

    if _FUMO_SHOP_RE.search(desc_u):
        mapped = "SHOP"
        if cat != mapped:
            return mapped, "articolo_fumo_shop"
        return cat, None

    if _GINSENG_PREPARATO_RE.search(desc_u):
        mapped = "CAFFE E THE"
        if cat != mapped:
            return mapped, "preparato_ginseng"
        return cat, None

    if _CREAMI_RICARICA_RE.search(desc_u):
        mapped = "PASTICCERIA"
        if cat != mapped:
            return mapped, "creami_ricarica_dolciaria"
        return cat, None

    if _CREAMI_DISPENSER_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "creami_dispenser_attrezzatura"
        return cat, None

    if _BLEND_T_FILTRI_RE.search(desc_u):
        mapped = "CAFFE E THE"
        if cat != mapped:
            return mapped, "blend_t_filtri_infusione"
        return cat, None

    if _LATTIERA_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "lattiera_linea_latticini"
        return cat, None

    if _TOPPING_CACAO_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "topping_cacao_bar"
        return cat, None

    if _TOPPING_BAR_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "topping_bar_specifico"
        return cat, None

    if _VASSOIO_ESPOSIZIONE_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "vassoio_esposizione_durevole"
        return cat, None

    if _ORZO_BAR_RE.search(desc_u):
        mapped = "CAFFE E THE"
        if cat != mapped:
            return mapped, "orzo_linea_bar"
        return cat, None

    # Brand/intrugli bar devono vincere prima di match generici come frutta o aromi.
    if _VARIE_BAR_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "ingrediente_bar_specifico"
        return cat, None

    # --- Regole prodotti comuni che l'AI spesso sbaglia ---

    if _TERRA_VITA_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "terra_vita_insalate"
        return cat, None

    if _PENNA_LATTE_ART_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "utensile_latte_art"
        return cat, None

    if _STOPPER_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "accessorio_stopper"
        return cat, None

    if _PROVOLONE_ABBREV_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "provolone_latticino"
        return cat, None

    if _GALBANINO_BIRAGHI_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "formaggio_brand_italiano"
        return cat, None

    if _FORMAGGIO_SPALMABILE_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "formaggio_spalmabile"
        return cat, None

    if _GRATTUGGIATO_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "formaggio_grattugiato"
        return cat, None

    if _ORTOFRUTTA_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "ortofrutta_generica"
        return cat, None

    if _BONDUELLE_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "bonduelle_conserve"
        return cat, None

    if _MAIS_PISELLI_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "mais_piselli_conserva"
        return cat, None

    if _CIPOLLINE_CONSERVA_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "cipolline_conserva"
        return cat, None

    if _ERBETTE_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "erbette_verdura"
        return cat, None

    if _PULYCAFF_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "pulizia_macchina_caffe"
        return cat, None

    if _BRITA_FILTRO_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "filtro_acqua_attrezzatura"
        return cat, None

    if _TEIERA_TAZZONE_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "contenitore_durevole"
        return cat, None

    if _COPPA_MAROCCHINO_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "coppa_marocchino_vetro"
        return cat, None

    if _TORTILLA_RE.search(desc_u):
        mapped = "PRODOTTI DA FORNO"
        if cat != mapped:
            return mapped, "tortilla_forno"
        return cat, None

    if _PIADA_RE.search(desc_u):
        mapped = "PRODOTTI DA FORNO"
        if cat != mapped:
            return mapped, "piadina_forno"
        return cat, None

    if _CACAO_POLVERE_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "cacao_polvere_bar"
        return cat, None

    if _CIOCCOLATA_CALDA_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "cioccolata_calda_bar"
        return cat, None

    if _MIELE_BUSTINE_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "miele_bustine_bar"
        return cat, None

    if _FRUTTI_BOSCO_RE.search(desc_u):
        mapped = "FRUTTA"
        if cat != mapped:
            return mapped, "frutti_bosco_frutta"
        return cat, None

    if _SPIANATA_RE.search(desc_u):
        mapped = "SALUMI"
        if cat != mapped:
            return mapped, "spianata_salume"
        return cat, None

    if _VINO_DOC_RE.search(desc_u):
        mapped = "VINI"
        if cat != mapped:
            return mapped, "vino_doc_denominazione"
        return cat, None

    if _SALE_ALIMENTARE_RE.search(desc_u):
        mapped = "SECCO"
        if cat != mapped:
            return mapped, "sale_alimentare"
        return cat, None

    if _VANIGLIA_BACCA_RE.search(desc_u):
        mapped = "SPEZIE E AROMI"
        if cat != mapped:
            return mapped, "vaniglia_spezia"
        return cat, None

    if _NOCI_PISTACCHIO_SECCO_RE.search(desc_u):
        mapped = "SECCO"
        if cat != mapped:
            return mapped, "frutta_secca_guscio"
        return cat, None

    if _NON_FOOD_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "articolo_non_food"
        return cat, None

    if _ALCOHOL_FREE_RE.search(desc_u):
        if _ALCOHOL_FREE_BIRRE_RE.search(desc_u):
            mapped = "BIRRE"
            if cat != mapped:
                return mapped, "alcohol_free_birra"
            return cat, None
        if _ALCOHOL_FREE_VINI_RE.search(desc_u):
            mapped = "VINI"
            if cat != mapped:
                return mapped, "alcohol_free_vino"
            return cat, None
        if _ALCOHOL_FREE_DISTILLATI_RE.search(desc_u):
            mapped = "DISTILLATI"
            if cat != mapped:
                return mapped, "alcohol_free_distillato"
            return cat, None
        if _ALCOHOL_FREE_AMARI_RE.search(desc_u):
            mapped = "AMARI/LIQUORI"
            if cat != mapped:
                return mapped, "alcohol_free_liquore"
            return cat, None

    if _DETERGENTE_BRAND_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "detergente_marca"
        return cat, None

    if _CROIS_RE.search(desc_u):
        mapped = "PASTICCERIA"
        if cat != mapped:
            return mapped, "abbreviazione_croissant"
        return cat, None

    if _CREMA_CATALANA_RE.search(desc_u):
        mapped = "PASTICCERIA"
        if cat != mapped:
            return mapped, "dessert_crema_catalana"
        return cat, None

    if _PRODUCTS_REPORT_RE.search(desc_u):
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, "reporting_piattaforma"
        return cat, None

    if _LAMPONI_FORMATO_RE.search(desc_u):
        mapped = "FRUTTA"
        if cat != mapped:
            return mapped, "frutta_fresca_formato"
        return cat, None

    if _PEPE_MACINATO_RE.search(desc_u):
        mapped = "SPEZIE E AROMI"
        if cat != mapped:
            return mapped, "spezia_macinata"
        return cat, None

    if _LMA_VASC_RE.search(desc_u):
        mapped = "GELATI"
        if cat != mapped:
            return mapped, "linea_gelato_vasca"
        return cat, None

    if _COPPA_GELATO_GUSTO_RE.search(desc_u):
        mapped = "GELATI"
        if cat != mapped:
            return mapped, "coppa_gelato_gusto"
        return cat, None

    if _CINGHIALE_RE.search(desc_u):
        mapped = "CARNE"
        if cat != mapped:
            return mapped, "carne_selvaggina"
        return cat, None

    if _COPPA_META_RE.search(desc_u):
        mapped = "SALUMI"
        if cat != mapped:
            return mapped, "coppa_salume"
        return cat, None

    if _AGLIO_CIPOLLA_TRECCIA_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "treccia_ortaggio"
        return cat, None

    if _VERDURA_IN_VASCHETTA_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "verdura_in_confezione"
        return cat, None

    if _ARANCE_SPREMUTA_RE.search(desc_u):
        mapped = "FRUTTA"
        if cat != mapped:
            return mapped, "frutta_per_spremuta"
        return cat, None

    if _FRUTTA_TROPICALE_RE.search(desc_u):
        mapped = "FRUTTA"
        if cat != mapped:
            return mapped, "frutta_tropicale"
        return cat, None

    if _GERMOGLI_SOIA_RE.search(desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "germogli_soia_verdura"
        return cat, None

    if _AVOCADO_TRASPORTO_RE.search(desc_u):
        mapped = "FRUTTA"
        if cat != mapped:
            return mapped, "frutta_con_descrittore_logistico"
        return cat, None

    if _PASTA_SFOGLIA_RE.search(desc_u):
        mapped = "PRODOTTI DA FORNO"
        if cat != mapped:
            return mapped, "impasto_sfoglia_forno"
        return cat, None

    if _POLPA_AVOCADO_RE.search(desc_u):
        mapped = "FRUTTA"
        if cat != mapped:
            return mapped, "polpa_frutta_specifica"
        return cat, None

    if _MANUTENZIONE_CONTRATTO_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "contratto_manutenzione"
        return cat, None

    if _RIVALSA_BOLLO_RE.search(desc_u):
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, "rivalsa_bollo_servizio"
        return cat, None

    if _INTERVENTO_TECNICO_ATTREZZATURE_RE.search(desc_u) and _APPARECCHI_CUCINA_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "intervento_tecnico_attrezzatura"
        return cat, None

    if _SERVIZI_EXTRA_RE.search(desc_u):
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, "servizio_accessorio"
        return cat, None

    if _CANONE_LOCALE_RE.search(desc_u):
        mapped = "UTENZE E LOCALI"
        if cat != mapped:
            return mapped, "canone_immobile"
        return cat, None

    if _SERVIZI_CANONI_RE.search(desc_u) and not _CANONE_LOCALE_RE.search(desc_u):
        mapped = "SERVIZI E CONSULENZE"
        if cat != mapped:
            return mapped, "canone_o_servizio"
        return cat, None

    if _UTENZE_LOCALI_RE.search(desc_u):
        mapped = "UTENZE E LOCALI"
        if cat != mapped:
            return mapped, "utenza_o_locazione"
        return cat, None

    if _TAPPI_FORMATO_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "tappi_formato_consumabile"
        return cat, None

    if _CAFFE_ASPORTO_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "caffe_asporto_consumabile"
        return cat, None

    if _VARIE_BAR_SERVICE_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "servizio_bar"
        return cat, None

    if _TAZZE_PIATTI_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "servizio_tazze_piatti"
        return cat, None

    if _COPPA_DUREVOLE_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "coppa_contenitore_durevole"
        return cat, None

    if _ACCESSORI_PRODUZIONE_CREMA_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "accessorio_produzione"
        return cat, None

    if _BICCHIERI_MONOUSO_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "bicchiere_monouso"
        return cat, None

    if _BICCHIERI_DUREVOLI_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "bicchiere_o_caraffa_durevole"
        return cat, None

    if _MATERIALE_CONSUMO_RE.search(desc_u):
        mapped = "MATERIALE DI CONSUMO"
        if cat != mapped:
            return mapped, "consumo_rapido_monouso"
        return cat, None

    if _MANUTENZIONE_ATTREZZATURE_RE.search(desc_u):
        mapped = "MANUTENZIONE E ATTREZZATURE"
        if cat != mapped:
            return mapped, "fornitura_durevole"
        return cat, None

    if _VARIE_BAR_RE.search(desc_u):
        mapped = "VARIE BAR"
        if cat != mapped:
            return mapped, "ingrediente_bar_specifico"
        return cat, None

    if _SUSHI_VARIE_RE.search(desc_u):
        mapped = "SUSHI VARIE"
        if cat != mapped:
            return mapped, "ingrediente_o_tool_sushi"
        return cat, None

    if _YOGURT_RE.search(desc_u):
        mapped = "LATTICINI"
        if cat != mapped:
            return mapped, "yogurt_latticino"
        return cat, None

    if _FECOLA_RE.search(desc_u):
        mapped = "SECCO"
        if cat != mapped:
            return mapped, "fecola_amido_secco"
        return cat, None

    if _BEVANDA_VEGETALE_RE.search(desc_u):
        mapped = "BEVANDE"
        if cat != mapped:
            return mapped, "bevanda_vegetale_pronta"
        return cat, None

    if _SCIROPPATO_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "prodotto_sciroppato"
        return cat, None

    if _CAFFE_THE_RE.search(desc_u):
        mapped = "CAFFE E THE"
        if cat != mapped:
            return mapped, "prodotto_tisana_the_caffe"
        return cat, None

    if _CONSERVA_RE.search(desc_u) and re.search(r"\b(PASSATA|PASSATE|PELATI|POLPA)\b", desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "prodotto_lavorato_conservato"
        return cat, None

    if _FORNO_RE.search(desc_u) and (_SURGELATO_RE.search(desc_u) or re.search(r"\bPIZZA\b", desc_u)):
        mapped = "PRODOTTI DA FORNO"
        if cat != mapped:
            return mapped, "forno_anche_surgelato"
        return cat, None

    if _DIMSUM_RE.search(desc_u):
        mapped = "SECCO"
        if cat != mapped:
            return mapped, "dimsum_come_raviolo"
        return cat, None

    if _PASTICCERIA_RE.search(desc_u) and _SALSA_CREMA_RE.search(desc_u):
        mapped = "PASTICCERIA"
        if cat != mapped:
            return mapped, "dolce_con_crema"
        return cat, None

    if re.search(r"\bSALSA\b", desc_u) and _PESCE_RE.search(desc_u):
        mapped = "SALSE E CREME"
        if cat != mapped:
            return mapped, "salsa_base_pesce"
        return cat, None

    if _PASTA_DI_RE.search(desc_u) and _PESCE_RE.search(desc_u):
        mapped = "PESCE"
        if cat != mapped:
            return mapped, "pasta_di_pesce"
        return cat, None

    if _PESCE_RE.search(desc_u):
        mapped = "PESCE"
        if cat != mapped:
            return mapped, "pesce_in_qualsiasi_stato"
        return cat, None

    if (_SALSA_CREMA_RE.search(desc_u) or _PASTA_DI_RE.search(desc_u) or _PASTA_CREMA_RE.search(desc_u)) and not _LIQUORE_CREMA_RE.search(desc_u):
        mapped = "SALSE E CREME"
        if cat != mapped:
            return mapped, "base_salsa_crema"
        return cat, None

    if _AROMI_RE.search(desc_u):
        mapped = "SPEZIE E AROMI"
        if cat != mapped:
            return mapped, "aroma_fresco_o_secco"
        return cat, None

    if _SURGELATO_RE.search(desc_u) and (_VERDURE_RE.search(desc_u) or _LEGUMI_RE.search(desc_u)):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "verdura_surgelata"
        return cat, None

    if _VERDURE_RE.search(desc_u) and _VERDURE_PROCESSATE_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "verdura_processata"
        return cat, None

    if _LEGUMI_RE.search(desc_u) and _SECCO_RE.search(desc_u):
        mapped = "SECCO"
        if cat != mapped:
            return mapped, "legume_secco_o_farina"
        return cat, None

    if (_LEGUMI_RE.search(desc_u) or _VERDURE_RE.search(desc_u)) and _CONSERVA_RE.search(desc_u):
        mapped = "SCATOLAME E CONSERVE"
        if cat != mapped:
            return mapped, "vegetale_conservato"
        return cat, None

    if re.search(r"\bPANNOCCHI[EA]\b", desc_u):
        mapped = "VERDURE"
        if cat != mapped:
            return mapped, "verdura_raw"
        return cat, None

    for expected, pattern in _CATEGORIA_REGEX_FORTI:
        if not re.search(pattern, desc_u):
            continue

        # Controlla eccezioni: se la descrizione matcha un'eccezione per questa regola, skip
        blocked = False
        for exc_pattern, exc_rule in _ECCEZIONI_REGOLE:
            if exc_rule == expected and re.search(exc_pattern, desc_u):
                blocked = True
                break
        if blocked:
            continue

        if cat_u in _CATEGORIE_PLACEHOLDER or cat_u != expected:
            return expected, f"regola_forte:{expected}"
        return cat, None

    return cat, None

def set_global_memory_enabled(enabled: bool):
    """
    Abilita/Disabilita l'uso della memoria globale (prodotti_master) in questa sessione.
    Utile per testare la logica senza influenze della memoria condivisa.
    """
    global _disable_global_memory
    _disable_global_memory = not enabled
    state = "DISABILITATA" if _disable_global_memory else "ABILITATA"
    logger.info(f"⚙️ Memoria Globale: {state}")


# ============================================================
# INIZIALIZZAZIONE OPENAI CLIENT
# ============================================================
@st.cache_resource
def _get_openai_client() -> OpenAI:
    """
    Ottiene client OpenAI singleton (cached).
    
    Returns:
        OpenAI: Client inizializzato e cached per tutta la sessione
        
    Raises:
        ValueError: Se API key non trovata in secrets
    """
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception as e:
        logger.exception("API Key OpenAI non trovata")
        raise ValueError("API Key OpenAI mancante") from e
    
    return OpenAI(api_key=api_key)


# ============================================================
# FUNZIONI MEMORIA CACHE
# ============================================================

_PAGE_SIZE = 1000  # Supabase default limit


def _fetch_all_rows(supabase_client, table: str, select: str, filters: dict | None = None) -> list:
    """Paginazione generica per superare il limite di 1000 righe di Supabase."""
    all_rows = []
    offset = 0
    while True:
        q = supabase_client.table(table).select(select)
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        result = q.range(offset, offset + _PAGE_SIZE - 1).execute()
        batch = result.data or []
        all_rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return all_rows


def carica_memoria_completa(user_id: str, supabase_client=None) -> Dict[str, Any]:
    """
    Carica TUTTE le memorie in una volta sola (1 query per tabella invece di N query).
    Elimina completamente il problema N+1 query.
    
    Args:
        user_id: UUID utente corrente
        supabase_client: Client Supabase (opzionale, usa default se None)
    
    Returns:
        dict: Cache completa con tutte le memorie
    """
    global _memoria_cache
    
    with _cache_lock:
        global_loaded = _memoria_cache['loaded']
        # TTL eviction: se la cache globale è scaduta, forza ricaricamento
        if global_loaded and (time.time() - _memoria_cache.get('_loaded_at', 0.0)) > _CACHE_TTL_SECONDS:
            logger.info("Cache globale scaduta (TTL 1h), forzo ricaricamento")
            _memoria_cache['loaded'] = False
            _memoria_cache['_loaded_at'] = 0.0
            global_loaded = False
        user_already_loaded = user_id in _memoria_cache.get('_loaded_user_ids', set())

    # I due stati sono gestiti indipendentemente nel try-block:
    # – global_loaded=False       → ricarica prodotti_master + classificazioni_manuali
    # – user_already_loaded=False → ricarica prodotti_utente per questo user_id
    if user_already_loaded and global_loaded:
        return _memoria_cache

    # Usa client iniettato o fallback a singleton
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return _memoria_cache

    try:
        # Carica dati LOCALE utente solo se non già caricati per questo user_id
        if not user_already_loaded:
            rows_locale = _fetch_all_rows(
                supabase_client, 'prodotti_utente',
                'descrizione, categoria',
                filters={'user_id': user_id}
            )

            if rows_locale:
                _memoria_cache['prodotti_utente'][user_id] = {
                    row['descrizione']: (_normalize_category_name(row.get('categoria')) or row.get('categoria'))
                    for row in rows_locale
                }
                logger.info(f"📦 Cache LOCALE caricata: {len(rows_locale)} prodotti per user {user_id[:8]}")
            else:
                _memoria_cache['prodotti_utente'][user_id] = {}

            _memoria_cache.setdefault('_loaded_user_ids', set()).add(user_id)

        # Carica dati GLOBALI solo se non già caricati
        if not global_loaded:
            # Query 2: Carica TUTTA la memoria globale (paginata)
            rows_globale = _fetch_all_rows(
                supabase_client, 'prodotti_master',
                'descrizione, categoria, confidence, consecutive_correct_classifications'
            )

            if rows_globale:
                _bypass = {}   # alta/altissima o streak>=3 → skip AI direttamente
                _hint = {}     # media/None → passa come hint, AI ha l'ultima parola
                _streak_promo = 0
                for row in rows_globale:
                    desc = row['descrizione']
                    cat = _normalize_category_name(row.get('categoria')) or row.get('categoria')
                    conf = row.get('confidence')
                    streak = row.get('consecutive_correct_classifications', 0) or 0
                    if conf in ('alta', 'altissima') or streak >= 3:
                        _bypass[desc] = cat
                        if streak >= 3 and conf not in ('alta', 'altissima'):
                            _streak_promo += 1
                    else:
                        _hint[desc] = cat
                _memoria_cache['prodotti_master'] = _bypass
                _memoria_cache['prodotti_master_hint'] = _hint
                logger.info(f"📦 Cache GLOBALE caricata: {len(_bypass)} bypass (alta/altissima + {_streak_promo} streak>=3), {len(_hint)} hint (media/None)")

            # Query 3: Carica TUTTE le classificazioni manuali admin (paginata)
            rows_manuali = _fetch_all_rows(
                supabase_client, 'classificazioni_manuali',
                'descrizione, categoria_corretta, is_dicitura'
            )

            if rows_manuali:
                _memoria_cache['classificazioni_manuali'] = {
                    row['descrizione']: {
                        'categoria': (_normalize_category_name(row.get('categoria_corretta')) or row.get('categoria_corretta')),
                        'is_dicitura': row.get('is_dicitura', False)
                    }
                    for row in rows_manuali
                }
                logger.info(f"📦 Cache MANUALI caricata: {len(rows_manuali)} classificazioni")

            # Query 4: Carica brand ambigui dinamici da Supabase
            try:
                result_brand = supabase_client.table('brand_ambigui')\
                    .select('brand')\
                    .eq('aggiunto_automaticamente', True)\
                    .execute()
                brand_dinamici = {row['brand'] for row in result_brand.data} if result_brand.data else set()
                _memoria_cache['brand_ambigui'] = brand_dinamici
                if brand_dinamici:
                    logger.info(f"📦 Cache BRAND AMBIGUI caricata: {len(brand_dinamici)} brand dinamici")
            except Exception as brand_err:
                # Tabella potrebbe non esistere ancora (migration non eseguita)
                logger.warning(f"⚠️ brand_ambigui non caricati (tabella assente?): {brand_err}")
                _memoria_cache['brand_ambigui'] = set()

            _memoria_cache['loaded'] = True
            _memoria_cache['_loaded_at'] = time.time()

        _memoria_cache['version'] += 1
        logger.info(f"✅ Cache caricata (v{_memoria_cache['version']}) per user {user_id[:8]}")
        return _memoria_cache

    except Exception as e:
        logger.error(f"Errore caricamento cache completa: {e}")
        return _memoria_cache


def invalida_cache_memoria():
    """
    Invalida la cache in-memory forzando ricaricamento al prossimo accesso.
    Da chiamare dopo INSERT/UPDATE/DELETE su tabelle memoria.
    Thread-safe: crea nuovo dict per evitare race condition su letture concorrenti.
    """
    global _memoria_cache
    with _cache_lock:
        _memoria_cache = {
            'loaded': False,
            'prodotti_utente': {},
            'prodotti_master': {},
            'prodotti_master_hint': {},
            'classificazioni_manuali': {},
            'brand_ambigui': set(),
            'version': (_memoria_cache.get('version', 0) + 1),
            'timestamp': None,
            '_loaded_at': 0.0,
            '_loaded_user_ids': set()
        }
    logger.info("🔄 Cache memoria invalidata")


def aggiorna_streak_classificazione(
    descrizione: str,
    categoria_gpt: str,
    supabase_client,
) -> None:
    """Dopo che il GPT classifica una descrizione, incrementa (o resetta) lo streak
    su prodotti_master. Quando lo streak raggiunge 3, il prodotto viene auto-promosso
    a confidence='alta', entrando nel bypass cache e riducendo le chiamate GPT future.

    Logica:
    - Se la categoria GPT coincide con quella già in prodotti_master → streak +1
    - Se la categoria è diversa → streak reset a 1 (nuova categoria)
    - Se il prodotto non esiste → inserimento con streak=1
    - A streak >= 3 → confidence impostata ad 'alta' + cache invalidata
    """
    if not categoria_gpt or categoria_gpt.strip() in ('', 'Da Classificare'):
        return
    if not descrizione or not supabase_client:
        return

    try:
        # Leggi lo stato attuale del prodotto
        res = supabase_client.table('prodotti_master') \
            .select('id, categoria, confidence, consecutive_correct_classifications, verified') \
            .eq('descrizione', descrizione) \
            .limit(1) \
            .execute()

        now_streak = 0
        new_confidence = None

        if res.data:
            row = res.data[0]
            # Non toccare prodotti verificati manualmente dall'admin
            if row.get('verified'):
                return

            current_cat = row.get('categoria', '')
            current_streak = row.get('consecutive_correct_classifications', 0) or 0
            current_conf = row.get('confidence')

            # Non degradare prodotti già alta/altissima (sono già al massimo)
            if current_conf in ('alta', 'altissima'):
                return

            if current_cat == categoria_gpt:
                now_streak = current_streak + 1
            else:
                # Categoria cambiata: nuovo ciclo di streak con la nuova categoria
                now_streak = 1

            update_data: dict = {
                'categoria': categoria_gpt,
                'consecutive_correct_classifications': now_streak,
            }
            if now_streak >= 3:
                update_data['confidence'] = 'alta'
                new_confidence = 'alta'

            supabase_client.table('prodotti_master') \
                .update(update_data) \
                .eq('id', row['id']) \
                .execute()

        else:
            # Prodotto non presente: upsert con streak=1 e confidence='media'
            supabase_client.table('prodotti_master') \
                .upsert({
                    'descrizione': descrizione,
                    'categoria': categoria_gpt,
                    'confidence': 'media',
                    'consecutive_correct_classifications': 1,
                }, on_conflict='descrizione') \
                .execute()
            now_streak = 1

        if new_confidence == 'alta':
            logger.info(
                f"🚀 STREAK PROMO: '{descrizione[:60]}' → '{categoria_gpt}' "
                f"(streak={now_streak}) promosso a bypass!"
            )
            invalida_cache_memoria()
        else:
            logger.debug(
                f"📈 Streak '{descrizione[:60]}': {now_streak} "
                f"→ '{categoria_gpt}'"
            )

    except Exception as e:
        # Non bloccare mai la classificazione principale per un errore di streak
        logger.warning(f"⚠️ aggiorna_streak_classificazione errore: {e}")


_MEMORIA_CAP = MEMORIA_SESSION_CAP

# Stop-word per estrazione brand (non sono brand)
_STOP_WORDS_BRAND = frozenset({
    'KG', 'GR', 'LT', 'ML', 'PZ', 'CF', 'CT', 'NR', 'X',
    'DI', 'DA', 'DEL', 'DELLA', 'DELLO', 'DEGLI', 'DELLE',
    'AL', 'ALLO', 'ALLA', 'AI', 'ALLE', 'IL', 'LO', 'LA',
    'I', 'GLI', 'LE', 'UN', 'UNA', 'CON', 'PER', 'IN',
    'CONF', 'CONFEZIONE', 'SURG', 'SURGELATO', 'BIO', 'BIOLOGICO',
    'FRESCO', 'FRESCA', 'INTERO', 'INTERA', 'LIGHT', 'ZERO',
    'CLASSIC', 'ORIGINAL', 'PREMIUM', 'SPECIALE', 'SPECIALI',
})


def estrai_brand_da_descrizione(descrizione: str) -> Optional[str]:
    """
    Estrae il brand (prima parola significativa) da una descrizione prodotto.
    Restituisce None se non riesce a identificare un brand attendibile.

    Criteri brand valido:
    - Almeno 3 caratteri alfabetici
    - Non è un numero o codice numerico
    - Non è una stop-word generica (KG, LT, DI, CONF...)
    """
    if not descrizione or not isinstance(descrizione, str):
        return None
    tokens = descrizione.upper().split()
    for token in tokens:
        # Rimuovi punteggiatura attaccata
        cleaned = re.sub(r'[^A-Z]', '', token)
        if (
            len(cleaned) >= 3
            and cleaned.isalpha()
            and cleaned not in _STOP_WORDS_BRAND
        ):
            return cleaned
    return None


def _aggiorna_brand_tracking(
    descrizione: str,
    vecchia_categoria: str,
    nuova_categoria: str,
    supabase_client=None
) -> None:
    """
    Traccia la correzione manuale nella tabella brand_ambigui.
    Se il brand raggiunge le soglie (>= 3 correzioni, >= 2 categorie, tasso > 20%)
    viene marcato aggiunto_automaticamente=TRUE e la cache brand viene invalidata.

    Chiamata in modo silenzioso (try/except totale) — non blocca mai il flusso principale.
    """
    if vecchia_categoria == nuova_categoria:
        return  # Correzione no-op, non tracciare

    brand = estrai_brand_da_descrizione(descrizione)
    if not brand:
        return

    # Non tracciare brand già nel set statico (già noti)
    if brand in BRAND_AMBIGUI_NO_DICT:
        return

    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception:
            return

    try:
        # Leggi record attuale (se esiste)
        existing = supabase_client.table('brand_ambigui')\
            .select('id, num_correzioni, categorie_viste, aggiunto_automaticamente')\
            .eq('brand', brand)\
            .limit(1)\
            .execute()

        if existing.data:
            rec = existing.data[0]
            num_corr = rec['num_correzioni'] + 1
            cat_viste = list(set(rec.get('categorie_viste') or []) | {vecchia_categoria, nuova_categoria})
        else:
            num_corr = 1
            cat_viste = list({vecchia_categoria, nuova_categoria})

        # Calcola tasso: num_correzioni / prodotti in prodotti_master con questo brand
        try:
            count_res = supabase_client.table('prodotti_master')\
                .select('id', count='exact', head=True)\
                .ilike('descrizione', f'{brand}%')\
                .execute()
            totale = count_res.count or 1
        except Exception:
            totale = max(num_corr, 1)

        tasso = round(num_corr / totale, 4)

        # Criteri per promozione automatica
        soglia_raggiunta = (
            not (existing.data and existing.data[0].get('aggiunto_automaticamente'))
            and num_corr >= 3
            and len(cat_viste) >= 2
            and tasso > 0.20
        )
        auto = soglia_raggiunta or (existing.data and existing.data[0].get('aggiunto_automaticamente', False))

        upsert_data = {
            'brand': brand,
            'num_correzioni': num_corr,
            'categorie_viste': cat_viste,
            'tasso_correzione': tasso,
            'aggiunto_automaticamente': auto,
            'ultima_modifica': datetime.now(timezone.utc).isoformat(),
        }
        if not existing.data:
            upsert_data['prima_vista'] = datetime.now(timezone.utc).isoformat()

        supabase_client.table('brand_ambigui').upsert(
            upsert_data, on_conflict='brand'
        ).execute()

        if soglia_raggiunta:
            # Invalida SOLO brand_ambigui nella cache (ottimizzazione: evita full reload)
            with _cache_lock:
                _memoria_cache['brand_ambigui'].add(brand)
            logger.warning(
                f"🚨 AUTO-BRAND: '{brand}' aggiunto a brand_ambigui "
                f"({num_corr} correzioni, {len(cat_viste)} categorie, tasso={tasso:.0%})"
            )
        else:
            logger.debug(
                f"📊 Brand tracking: '{brand}' — {num_corr} corr., "
                f"{len(cat_viste)} cat., tasso={tasso:.0%}"
            )

    except Exception as e:
        # Mai bloccare il flusso principale per un errore di tracking
        logger.debug(f"Brand tracking silenzioso fallito per '{brand}': {e}")


def ottieni_hint_per_ai(descrizione: str, user_id: str) -> Optional[str]:
    """
    Restituisce la categoria hint per l'AI (prodotti_master con confidence 'media' o NULL).
    Se trovato, l'AI usa questa come suggerimento debole nel payload.
    Restituisce None se il prodotto non è in memoria o ha confidence alta/altissima
    (in quel caso viene già bypassata l'AI completamente da categorizza_con_memoria).
    """
    try:
        desc_normalized, _ = get_descrizione_normalizzata_e_originale(descrizione)
        return _memoria_cache.get('prodotti_master_hint', {}).get(desc_normalized)
    except Exception:
        return None


def _traccia_memoria_categorizzata(descrizione: str):
    """Traccia descrizione come categorizzata da memoria (icona 🧠), cap a _MEMORIA_CAP."""
    if 'righe_memoria_appena_categorizzate' not in st.session_state:
        st.session_state.righe_memoria_appena_categorizzate = []
    lista = st.session_state.righe_memoria_appena_categorizzate
    if descrizione not in lista:
        if len(lista) < _MEMORIA_CAP:
            lista.append(descrizione)
        elif len(lista) == _MEMORIA_CAP:
            logger.warning(f"⚠️ Raggiunto limite {_MEMORIA_CAP} righe memoria categorizzate nella sessione")


def ottieni_categoria_prodotto(descrizione: str, user_id: str, supabase_client=None) -> str:
    """
    Ottiene categoria prodotto con priorità IBRIDA usando CACHE IN-MEMORY.
    ELIMINA N+1 QUERY: usa cache invece di query ripetute.
    
    PRIORITÀ (allineata con categorizza_con_memoria):
    1. Memoria ADMIN (classificazioni_manuali) - PRIORITÀ ASSOLUTA
    2. Memoria LOCALE utente (prodotti_utente) - personalizzazioni cliente
    3. Memoria GLOBALE (prodotti_master) - condivisa tra tutti i clienti
    4. "Da Classificare" (se non trovato in nessuna memoria)
    
    Args:
        descrizione: descrizione prodotto
        user_id: UUID utente
    
    Returns:
        str: categoria trovata
    """
    global _memoria_cache

    try:
        # Carica cache se non già caricata per questo utente
        if not _memoria_cache['loaded'] or user_id not in _memoria_cache.get('_loaded_user_ids', set()):
            carica_memoria_completa(user_id, supabase_client=supabase_client)

        # Snapshot locale: protegge da invalidazioni parallele durante la lettura.
        # Se un altro thread chiama invalida_cache_memoria() ora, _memoria_cache viene
        # sostituito ma questo thread continua a lavorare sul riferimento stabile.
        cache = _memoria_cache

        # Normalizza per matching consistente (stesso trattamento di categorizza_con_memoria)
        desc_stripped = descrizione.strip()

        # 0️⃣ Check memoria ADMIN (classificazioni_manuali) - PRIORITÀ ASSOLUTA
        if desc_stripped in cache['classificazioni_manuali']:
            record = cache['classificazioni_manuali'][desc_stripped]
            if record.get('is_dicitura'):
                logger.info(f"📋 Memoria Admin (cache/ottieni): '{descrizione[:40]}' → DICITURA")
                return "📝 NOTE E DICITURE"
            else:
                logger.info(f"📋 Memoria Admin (cache/ottieni): '{descrizione[:40]}' → {record['categoria']}")
                return record['categoria']

        # 0.5️⃣ Override forti non negoziabili: non devono essere battuti da cache auto errata.
        categoria_forzata, motivo_forzato = applica_regole_categoria_forti(descrizione, "Da Classificare")
        if motivo_forzato in _NON_NEGOZIABILI_CACHE_OVERRIDE:
            return categoria_forzata
        
        # 1️⃣ Check memoria LOCALE utente (da cache, 0 query!)
        if user_id in cache['prodotti_utente']:
            locale_dict = cache['prodotti_utente'][user_id]
            if descrizione in locale_dict:
                categoria = locale_dict[descrizione]
                _traccia_memoria_categorizzata(descrizione)
                return categoria
        
        # 2️⃣ Check memoria GLOBALE (da cache, 0 query!) se abilitata
        if not _disable_global_memory:
            # Prova con descrizione esatta
            if descrizione in cache['prodotti_master']:
                categoria = cache['prodotti_master'][descrizione]
                _traccia_memoria_categorizzata(descrizione)
                return categoria

            # Prova anche con descrizione normalizzata (per matching consistente)
            desc_normalized, _ = get_descrizione_normalizzata_e_originale(descrizione)
            if desc_normalized != descrizione and desc_normalized in cache['prodotti_master']:
                categoria = cache['prodotti_master'][desc_normalized]
                _traccia_memoria_categorizzata(descrizione)
                return categoria
        
        # 3️⃣ Fallback
        return "Da Classificare"
        
    except Exception as e:
        logger.warning(f"Errore ottieni_categoria (cache) per '{descrizione[:40]}...': {e}")
        return "Da Classificare"


# ============================================================
# FUNZIONI CORREZIONE E CATEGORIZZAZIONE
# ============================================================

# ── PRE-COMPUTED KEYWORD MATCHING (compilato una volta all'import) ──────────
# Keywords contenitori/packaging → BASSA PRIORITÀ
# Se non c'è nessun alimento, questi matchano e danno MATERIALE DI CONSUMO
_KEYWORDS_CONTENITORI = frozenset({
    "VASCHETTA", "VASCHETTE", "VASCHETTINA", "VASC",
    "CONFEZIONE", "CONF", "BUSTA", "BUSTE", "SCATOLA", "CARTONE",
    "PACCO", "BARATTOLO", "BOTTIGLIA", "LATTINA",
    "SACCHETTI", "SACCHETTO", "SACCHI", "SACCO",
})

def _build_compiled_patterns() -> Tuple[list, list]:
    """
    Costruisce le liste di (pattern_compilato, categoria) ordinate per lunghezza keyword decrescente.
    Chiamata UNA VOLTA all'import del modulo. Ritorna (patterns_alimenti, patterns_contenitori).
    
    Il pattern boundary accetta anche cifre come separatore sinistro per gestire
    codici GDO con numeri incollati (es. "200CANGURINO", "G500STOP-TOAST").
    """
    patterns_alimenti = []
    patterns_contenitori = []
    
    for keyword, categoria in sorted(DIZIONARIO_CORREZIONI.items(), key=lambda x: len(x[0]), reverse=True):
        # Boundary sinistro: inizio stringa, whitespace, non-alfanumerico, O cifra (per codici GDO)
        pattern = re.compile(r'(?:^|[\s\W\d])' + re.escape(keyword) + r'(?:[\s\W]|$)')
        if keyword in _KEYWORDS_CONTENITORI:
            patterns_contenitori.append((pattern, categoria))
        else:
            patterns_alimenti.append((pattern, categoria))
    
    return patterns_alimenti, patterns_contenitori

# Compilati una volta all'avvio (0 overhead nelle chiamate successive)
try:
    _PATTERNS_ALIMENTI, _PATTERNS_CONTENITORI = _build_compiled_patterns()
except Exception as e:
    logger.error(f"Errore buildcompiledpatterns: {e}")
    _PATTERNS_ALIMENTI, _PATTERNS_CONTENITORI = [], []

# Regex controllo caratteri (compilata a livello modulo, non ad ogni chiamata)
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def applica_correzioni_dizionario(descrizione: str, categoria_ai: str) -> str:
    """
    Applica correzioni basate su keyword nel dizionario con PRIORITÀ INTELLIGENTE.
    
    STRATEGIA: I CIBI hanno priorità sui CONTENITORI.
    - Se trova un ALIMENTO (SALSICCIA, CAROTE, etc.), lo classifica per quello
    - Se trova SOLO un CONTENITORE (VASC, CONF, BUSTA, etc.), classifica MATERIALE DI CONSUMO
    - Ignora i contenitori se c'è un alimento presente
    
    Usa pattern regex pre-compilati e pre-ordinati per lunghezza decrescente (ottimizzazione).
    
    Args:
        descrizione: testo descrizione prodotto
        categoria_ai: categoria assegnata da AI (fallback)
    
    Returns:
        str: categoria corretta o categoria_ai se nessun match
    """
    if not descrizione or not isinstance(descrizione, str):
        return categoria_ai

    # Brand multi-categoria → bypass dizionario, forza AI per classificazione per-prodotto.
    # Check ibrido: set statico (constants.py) UNION set dinamico (Supabase brand_ambigui).
    desc_upper = descrizione.upper()
    _brand_set = BRAND_AMBIGUI_NO_DICT | _memoria_cache.get('brand_ambigui', set())
    if any(brand in desc_upper for brand in _brand_set):
        return categoria_ai

    # Padding per garantire match ai bordi (i pattern usano boundary [\s\W])
    desc_padded = ' ' + desc_upper + ' '

    # STEP 1: Cerca ALIMENTI (priorità alta) - se trovi uno, ritorna subito
    for pattern, categoria in _PATTERNS_ALIMENTI:
        if pattern.search(desc_padded):
            return categoria
    
    # STEP 2: Cerca CONTENITORI (priorità bassa) - solo se nessun alimento trovato
    for pattern, categoria in _PATTERNS_CONTENITORI:
        if pattern.search(desc_padded):
            return categoria
    
    return categoria_ai


def salva_correzione_in_memoria_locale(
    descrizione: str,
    nuova_categoria: str,
    user_id: str,
    user_email: str,
    supabase_client=None,
    vecchia_categoria: Optional[str] = None
) -> bool:
    """
    Salva correzione MANUALE del cliente in memoria LOCALE (solo per lui).
    Le modifiche manuali dei clienti NON devono impattare la memoria globale.
    
    PRIORITÀ:
    - Memoria locale (prodotti_utente) ha priorità su memoria globale
    - Se cliente modifica manualmente, vede sempre la sua personalizzazione
    - Altri clienti continuano a usare memoria globale
    
    Args:
        descrizione: descrizione prodotto
        nuova_categoria: categoria scelta dall'utente
        user_id: UUID utente
        user_email: email utente (per log)
        supabase_client: Client Supabase (opzionale)
    
    Returns:
        bool: True se successo, False altrimenti
    """
    # Usa client iniettato o fallback a singleton
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return False
    
    try:
        nuova_categoria = _normalize_category_name(nuova_categoria) or nuova_categoria

        # Normalizza descrizione
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        # Sanitizza: rimuovi null bytes e limita lunghezza
        desc_normalized = desc_normalized.replace('\x00', '').strip()[:MAX_DESC_LENGTH_DB]
        if not desc_normalized:
            logger.warning("Descrizione vuota dopo sanitizzazione, skip salvataggio locale")
            return False
        
        logger.info(f"💾 SALVATAGGIO LOCALE: '{desc_normalized}' → {nuova_categoria} (user={user_email})")
        
        # Colonne ESSENZIALI (sicuramente presenti nella tabella)
        upsert_data = {
            'user_id': user_id,
            'descrizione': desc_normalized,
            'categoria': nuova_categoria,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Colonne OPZIONALI - aggiungi e rimuovi se il DB le rifiuta
        optional_cols = {
            'volte_visto': 1,
            'classificato_da': f'Manuale ({user_email})'
        }
        
        # Prova con tutte le colonne, rimuovi quelle mancanti una alla volta
        upsert_data.update(optional_cols)
        result = None
        max_retries = len(optional_cols) + 1  # Al massimo rimuoviamo tutte le opzionali
        
        for attempt in range(max_retries):
            try:
                result = supabase_client.table('prodotti_utente').upsert(
                    upsert_data, on_conflict='user_id,descrizione'
                ).execute()
                break  # Successo!
            except Exception as col_err:
                err_msg = str(col_err)
                if 'PGRST204' in err_msg:
                    # Trova quale colonna manca dal messaggio di errore
                    import re
                    match = re.search(r"'(\w+)' column", err_msg)
                    if match:
                        missing_col = match.group(1)
                        logger.warning(f"Colonna '{missing_col}' non trovata nel DB, rimuovo e riprovo")
                        upsert_data.pop(missing_col, None)
                        continue
                raise col_err  # Errore diverso, non gestibile
        
        if result is None:
            logger.error("❌ Upsert fallito dopo rimozione colonne opzionali")
            return False
        
        if result.data:
            logger.info(f"✅ Salvato locale: '{desc_normalized}' → {nuova_categoria}")
        else:
            logger.warning(f"⚠️ Upsert eseguito ma nessun dato restituito")
        
        # Invalida cache per forzare ricaricamento
        invalida_cache_memoria()

        # Tracking brand ambigui (silenzioso, non blocca il return)
        if vecchia_categoria:
            _aggiorna_brand_tracking(
                descrizione=descrizione,
                vecchia_categoria=vecchia_categoria,
                nuova_categoria=nuova_categoria,
                supabase_client=supabase_client
            )

        return True
    
    except Exception as e:
        logger.error(f"❌ Errore salvataggio memoria locale: {e}")
        logger.exception("Dettaglio errore completo:")
        return False


def salva_correzione_in_memoria_globale(
    descrizione: str,
    vecchia_categoria: str,
    nuova_categoria: str,
    user_email: str,
    supabase_client=None,
    is_admin: bool = False
) -> bool:
    """
    Salva correzione in memoria GLOBALE (condivisa tra tutti i clienti).
    
    ⚠️ USARE SOLO PER:
    - Modifiche dell'admin dalla TAB "Memoria Globale"
    - Admin impersonificato che vuole modificare per tutti
    
    ❌ NON usare per modifiche manuali normali dei clienti → usa salva_correzione_in_memoria_locale()
    
    Args:
        descrizione: descrizione prodotto
        vecchia_categoria: categoria precedente
        nuova_categoria: categoria corretta
        user_email: email utente
        supabase_client: Client Supabase (opzionale)
        is_admin: True se modifica da admin (per log)
    
    Returns:
        bool: True se successo, False altrimenti
    """
    # Usa client iniettato o fallback a singleton
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return False
    
    try:
        vecchia_categoria = _normalize_category_name(vecchia_categoria) or vecchia_categoria
        nuova_categoria = _normalize_category_name(nuova_categoria) or nuova_categoria

        # Normalizza descrizione
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        # Sanitizza: rimuovi null bytes e limita lunghezza
        desc_normalized = desc_normalized.replace('\x00', '').strip()[:MAX_DESC_LENGTH_DB]
        if not desc_normalized:
            logger.warning("Descrizione vuota dopo sanitizzazione, skip salvataggio globale")
            return False
        
        # Check se esiste già in memoria
        existing = supabase_client.table('prodotti_master')\
            .select('id, volte_visto')\
            .eq('descrizione', desc_normalized)\
            .limit(1)\
            .execute()
        
        if existing.data and len(existing.data) > 0:
            # AGGIORNA esistente con categoria corretta
            record = existing.data[0]
            
            supabase_client.table('prodotti_master').update({
                'categoria': nuova_categoria,
                'classificato_da': f'Utente ({user_email})',
                'confidence': 'altissima',
                'verified': True,  # ✅ Auto-verifica: correzione manuale = già controllata
                'ultima_modifica': datetime.now(timezone.utc).isoformat()
            }).eq('id', record['id']).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()

            # Tracking brand ambigui
            _aggiorna_brand_tracking(descrizione, vecchia_categoria, nuova_categoria, supabase_client)

            # Log con prefisso corretto
            prefisso = "🔧 ADMIN" if is_admin else "🟢 GLOBALE"
            logger.info(f"{prefisso}: '{desc_normalized}' {vecchia_categoria} → {nuova_categoria} (by {user_email})")
        
        else:
            # INSERISCI nuovo record con categoria corretta
            supabase_client.table('prodotti_master').insert({
                'descrizione': desc_normalized,
                'categoria': nuova_categoria,
                'classificato_da': f'Admin ({user_email})' if is_admin else f'Utente ({user_email})',
                'confidence': 'altissima',
                'verified': True,  # ✅ Auto-verifica: correzione manuale = già controllata
                'volte_visto': 1,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'ultima_modifica': datetime.now(timezone.utc).isoformat()
            }).execute()
            
            # Invalida cache per forzare ricaricamento
            invalida_cache_memoria()

            # Tracking brand ambigui
            _aggiorna_brand_tracking(descrizione, vecchia_categoria, nuova_categoria, supabase_client)

            # Log con prefisso corretto
            prefisso = "🔧 ADMIN" if is_admin else "🟢 GLOBALE"
            logger.info(f"{prefisso}: '{desc_normalized}' → {nuova_categoria} (by {user_email})")
        
        return True
    
    except Exception as e:
        logger.error(f"Errore salvataggio correzione in memoria: {e}")
        return False


def categorizza_con_memoria(
    descrizione: str,
    prezzo: float,
    quantita: float,
    user_id: Optional[str] = None,
    supabase_client=None,
    fornitore: Optional[str] = None,
    unita_misura: Optional[str] = None
) -> str:
    """
    Categorizza usando memoria GLOBALE multi-livello con CACHE IN-MEMORY.
    ELIMINA N+1 QUERY: usa cache invece di query ripetute.
    
    PRIORITÀ CORRETTA:
    1. Memoria correzioni admin (classificazioni_manuali) - PRIORITÀ ASSOLUTA
    2. Memoria LOCALE utente (prodotti_utente) - personalizzazioni cliente
    3. Memoria GLOBALE prodotti (prodotti_master) - condivisa tra tutti
    4. Check dicitura (se prezzo = 0)
    5. Regola FORNITORE specifico - categorizzazione automatica
    6. Regola UNITÀ MISURA - categorizzazione automatica
    7. Dizionario keyword - FALLBACK FINALE
    
    Args:
        descrizione: testo descrizione
        prezzo: prezzo_unitario
        quantita: quantità
        user_id: ID utente (per log)
        supabase_client: Client Supabase (opzionale)
        fornitore: Nome fornitore (opzionale)
        unita_misura: Unità di misura normalizzata (opzionale)
    
    Returns:
        str: categoria finale
    """
    global _memoria_cache

    # Usa client iniettato o fallback
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.warning(f"Impossibile inizializzare Supabase client: {e}")

    try:
        # Carica cache se non già caricata per questo utente
        if user_id and (not _memoria_cache['loaded'] or user_id not in _memoria_cache.get('_loaded_user_ids', set())):
            carica_memoria_completa(user_id, supabase_client)

        # Snapshot locale: protegge da invalidazioni parallele durante la lettura.
        # Con integrazione invoicetronic (flusso multi-client parallelo), senza snapshot
        # un thread potrebbe leggere la cache già svuotata da un altro thread.
        cache = _memoria_cache

        # LIVELLO 1: Check memoria admin (da cache, 0 query!)
        desc_stripped = descrizione.strip()
        if desc_stripped in cache['classificazioni_manuali']:
            record = cache['classificazioni_manuali'][desc_stripped]
            if record.get('is_dicitura'):
                logger.info(f"📋 Memoria Admin (cache): '{descrizione}' → DICITURA (validata admin)")
                return "📝 NOTE E DICITURE"
            else:
                logger.info(f"📋 Memoria Admin (cache): '{descrizione}' → {record['categoria']} (validata admin)")
                return record['categoria']

        # LIVELLO 1.5: Override forti non negoziabili prima della memoria automatica.
        categoria_forzata, motivo_forzato = applica_regole_categoria_forti(descrizione, "Da Classificare")
        if motivo_forzato in _NON_NEGOZIABILI_CACHE_OVERRIDE:
            return categoria_forzata
    
    except Exception as e:
        logger.warning(f"Errore check memoria admin (cache): {e}")
    
    # LIVELLO 2: Check memoria LOCALE utente (personalizzazioni cliente - priorità alta)
    try:
        if user_id and user_id in cache['prodotti_utente']:
            locale_dict = cache['prodotti_utente'][user_id]
            if descrizione in locale_dict:
                categoria = locale_dict[descrizione]
                logger.info(f"🔵 LOCALE UTENTE (cache): '{descrizione}' → {categoria} (personalizzazione cliente)")
                return categoria
    
    except Exception as e:
        logger.warning(f"Errore check memoria locale utente (cache): {e}")
    
    # LIVELLO 3: Check memoria GLOBALE (da cache, 0 query!)
    try:
        # Normalizza descrizione per matching intelligente
        desc_normalized, desc_original = get_descrizione_normalizzata_e_originale(descrizione)
        
        if not _disable_global_memory:
            if desc_normalized in cache['prodotti_master']:
                categoria = cache['prodotti_master'][desc_normalized]
                logger.info(f"🟢 MEMORIA GLOBALE (cache): '{descrizione}' → {categoria} (norm: '{desc_normalized}')")
                return categoria
    
    except Exception as e:
        logger.warning(f"Errore check memoria globale (cache): {e}")
    
    # LIVELLO 4: Check dicitura (se prezzo = 0)
    if prezzo == 0 and is_dicitura_sicura(descrizione, prezzo, quantita):
        return "📝 NOTE E DICITURE"
    
    # LIVELLO 5: Regola FORNITORE specifico (priorità ALTA)
    if fornitore:
        from config.constants import CATEGORIA_PER_FORNITORE
        fornitore_upper = fornitore.strip().upper()
        for fornitore_key, categoria in CATEGORIA_PER_FORNITORE.items():
            if fornitore_key.upper() in fornitore_upper or fornitore_upper in fornitore_key.upper():
                logger.info(f"🏭 FORNITORE: '{descrizione}' → {categoria} (fornitore: {fornitore})")
                return categoria
    
    # LIVELLO 6: Regola UNITÀ MISURA (priorità ALTA)
    if unita_misura:
        from config.constants import UNITA_MISURA_CATEGORIA
        unita_upper = unita_misura.strip().upper()
        if unita_upper in UNITA_MISURA_CATEGORIA:
            categoria = UNITA_MISURA_CATEGORIA[unita_upper]
            logger.info(f"📏 UNITÀ MISURA: '{descrizione}' → {categoria} (U.M.: {unita_misura})")
            return categoria
    
    # LIVELLO 7: Dizionario keyword (fallback)
    categoria_keyword = applica_correzioni_dizionario(descrizione, "Da Classificare")
    categoria_keyword, motivo_override = applica_regole_categoria_forti(descrizione, categoria_keyword)
    if motivo_override:
        logger.info(
            f"🧭 OVERRIDE SICUREZZA (keyword): '{descrizione[:60]}' -> {categoria_keyword} [{motivo_override}]"
        )
    
    # 💾 SALVATAGGIO AUTOMATICO IN MEMORIA LOCALE UTENTE
    # Evita contaminazione cross-tenant: i suggerimenti automatici non entrano nella memoria globale.
    # 🛡️ QUARANTENA: NON salvare righe con prezzo = 0 in memoria locale automatica.
    if categoria_keyword != "Da Classificare" and supabase_client and prezzo != 0:
        try:
            desc_local = descrizione.strip()

            supabase_client.table('prodotti_utente').upsert({
                'user_id': user_id,
                'descrizione': desc_local,
                'categoria': categoria_keyword,
                'volte_visto': 1,
                'classificato_da': 'keyword-auto',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }, on_conflict='user_id,descrizione').execute()
            logger.info(f"💾 MEMORIA LOCALE (auto-save): '{desc_local}' → {categoria_keyword} (keyword-auto)")
        except Exception as e:
            logger.warning(f"❌ Errore salvataggio memoria locale per '{descrizione[:40]}': {e}")
    elif categoria_keyword != "Da Classificare" and prezzo == 0:
        # 🛡️ QUARANTENA: Riga €0 categorizzata ma NON salvata in memoria automatica
        # Andrà nel tab "Review Righe 0€" per validazione admin
        logger.info(f"🛡️ QUARANTENA €0: '{descrizione[:60]}' → {categoria_keyword} (NON salvato in memoria automatica, in attesa review)")
    else:
        # AUTO-CATEGORIZZAZIONE FALLITA: nessun match nel dizionario
        logger.info(f"⚠️ AUTO-CATEGORIZZAZIONE FALLITA: '{descrizione[:60]}' rimasto 'Da Classificare' (NON salvato in memoria globale)")
    
    return categoria_keyword


# ============================================================
# SVUOTA MEMORIA GLOBALE (DB + file legacy)
# ============================================================

def svuota_memoria_globale(supabase_client=None) -> bool:
    """
    Svuota la memoria globale AI:
    - Cancella tutti i record in 'prodotti_master' su Supabase
    - Invalida cache in-memory
    - Cancella file legacy 'memoria_ai_correzioni.json' se presente
    """
    # Usa client iniettato o fallback
    if supabase_client is None:
        try:
            from services import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Impossibile creare client Supabase: {e}")
            return False

    try:
        # Preleva tutti gli id per cancellazione batch
        resp = supabase_client.table('prodotti_master').select('id').execute()
        ids = [row['id'] for row in (resp.data or []) if 'id' in row]

        deleted = 0
        if ids:
            # Cancella in batch (blocchi da 1000 per sicurezza)
            batch_size = 1000
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i+batch_size]
                supabase_client.table('prodotti_master').delete().in_('id', batch).execute()
                deleted += len(batch)
        logger.info(f"🗑️ Memoria Globale DB svuotata: {deleted} record rimossi")

        # Invalida cache
        invalida_cache_memoria()

        # Cancella file legacy
        try:
            if os.path.exists(MEMORIA_AI_FILE):
                os.remove(MEMORIA_AI_FILE)
                logger.info("🧹 File legacy memoria AI rimosso")
        except Exception as fe:
            logger.warning(f"Impossibile rimuovere file legacy: {fe}")

        return True

    except Exception as e:
        logger.error(f"Errore svuotamento memoria globale: {e}")
        return False


# ============================================================
# CLASSIFICAZIONE BATCH CON OPENAI
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRIABLE_ERRORS)
)
def _chiama_gpt_classificazione(
    da_chiedere_gpt: List[str],
    openai_client,
    max_tokens: int = 4096,
    lista_fornitori: Optional[List[str]] = None,
    lista_iva: Optional[List[int]] = None,
    lista_hint: Optional[List[Optional[str]]] = None,
) -> List[str]:
    """
    Singola chiamata GPT per classificazione. Ritorna lista categorie (stesso ordine input).
    Se GPT ritorna meno categorie del previsto, le mancanti saranno "Da Classificare".

    Quando lista_fornitori e/o lista_iva sono fornite (allineate con da_chiedere_gpt),
    il payload inviato a GPT è arricchito: {articolo, fornitore, iva} invece di semplici stringhe.
    Le descrizioni vengono inoltre normalizzate (rimozione prefissi peso GDO, espansione
    abbreviazioni) prima di essere inviate, per migliorare l'accuratezza.
    """
    from config.prompt_ai_potenziato import get_prompt_classificazione
    from utils.text_utils import normalizza_descrizione

    # 🔒 Sanitizza input: rimuovi caratteri di controllo, limita lunghezza per descrizione
    _MAX_DESC_LEN = 300
    da_chiedere_sanitized = [
        _CTRL_RE.sub('', desc)[:_MAX_DESC_LEN] for desc in da_chiedere_gpt
    ]

    # 🧹 Normalizza descrizioni per rimuovere prefissi GDO (es: "G100 PANBURGER" → "PANBURGER")
    # ed espandere abbreviazioni (es: "INS.NOVELLA" → "INSALATA NOVELLA").
    # Usiamo la versione normalizzata SOLO nel payload inviato a GPT; la mappatura risultati
    # avviene per indice, quindi il cambio di testo non crea disallineamenti.
    da_chiedere_normalizzate = [
        normalizza_descrizione(desc) or desc  # fallback a originale se normalizzazione svuota
        for desc in da_chiedere_sanitized
    ]

    # 📦 Costruisci payload: arricchito (dict) se i metadati sono disponibili, altrimenti plain list
    _ha_fornitori = lista_fornitori and len(lista_fornitori) == len(da_chiedere_gpt)
    _ha_iva = lista_iva and len(lista_iva) == len(da_chiedere_gpt)
    _ha_hint = lista_hint and len(lista_hint) == len(da_chiedere_gpt)
    _items_with_hint = 0
    if _ha_fornitori or _ha_iva or _ha_hint:
        payload = []
        for idx, desc_norm in enumerate(da_chiedere_normalizzate):
            item: Dict[str, Any] = {"articolo": desc_norm}
            if _ha_fornitori:
                forn = (lista_fornitori[idx] or "").strip()
                if forn:
                    item["fornitore"] = forn
            if _ha_iva:
                iva_val = lista_iva[idx]
                if iva_val:
                    item["iva"] = iva_val
            if _ha_hint:
                hint_val = lista_hint[idx]
                if hint_val:
                    item["hint"] = hint_val
                    _items_with_hint += 1
            payload.append(item)
        articoli_json = json.dumps(payload, ensure_ascii=False)
    else:
        articoli_json = json.dumps(da_chiedere_normalizzate, ensure_ascii=False)

    prompt = get_prompt_classificazione(articoli_json)
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1,
        response_format={"type": "json_object"}
    )
    
    # 💰 TRACKING COSTI AI - Categorizzazione
    try:
        usage = response.usage
        if usage:
            from services.ai_cost_service import track_ai_usage

            track_ai_usage(
                operation_type='categorization',
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                ristorante_id=st.session_state.get('ristorante_id'),
                item_count=len(da_chiedere_gpt),
                metadata={
                    'source': 'categorization-batch',
                    'batch_size': len(da_chiedere_gpt),
                    'items_with_hint': _items_with_hint,
                },
            )
    except Exception as cost_err:
        logger.warning(f"⚠️ Errore calcolo costo categorizzazione: {cost_err}")
    
    testo = response.choices[0].message.content.strip()
    dati = json.loads(testo)
    categorie_gpt = dati.get("categorie", [])
    
    # Valida e costruisci lista risultati
    risultati = []
    for idx, desc in enumerate(da_chiedere_gpt):
        if idx < len(categorie_gpt):
            cat = categorie_gpt[idx]
            
            # ⚠️ VALIDAZIONE: Blocca categorie non valide (incluso NOTE E DICITURE)
            if cat not in TUTTE_LE_CATEGORIE and cat != "Da Classificare":
                logger.warning(f"⚠️ AI ha generato categoria non valida '{cat}' per '{desc}' → applicando dizionario")
                cat = applica_correzioni_dizionario(desc, "Da Classificare")
            risultati.append(cat)
        else:
            logger.warning(f"⚠️ AI non ha restituito categoria per indice {idx}: '{desc[:40]}' → Da Classificare")
            risultati.append("Da Classificare")
    
    if len(categorie_gpt) != len(da_chiedere_gpt):
        logger.warning(f"⚠️ MISMATCH: inviate {len(da_chiedere_gpt)} descrizioni, ricevute {len(categorie_gpt)} categorie")
    
    return risultati


def classifica_con_ai(
    lista_descrizioni: List[str],
    lista_fornitori: Optional[List[str]] = None,
    lista_iva: Optional[List[int]] = None,
    lista_hint: Optional[List[Optional[str]]] = None,
    openai_client: Optional[OpenAI] = None,
    ristorante_id: Optional[str] = None,
) -> List[str]:
    """
    Classificazione AI con JSON strutturato + correzioni dizionario.
    Usa retry automatico per gestire rate limits OpenAI e risposte incomplete.
    
    Se la prima chiamata GPT restituisce "Da Classificare" per alcuni item,
    ritenta automaticamente (max 2 retry) con batch più piccoli.
    
    Args:
        lista_descrizioni: Lista descrizioni prodotti da classificare
        lista_fornitori: Lista fornitori ALLINEATA con lista_descrizioni (opzionale)
        lista_iva: Lista IVA% ALLINEATA con lista_descrizioni (es: 4, 10, 22) (opzionale)
        lista_hint: Lista hint categoria ALLINEATA con lista_descrizioni (opzionale).
                    Ogni elemento è una categoria suggerita (confidence 'media') o None.
        openai_client: Client OpenAI (opzionale, crea nuovo se None)
        ristorante_id: ID ristorante per rate limit giornaliero (opzionale)
    
    Returns:
        List[str]: Lista categorie classificate (stesso ordine input)
    
    Raises:
        RuntimeError: Se il limite giornaliero AI per ristorante è superato.
    """
    if not lista_descrizioni:
        return []

    # � Admin e impersonazione bypassano i limiti giornalieri AI per test operativi
    _is_unrestricted_admin = bool(st.session_state.get('user_is_admin', False) or st.session_state.get('impersonating', False))
    if ristorante_id and not _is_unrestricted_admin:
        try:
            from services.ai_cost_service import get_daily_quota_status

            quota = get_daily_quota_status(
                ristorante_id=ristorante_id,
                operation_types=['categorization'],
                daily_limit=MAX_AI_CALLS_PER_DAY,
            )
            _calls_today = int(quota['used'])
            if quota['is_exceeded']:
                logger.warning(
                    f"🔒 Rate limit categorizzazioni superato per ristorante {ristorante_id}: "
                    f"{_calls_today}/{MAX_AI_CALLS_PER_DAY} chiamate oggi"
                )
                raise RuntimeError(
                    f"Limite giornaliero categorizzazioni AI raggiunto ({MAX_AI_CALLS_PER_DAY} chiamate/giorno). "
                    f"Riprova domani."
                )
        except RuntimeError:
            raise
        except Exception as _rl_err:
            logger.warning(f"⚠️ Errore check rate limit AI: {_rl_err} — proseguo senza limite")
    
    # Usa client iniettato o crea nuovo
    if openai_client is None:
        openai_client = _get_openai_client()
    
    # ⚠️ DEPRECATO: Legacy JSON memory ignorata per evitare conflitti con DB Supabase
    # La priorità è ora gestita da carica_memoria_completa() (classificazioni_manuali > locale > globale)
    risultati = {}
    da_chiedere_gpt = list(lista_descrizioni)  # Tutte da classificare via GPT

    # Costruisci indici posizionali per fornitori e IVA (allineati con da_chiedere_gpt)
    _idx_map = {desc: i for i, desc in enumerate(lista_descrizioni)}

    def _get_fornitori_aligned(descs: List[str]) -> Optional[List[str]]:
        if not lista_fornitori or len(lista_fornitori) != len(lista_descrizioni):
            return None
        return [lista_fornitori[_idx_map[d]] for d in descs if d in _idx_map]

    def _get_iva_aligned(descs: List[str]) -> Optional[List[int]]:
        if not lista_iva or len(lista_iva) != len(lista_descrizioni):
            return None
        return [lista_iva[_idx_map[d]] for d in descs if d in _idx_map]

    def _get_hint_aligned(descs: List[str]) -> Optional[List[Optional[str]]]:
        if not lista_hint or len(lista_hint) != len(lista_descrizioni):
            return None
        return [lista_hint[_idx_map[d]] for d in descs if d in _idx_map]

    if not da_chiedere_gpt:
        return [
            risultati[d] if d in risultati 
            else applica_correzioni_dizionario(d, "Da Classificare")
            for d in lista_descrizioni
        ]

    try:
        # 🧠 PRIMA CHIAMATA GPT (max_tokens=4096 per evitare troncamenti)
        cats_prima = _chiama_gpt_classificazione(
            da_chiedere_gpt, openai_client, max_tokens=4096,
            lista_fornitori=_get_fornitori_aligned(da_chiedere_gpt),
            lista_iva=_get_iva_aligned(da_chiedere_gpt),
            lista_hint=_get_hint_aligned(da_chiedere_gpt),
        )
        
        for desc, cat in zip(da_chiedere_gpt, cats_prima):
            risultati[desc] = cat
        
        # 🔄 RETRY AUTOMATICO: Se ci sono "Da Classificare", ritenta con batch più piccoli
        MAX_RETRY = 2
        for retry_num in range(1, MAX_RETRY + 1):
            # Trova descrizioni ancora "Da Classificare"
            da_ritentare = [d for d in da_chiedere_gpt if risultati.get(d) == "Da Classificare"]
            
            if not da_ritentare:
                break  # Tutto classificato!
            
            logger.info(f"🔄 RETRY {retry_num}/{MAX_RETRY}: {len(da_ritentare)} descrizioni ancora Da Classificare, ritentando...")
            
            try:
                # Usa batch più piccoli nei retry per migliorare precisione
                retry_chunk_size = min(20, len(da_ritentare))
                for i in range(0, len(da_ritentare), retry_chunk_size):
                    chunk_retry = da_ritentare[i:i+retry_chunk_size]
                    cats_retry = _chiama_gpt_classificazione(
                        chunk_retry, openai_client, max_tokens=4096,
                        lista_fornitori=_get_fornitori_aligned(chunk_retry),
                        lista_iva=_get_iva_aligned(chunk_retry),
                        lista_hint=_get_hint_aligned(chunk_retry),
                    )
                    
                    for desc, cat in zip(chunk_retry, cats_retry):
                        if cat and cat != "Da Classificare":
                            risultati[desc] = cat
                            logger.info(f"✅ RETRY {retry_num}: '{desc[:40]}' → {cat}")
            except Exception as retry_err:
                logger.warning(f"⚠️ Errore durante retry {retry_num}: {retry_err}")
                # Continua con i risultati che abbiamo
        
        # 🔧 SAFETY NET: Applica regole forti + dizionario ai "Da Classificare" residui
        _fallback_count = 0
        for desc in da_chiedere_gpt:
            if risultati.get(desc) == "Da Classificare":
                # Try strong rules first (higher precision)
                cat_strong, reason = applica_regole_categoria_forti(desc, "Da Classificare")
                if cat_strong != "Da Classificare":
                    risultati[desc] = cat_strong
                    _fallback_count += 1
                    logger.info(f"🧭 REGOLA FORTE FALLBACK: '{desc[:40]}' → {cat_strong} [{reason}]")
                    continue
                # Then try dictionary corrections
                cat_dict = applica_correzioni_dizionario(desc, "Da Classificare")
                if cat_dict != "Da Classificare":
                    risultati[desc] = cat_dict
                    _fallback_count += 1
                    logger.info(f"📖 DIZIONARIO FALLBACK: '{desc[:40]}' → {cat_dict}")
        if _fallback_count > 0:
            logger.info(f"🔧 SAFETY NET: {_fallback_count} descrizioni recuperate con regole forti/dizionario")
        
        # Log finale
        ancora_da_class = sum(1 for d in da_chiedere_gpt if risultati.get(d) == "Da Classificare")
        if ancora_da_class > 0:
            logger.warning(f"⚠️ Dopo {MAX_RETRY} retry + safety net, {ancora_da_class}/{len(da_chiedere_gpt)} descrizioni rimangono Da Classificare")
        else:
            logger.info(f"✅ Tutte le {len(da_chiedere_gpt)} descrizioni classificate con successo")
        
        # Ritorna nell'ordine originale
        return [risultati.get(d, "Da Classificare") for d in lista_descrizioni]
        
    except json.JSONDecodeError as e:
        logger.error(f"Errore parsing JSON da OpenAI: {e}")
        return [applica_correzioni_dizionario(d, "Da Classificare") for d in lista_descrizioni]
    except Exception as e:
        logger.error(f"Errore classificazione AI: {e}")
        return [applica_correzioni_dizionario(d, "Da Classificare") for d in lista_descrizioni]


# ============================================================
# UI HELPER: LOADING ANIMATION
# ============================================================

def mostra_loading_ai(placeholder, messaggio: str = "Elaborazione in corso"):
    """
    Mostra animazione loading a tema AI/Neural Network in un placeholder.
    Usa st.empty() placeholder per garantire rimozione anche in caso di errore.
    
    Args:
        placeholder: st.empty() placeholder per rendering
        messaggio: Testo messaggio da mostrare
    """
    placeholder.markdown(f"""
        <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 0.4; }}
            50% {{ opacity: 1; }}
        }}
        .loading-ai {{
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
            color: white;
            font-weight: 600;
            animation: pulse 2s ease-in-out infinite;
        }}
        .loading-ai::before {{
            content: "🧠";
            font-size: clamp(1.4rem, 2vw + 0.8rem, 2rem);
            margin-right: clamp(0.6rem, 1.6vw, 0.95rem);
        }}
        </style>
        <div class="loading-ai">
            {messaggio}...
        </div>
    """, unsafe_allow_html=True)
