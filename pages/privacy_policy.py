import streamlit as st

st.set_page_config(page_title="Privacy Policy", page_icon="📋")

# La pagina è pubblica, mostra avviso se non loggati
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.info("ℹ️ Questa pagina è consultabile pubblicamente. Torna al Login per accedere al servizio.")

# Nascondi sidebar
st.markdown("""
<style>
[data-testid="stSidebar"] {display: none;}
[data-testid="collapsedControl"] {display: none;}
</style>
""", unsafe_allow_html=True)

st.title("📋 Privacy Policy & Informativa Cookie")

st.markdown("""
### Titolare del Trattamento
**Mattia D'Avolio**  
P.IVA: IT09599210961  
Email: [SOSTITUISCI CON TUA EMAIL]

---

### Dati Raccolti
- **Dati anagrafici:** Email, nome ristorante, P.IVA, ragione sociale
- **Dati di accesso:** Password (conservata in formato hash crittografico Argon2)
- **Documenti:** Fatture XML/PDF caricate dall'utente per analisi

---

### Finalità del Trattamento
Erogazione servizio di analisi fatture e controllo gestionale costi.

**⚠️ Importante:** Questo servizio NON effettua Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture presso i canali certificati.

---

### Base Giuridica
Esecuzione del contratto (Art. 6.1.b GDPR)

---

### Conservazione Dati
I dati sono conservati per la durata del rapporto contrattuale. Alla cancellazione dell'account, tutti i dati vengono eliminati in modo permanente dai nostri server applicativi.

---

### Destinatari dei Dati
I tuoi dati sono trattati dai seguenti fornitori di servizi:

- **Supabase Inc.** - Hosting database (server ubicati in UE)
- **OpenAI LP** - Elaborazione AI per categorizzazione automatica (USA, con clausole contrattuali standard UE)
- **Brevo SAS** - Invio email transazionali (UE)

---

### Cookie Utilizzati
Utilizziamo **esclusivamente cookie tecnici** strettamente necessari per:
- Mantenere la sessione di login durante la navigazione
- Garantire il corretto funzionamento dell'applicazione

**NON utilizziamo:**
- Cookie di profilazione
- Cookie analytics o di tracciamento
- Cookie di terze parti per pubblicità

---

### Diritti dell'Utente (Art. 15-22 GDPR)
Hai diritto a:

- **Accesso:** Visualizzazione dei propri dati tramite interfaccia app
- **Cancellazione:** Funzione "Elimina Account" self-service (eliminazione permanente)
- **Portabilità:** Download dei propri dati in formato strutturato
- **Rettifica:** Modifica dei dati anagrafici dal profilo

Per esercitare i diritti, utilizza le funzioni disponibili nell'applicazione o contatta l'indirizzo email sopra indicato.

---

### Modifiche alla Privacy Policy
Ultimo aggiornamento: **5 Febbraio 2026**

Ci riserviamo il diritto di modificare questa informativa. Gli utenti verranno informati tramite notifica nell'applicazione in caso di modifiche sostanziali.

---
""")

st.markdown("<br>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 1, 1])
with col2:
    if st.button("← Torna all'App", type="primary", use_container_width=True):
        st.switch_page("app.py")
