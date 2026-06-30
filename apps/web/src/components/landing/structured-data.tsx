// JSON-LD (Schema.org) per la landing. NON è visibile in pagina: è letto dai
// motori e abilita i rich snippet (prezzo, descrizione, FAQ) nei risultati Google.
// Dati 100% reali dal prodotto: prezzi 39/59/79 +IVA, trial 7 giorni, P.IVA Recoma.
// Server-rendered: lo <script> finisce nell'HTML iniziale, leggibile dai crawler.
//
// Tre entità:
//  - Organization: chi c'è dietro (Recoma System), per il Knowledge Graph.
//  - SoftwareApplication: il prodotto, con i 3 piani come Offer.
//  - FAQPage: domande che il ristoratore si fa prima di provare — buone per la
//    SEO e candidate a comparire come accordion nei risultati.

const PIANI = [
  { nome: "Base", prezzo: "39" },
  { nome: "Plus", prezzo: "59" },
  { nome: "Pro", prezzo: "79" },
] as const;

const FAQ = [
  {
    q: "Come arrivano le fatture su ONEFLUX?",
    a: "Le fatture elettroniche dei fornitori arrivano in automatico, direttamente dal Sistema di Interscambio dell'Agenzia delle Entrate. L'assistente le legge e le categorizza da solo: non devi caricare niente a mano.",
  },
  {
    q: "ONEFLUX calcola il food cost e la marginalità?",
    a: "Sì. ONEFLUX categorizza ogni voce delle fatture e ricostruisce costi, food cost e marginalità del locale, confrontandoli con il tuo andamento e avvisandoti quando un fornitore alza i prezzi.",
  },
  {
    q: "Quanto costa ONEFLUX?",
    a: "Tre piani: Base 39€, Plus 59€ e Pro 79€ al mese (IVA esclusa). Tutte le funzioni sono incluse in ogni piano: cambia solo il volume di fatture e di domande all'assistente. La prova è gratis per 7 giorni, senza carta.",
  },
  {
    q: "Ho più locali: ONEFLUX li gestisce insieme?",
    a: "Sì, con la modalità catena disponibile su ogni piano: vedi ogni locale singolarmente e il gruppo nel suo insieme.",
  },
  {
    q: "Serve un commercialista o competenze tecniche per usarlo?",
    a: "No. ONEFLUX è pensato per chi gestisce il locale, non per tecnici: gli scrivi come a una persona e ti risponde. Dall'altra parte c'è una persona vera che ti segue.",
  },
] as const;

export function StructuredData() {
  const data = [
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "ONEFLUX",
      legalName: "Recoma System S.r.l.",
      url: "https://www.oneflux.it",
      logo: "https://www.oneflux.it/icon.svg",
      vatID: "IT09599210961",
      email: "mattia.davolio@recomasystem.it",
      contactPoint: {
        "@type": "ContactPoint",
        contactType: "sales",
        telephone: "+393488014534",
        availableLanguage: "it",
      },
    },
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name: "ONEFLUX",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      url: "https://www.oneflux.it",
      description:
        "Software di controllo costi, food cost e marginalità per ristoranti. Le fatture elettroniche entrano in automatico, l'assistente le categorizza e ti dice ogni mattina come va il locale, con avvisi sui rincari dei fornitori.",
      inLanguage: "it",
      offers: {
        "@type": "AggregateOffer",
        priceCurrency: "EUR",
        lowPrice: "39",
        highPrice: "79",
        offerCount: PIANI.length,
        offers: PIANI.map((p) => ({
          "@type": "Offer",
          name: `Piano ${p.nome}`,
          price: p.prezzo,
          priceCurrency: "EUR",
          // billingIncrement mensile; il prezzo è IVA esclusa (B2B).
          category: "subscription",
        })),
      },
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: FAQ.map((f) => ({
        "@type": "Question",
        name: f.q,
        acceptedAnswer: { "@type": "Answer", text: f.a },
      })),
    },
  ];

  return (
    <script
      type="application/ld+json"
      // JSON-LD: serializzazione controllata, nessun input utente -> safe.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
