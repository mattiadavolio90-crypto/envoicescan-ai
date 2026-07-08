// Sequenza del Demo Tour: 6 step di contenuto + 1 schermata di conversione.
//
// Il tour è LINEARE e CHIUSO: si va avanti/indietro tra step fissi, si finisce
// sempre sulla schermata WhatsApp. Ogni step dice:
//   - quale "schermata" dell'app mostrare (screen)
//   - quale elemento cerchiare col faretto (anchorId → data-demo-anchor)
//   - titolo + testo, mostrati nel banner-guida in alto (DemoTopBar)
//
// Gli id delle ancore sono gli stessi valori messi in `data-demo-anchor="…"`
// nelle schermate demo. Tenerli qui, in un posto solo, evita ancore orfane.

export type DemoScreen = "home" | "analisi" | "prezzi" | "margini";

export type DemoStep = {
  id: string;
  // Schermata dell'app mostrata nel passo.
  screen: DemoScreen;
  // Elemento da cerchiare col faretto. null = nessun faretto (schermata intera).
  anchorId: string | null;
  // Se true, apre il pannello Chat AI sopra la Home (step dedicato).
  openChat?: boolean;
  title: string;
  body: string;
};

// Passo di CHIUSURA a parte: non ha spotlight né schermata dell'app dietro,
// è una schermata piena a sé (conversione). Lo shell lo tratta separatamente.
//
// VOCE NARRANTE = L'ASSISTENTE, in prima persona. Non è un narratore di
// marketing che descrive il prodotto: è il prodotto che si presenta. Coerente
// col posizionamento della landing ("si adatta a te, non il contrario") e col
// doppio cuore lui-ti-parla / tu-gli-parli.
//
// ORDINE = DRAMMATURGIA, non mappa dell'app: wow subito (chat con messaggio di
// trattativa), poi i soldi (rincari in euro), poi dove finiscono (MOL), poi
// l'ammazza-obiezione fatica ("non hai scritto un numero") un passo prima
// della CTA, e il configuratore per ultimo come chiudi-fiducia ("comandi tu").
// Il salmone +16% è il filo: briefing → chat → prezzi → margini, DICHIARATO
// nei testi ("ci torniamo", "eccolo", "dove sono finiti").
export const DEMO_STEPS: DemoStep[] = [
  {
    id: "home-briefing",
    screen: "home",
    anchorId: "briefing",
    title: "Ciao, sono l'assistente di ONEFLUX",
    body:
      "Questo è il briefing che ti preparo ogni mattina: com'è andata e cosa guardare. Oggi ho notato un rincaro sul salmone — tienilo a mente, ci torniamo.",
  },
  {
    id: "home-chat",
    screen: "home",
    anchorId: "chat",
    openChat: true,
    title: "Chiedimi quello che vuoi",
    body:
      "«Conviene cambiare fornitore per il salmone?» Confronto i fornitori sulle tue fatture, ti dico quanto pesi come cliente — e ti preparo il messaggio per trattare, pronto da incollare.",
  },
  {
    id: "prezzi-variazioni",
    screen: "prezzi",
    anchorId: "variazione-salmone",
    title: "Il salmone del briefing? Eccolo, in euro",
    body:
      "Ogni rincaro lo traduco in euro al mese: il salmone +16% vale +148 €, poi prosecco e vermentino — 220 € di rincari in tutto. In cima ciò che pesa di più, con storico e fattura di origine a un click.",
  },
  {
    id: "margini-mol",
    screen: "margini",
    anchorId: "mol",
    title: "E qui vedi dove sono finiti",
    body:
      "Fatturato meno costi, mese per mese: a maggio il MOL è al 21%, tre punti meno di aprile. Ti dico subito quale costo si è mangiato il margine.",
  },
  {
    id: "analisi-articoli",
    screen: "analisi",
    anchorId: "articoli",
    title: "Tutto questo, senza inserire niente",
    body:
      "Le fatture arrivano da sole: le leggo, le categorizzo e le tengo in ordine io. Quanto compri, da chi, a che prezzo — e tu non hai scritto un numero.",
  },
  {
    id: "home-config",
    screen: "home",
    anchorId: "config",
    title: "E comandi tu, non io",
    body:
      "Scegli il tuo nome, quali avvisi ricevere e da che soglia scattano. Mi adatto a come lavori tu — non il contrario.",
  },
];

// "Bottino" della demo: somma dei 3 rincari mostrati nell'Osservatorio
// (salmone 148 + prosecco 48 + vermentino 24). NON è l'impatto netto (+173 €,
// che include il ribasso ricciola −47): qui contiamo i rincari INTERCETTATI,
// il numero che il prospect può verificare sommando le card rosse.
export const DEMO_RINCARI_TROVATI = 220;

export const DEMO_LAST_INDEX = DEMO_STEPS.length; // indice della schermata di chiusura

// Numero WhatsApp per la CTA di conversione.
export const DEMO_WHATSAPP_NUMBER = "393488014534";
export const DEMO_WHATSAPP_MESSAGE =
  "Ciao! Ho visto la demo di ONEFLUX e vorrei attivare i 7 giorni gratis sul mio locale.";
