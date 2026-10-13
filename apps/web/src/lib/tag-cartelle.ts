// Cartelle e preferiti della barra dei tag in «Analisi e Tag». Servono solo a
// organizzare la vista: non entrano in nessuna analisi. Logica estratta qui
// perche' un .tsx non e' raggiungibile dai test (tests/test_tag_cartelle_frontend.py).

import type { CartellaTag, CustomTag } from "./tag";

export type VistaTag = "preferiti" | "tutte";

export type RigaCartella = {
  /** null = «Senza cartella». */
  cartella: CartellaTag | null;
  tags: CustomTag[];
};

export type StatoComodo = {
  vista: VistaTag;
  /** Id delle cartelle chiuse (▸). */
  chiuse: number[];
};

export const STATO_COMODO_PREDEFINITO: StatoComodo = { vista: "tutte", chiuse: [] };

// Oltre questo numero gli id chiusi sono quasi certamente cartelle eliminate
// da tempo: non vale la pena portarseli dietro in localStorage.
const MAX_CHIUSE = 200;

function perNome(a: CustomTag, b: CustomTag): number {
  return a.nome.localeCompare(b.nome, "it", { sensitivity: "base" }) || a.id - b.id;
}

export function ordinaCartelle(cartelle: CartellaTag[]): CartellaTag[] {
  return [...cartelle].sort((a, b) => a.ordine - b.ordine || a.id - b.id);
}

/**
 * Le righe della barra: prima le cartelle per (ordine, id), anche vuote perche'
 * ci si possa trascinare dentro un tag, poi «Senza cartella» solo se non e'
 * vuota o se `mostraSenzaCartella` (durante il trascinamento di un tag).
 * Un tag che punta a una cartella sconosciuta finisce in «Senza cartella»:
 * nascosto non si potrebbe piu' ne' vedere ne' spostare.
 */
export function raggruppa(
  tags: CustomTag[],
  cartelle: CartellaTag[],
  opzioni: { mostraSenzaCartella?: boolean } = {},
): RigaCartella[] {
  const ordinate = ordinaCartelle(cartelle);
  const perCartella = new Map<number, CustomTag[]>(ordinate.map(c => [c.id, []]));
  const senza: CustomTag[] = [];
  for (const t of tags) {
    const lista = t.cartella_id != null ? perCartella.get(t.cartella_id) : undefined;
    (lista ?? senza).push(t);
  }
  const righe: RigaCartella[] = ordinate.map(c => ({
    cartella: c,
    tags: (perCartella.get(c.id) ?? []).sort(perNome),
  }));
  if (senza.length > 0 || opzioni.mostraSenzaCartella) {
    righe.push({ cartella: null, tags: senza.sort(perNome) });
  }
  return righe;
}

export function soloPreferiti(tags: CustomTag[]): CustomTag[] {
  return tags.filter(t => t.preferito === true).sort(perNome);
}

/** Sposta `daId` al posto di `aId` (come arrayMove). Id assenti: copia invariata. */
export function riordina<T>(ids: T[], daId: T, aId: T): T[] {
  const copia = [...ids];
  const da = copia.indexOf(daId);
  const a = copia.indexOf(aId);
  if (da < 0 || a < 0 || da === a) return copia;
  const [mosso] = copia.splice(da, 1);
  copia.splice(a, 0, mosso);
  return copia;
}

/** Le cartelle con `ordine` = posizione nell'elenco `ids`; quelle fuori elenco in coda. */
export function applicaOrdine(cartelle: CartellaTag[], ids: number[]): CartellaTag[] {
  const posizione = new Map(ids.map((id, i) => [id, i]));
  return cartelle.map(c => ({ ...c, ordine: posizione.get(c.id) ?? ids.length + c.ordine }));
}

/** Vero se le cartelle, nell'ordine mostrato, sono esattamente `ids`. */
export function stessoOrdine(cartelle: CartellaTag[], ids: number[]): boolean {
  const correnti = ordinaCartelle(cartelle).map(c => c.id);
  return correnti.length === ids.length && correnti.every((id, i) => id === ids[i]);
}

/** Il tag con `cartella_id` cambiato, gli altri intatti. */
export function spostaTag(tags: CustomTag[], tagId: number, cartellaId: number | null): CustomTag[] {
  return tags.map(t => (t.id === tagId ? { ...t, cartella_id: cartellaId } : t));
}

/**
 * Il primo tag nell'ordine mostrato, per la selezione all'apertura. Nella vista
 * «Preferiti» e' il primo preferito; se non ce ne sono si ripiega sull'ordine
 * delle cartelle, cosi' sotto la barra c'e' comunque un tag da analizzare.
 * Le cartelle chiuse si saltano finche' ce n'e' una aperta con dei tag.
 */
export function primoTagMostrato(
  vista: VistaTag,
  righe: RigaCartella[],
  preferiti: CustomTag[],
  chiuse: number[] = [],
): number | null {
  if (vista === "preferiti" && preferiti.length > 0) return preferiti[0].id;
  const chiuseSet = new Set(chiuse);
  const aperta = righe.find(r => r.tags.length > 0 && !(r.cartella && chiuseSet.has(r.cartella.id)));
  const qualsiasi = aperta ?? righe.find(r => r.tags.length > 0);
  return qualsiasi ? qualsiasi.tags[0].id : null;
}

