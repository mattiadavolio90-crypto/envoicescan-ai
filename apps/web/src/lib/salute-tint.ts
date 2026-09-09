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
export const SALUTE_TINT = {
  verde: {
    ring: "text-emerald-500",
    text: "text-emerald-600 dark:text-emerald-500",
    badge: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
    card: "bg-gradient-to-br from-emerald-500/10 via-emerald-500/[0.03] to-background",
    orb1: "bg-emerald-400/15",
    orb2: "bg-emerald-400/8",
    dot: "bg-emerald-500",
    label: "In salute",
  },
  giallo: {
    ring: "text-amber-500",
    text: "text-amber-600 dark:text-amber-500",
    badge: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
    card: "bg-gradient-to-br from-amber-500/10 via-amber-500/[0.03] to-background",
    orb1: "bg-amber-400/15",
    orb2: "bg-amber-400/8",
    dot: "bg-amber-500",
    label: "Da completare",
  },
  rosso: {
    ring: "text-rose-500",
    text: "text-rose-600 dark:text-rose-500",
    badge: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400",
    card: "bg-gradient-to-br from-rose-500/10 via-rose-500/[0.03] to-background",
    orb1: "bg-rose-400/15",
    orb2: "bg-rose-400/8",
    dot: "bg-rose-500",
    label: "Dati incompleti",
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

/** Le classi devono reggere in ENTRAMBI i temi: un colore pieno senza variante
 *  dark e' il difetto che la copia del PV aveva (misura, non gusto). */
export function tintHaEntrambiITemi(colore: ColoreSalute): boolean {
  const t = SALUTE_TINT[colore];
  const pieno = /\b(?:text|bg)-(?:emerald|amber|rose)-\d{3}\b/;
  for (const cls of [t.text, t.badge]) {
    if (pieno.test(cls) && !cls.includes("dark:")) return false;
  }
  return true;
}
