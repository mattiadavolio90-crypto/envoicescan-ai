"""
Script per analizzare e mostrare:
1. Prodotti NON categorizzati (Da Classificare)
2. Categorie errate/invalide
3. Errori di categorizzazione
"""

import os
import toml
from supabase import create_client
from config.constants import TUTTE_LE_CATEGORIE
import pandas as pd

# Carica credenziali
secrets_path = os.path.join(os.path.dirname(__file__), '.streamlit', 'secrets.toml')
secrets = toml.load(secrets_path)
SUPABASE_URL = secrets["supabase"]["url"]
SUPABASE_KEY = secrets["supabase"]["key"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("=" * 100)
print("ANALISI ERRORI CATEGORIZZAZIONE")
print("=" * 100)

# Carica tutte le righe
print("\n📥 Caricamento dati...")
response = supabase.table('fatture')\
    .select('id, descrizione, categoria, fornitore, totale_riga, quantita')\
    .execute()

df = pd.DataFrame(response.data)
print(f"✅ Caricate {len(df)} righe")

# Prepara categorie valide
categorie_valide = set(TUTTE_LE_CATEGORIE) | {"Da Classificare", "📝 NOTE E DICITURE", None, ""}

# ============================================================
# 1. PRODOTTI NON CATEGORIZZATI
# ============================================================
print("\n" + "=" * 100)
print("1️⃣  PRODOTTI NON CATEGORIZZATI (Da Classificare)")
print("=" * 100)

non_cat = df[(df['categoria'] == 'Da Classificare') | 
             (df['categoria'].isna()) | 
             (df['categoria'] == '')].copy()

print(f"\n📊 TOTALE: {len(non_cat)} prodotti su {len(df)} ({len(non_cat)*100//len(df)}%)\n")

if len(non_cat) > 0:
    print("LISTA PRODOTTI NON CATEGORIZZATI:")
    print("-" * 100)
    for idx, row in non_cat.iterrows():
        desc = row['descrizione'][:60] if row['descrizione'] else 'N/A'
        fornitore = row['fornitore'][:30] if row['fornitore'] else 'N/A'
        totale = row['totale_riga'] if row['totale_riga'] else 0
        print(f"  • {desc:65} | Fornitore: {fornitore:30} | €{totale:.2f}")

# ============================================================
# 2. CATEGORIE ERRATE/INVALIDE
# ============================================================
print("\n" + "=" * 100)
print("2️⃣  CATEGORIE ERRATE/INVALIDE")
print("=" * 100)

errate = df[~df['categoria'].isin(categorie_valide)].copy()

print(f"\n📊 TOTALE: {len(errate)} prodotti\n")

if len(errate) > 0:
    print("CATEGORIE NON RICONOSCIUTE:")
    print("-" * 100)
    
    cat_count = errate['categoria'].value_counts()
    for cat, count in cat_count.items():
        print(f"  ❌ '{cat}': {count} prodotti")
    
    print("\nESEMPI DI PRODOTTI CON CATEGORIA ERRATA:")
    print("-" * 100)
    for idx, row in errate.head(15).iterrows():
        desc = row['descrizione'][:50] if row['descrizione'] else 'N/A'
        cat = row['categoria']
        print(f"  • {desc:55} → {cat}")

# ============================================================
# 3. ANALISI PER FORNITORE
# ============================================================
print("\n" + "=" * 100)
print("3️⃣  ANALISI PER FORNITORE (fornitori con più non-categorizzati)")
print("=" * 100)

fornitore_nc = non_cat['fornitore'].value_counts().head(10)
print(f"\nFORNITORI CON PIÙ PRODOTTI NON CATEGORIZZATI:")
print("-" * 100)
for fornitore, count in fornitore_nc.items():
    print(f"  • {fornitore}: {count} prodotti")

# ============================================================
# 4. STATISTICHE GENERALI
# ============================================================
print("\n" + "=" * 100)
print("4️⃣  STATISTICHE GENERALI")
print("=" * 100)

print(f"\n📊 RIEPILOGO CATEGORIZZAZIONE:")
print(f"  ✅ Categorizzati correttamente: {len(df) - len(non_cat) - len(errate)} ({(len(df) - len(non_cat) - len(errate))*100//len(df)}%)")
print(f"  ⚠️  Non categorizzati: {len(non_cat)} ({len(non_cat)*100//len(df)}%)")
print(f"  ❌ Categorie errate: {len(errate)} ({len(errate)*100//len(df)}%)")
print(f"  📊 TOTALE RIGHE: {len(df)}")

print(f"\n💰 IMPORTI:")
print(f"  ✅ Valore categorizzato correttamente: €{(df[~df.index.isin(non_cat.index) & ~df.index.isin(errate.index)]['totale_riga'].sum() or 0):.2f}")
print(f"  ⚠️  Valore non categorizzato: €{(non_cat['totale_riga'].sum() or 0):.2f}")
print(f"  ❌ Valore con categoria errata: €{(errate['totale_riga'].sum() or 0):.2f}")

# ============================================================
# 5. DISTRIBUZIONE CATEGORIE CORRETTE
# ============================================================
print("\n" + "=" * 100)
print("5️⃣  DISTRIBUZIONE CATEGORIE CORRETTE")
print("=" * 100)

corrette = df[df['categoria'].isin(TUTTE_LE_CATEGORIE)].copy()
cat_dist = corrette['categoria'].value_counts().sort_values(ascending=False)

print(f"\nTOP 15 CATEGORIE:")
print("-" * 100)
for cat, count in cat_dist.head(15).items():
    valore = corrette[corrette['categoria'] == cat]['totale_riga'].sum()
    pct = count * 100 // len(corrette) if len(corrette) > 0 else 0
    print(f"  • {cat:35} {count:4d} prodotti ({pct:2d}%) | €{valore:.2f}")

print("\n" + "=" * 100)
