// Admin → Categorie, «Da sistemare» (14/10/2026): le righe su cui serve una
// decisione, un gruppo per descrizione, il piu' pesante in euro per primo. I
// gruppi li compone il worker (services/admin_categorie_service.py); qui solo
// cio' che serve alla pagina. Logica pura: l'unica rete sul frontend esegue lib/.

export const DA_CLASSIFICARE = "Da Classificare";

export type GruppoDaSistemare = {
  chiave: string;
  descrizione: string;
  ids: number[];
  righe: number;
  euro: number;
  categoria: string;
  categorie: string[];
  fornitore: string | null;
  cliente_ids: string[];
  cliente: string;
  suggerita: string | null;
  fonte: string | null;
};

export type ClienteCategorie = { id: string; nome: string };

export type DatiDaSistemare = { gruppi: GruppoDaSistemare[]; clienti: ClienteCategorie[] };

function eGruppo(g: unknown): g is GruppoDaSistemare {
  if (!g || typeof g !== "object") return false;
  const x = g as Record<string, unknown>;
  return typeof x.chiave === "string"
    && typeof x.descrizione === "string"
    && Array.isArray(x.ids) && x.ids.length > 0 && x.ids.every((i) => typeof i === "number")
    && typeof x.euro === "number"
    && typeof x.categoria === "string"
    && Array.isArray(x.categorie)
    && Array.isArray(x.cliente_ids);
}

/** La risposta del worker, o null se non ha la forma attesa: la pagina mostra
 *  «non riesco a leggere» invece di una lista vuota che direbbe «tutto a posto». */
export function leggiDaSistemare(json: unknown): DatiDaSistemare | null {
  if (!json || typeof json !== "object") return null;
  const d = json as Record<string, unknown>;
  if (!Array.isArray(d.gruppi) || !d.gruppi.every(eGruppo)) return null;
  const clienti = Array.isArray(d.clienti)
    ? d.clienti.filter((c): c is ClienteCategorie => !!c && typeof c.id === "string" && typeof c.nome === "string")
    : [];
  return { gruppi: d.gruppi, clienti };
}

/** Il filtro per cliente e la ricerca stanno nel browser: la lista e' piccola. */
export function filtra(gruppi: GruppoDaSistemare[], clienteId: string, testo: string): GruppoDaSistemare[] {
  const cerca = testo.trim().toUpperCase();
  return gruppi.filter((g) =>
    (clienteId === "tutti" || g.cliente_ids.includes(clienteId))
    && (!cerca || g.descrizione.toUpperCase().includes(cerca) || (g.fornitore ?? "").toUpperCase().includes(cerca)));
}

/** «Giusta» conferma la categoria che c'e': non vale se non ce n'e' una
 *  (Da Classificare) o se il gruppo ne ha piu' d'una (quale delle due?). */
export function puoConfermare(g: GruppoDaSistemare): boolean {
  return g.categorie.length === 1 && g.categoria !== DA_CLASSIFICARE;
}

/** Sotto la descrizione: chi l'ha comprata e da chi. */
export function rigaSotto(g: GruppoDaSistemare): string {
  return [g.fornitore, g.cliente, g.righe === 1 ? "1 riga" : `${g.righe} righe`].filter(Boolean).join(" · ");
}

/** Il toast dopo un salvataggio: il backend scrive NOTE solo sulle righe a zero
 *  euro (regola di dominio #2) e lascia in coda i gate di settore. */
export function esitoClassifica(scritte: number, chieste: number): string {
  if (scritte >= chieste) return scritte === 1 ? "1 riga sistemata" : `${scritte} righe sistemate`;
  return `${scritte} di ${chieste} righe sistemate, le altre restano qui`;
}

/** Dopo un salvataggio il gruppo sparisce solo se tutte le sue righe sono state
 *  scritte; altrimenti si rilegge la lista. */
export function toglieGruppo(scritte: number, chieste: number): boolean {
  return scritte >= chieste;
}

export function riepilogo(gruppi: GruppoDaSistemare[]): { gruppi: number; righe: number; euro: number } {
  return {
    gruppi: gruppi.length,
    righe: gruppi.reduce((s, g) => s + g.righe, 0),
    euro: gruppi.reduce((s, g) => s + g.euro, 0),
  };
}
