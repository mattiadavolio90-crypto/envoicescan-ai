// Nomi dei mesi in italiano — fonte unica. Prima erano ridefiniti in 8+ file
// (mobile/diario, workspace, scadenziario, prezzi, catena, margini...), con
// piccole divergenze (maiuscole, abbreviazioni). Centralizzati qui per coerenza.
//
// Indici 0-based (MESI_LUNGHI[0] = "Gennaio"). Per l'uso 1-based (mese 1-12)
// sottrai 1: MESI_LUNGHI[mese - 1].

export const MESI_LUNGHI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
] as const;

export const MESI_CORTI = [
  "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
  "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
] as const;

// Minuscoli abbreviati — usati nelle label compatte di catena/turni mobile.
export const MESI_ABBR = [
  "gen", "feb", "mar", "apr", "mag", "giu",
  "lug", "ago", "set", "ott", "nov", "dic",
] as const;
