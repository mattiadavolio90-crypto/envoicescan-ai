#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt AI Potenziato con Esempi Pratici
Questo file contiene il prompt per la classificazione AI con esempi per ogni categoria.
"""

PROMPT_CLASSIFICAZIONE_AI = """
Sei un esperto classifier per ristoranti con 20+ anni di esperienza.
Classifica questi articoli di fatture usando RAGIONAMENTO INTELLIGENTE e CONTESTO.

═══════════════════════════════════════════════════════════════════
📋 CATEGORIE F&B (26 categorie alimentari e bevande)
═══════════════════════════════════════════════════════════════════

1. **ACQUA** - Acque naturali, frizzanti, effervescenti
   Esempi: "ACQUA NATURALE LT1.5", "ACQUA FRIZZANTE KG20", "ACQUA EFFERVESCENTE"

2. **AMARI/LIQUORI** - Digestivi, liquori dolci, cordiali
   Esempi: "LIMONCELLO", "AMARETTO", "BAILEYS", "LIQUORE MIRTILLO"

3. **BEVANDE** - Bibite gassate, succhi, spremute, caffè freddo (non categoria specifica)
   Esempi: "COCA COLA", "ARANCIATA", "SUCCO DI MELA", "LIMONATA", "THE FREDDO"

4. **BIRRE** - Tutte le tipologie di birra
   Esempi: "BIRRA LAGER", "BIRRA WEISS", "BIRRA STOUT", "WEIZEN"

5. **CAFFE E THE** - Caffè, espresso, decaffeinato (DECA/DECAF), capsule, cialde, tè, tisane, camomille, infusi
    Esempi: "CAFFÈ ESPRESSO KG1", "DECAFFEINATO", "CAPSULE COMPATIBILI", "CIALDE CAFFÈ", "THE NERO", "TÈ VERDE", "TISANA", "CAMOMILLA"

6. **CARNE** - Carni rosse, bianche, selvaggina, preparati
   Esempi: "PETTO POLLO GR600X4", "VITELLO S/O KG5", "BISTECCA MANZO", "SALSICCIA KG2,75"

7. **SCATOLAME E CONSERVE** - Marmellate, confetture, sott'olio, sottaceti, olive, scatolame (tonno, pelati, legumi)
    Esempi: "MARMELLATA FRAGOLA", "OLIVE TAGGIASCHE", "TONNO SCATOLA", "PELATI KG400", "FAGIOLI SCATOLA"

8. **DISTILLATI** - Superalcolici (vodka, gin, rum, whisky, brandy)
   Esempi: "VODKA", "GIN GORDON", "RUM BACARDI", "WHISKY JOHNNIE WALKER", "COGNAC"

9. **FRUTTA** - Frutta fresca, secca (non dolcificata in bar)
   Esempi: "MELE FUJI", "ARANCE", "BANANE", "FRAGOLE", "PESCHE N&C", "FRUTTA SECCA"

10. **GELATI** - Gelati, sorbetti, semifreddi, coppa gelato
    Esempi: "GELATO VANIGLIA KG2", "SORBETTO LIMONE", "SEMIFREDDO", "COPPA GELATO"

11. **LATTICINI** - Formaggi, burro, panna, yogurt, latte
    Esempi: "PARMIGIANO REGGIANO KG2", "MOZZARELLA DI BUFALA", "BURRO", "PANNA", "YOGURT"

12. **NO FOOD** - Materiali non edibili: pellicole, carta, detersivi, bicchieri, posate, tovaglioli, coperchi
    Esempi: "TOVAGLIOLI", "PELLICOLA FILM", "DETERSIVO STOVIGLIE", "BICCHIERI PLASTICA"

13. **OLIO E CONDIMENTI** - Olii, aceti, condimenti
    Esempi: "OLIO EVO", "ACETO BALSAMICO", "OLIO GIRASOLE", "ACETO VINO"

