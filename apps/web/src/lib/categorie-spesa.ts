import { CATEGORIE_TUTTE } from "@/lib/admin";

// Le 4 categorie NON Food & Beverage (config/constants.py CATEGORIE_SPESE_GENERALI).
// "MATERIALE DI CONSUMO" e' qui pur non essendo ovvio: dal punto di vista logico
// rientra nelle spese generali, anche se la stringa nel DB non cambia.
//
// FONTE UNICA lato frontend: articoli-tab, pivot-tab e dropdown-categoria ne
// tenevano una copia letterale a testa. Quattro liste che dovevano restare
// identiche per sempre significa che prima o poi divergono, e una categoria
// finita nel gruppo sbagliato sposta soldi tra i secchi del MOL senza dare
// errore. Chi serve queste 4 stringhe importa DA QUI.
export const SPESE_GENERALI_SET = new Set([
  "SERVIZI E CONSULENZE",
  "UTENZE E LOCALI",
  "MANUTENZIONE E ATTREZZATURE",
  "MATERIALE DI CONSUMO",
]);

// Lo stato esplicito di "l'AI non ha saputo classificarla" (config/constants.py
// CATEGORIA_NON_CLASSIFICATA). Stessa ragione di SPESE_GENERALI_SET: era ripetuta
// come literal in 4 file, e la variante errata "Da Clasificare" (una sola "s")
// non darebbe nessun errore — filtrerebbe semplicemente zero righe per sempre.
export const CATEGORIA_NON_CLASSIFICATA = "Da Classificare";

// Una riga è "da scegliere" se il backend la marca needs_review, o se la categoria
// manca del tutto, o se è lo stato esplicito. Le tre condizioni erano ricopiate a
// mano in analisi-fatture e in catena: qui restano una cosa sola.
export function daScegliereCategoria(
  needsReview: boolean | null | undefined,
  categoria: string | null | undefined,
): boolean {
  return Boolean(needsReview) || !categoria || categoria === CATEGORIA_NON_CLASSIFICATA;
}

export type TipoSpesa = "fb" | "generale";

// Le categorie selezionabili su una spesa extra: le 29 canoniche, senza
// "📝 NOTE E DICITURE" (riservata alle righe fattura a importo zero) e senza
// "Da Classificare" (qui e' l'utente stesso a scrivere la spesa: sa cos'e').
const SELEZIONABILI = CATEGORIE_TUTTE.filter(
  (c) => c !== "📝 NOTE E DICITURE" && c !== CATEGORIA_NON_CLASSIFICATA,
);

export const CATEGORIE_SPESA_FB = SELEZIONABILI.filter((c) => !SPESE_GENERALI_SET.has(c));
export const CATEGORIE_SPESA_GENERALI = SELEZIONABILI.filter((c) => SPESE_GENERALI_SET.has(c));

// Deve restare identica a _tipo_da_categoria() in services/routers/workspace.py:
// qui serve solo a mostrare in anticipo il binario, la verita' la scrive il backend.
export function tipoDaCategoria(categoria: string): TipoSpesa {
  return SPESE_GENERALI_SET.has(categoria) ? "generale" : "fb";
}

export const TIPO_SPESA_LABEL: Record<TipoSpesa, string> = {
  fb: "Costi F&B",
  generale: "Spese Generali",
};
