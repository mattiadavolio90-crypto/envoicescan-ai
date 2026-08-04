import { CATEGORIE_TUTTE } from "@/lib/admin";

// Le 4 categorie NON Food & Beverage (config/constants.py CATEGORIE_SPESE_GENERALI).
// "MATERIALE DI CONSUMO" e' qui pur non essendo ovvio: dal punto di vista logico
// rientra nelle spese generali, anche se la stringa nel DB non cambia.
export const SPESE_GENERALI_SET = new Set([
  "SERVIZI E CONSULENZE",
  "UTENZE E LOCALI",
  "MANUTENZIONE E ATTREZZATURE",
  "MATERIALE DI CONSUMO",
]);

export type TipoSpesa = "fb" | "generale";

// Le categorie selezionabili su una spesa extra: le 29 canoniche, senza
// "📝 NOTE E DICITURE" (riservata alle righe fattura a importo zero) e senza
// "Da Classificare" (qui e' l'utente stesso a scrivere la spesa: sa cos'e').
const SELEZIONABILI = CATEGORIE_TUTTE.filter(
  (c) => c !== "📝 NOTE E DICITURE" && c !== "Da Classificare",
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