/** Stato di comodo da localStorage: qualunque input malformato da' il predefinito, mai un'eccezione. */
export function leggiStatoComodo(grezzo: string | null | undefined): StatoComodo {
  if (typeof grezzo !== "string" || !grezzo) return { ...STATO_COMODO_PREDEFINITO, chiuse: [] };
  let dato: unknown;
  try {
    dato = JSON.parse(grezzo);
  } catch {
    return { ...STATO_COMODO_PREDEFINITO, chiuse: [] };
  }
  if (!dato || typeof dato !== "object" || Array.isArray(dato)) {
    return { ...STATO_COMODO_PREDEFINITO, chiuse: [] };
  }
  const { vista, chiuse } = dato as { vista?: unknown; chiuse?: unknown };
  const vistaValida: VistaTag = vista === "preferiti" || vista === "tutte" ? vista : STATO_COMODO_PREDEFINITO.vista;
  const idValidi = Array.isArray(chiuse)
    ? chiuse.filter((x): x is number => typeof x === "number" && Number.isSafeInteger(x) && x > 0)
    : [];
  return { vista: vistaValida, chiuse: [...new Set(idValidi)].slice(0, MAX_CHIUSE) };
}

export function scriviStatoComodo(stato: StatoComodo): string {
  return JSON.stringify({ vista: stato.vista, chiuse: [...new Set(stato.chiuse)].slice(0, MAX_CHIUSE) });
}

export function alternaChiusa(chiuse: number[], id: number): number[] {
  return chiuse.includes(id) ? chiuse.filter(x => x !== id) : [...chiuse, id];
}

function chiaveNome(nome: string): string {
  return nome.trim().toLocaleLowerCase("it");
}

/** Stesso criterio dell'indice unico del DB: lower(btrim(nome)) nella sede. */
export function nomeCartellaGiaUsato(cartelle: CartellaTag[], nome: string, escludiId?: number): boolean {
  const chiave = chiaveNome(nome);
  return cartelle.some(c => c.id !== escludiId && chiaveNome(c.nome) === chiave);
}

/** Il messaggio per una risposta non riuscita delle rotte delle cartelle. */
export function messaggioErroreCartella(status: number, dettaglio: string): string {
  if (status === 409) return "Esiste già una cartella con questo nome";
  if (status === 401) return "Sessione scaduta, ricarica la pagina";
  if (status === 404) return "La cartella non esiste più: ricarica la pagina";
  if (status === 400) return dettaglio || "Il nome della cartella non può essere vuoto";
  if (status === 502 && !dettaglio) return "Il servizio non risponde, riprova fra poco";
  return dettaglio || "Operazione non riuscita, riprova";
}

export type CampiTag = {
  nome?: string;
  emoji?: string | null;
  cartella_id?: number | null;
};

/**
 * I soli campi cambiati rispetto al tag salvato, per la PATCH del riquadro.
 * Una cartella che non esiste piu' vale «Senza cartella», com'e' mostrata nella
 * barra: lasciarla com'e' non deve diventare una modifica.
 */
export function campiCambiati(
  base: CustomTag,
  scelti: { nome: string; emoji: string | null; cartella_id: number | null },
  cartelle: CartellaTag[],
): CampiTag {
  const note = new Set(cartelle.map(c => c.id));
  const cartellaIniziale = base.cartella_id != null && note.has(base.cartella_id) ? base.cartella_id : null;
  const campi: CampiTag = {};
  if (scelti.nome !== base.nome) campi.nome = scelti.nome;
  if (scelti.emoji !== (base.emoji ?? null)) campi.emoji = scelti.emoji;
  if (scelti.cartella_id !== cartellaIniziale) campi.cartella_id = scelti.cartella_id;
  return campi;
}

// Identificativi dnd-kit: le righe (cartelle e «Senza cartella») sono bersagli,
// i tag sono trascinabili. Un prefisso per tipo, cosi' un id di cartella non si
// confonde con quello di un tag.
export const ID_SENZA_CARTELLA = "cartella:senza";

export function idRiga(cartellaId: number | null): string {
  return cartellaId == null ? ID_SENZA_CARTELLA : `cartella:${cartellaId}`;
}

export function idTagTrascinabile(tagId: number): string {
  return `tag:${tagId}`;
}

/** null = «Senza cartella»; undefined = l'id non e' una riga. */
export function cartellaDaIdRiga(id: string | number | null | undefined): number | null | undefined {
  if (id === ID_SENZA_CARTELLA) return null;
  if (typeof id !== "string" || !id.startsWith("cartella:")) return undefined;
  const n = Number(id.slice("cartella:".length));
  return Number.isSafeInteger(n) && n > 0 ? n : undefined;
}

export function tagDaIdTrascinabile(id: string | number | null | undefined): number | undefined {
  if (typeof id !== "string" || !id.startsWith("tag:")) return undefined;
  const n = Number(id.slice("tag:".length));
  return Number.isSafeInteger(n) && n > 0 ? n : undefined;
}
