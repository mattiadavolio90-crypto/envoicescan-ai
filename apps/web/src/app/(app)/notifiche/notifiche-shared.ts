import { type Notifica } from "@/lib/notifiche";

// --- Priorita' visiva per severity -----------------------------------------
// Ordine: error (rosso) > warning (giallo) > info (blu) > success (verde).
// Usato sia per ordinare che per i colori del bordo/badge.
export const SEVERITY_RANK: Record<Notifica["severity"], number> = {
  error: 0,
  warning: 1,
  info: 2,
  success: 3,
};

// --- Raggruppamento per origine ---------------------------------------------
// source_type reali emessi dal backend (upload_handler, anomaly_radar,
// tag_suggestion, scadenziario): mappati a categorie leggibili. Sconosciuti -> "Altro".
type Gruppo = { key: string; label: string };

const SOURCE_GROUP: Record<string, Gruppo> = {
  upload: { key: "upload", label: "Fatture caricate" },
  radar: { key: "radar", label: "Anomalie e prezzi" },
  operativa: { key: "operativa", label: "Da sistemare" },
  scadenza: { key: "scadenza", label: "Scadenze" },
  scadenziario: { key: "scadenza", label: "Scadenze" },
};

const GRUPPO_ALTRO: Gruppo = { key: "altro", label: "Altro" };

// Ordine di visualizzazione dei gruppi.
const GRUPPO_ORDINE = ["scadenza", "upload", "radar", "operativa", "altro"];

export function gruppoDi(n: Notifica): Gruppo {
  const st = (n.source_type ?? "").toLowerCase();
  return SOURCE_GROUP[st] ?? GRUPPO_ALTRO;
}

export type GruppoNotifiche = {
  key: string;
  label: string;
  notifiche: Notifica[];
};

// Raggruppa per origine e ordina i gruppi (per GRUPPO_ORDINE) e le notifiche
// interne (per priorita' severity, poi data desc — le piu' recenti prima).
export function raggruppa(notifiche: Notifica[]): GruppoNotifiche[] {
  const byKey = new Map<string, GruppoNotifiche>();
  for (const n of notifiche) {
    const g = gruppoDi(n);
    const esistente = byKey.get(g.key);
    if (esistente) esistente.notifiche.push(n);
    else byKey.set(g.key, { key: g.key, label: g.label, notifiche: [n] });
  }
  for (const g of byKey.values()) {
    g.notifiche.sort((a, b) => {
      const r = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
      if (r !== 0) return r;
      return (b.created_at ?? "").localeCompare(a.created_at ?? "");
    });
  }
  return [...byKey.values()].sort(
    (a, b) => GRUPPO_ORDINE.indexOf(a.key) - GRUPPO_ORDINE.indexOf(b.key),
  );
}

// --- CTA inline: action_page -> rotta Next ----------------------------------
// Molte action_page nel DB sono ancora path Streamlit legacy
// ("pages/3_controllo_prezzi.py"). Le traduciamo in rotte Next; quelle non
// mappabili NON producono un bottone (niente link rotti). Stessa logica del
// briefing lato worker (daily_briefing_service).
const LEGACY_TO_NEXT: Record<string, string> = {
  "pages/3_controllo_prezzi.py": "/prezzi",
  "pages/1_calcolo_margine.py": "/margini",
  "pages/5_notifiche_e_gestione.py": "/analisi-e-tag",
  "pages/2_analisi_fatture.py": "/analisi-fatture",
  dashboard: "/dashboard",
};

export function ctaDi(n: Notifica): { href: string; label: string } | null {
  const raw = (n.action_page ?? "").trim();
  if (!raw) return null;
  // Gia' rotta Next.
  if (raw.startsWith("/")) return { href: raw, label: "Vai" };
  const mapped = LEGACY_TO_NEXT[raw] ?? LEGACY_TO_NEXT[raw.toLowerCase()];
  return mapped ? { href: mapped, label: "Vai" } : null;
}

// --- Pulizia testo (markdown grezzo -> testo semplice) ----------------------
export function pulisci(testo: string): string {
  return testo
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`/g, "")
    .trim();
}
