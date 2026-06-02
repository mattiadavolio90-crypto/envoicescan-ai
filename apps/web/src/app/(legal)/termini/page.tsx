import type { Metadata } from "next";
import Link from "next/link";
import { LegalProse, LegalCallout } from "../legal-prose";

export const metadata: Metadata = {
  title: "Termini di Servizio",
  description: "Termini e condizioni d'uso della piattaforma ONEFLUX.",
};

export default function TerminiPage() {
  return (
    <LegalProse>
      <h1 className="text-2xl font-bold text-foreground">Termini di Servizio</h1>
      <p className="text-xs text-muted-foreground">Ultimo aggiornamento: 2 giugno 2026</p>

      <h2>1. Oggetto del Servizio</h2>
      <p>
        Il servizio <strong>ONEFLUX</strong> (di seguito &quot;Servizio&quot;) è una piattaforma SaaS
        di analisi e gestione dei costi per attività di ristorazione, fornita da{" "}
        <strong>Recoma System S.r.l.</strong> (P.IVA: IT09599210961, referente: Mattia
        D&apos;Avolio).
      </p>
      <p>Il Servizio include:</p>
      <ul>
        <li>Caricamento e analisi automatica di fatture elettroniche (XML, P7M, PDF)</li>
        <li>Ricezione automatica fatture elettroniche dal Sistema di Interscambio (SDI) via Invoicetronic</li>
        <li>Classificazione dei prodotti tramite intelligenza artificiale</li>
        <li>Calcolo margini e analisi dei costi alimentari</li>
        <li>Gestione area Foodcost (ricette, ingredienti, diario)</li>
        <li>Controllo prezzi e confronto fornitori</li>
        <li>Worker automatico di elaborazione fatture con coda persistente</li>
      </ul>
      <LegalCallout>
        <strong>⚠️ Il Servizio NON sostituisce la consulenza fiscale, contabile o legale</strong> e
        NON costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014.
        L&apos;utente rimane responsabile delle proprie decisioni operative e fiscali.
      </LegalCallout>

      <h2>2. Registrazione e Account</h2>
      <ul>
        <li>L&apos;accesso al Servizio richiede la creazione di un account con email, P.IVA e dati del ristorante.</li>
        <li>Al primo accesso è richiesta l&apos;accettazione esplicita della Privacy Policy (consenso GDPR Art. 6.1.b).</li>
        <li>L&apos;account è <strong>personale e non cedibile</strong>. L&apos;utente è responsabile della custodia delle proprie credenziali.</li>
        <li>L&apos;utente garantisce la veridicità dei dati forniti in fase di registrazione.</li>
        <li>Il Titolare si riserva il diritto di sospendere account con dati manifestamente falsi.</li>
      </ul>

      <h2>3. Utilizzo Consentito</h2>
      <p>L&apos;utente si impegna a:</p>
      <ul>
        <li>Utilizzare il Servizio esclusivamente per finalità lecite e connesse alla propria attività</li>
        <li>Non tentare di accedere a dati di altri utenti</li>
        <li>Non sovraccaricare il sistema con upload massivi o automatizzati non previsti</li>
        <li>Non decompilare, disassemblare o effettuare reverse engineering del software</li>
        <li>Non riprodurre, distribuire o rivendere il Servizio o parte di esso</li>
        <li>Non utilizzare il Servizio per attività di scraping, data mining o raccolta sistematica di dati</li>
      </ul>

      <h2>4. Proprietà Intellettuale</h2>
      <p>
        Il software, i codici sorgente, il design, i marchi e tutti i contenuti del Servizio sono di{" "}
        <strong>proprietà esclusiva del Titolare</strong> e protetti dalle leggi italiane ed europee
        sul diritto d&apos;autore (L. 633/1941, Direttiva UE 2019/790).
      </p>
      <p>
        L&apos;utente ottiene una <strong>licenza d&apos;uso non esclusiva, non trasferibile e
        revocabile</strong> per la durata dell&apos;abbonamento.
      </p>
      <p>
        I dati caricati dall&apos;utente (fatture, ricette, note) restano di{" "}
        <strong>proprietà dell&apos;utente</strong>.
      </p>

      <h2>5. Classificazione AI e Limitazioni</h2>
      <ul>
        <li>La classificazione automatica dei prodotti è fornita tramite intelligenza artificiale e ha natura <strong>indicativa</strong>.</li>
        <li>Il Titolare <strong>non garantisce l&apos;accuratezza al 100%</strong> delle classificazioni AI.</li>
        <li>I contenuti delle fatture vengono trasmessi al provider AI <strong>esclusivamente on-the-fly</strong> per la categorizzazione, senza archivio permanente.</li>
        <li>L&apos;utente è tenuto a verificare e correggere le classificazioni quando necessario.</li>
        <li>Il Servizio fornisce strumenti di revisione e conferma manuale a tale scopo.</li>
      </ul>

      <h2>6. Sicurezza e Responsabilità dell&apos;Utente</h2>
      <p>
        Il Titolare adotta misure di sicurezza adeguate (Argon2id, TLS 1.3, rate limiting, RLS
        PostgreSQL). Tuttavia:
      </p>
      <ul>
        <li>L&apos;utente è responsabile della sicurezza delle proprie credenziali di accesso.</li>
        <li>In caso di sospetta compromissione dell&apos;account, l&apos;utente deve notificare immediatamente il Titolare.</li>
        <li>Il Titolare non può essere ritenuto responsabile per accessi non autorizzati causati da negligenza dell&apos;utente.</li>
      </ul>

      <h2>7. Disponibilità del Servizio</h2>
      <ul>
        <li>Il Titolare si impegna a garantire la disponibilità del Servizio (target SLA: 99,5% mensile).</li>
        <li>Sono previste interruzioni per manutenzione programmata, con preavviso quando possibile.</li>
        <li>Il Titolare non è responsabile per interruzioni causate da fornitori terzi (Supabase, OpenAI, Brevo, Invoicetronic, Vercel, Railway) o cause di forza maggiore.</li>
      </ul>

      <h2>8. Limitazione di Responsabilità</h2>
      <ul>
        <li>Il Servizio è fornito <strong>&quot;così com&apos;è&quot; (as is)</strong>.</li>
        <li>Il Titolare non è responsabile per danni diretti o indiretti derivanti dall&apos;uso del Servizio, inclusi ma non limitati a: perdita di dati, decisioni aziendali basate sulle analisi, interruzioni del servizio, classificazioni AI errate.</li>
        <li>La responsabilità massima del Titolare è in ogni caso limitata all&apos;importo pagato dall&apos;utente nei 12 mesi precedenti l&apos;evento dannoso.</li>
      </ul>

      <h2>9. Sospensione e Cessazione</h2>
      <p>Il Titolare si riserva il diritto di sospendere o cessare l&apos;account dell&apos;utente in caso di:</p>
      <ul>
        <li>Violazione dei presenti Termini</li>
        <li>Uso fraudolento o abusivo del Servizio</li>
        <li>Mancato pagamento (se applicabile)</li>
        <li>Richiesta dell&apos;autorità giudiziaria</li>
      </ul>
      <p>
        L&apos;utente può cancellare il proprio account in qualsiasi momento dalla sezione
        &quot;Impostazioni&quot;. Alla cancellazione, tutti i dati vengono eliminati in modo
        permanente e irreversibile.
      </p>

      <h2>10. Legge Applicabile e Foro Competente</h2>
      <p>
        I presenti Termini sono regolati dalla <strong>legge italiana</strong>. Per qualsiasi
        controversia è competente il <strong>Foro di Milano</strong>, salvo diversa disposizione
        inderogabile di legge a favore del consumatore.
      </p>

      <h2>11. Modifiche ai Termini</h2>
      <p>
        Il Titolare si riserva il diritto di modificare i presenti Termini. Le modifiche sostanziali
        saranno comunicate tramite notifica nell&apos;applicazione con almeno 15 giorni di preavviso.
        L&apos;uso continuato del Servizio dopo la comunicazione costituisce accettazione delle
        modifiche.
      </p>

      <h2>Contatti</h2>
      <p>
        <strong>Recoma System S.r.l.</strong>
        <br />
        Referente: Mattia D&apos;Avolio
        <br />
        Email: <a href="mailto:md@oneflux.it">md@oneflux.it</a>
        <br />
        P.IVA: IT09599210961
      </p>

      <p className="pt-4">
        Consulta anche la <Link href="/privacy">Privacy & Cookie Policy</Link>.
      </p>
    </LegalProse>
  );
}
