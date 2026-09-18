/**
 * Palette della Salute (indice 0-100 → colore), condivisa da Home PV e catena.
 *
 * Fino al 9/9/2026 viveva in due copie: `COLORI` in dashboard/salute-card.tsx e
 * `TINT` in catena/sintesi-catena.tsx, con una differenza reale: il PV non aveva
 * le varianti dark del testo (emerald-600 su fondo scuro), la catena si'. Una
 * copia della palette e' un tema che diverge in silenzio; qui ce n'e' una sola.
 *
 * `grigio` = "non lo so" (indice non determinabile, lettura fallita): lo usa la
 * catena; il PV oggi non lo emette ma la chiave e' qui perche' se un giorno lo
 * emettera' avra' gia' il suo colore, non un crash su una chiave assente.
 */
/**
 * La parola con cui il prodotto dice "i dati di questa sede non sono completi".
 *
 * Fonte unica, importata da chi la scrive a video E dall'export Excel. Nasce da
 * un difetto del 18/09/2026: la cella dell'export diceva "Incompleto" mentre la
 * stessa tabella a schermo diceva "incompleto" minuscolo, e il cliente
 * scaricava il file leggendo una parola diversa da quella vista. Un presidio a
 * regex ci vedeva solo le divergenze di GRAFIA di questa parola, non quelle
 * verso una parola diversa (che e' lo scenario di una rinomina). Con una
 * costante sola la coerenza la garantisce il compilatore, non un test.
 */
export const ETICHETTA_INCOMPLETO = "Incompleto";

export const SALUTE_TINT = {
  verde: {
    ring: "text-positivo",
    text: "text-positivo",
    badge: "bg-positivo/10 text-positivo",
    card: "bg-gradient-to-br from-positivo/10 via-positivo/[0.03] to-background",
    orb1: "bg-positivo/10",
    orb2: "bg-positivo/8",
    dot: "bg-positivo",
    label: "Completo",
  },
  giallo: {
    ring: "text-incerto",
    text: "text-incerto",
    badge: "bg-incerto/10 text-incerto",
    card: "bg-gradient-to-br from-incerto/10 via-incerto/[0.03] to-background",
    orb1: "bg-incerto/10",
    orb2: "bg-incerto/8",
    dot: "bg-incerto",
    label: "Quasi completo",
  },
  rosso: {
    ring: "text-negativo",
    text: "text-negativo",
    badge: "bg-negativo/10 text-negativo",
    card: "bg-gradient-to-br from-negativo/10 via-negativo/[0.03] to-background",
    orb1: "bg-negativo/10",
    orb2: "bg-negativo/8",
    dot: "bg-negativo",
    label: ETICHETTA_INCOMPLETO,
  },
  grigio: {
    ring: "text-muted-foreground/40",
    text: "text-muted-foreground",
    badge: "bg-muted text-muted-foreground",
    card: "bg-card",
    orb1: "bg-transparent",
    orb2: "bg-transparent",
    dot: "bg-muted-foreground/40",
    // "Non lo so", non "i dati mancano": il grigio copre anche il caso in cui
    // la lettura e' fallita, dove non sappiamo nemmeno se i dati ci siano.
    label: "Dato non disponibile",
  },
} as const;

export type ColoreSalute = keyof typeof SALUTE_TINT;

export type Tint = (typeof SALUTE_TINT)[ColoreSalute];

/** Le classi devono reggere in ENTRAMBI i temi (misura, non gusto). Fino al
 *  18/09/2026 lo garantiva una variante `dark:` per ogni colore pieno; ora lo
 *  garantisce il token (`positivo`, `incerto`, `negativo`), che porta i due
 *  valori. Il difetto da cercare e' quindi una classe di palette cruda
 *  (`emerald-600`, `sky-500`...), che ha un valore solo e non conosce il tema. */
export function tintUsaSoloToken(t: Pick<Tint, "ring" | "text" | "badge" | "card" | "orb1" | "orb2" | "dot">): boolean {
  const crudo = /\b(?:text|bg|from|via|to|border|ring)-(?:sky|blue|indigo|violet|purple|pink|emerald|green|teal|amber|yellow|orange|rose|red|slate|gray|zinc)-\d{2,3}\b/;
  return ![t.ring, t.text, t.badge, t.card, t.orb1, t.orb2, t.dot].some((cls) => crudo.test(cls));
}