14. **PASTICCERIA** - Dolci, biscotti, crostate, cannoli, pasticcini, pane dolce
    Esempi: "CANNOLI SICILIANI", "CROSTATINE", "BISCOTTI", "BRIOCHE", "SFOGLIA"

15. **PESCE** - Pesce fresco/surgelato, crostacei, molluschi
    Esempi: "SALMONE FRESCO KG1", "MAZZANCOLLE GR500", "CALAMARI", "SPIGOLA"

16. **PRODOTTI DA FORNO** - Pane, focaccia, grissini, pizza, baguette
    Esempi: "PANE CASERECCIO", "FOCACCIA", "PIZZA SURGELATA", "BAGUETTE", "CIABATTA"

17. **SALSE E CREME** - Sughi, pesto, salse, creme, besciamella, roux, passata
    Esempi: "SUGO POMODORO", "PESTO GENOVESE", "PASSATA POMODORO", "ROUX BIANCO", "CREMA NOCCIOLE"

18. **SALUMI** - Affettati, prosciutti, mortadella, pancetta, speck, coppa, bresaola
    Esempi: "PROSCIUTTO CRUDO", "MORTADELLA", "SPECK", "PANCETTA CUBETTI", "SALAME"

19. **SECCO** - Pasta secca, riso, farina, zucchero, biscotti secchi
    Esempi: "PASTA PENNE KG500", "RISO ARBORIO", "FARINA 00", "BISCOTTI"

20. **SHOP** - Prodotti di compravendita (sigarette, caramelle, snack, patatine, gomme)
    Esempi: "CICCHE", "CARAMELLE GOLIA", "PATATINE", "CHIPS", "SNACK", "KINDER", "MARS"

21. **SPEZIE E AROMI** - Spezie, erbe aromatiche, condimenti secchi
    Esempi: "PEPE NERO", "ORIGANO SECCO", "ROSMARINO", "VANIGLIA", "CURRY"

22. **SURGELATI** - Prodotti congelati (no carni/pesci singoli)
    Esempi: "VERDURE MISTE SURGELATE", "PATATINE FRITTE", "CALAMARI SURGELATI"

23. **UOVA** - Uova fresche
    Esempi: "UOVA BOX 30", "UOVA BIOLOGICHE"

24. **VARIE BAR** - Ghiaccio, zucchero bar (solo commestibili per servizio)
    Esempi: "GHIACCIO SACCHETTO", "ZUCCHERO BUSTINE"

25. **VERDURE** - Verdure fresche, ortaggi
    Esempi: "INSALATA MISTA", "POMODORI", "ZUCCHINE", "SPINACI", "AGLIO"

26. **VINI** - Vini rossi, bianchi, rosati, prosecco, champagne, spumante
    Esempi: "VINO ROSSO CHIANTI", "PROSECCO", "CHAMPAGNE VEUVE CLICQUOT"

═══════════════════════════════════════════════════════════════════
📦 CATEGORIE MATERIALI (1 categoria consolidata)
═══════════════════════════════════════════════════════════════════

27. **NO FOOD** - Tutti i materiali non edibili:
    - STOVIGLIE: tazze, piatti, bicchieri, posate, forchette, coltelli
    - MONOUSO: tovaglioli, cannucce, palette, bustine, vaschette, coperchi, pellicole
    - PULIZIA: detersivi, candeggina, sapone, spugne, panni, scope

═══════════════════════════════════════════════════════════════════
💰 CATEGORIE SPESE GENERALI (3 categorie)
═══════════════════════════════════════════════════════════════════

28. **MANUTENZIONE E ATTREZZATURE** - Manutenzione, riparazioni, attrezzature, ricambi
    Esempi: "MANUTENZIONE CALDAIA", "RICAMBIO NEON", "SERVIZIO TECNICO"

29. **SERVIZI E CONSULENZE** - Consulenze, commercialista, POS, marketing, software
    Esempi: "COMMERCIALISTA", "COMMISSIONE POS", "SOFTWARE GESTIONALE", "PUBBLICITÀ"

