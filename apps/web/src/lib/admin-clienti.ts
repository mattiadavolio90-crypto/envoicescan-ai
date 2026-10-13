// Menu, lista clienti e scheda cliente dell'admin (riordino del 13/10/2026).
// Logica pura qui, perche' l'unica rete sul frontend esegue lib/ e non i .tsx.

// ─── Menu ────────────────────────────────────────────────────────────────────

export const MENU_ADMIN: { href: string; label: string }[] = [
  { href: "/admin", label: "Oggi" },
  { href: "/admin/clienti", label: "Clienti" },
  { href: "/admin/categorie", label: "Categorie" },
];

/** «Oggi» e' attiva solo su /admin esatto, le altre anche sulle sottopagine
 *  (la scheda di un cliente accende «Clienti»). Il confronto e' per segmento:
 *  un prefisso nudo accenderebbe /admin/clienti anche su /admin/clientiXYZ. */
export function voceAttiva(pathname: string, href: string): boolean {
  const p = pathname.replace(/\/+$/, "") || "/";
  if (href === "/admin") return p === "/admin";
  return p === href || p.startsWith(href + "/");
}

export type Filtro = "tutti" | "fermi" | "trial" | "disattivi";

export const FILTRI: { key: Filtro; label: string }[] = [
  { key: "tutti", label: "Tutti" },
  { key: "fermi", label: "Fermi da 7 giorni" },
  { key: "trial", label: "In prova" },
  { key: "disattivi", label: "Disattivi" },
];

/** Oltre questa soglia un cliente attivo che non carica e' «fermo». */
export const GIORNI_FERMO = 7;

const GIORNO_MS = 86_400_000;

export type ClienteLista = {
  email: string;
  nome_ristorante: string;
  nome_gruppo: string | null;
  partita_iva: string | null;
  attivo: boolean;
  trial: { active?: boolean } | null;
  ultimo_caricamento_at?: string | null;
  sedi: { partita_iva: string | null }[];
};

/** Giorni interi trascorsi; null se la data manca o non si legge. */
export function giorniDa(iso: string | null | undefined, adesso: number): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((adesso - t) / GIORNO_MS));
}

/** «Oggi», «Ieri», «5 giorni fa», «Mai». */
export function testoGiorni(iso: string | null | undefined, adesso: number): string {
  const g = giorniDa(iso, adesso);
  if (g === null) return "Mai";
  if (g === 0) return "Oggi";
  if (g === 1) return "Ieri";
  return `${g} giorni fa`;
}

/** Un cliente attivo e' fermo se non carica da GIORNI_FERMO giorni o non ha
 *  mai caricato. Un account disattivo non e' «fermo»: e' spento. */
export function eFermo(c: ClienteLista, adesso: number): boolean {
  if (!c.attivo) return false;
  const g = giorniDa(c.ultimo_caricamento_at, adesso);
  return g === null || g >= GIORNI_FERMO;
}

function corrisponde(c: ClienteLista, cerca: string): boolean {
  const q = cerca.trim().toLowerCase();
  if (!q) return true;
  return (
    c.email.toLowerCase().includes(q) ||
    (c.nome_ristorante || "").toLowerCase().includes(q) ||
    (c.nome_gruppo || "").toLowerCase().includes(q) ||
    (c.partita_iva || "").includes(q) ||
    c.sedi.some((s) => (s.partita_iva || "").includes(q))
  );
}

function nelFiltro(c: ClienteLista, filtro: Filtro, adesso: number): boolean {
  if (filtro === "fermi") return eFermo(c, adesso);
  if (filtro === "trial") return c.trial?.active === true;
  if (filtro === "disattivi") return !c.attivo;
  return true;
}

/** Quanti clienti per ogni filtro, per i numeri accanto alle etichette. */
export function contaFiltri(clienti: ClienteLista[], adesso: number): Record<Filtro, number> {
  const conta = { tutti: 0, fermi: 0, trial: 0, disattivi: 0 };
  for (const c of clienti) {
    for (const f of FILTRI) if (nelFiltro(c, f.key, adesso)) conta[f.key] += 1;
  }
  return conta;
}

/** Filtra e ordina: prima i fermi (da piu' tempo in cima), poi gli attivi per
 *  nome, in fondo i disattivi. Chi deve fare qualcosa lo trova in alto. */
export function clientiVisibili<T extends ClienteLista>(
  clienti: T[],
  cerca: string,
  filtro: Filtro,
  adesso: number,
): T[] {
  const nome = (c: ClienteLista) => (c.nome_gruppo || c.nome_ristorante || c.email).toLowerCase();
  const gruppo = (c: ClienteLista) => (!c.attivo ? 2 : eFermo(c, adesso) ? 0 : 1);
  const giorni = (c: ClienteLista) => giorniDa(c.ultimo_caricamento_at, adesso) ?? Number.MAX_SAFE_INTEGER;
  return clienti
    .filter((c) => corrisponde(c, cerca) && nelFiltro(c, filtro, adesso))
    .sort((a, b) =>
      gruppo(a) - gruppo(b) ||
      (gruppo(a) === 0 ? giorni(b) - giorni(a) : 0) ||
      nome(a).localeCompare(nome(b), "it"),
    );
}

// ─── Scheda cliente ──────────────────────────────────────────────────────────

export type TabCliente = "panoramica" | "sedi" | "funzioni" | "invii" | "account";

export const TAB_CLIENTE: { key: TabCliente; label: string }[] = [
  { key: "panoramica", label: "Panoramica" },
  { key: "sedi", label: "Sedi" },
  { key: "funzioni", label: "Funzioni" },
  { key: "invii", label: "Invii automatici" },
  { key: "account", label: "Account" },
];

/** La tab arriva dall'URL (?tab=): un valore sconosciuto apre la Panoramica. */
export function tabDaUrl(valore: string | null | undefined): TabCliente {
  return TAB_CLIENTE.some((t) => t.key === valore) ? (valore as TabCliente) : "panoramica";
}

/** L'eliminazione di un account si sblocca solo riscrivendo la sua email:
 *  un clic distratto non basta a cancellare tutti i dati di un cliente. */
export function eliminazioneConfermata(scritta: string, email: string): boolean {
  const s = scritta.trim().toLowerCase();
  return s.length > 0 && s === email.trim().toLowerCase();
}
