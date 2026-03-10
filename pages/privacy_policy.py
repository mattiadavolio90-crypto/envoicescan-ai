import streamlit as st
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header

st.set_page_config(
    page_title="Privacy Policy & Termini di Servizio", 
    page_icon="📋",
    initial_sidebar_state="expanded"
)

# Nascondi sidebar immediatamente se non loggato
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.markdown("""
        <style>
        [data-testid="stSidebar"],
        section[data-testid="stSidebar"] {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

# La pagina è pubblica, mostra avviso se non loggati
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.info("ℹ️ Questa pagina è consultabile pubblicamente. Torna al Login per accedere al servizio.")
else:
    # Mostra sidebar solo per utenti loggati
    render_sidebar(st.session_state.user_data)

render_oh_yeah_header()
st.title("📋 Privacy Policy & Termini di Servizio")

# Tab per navigazione tra le due sezioni
tab_privacy, tab_tos = st.tabs(["🔒 Privacy Policy", "📑 Termini di Servizio"])

with tab_privacy:

    st.markdown("""
    ### Titolare del Trattamento
    **Mattia D'Avolio**  
    P.IVA: IT09599210961  
    Email: mattiadavolio90@gmail.com

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

with tab_tos:

    st.markdown("""
    ### 1. Oggetto del Servizio
    Il servizio **OH YEAH!** (di seguito "Servizio") è una piattaforma SaaS di analisi e gestione dei costi per attività di ristorazione, fornita da **Mattia D'Avolio** (P.IVA: IT09599210961).

    Il Servizio include:
    - Caricamento e analisi automatica di fatture elettroniche (XML, PDF, immagini)
    - Classificazione dei prodotti tramite intelligenza artificiale
    - Calcolo margini e analisi dei costi alimentari
    - Gestione workspace operativo (ricette, ingredienti, diario)
    - Controllo prezzi e confronto fornitori

    **⚠️ Il Servizio NON sostituisce la consulenza fiscale, contabile o legale.** L'utente rimane responsabile delle proprie decisioni operative e fiscali.

    ---

    ### 2. Registrazione e Account
    - L'accesso al Servizio richiede la creazione di un account con email, P.IVA e dati del ristorante.
    - L'account è **personale e non cedibile**. L'utente è responsabile della custodia delle proprie credenziali.
    - L'utente garantisce la veridicità dei dati forniti in fase di registrazione.
    - Il Titolare si riserva il diritto di sospendere account con dati manifestamente falsi.

    ---

    ### 3. Utilizzo Consentito
    L'utente si impegna a:
    - Utilizzare il Servizio esclusivamente per finalità lecite e connesse alla propria attività
    - Non tentare di accedere a dati di altri utenti
    - Non sovraccaricare il sistema con upload massivi o automatizzati
    - Non decompilare, disassemblare o effettuare reverse engineering del software
    - Non riprodurre, distribuire o rivendere il Servizio o parte di esso

    ---

    ### 4. Proprietà Intellettuale
    Il software, i codici sorgente, il design, i marchi e tutti i contenuti del Servizio sono di **proprietà esclusiva del Titolare** e protetti dalle leggi italiane ed europee sul diritto d'autore (L. 633/1941, Direttiva UE 2019/790).

    L'utente ottiene una **licenza d'uso non esclusiva, non trasferibile e revocabile** per la durata dell'abbonamento.

    I dati caricati dall'utente (fatture, ricette, note) restano di **proprietà dell'utente**.

    ---

    ### 5. Classificazione AI e Limitazioni
    - La classificazione automatica dei prodotti è fornita tramite intelligenza artificiale e ha natura **indicativa**.
    - Il Titolare **non garantisce l'accuratezza al 100%** delle classificazioni AI.
    - L'utente è tenuto a verificare e correggere le classificazioni quando necessario.
    - Il Servizio fornisce strumenti di revisione e conferma manuale a tale scopo.

    ---

    ### 6. Disponibilità del Servizio
    - Il Titolare si impegna a garantire la disponibilità del Servizio, ma non garantisce un uptime del 100%.
    - Sono previste interruzioni per manutenzione programmata, con preavviso quando possibile.
    - Il Titolare non è responsabile per interruzioni causate da fornitori terzi (Supabase, OpenAI, Brevo) o cause di forza maggiore.

    ---

    ### 7. Limitazione di Responsabilità
    - Il Servizio è fornito **"così com'è" (as is)**.
    - Il Titolare non è responsabile per danni diretti o indiretti derivanti dall'uso del Servizio, inclusi ma non limitati a: perdita di dati, decisioni aziendali basate sulle analisi, interruzioni del servizio.
    - La responsabilità massima del Titolare è in ogni caso limitata all'importo pagato dall'utente nei 12 mesi precedenti.

    ---

    ### 8. Sospensione e Cessazione
    Il Titolare si riserva il diritto di sospendere o cessare l'account dell'utente in caso di:
    - Violazione dei presenti Termini
    - Uso fraudolento o abusivo del Servizio
    - Mancato pagamento (se applicabile)
    - Richiesta dell'autorità giudiziaria

    L'utente può cancellare il proprio account in qualsiasi momento dalla sezione "Gestione Account". Alla cancellazione, tutti i dati vengono eliminati in modo permanente.

    ---

    ### 9. Legge Applicabile e Foro Competente
    I presenti Termini sono regolati dalla **legge italiana**. Per qualsiasi controversia è competente il **Foro di Milano**, salvo diversa disposizione inderogabile di legge a favore del consumatore.

    ---

    ### 10. Modifiche ai Termini
    Ultimo aggiornamento: **10 Marzo 2026**

    Il Titolare si riserva il diritto di modificare i presenti Termini. Le modifiche sostanziali saranno comunicate tramite notifica nell'applicazione con almeno 15 giorni di preavviso. L'uso continuato del Servizio dopo la comunicazione costituisce accettazione delle modifiche.

    ---

    ### Contatti
    **Mattia D'Avolio**  
    Email: mattiadavolio90@gmail.com  
    P.IVA: IT09599210961
    """)