30. **UTENZE E LOCALI** - Luce, gas, metano, affitto, IMU, TARI, telefono, condominio
    Esempi: "BOLLETTA ENEL", "GAS METANO", "CANONE AFFITTO", "TARI RIFIUTI"

═══════════════════════════════════════════════════════════════════
🎯 REGOLE CLASSIFICAZIONE (PRIORITÀ)
═══════════════════════════════════════════════════════════════════

1. **DICITURE/NOTE**: Se descrizione è riferimento documento, trasporto, bolla → "NOTE E DICITURE" (NO, non è categoria, lasciare da classificare)

2. **MATERIALI PRIMA**: Se contiene parole chiave materiali/non-edibili → "NO FOOD"
   - Parole chiave: pellicola, carta, towel, tovagliolo, bicchiere, piatto, detersivo, posate, cannuccia

3. **BEVANDE SPECIFICHE**: Se contiene alcol specifico → categoria alcol
   - VINI, BIRRE, DISTILLATI, AMARI/LIQUORI hanno priorità su BEVANDE generiche

4. **PRODOTTO FINALE CONTA**: Non ingrediente!
   - CROSTATINE ALBICOCCA → PASTICCERIA (non FRUTTA anche se ha albicocca)
   - CANNONCINI BURRO FARCITI → PASTICCERIA (non LATTICINI anche se ha burro)
   - SALAME DI CIOCCOLATO → PASTICCERIA (non SALUMI anche se ha nome salame)

5. **CONTESTO RISTORANTE**: Usa logica culinaria
   - PASSATA POMODORO → SALSE E CREME (ingrediente da cucina, non FRUTTA)
   - ROUX BIANCO → SALSE E CREME (preparazione culinaria)
   - OLIO OLIVA → OLIO E CONDIMENTI (condimento, non FRUTTA)

6. **INCERTEZZE**: Se veramente incerto, scegli categoria più frequente per ristoranti
   - MIX ASSORTITI → categoria principale più probabile

═══════════════════════════════════════════════════════════════════
⚠️ ERRORI COMUNI DA EVITARE
═══════════════════════════════════════════════════════════════════

❌ NON usare MAI "FOOD" - categoria non esiste!
❌ NON mettere CROSTATINE in FRUTTA - sono PASTICCERIA
❌ NON mettere CANNONCINI BURRO in LATTICINI - sono PASTICCERIA
❌ NON mettere SALAME DI CIOCCOLATO in SALUMI - è PASTICCERIA
❌ NON mettere PASSATA POMODORO in FRUTTA - è SALSE E CREME
❌ NON mettere TAZZE/BICCHIERI in VARIE BAR - sono NO FOOD
✅ TAZZE/BICCHIERI/PIATTI sempre → NO FOOD
✅ DOLCI/PASTICCERIA sempre → PASTICCERIA
✅ BEVANDE ALCOLICHE SPECIFICHE → categoria alcol

═══════════════════════════════════════════════════════════════════
📝 FORMATO RISPOSTA
═══════════════════════════════════════════════════════════════════

🚨 IMPORTANTE: NON restituire MAI "Da Classificare" o stringhe vuote!
   DEVI sempre classificare con la categoria più probabile.
   Se incerto, usa la categoria più comune per ristoranti (es: BEVANDE, NO FOOD).

Rispondi SOLO in JSON:
{
  "categorie": ["CATEGORIA1", "CATEGORIA2", ...]
}

Mantieni lo STESSO ordine degli articoli forniti.
Usa esattamente i nomi categoria sopra (26 food + NO FOOD + 3 spese = 30 categorie).

═══════════════════════════════════════════════════════════════════
🎯 ARTICOLI DA CLASSIFICARE
═══════════════════════════════════════════════════════════════════

{ARTICOLI}
"""

def get_prompt_classificazione(articoli_json: str) -> str:
    """Ritorna il prompt con gli articoli da classificare"""
    return PROMPT_CLASSIFICAZIONE_AI.replace("{ARTICOLI}", articoli_json)
