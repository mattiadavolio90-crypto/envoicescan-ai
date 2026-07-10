import type { Metadata } from "next";
import Link from "next/link";
import { LegalProse, LegalTable, LegalCallout } from "../legal-prose";

export const metadata: Metadata = {
  title: "Privacy & Cookie Policy",
  description: "Informativa privacy e cookie di ONEFLUX ai sensi del GDPR UE 2016/679.",
};

export default function PrivacyPage() {
  return (
    <LegalProse>
      <h1 className="text-2xl font-bold text-foreground">Privacy & Cookie Policy</h1>
      <p className="text-xs text-muted-foreground">
        Ultimo aggiornamento: 19 giugno 2026 — versione 4.1
      </p>

      <h2>Titolare del Trattamento</h2>
      <p>
        <strong>RECOMASYSTEM Srl</strong>
        <br />
        Sede legale: Via Leonardo da Vinci 249, 20090 Trezzano sul Naviglio (MI)
        <br />
        P.IVA: 12993240154
        <br />
        Email: <a href="mailto:md@oneflux.it">md@oneflux.it</a>
      </p>
      <p>
        ONEFLUX è ideato e sviluppato da <strong>Mattia D&apos;Avolio</strong>, fondatore e
        creatore della piattaforma, che ne cura lo sviluppo e funge da referente tecnico
        per il trattamento dei dati.
      </p>

      <h2>Dati Raccolti</h2>
      <ul>
        <li>
          <strong>Dati anagrafici:</strong> email, nome ristorante, P.IVA, ragione sociale
        </li>
        <li>
          <strong>Dati di accesso:</strong> password (conservata esclusivamente in formato hash
          crittografico Argon2id — la password in chiaro non viene mai archiviata)
        </li>
        <li>
          <strong>Documenti:</strong> fatture elettroniche XML/P7M/PDF caricate dall&apos;utente o
          ricevute automaticamente tramite SDI (Invoicetronic)
        </li>
        <li>
          <strong>Dati operativi:</strong> ricette, ingredienti, note diario, margini mensili
        </li>
        <li>
          <strong>Dati di sessione:</strong> token di sessione opachi ad alta entropia generati lato
          server, con scadenza, timestamp login/logout e controlli di inattività
        </li>
        <li>
          <strong>Log operativi:</strong> registro upload (nome file, esito, conteggi righe),
          registro utilizzo AI (modello, token consumati, costo per operazione)
        </li>
        <li>
          <strong>Preferenze applicazione:</strong> stato periodo di prova, preferenze notifiche
          in-app (ID notifiche nascoste)
        </li>
      </ul>

      <h2>Finalità del Trattamento</h2>
      <p>
        Erogazione del servizio di analisi fatture, controllo gestionale costi e supporto operativo
        per attività di ristorazione.
      </p>
      <LegalCallout>
        <strong>⚠️ Importante:</strong> questo servizio NON effettua Conservazione Sostitutiva ai
        sensi del D.M. 17 giugno 2014. L&apos;utente resta responsabile della conservazione fiscale
        delle fatture elettroniche per 10 anni presso i canali certificati AgID.
      </LegalCallout>

      <h2>Base Giuridica del Trattamento</h2>
      <ul>
        <li>
          <strong>Art. 6.1.b GDPR</strong> — esecuzione del contratto di servizio
        </li>
        <li>
          <strong>Consenso esplicito</strong> — raccolto mediante checkbox obbligatorio al primo
          accesso (attivazione account), con riferimento al presente documento. Il timestamp del
          consenso è registrato a fini probatori (Art. 7.1 GDPR).
        </li>
      </ul>

      <h2>Conservazione Dati</h2>
      <ul>
        <li>I dati sono conservati per la durata del rapporto contrattuale.</li>
        <li>
          <strong>Fatture:</strong> trattenute fino a eliminazione volontaria da parte
          dell&apos;utente.
        </li>
        <li>
          <strong>File XML/P7M originali:</strong> purgati automaticamente dopo il processing (non
          archiviati in forma grezza). I file ricevuti via SDI (Invoicetronic) vengono purgati dalla
          coda entro 24 ore dall&apos;elaborazione.
        </li>
        <li>
          <strong>Log operativi (upload e AI):</strong> conservati per la durata dell&apos;account a
          fini di trasparenza e supporto tecnico.
        </li>
        <li>
          <strong>Log applicativi:</strong> rotazione automatica, senza dati PII in chiaro.
        </li>
        <li>
          <strong>Tentativi di accesso:</strong> conservati per 15 minuti (rate limiting
          anti-brute-force), poi eliminati automaticamente.
        </li>
        <li>
          Alla cancellazione dell&apos;account, <strong>tutti i dati vengono eliminati in modo
          permanente</strong> (eliminazione a cascata su tutte le tabelle correlate — Art. 17 GDPR).
        </li>
      </ul>

      <h2>Destinatari dei Dati</h2>
      <p>I tuoi dati sono trattati dai seguenti fornitori terzi (sub-responsabili del trattamento):</p>
      <LegalTable
        head={["Fornitore", "Ruolo", "Sede", "Garanzie"]}
        rows={[
          [
            "Supabase Inc.",
            "Hosting database",
            "UE — Frankfurt 🇩🇪",
            "Dati persistiti esclusivamente in UE",
          ],
          [
            "OpenAI LP",
            "Elaborazione AI categorizzazione",
            "USA",
            "Clausole contrattuali standard UE (SCCs); dati elaborati on-the-fly, non archiviati per training",
          ],
          ["Brevo SAS", "SMTP transazionale", "UE — Francia 🇫🇷", "Nessun contenuto di fatture trasmesso"],
          [
            "Invoicetronic S.r.l.",
            "Ricezione fatture SDI e inoltro webhook",
            "Italia 🇮🇹",
            "Eventi webhook e metadati fatture inoltrati verso l'infrastruttura ONEFLUX; XML grezzo non archiviato dopo la consegna",
          ],
          [
            "Vercel Inc.",
            "Hosting interfaccia web (Next.js)",
            "UE (region Frankfurt) / USA",
            "Nessun dato applicativo persistito lato Vercel; SCCs UE",
          ],
          [
            "Railway Corp.",
            "Worker elaborazione fatture e API",
            "USA",
            "Elaborazione in memoria, nessun dato persistito; SCCs UE",
          ],
        ]}
      />

      <h2>Cookie e Tecnologie di Tracciamento</h2>
      <p>
        Utilizziamo <strong>esclusivamente cookie tecnici</strong>, strettamente necessari per:
      </p>
      <ul>
        <li>Mantenere autenticata la sessione di login durante la navigazione</li>
        <li>Garantire il corretto funzionamento dell&apos;applicazione</li>
      </ul>
      <p>
        <strong>Caratteristiche tecniche dei cookie utilizzati:</strong>
      </p>
      <LegalTable
        head={["Cookie", "Tipo", "Scadenza", "Contenuto", "Note"]}
        rows={[
          [
            "oneflux_session",
            "Tecnico / sessione",
            "30 giorni",
            "Token di sessione opaco ad alta entropia",
            "Mantenimento sessione di login",
          ],
          [
            "oneflux_session_backup",
            "Tecnico / amministrativo",
            "8 ore",
            "Token sessione admin originale durante l'impersonazione",
            "Solo per account amministratori; ripristino sessione admin",
          ],
          [
            "oneflux_impersonate",
            "Tecnico / amministrativo",
            "8 ore",
            "Flag tecnico (nessun dato personale)",
            "Solo per account amministratori; segnala una sessione di supporto attiva",
          ],
        ]}
      />
      <p>
        Tutti i cookie sono impostati con <strong>SameSite=Lax</strong>, flag{" "}
        <strong>Secure</strong> in produzione (trasmessi solo su HTTPS) e{" "}
        <strong>HttpOnly</strong> (non accessibili da JavaScript). Nessun cookie contiene dati
        personali in chiaro: l&apos;identità dell&apos;utente eventualmente impersonato da un
        amministratore durante una sessione di supporto è derivata lato server e non è esposta nei
        cookie del browser.
      </p>
      <p>
        <strong>NON utilizziamo:</strong>
      </p>
      <ul>
        <li>Cookie di profilazione o marketing</li>
        <li>Cookie analytics o di tracciamento comportamentale</li>
        <li>Cookie di terze parti per pubblicità</li>
        <li>Pixel di tracciamento</li>
      </ul>
      <p>
        I font dell&apos;interfaccia sono ospitati internamente (self-hosted): nessuna richiesta a
        CDN di terze parti viene effettuata durante la navigazione.
      </p>
      <p>
        Ai sensi del Provvedimento del Garante Privacy del 10 giugno 2021 e delle Linee Guida sui
        cookie, i cookie tecnici strettamente necessari{" "}
        <strong>non richiedono consenso preventivo</strong>, ma richiedono informativa — fornita dal
        presente documento e da un avviso informativo all&apos;interno dell&apos;applicazione.
      </p>
      <p>
        Per eliminare i cookie tecnici è sufficiente cancellare i cookie del browser nelle relative
        impostazioni. L&apos;operazione comporterà la disconnessione dall&apos;applicazione.
      </p>

      <h2>Consenso al Trattamento</h2>
      <p>
        Al primo accesso (attivazione account) viene richiesto il <strong>consenso esplicito</strong>{" "}
        mediante checkbox obbligatorio, con riferimento alla presente Informativa Privacy (D.lgs.
        196/2003 e GDPR UE 2016/679). Il servizio non viene erogato in assenza di consenso, e il
        relativo timestamp viene registrato a fini probatori.
      </p>
      <p>
        Il consenso è revocabile in qualsiasi momento eliminando l&apos;account da{" "}
        <strong>Impostazioni → Privacy e dati → &quot;Elimina il mio account&quot;</strong>.
      </p>

      <h2>Misure di Sicurezza Tecniche e Organizzative</h2>
      <p>In conformità all&apos;Art. 32 GDPR, adottiamo le seguenti misure:</p>
      <ul>
        <li>
          <strong>Cifratura password:</strong> Argon2id (m=65536, t=3, p=1) — standard OWASP
        </li>
        <li>
          <strong>Cifratura in transito:</strong> TLS 1.3 su tutti i canali
        </li>
        <li>
          <strong>Cifratura a riposo:</strong> AES-256 (gestita da Supabase)
        </li>
        <li>
          <strong>Controllo accessi:</strong> multi-tenancy con Row-Level Security PostgreSQL +
          filtri applicativi per utente e ristorante
        </li>
        <li>
          <strong>Rate limiting:</strong> protezione brute-force su login e reset password,
          persistente su database
        </li>
        <li>
          <strong>Gestione sessioni:</strong> invalidazione esplicita al logout e su token non
          valido, scadenza automatica, cookie HttpOnly + Secure + SameSite=Lax
        </li>
        <li>
          <strong>IDOR protection:</strong> filtro per identità utente su tutte le operazioni di
          modifica
        </li>
        <li>
          <strong>Protezione XXE:</strong> validazione XML con defusedxml prima del parsing
        </li>
        <li>
          <strong>Protezione SSRF:</strong> whitelist host autorizzati per fetch XML remoti
        </li>
        <li>
          <strong>Test di sicurezza:</strong> suite di test automatizzati, pipeline CI/CD con
          verifica ad ogni rilascio
        </li>
      </ul>

      <h2>Diritti dell&apos;Utente (Art. 15-22 GDPR)</h2>
      <LegalTable
        head={["Diritto", "Come esercitarlo"]}
        rows={[
          ["Accesso (Art. 15)", "Visualizzazione dati tramite interfaccia app"],
          [
            "Cancellazione (Art. 17)",
            "Impostazioni → Privacy e dati → \"Elimina il mio account\": eliminazione permanente e immediata, self-service",
          ],
          [
            "Portabilità (Art. 20)",
            "Impostazioni → Privacy e dati → \"Scarica i miei dati\": export in formato JSON strutturato",
          ],
          ["Rettifica (Art. 16)", "Modifica dati anagrafici dal profilo"],
          ["Opposizione (Art. 21)", "Contatto email con il Titolare"],
          ["Limitazione (Art. 18)", "Richiesta via email al Titolare"],
        ]}
      />
      <p>
        Hai inoltre il diritto di proporre reclamo all&apos;
        <strong>Autorità Garante per la Protezione dei Dati Personali</strong> (
        <a href="https://www.garanteprivacy.it" target="_blank" rel="noopener noreferrer">
          www.garanteprivacy.it
        </a>
        ).
      </p>

      <h2>Modifiche alla Privacy Policy</h2>
      <p>
        Ci riserviamo il diritto di modificare questa informativa. Gli utenti registrati verranno
        informati tramite notifica nell&apos;applicazione in caso di modifiche sostanziali, con
        preavviso di almeno 15 giorni.
      </p>

      <p className="pt-4">
        Consulta anche i{" "}
        <Link href="/termini">Termini di Servizio</Link>.
      </p>
    </LegalProse>
  );
}
