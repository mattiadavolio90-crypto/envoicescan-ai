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
    **Recoma System S.r.l.**  
    P.IVA: IT09599210961  
    Referente tecnico: Mattia D'Avolio  
    Email: mattiadavolio90@gmail.com

    ---

    ### Dati Raccolti
    - **Dati anagrafici:** Email, nome ristorante, P.IVA, ragione sociale
    - **Dati di accesso:** Password (conservata esclusivamente in formato hash crittografico Argon2id — la password in chiaro non viene mai archiviata)
    - **Documenti:** Fatture elettroniche XML/P7M/PDF caricate dall'utente per analisi gestionale
    - **Dati operativi:** Ricette, ingredienti, note diario, margini mensili
    - **Dati di sessione:** Token di sessione UUID4 con scadenza, timestamp login/logout

    ---

    ### Finalità del Trattamento
    Erogazione del servizio di analisi fatture, controllo gestionale costi e supporto operativo per attività di ristorazione.

    **⚠️ Importante:** Questo servizio NON effettua Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente resta responsabile della conservazione fiscale delle fatture elettroniche per 10 anni presso i canali certificati AgID.

    ---

    ### Base Giuridica del Trattamento
    - **Art. 6.1.b GDPR** — Esecuzione del contratto di servizio
    - **Consenso esplicito** — Raccolto mediante checkbox obbligatorio al primo accesso (attivazione account), con riferimento al presente documento

    ---

    ### Conservazione Dati
    - I dati sono conservati per la durata del rapporto contrattuale.
    - **Fatture:** trattenute fino a eliminazione volontaria da parte dell'utente.
    - **File XML/P7M originali:** purgati automaticamente dopo il processing (non archiviati in forma grezza).
    - **Log applicativi:** rotazione automatica — 50 MB × 10 file di backup, senza dati PII in chiaro.
    - Alla cancellazione dell'account, **tutti i dati vengono eliminati in modo permanente** (eliminazione a cascata su tutte le tabelle correlate — Art. 17 GDPR).

    ---

    ### Destinatari dei Dati
    I tuoi dati sono trattati dai seguenti fornitori terzi (sub-responsabili del trattamento):

    | Fornitore | Ruolo | Sede | Garanzie |
    |-----------|-------|------|-----------|
    | **Supabase Inc.** | Hosting database | UE — Frankfurt 🇩🇪 | Dati persistiti esclusivamente in UE |
    | **OpenAI LP** | Elaborazione AI categorizzazione | USA | Clausole contrattuali standard UE (SCCs); dati elaborati on-the-fly, non archiviati per training |
    | **Brevo SAS** | SMTP transazionale | UE | Nessun contenuto di fatture trasmesso |

    ---

    ### Cookie e Tecnologie di Tracciamento
    Utilizziamo **esclusivamente cookie tecnici di sessione**, strettamente necessari per:
    - Mantenere autenticata la sessione di login durante la navigazione
    - Garantire il corretto funzionamento dell'applicazione

    **Caratteristiche tecniche del cookie di sessione:**
    - Nome: `session_token`
    - Tipo: cookie tecnico di sessione (strettamente necessario)
    - Scadenza: 30 giorni
    - Contenuto: token UUID4 opaco, senza dati personali in chiaro
    - Scope: `SameSite=Lax`, trasmesso solo su HTTPS

    **NON utilizziamo:**
    - Cookie di profilazione o marketing
    - Cookie analytics o di tracciamento comportamentale
    - Cookie di terze parti per pubblicità
    - Pixel di tracciamento

    Ai sensi del Provvedimento del Garante Privacy dell'8 gennaio 2015 e delle Linee Guida 2022, i cookie tecnici strettamente necessari **non richiedono consenso preventivo**, ma richiedono informativa — che viene fornita tramite banner informativo nella pagina di accesso.

    ---

    ### Consenso al Trattamento
    Al primo accesso (attivazione account), viene richiesto il **consenso esplicito** mediante checkbox obbligatorio, con riferimento alla presente Informativa Privacy (D.lgs. 196/2003 e GDPR UE 2016/679). Il servizio non viene erogato in assenza di consenso.

    Il consenso è revocabile in qualsiasi momento eliminando l'account tramite la funzione "Elimina Account" nella sezione Gestione Account.

    ---

    ### Misure di Sicurezza Tecniche e Organizzative
    In conformità all'Art. 32 GDPR, adottiamo le seguenti misure:
    - **Cifratura password:** Argon2id (m=65536, t=2, p=1) — standard OWASP 2024
    - **Cifratura in transito:** TLS 1.3 su tutti i canali (Supabase, Streamlit)
    - **Cifratura a riposo:** AES-256 (gestita da Supabase)
    - **Controllo accessi:** Multi-tenancy con Row-Level Security PostgreSQL + filtri applicativi per utente e ristorante
    - **Rate limiting:** protezione brute-force su login (5 tentativi/15 min) e reset password (1/5 min), persistente su database
    - **Gestione sessioni:** invalidazione esplicita al logout, scadenza automatica a 30 giorni
    - **Test di sicurezza:** 172 test automatizzati, pipeline CI/CD con verifica ad ogni rilascio

    ---

    ### Diritti dell'Utente (Art. 15-22 GDPR)
    Hai diritto a:

    | Diritto | Come esercitarlo |
    |---------|-----------------|
    | **Accesso** (Art. 15) | Visualizzazione dati tramite interfaccia app |
    | **Cancellazione** (Art. 17) | Funzione "Elimina Account" self-service — eliminazione permanente immediata |
    | **Portabilità** (Art. 20) | Download dati in formato strutturato |
    | **Rettifica** (Art. 16) | Modifica dati anagrafici dal profilo |
    | **Opposizione** (Art. 21) | Contatto email con il Titolare |
    | **Limitazione** (Art. 18) | Richiesta via email al Titolare |

    Hai inoltre il diritto di proporre reclamo all'**Autorità Garante per la Protezione dei Dati Personali** (www.garanteprivacy.it).

    ---

    ### Modifiche alla Privacy Policy
    Ultimo aggiornamento: **21 Marzo 2026**

    Ci riserviamo il diritto di modificare questa informativa. Gli utenti registrati verranno informati tramite notifica nell'applicazione in caso di modifiche sostanziali, con preavviso di almeno 15 giorni.

    ---
    """)

with tab_tos:

    st.markdown("""
    ### 1. Oggetto del Servizio
    Il servizio **OH YEAH! Hub** (di seguito "Servizio") è una piattaforma SaaS di analisi e gestione dei costi per attività di ristorazione, fornita da **Recoma System S.r.l.** (P.IVA: IT09599210961, referente: Mattia D'Avolio).

    Il Servizio include:
    - Caricamento e analisi automatica di fatture elettroniche (XML, P7M, PDF)
    - Classificazione dei prodotti tramite intelligenza artificiale
    - Calcolo margini e analisi dei costi alimentari
    - Gestione workspace operativo (ricette, ingredienti, diario)
    - Controllo prezzi e confronto fornitori
    - Worker automatico di elaborazione fatture con coda persistente

    **⚠️ Il Servizio NON sostituisce la consulenza fiscale, contabile o legale** e NON costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014. L'utente rimane responsabile delle proprie decisioni operative e fiscali.

    ---

    ### 2. Registrazione e Account
    - L'accesso al Servizio richiede la creazione di un account con email, P.IVA e dati del ristorante.
    - Al primo accesso è richiesta l'accettazione esplicita della Privacy Policy (consenso GDPR Art. 6.1.b).
    - L'account è **personale e non cedibile**. L'utente è responsabile della custodia delle proprie credenziali.
    - L'utente garantisce la veridicità dei dati forniti in fase di registrazione.
    - Il Titolare si riserva il diritto di sospendere account con dati manifestamente falsi.

    ---

    ### 3. Utilizzo Consentito
    L'utente si impegna a:
    - Utilizzare il Servizio esclusivamente per finalità lecite e connesse alla propria attività
    - Non tentare di accedere a dati di altri utenti
    - Non sovraccaricare il sistema con upload massivi o automatizzati non previsti
    - Non decompilare, disassemblare o effettuare reverse engineering del software
    - Non riprodurre, distribuire o rivendere il Servizio o parte di esso
    - Non utilizzare il Servizio per attività di scraping, data mining o raccolta sistematica di dati

    ---

    ### 4. Proprietà Intellettuale
    Il software, i codici sorgente, il design, i marchi e tutti i contenuti del Servizio sono di **proprietà esclusiva del Titolare** e protetti dalle leggi italiane ed europee sul diritto d'autore (L. 633/1941, Direttiva UE 2019/790).

    L'utente ottiene una **licenza d'uso non esclusiva, non trasferibile e revocabile** per la durata dell'abbonamento.

    I dati caricati dall'utente (fatture, ricette, note) restano di **proprietà dell'utente**.

    ---

    ### 5. Classificazione AI e Limitazioni
    - La classificazione automatica dei prodotti è fornita tramite intelligenza artificiale (OpenAI GPT-4o) e ha natura **indicativa**.
    - Il Titolare **non garantisce l'accuratezza al 100%** delle classificazioni AI.
    - I contenuti delle fatture vengono trasmessi ad OpenAI **esclusivamente on-the-fly** per la categorizzazione, senza archivio permanente.
    - L'utente è tenuto a verificare e correggere le classificazioni quando necessario.
    - Il Servizio fornisce strumenti di revisione e conferma manuale a tale scopo.

    ---

    ### 6. Sicurezza e Responsabilità dell'Utente
    Il Titolare adotta misure di sicurezza adeguate (Argon2id, TLS 1.3, rate limiting, RLS PostgreSQL). Tuttavia:
    - L'utente è responsabile della sicurezza delle proprie credenziali di accesso.
    - In caso di sospetta compromissione dell'account, l'utente deve notificare immediatamente il Titolare.
    - Il Titolare non può essere ritenuto responsabile per accessi non autorizzati causati da negligenza dell'utente.

    ---

    ### 7. Disponibilità del Servizio
    - Il Titolare si impegna a garantire la disponibilità del Servizio (target SLA: 99,5% mensile).
    - Sono previste interruzioni per manutenzione programmata, con preavviso quando possibile.
    - Il Titolare non è responsabile per interruzioni causate da fornitori terzi (Supabase, OpenAI, Brevo, Streamlit Cloud) o cause di forza maggiore.

    ---

    ### 8. Limitazione di Responsabilità
    - Il Servizio è fornito **"così com'è" (as is)**.
    - Il Titolare non è responsabile per danni diretti o indiretti derivanti dall'uso del Servizio, inclusi ma non limitati a: perdita di dati, decisioni aziendali basate sulle analisi, interruzioni del servizio, classificazioni AI errate.
    - La responsabilità massima del Titolare è in ogni caso limitata all'importo pagato dall'utente nei 12 mesi precedenti l'evento dannoso.

    ---

    ### 9. Sospensione e Cessazione
    Il Titolare si riserva il diritto di sospendere o cessare l'account dell'utente in caso di:
    - Violazione dei presenti Termini
    - Uso fraudolento o abusivo del Servizio
    - Mancato pagamento (se applicabile)
    - Richiesta dell'autorità giudiziaria

    L'utente può cancellare il proprio account in qualsiasi momento dalla sezione "Gestione Account". Alla cancellazione, tutti i dati vengono eliminati in modo permanente e irreversibile.

    ---

    ### 10. Legge Applicabile e Foro Competente
    I presenti Termini sono regolati dalla **legge italiana**. Per qualsiasi controversia è competente il **Foro di Milano**, salvo diversa disposizione inderogabile di legge a favore del consumatore.

    ---

    ### 11. Modifiche ai Termini
    Ultimo aggiornamento: **21 Marzo 2026**

    Il Titolare si riserva il diritto di modificare i presenti Termini. Le modifiche sostanziali saranno comunicate tramite notifica nell'applicazione con almeno 15 giorni di preavviso. L'uso continuato del Servizio dopo la comunicazione costituisce accettazione delle modifiche.

    ---

    ### Contatti
    **Recoma System S.r.l.**  
    Referente: Mattia D'Avolio  
    Email: mattiadavolio90@gmail.com  
    P.IVA: IT09599210961
    """)

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
