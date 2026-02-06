# 🚀 GUIDA: Esecuzione Migration Ricette

## ❌ ERRORE ATTUALE
```
Could not find the table 'public.ricette' in the schema cache
```

**Causa**: La tabella `ricette` non esiste ancora nel database Supabase.

---

## ✅ SOLUZIONE: Esegui Migration SQL

### STEP 1: Accedi alla Dashboard Supabase

1. Vai su: https://supabase.com/dashboard
2. Login con le tue credenziali
3. Seleziona il progetto FCI

### STEP 2: Apri SQL Editor

1. Nel menu laterale sinistro clicca su **"SQL Editor"**
2. Clicca sul bottone **"New Query"** in alto a destra

### STEP 3: Copia/Incolla Migration

1. Apri il file: `migrations/018_create_ricette_table.sql`
2. Seleziona TUTTO il contenuto (Ctrl+A)
3. Copia (Ctrl+C)
4. Incolla nell'SQL Editor di Supabase (Ctrl+V)

### STEP 4: Esegui Query

1. Clicca sul bottone **"Run"** (o premi Ctrl+Enter)
2. Attendi qualche secondo
3. Dovresti vedere il messaggio: **"Success. No rows returned"**

### STEP 5: Verifica Creazione

1. Nel menu laterale clicca su **"Table Editor"**
2. Dovresti vedere la nuova tabella **"ricette"** nell'elenco
3. Clicca su "ricette" e verifica le colonne:
   - id (uuid)
   - userid (uuid)
   - ristorante_id (uuid)
   - nome (text)
   - categoria (text)
   - ingredienti (jsonb)
   - foodcost_totale (numeric)
   - ordine_visualizzazione (int4)
   - created_at (timestamptz)
   - updated_at (timestamptz)

---

## 🔍 VERIFICA RLS POLICIES

Dopo aver eseguito la migration, verifica le policies:

1. Vai su **"Authentication"** → **"Policies"** nel menu Supabase
2. Cerca la tabella **"ricette"**
3. Dovresti vedere 4 policies:
   - `ricette_select_policy` (SELECT)
   - `ricette_insert_policy` (INSERT)
   - `ricette_update_policy` (UPDATE)
   - `ricette_delete_policy` (DELETE)

---

## 🧪 TEST FUNZIONALITÀ

Dopo la migration:

1. Ricarica la pagina Workspace nell'app (F5)
2. L'errore **"Could not find table"** dovrebbe sparire
3. Dovresti vedere tab vuoti con il messaggio: _"Nessuna ricetta salvata"_
4. Vai su tab **"Nuova Ricetta"**
5. Crea la tua prima ricetta di test

---

## ⚠️ TROUBLESHOOTING

### Errore: "permission denied for schema public"
**Soluzione**: Verifica che l'utente Supabase abbia permessi di CREATE TABLE.
Esegui nel SQL Editor:
```sql
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres;
```

### Errore: "function uuid_generate_v4() does not exist"
**Soluzione**: Abilita estensione UUID.
Esegui nel SQL Editor:
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Tabella creata ma policies non funzionano
**Soluzione**: Verifica che RLS sia abilitato.
Esegui nel SQL Editor:
```sql
ALTER TABLE ricette ENABLE ROW LEVEL SECURITY;
```

---

## 📝 NOTE IMPORTANTI

1. ⚠️ **Backup**: Se il database contiene già dati importanti, fai un backup prima di eseguire migration
2. ✅ **Idempotenza**: La migration usa `IF NOT EXISTS` quindi è sicuro eseguirla più volte
3. 🔒 **RLS**: Le policies garantiscono che ogni utente veda solo le proprie ricette
4. 🏢 **Multi-ristorante**: Ogni ricetta è legata a un `ristorante_id` specifico

---

## ✅ CHECKLIST POST-MIGRATION

- [ ] Tabella `ricette` creata
- [ ] 10 colonne presenti nella tabella
- [ ] 4 policies RLS attive
- [ ] 4 indici creati (incluso GIN per JSONB)
- [ ] 2 RPC functions create (`swap_ricette_order`, `get_next_ordine_ricetta`)
- [ ] Trigger `update_ricette_timestamp` attivo
- [ ] Test creazione ricetta funziona
- [ ] Export Excel disponibile

---

**Una volta completata la migration, ricarica l'app e il sistema ricette sarà completamente funzionante!** 🎉
