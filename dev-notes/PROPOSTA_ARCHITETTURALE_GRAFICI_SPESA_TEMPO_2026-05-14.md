# PROPOSTA ARCHITETTURALE - Grafici Spesa nel Tempo

Data: 2026-05-14
Stato: VALIDATA

## Obiettivo
Implementare i grafici mensili di spesa per Fornitore e Categoria (punto 2) nel tab Variazioni Prezzo, riusando il dataset gia caricato in pagina.

## Mappatura file coinvolti
- Modifica: pages/3_controllo_prezzi.py
- Modifica: services/db_service.py
- Modifica: tests/test_db_service.py

## Modello dati reale coinvolto
- Fonte primaria: tabella fatture (gia caricata da carica_e_prepara_dataframe).
- Colonne usate: DataDocumento, TotaleRiga, Fornitore, Categoria.
- Filtri gia applicati upstream: user_id, ristorante_id, deleted_at IS NULL.

## Firme canoniche nuove
- services/db_service.py
  - calcola_spesa_mensile_aggregata(df: pd.DataFrame, dimensione: str) -> pd.DataFrame

Output atteso funzione:
- colonne: mese (Timestamp inizio mese), dimensione, spesa_totale
- ordinamento: dimensione asc, mese asc

## Migliorie tecniche proposte
1. Normalizzazione deterministica delle chiavi fornitore/categoria:
   - trim spazi
   - collapse whitespace interno
   - esclusione valori vuoti
2. Robustezza temporale:
   - parsing DataDocumento con coercion
   - bucket mensile su inizio mese
3. Robustezza numerica:
   - TotaleRiga convertito numerico con fallback 0
4. UX trend:
   - reindex mensile continuo per evitare buchi nel grafico
   - linea media ultimi 12 mesi tratteggiata
5. Performance:
   - nessuna nuova query DB
   - aggregazione in-memory su dataframe gia disponibile

## Cache + session state
- Nessuna nuova cache necessaria.
- Nuove chiavi session_state con namespace cp_:
  - cp_spesa_fornitore_sel
  - cp_spesa_categoria_sel

## Auth + multi-tenant
- Nessuna nuova superficie auth.
- Dataset gia tenant-scoped da pagina (user_id + current_ristorante).

## Step plan operativo
1. Aggiungere helper aggregazione in services/db_service.py.
2. Inserire test unitari su funzione aggregazione in tests/test_db_service.py.
3. Integrare sezione UI in pages/3_controllo_prezzi.py nel tab variazioni.
4. Eseguire test mirati e verifica errori lint/runtime.

## Rollback plan
- Revert puntuale di:
  - import + sezione grafici in pages/3_controllo_prezzi.py
  - funzione calcola_spesa_mensile_aggregata in services/db_service.py
  - test aggiunti in tests/test_db_service.py
