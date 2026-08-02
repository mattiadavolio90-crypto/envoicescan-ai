// Topic "incombenza reale" calcolati live dal backend: la card sparisce da sola
// quando inserisci il dato, e si rigenera ogni giorno finche' manca. "Ignora"
// qui sarebbe ingannevole (ricomparirebbe al refresh): non lo mostriamo. Devono
// esserci TUTTI i topic live ricalcolati ad ogni briefing (non solo i dati
// mensili): anche fatture mancanti e righe da controllare tornano al refresh.
// Condivisa fra home-briefing.tsx (desktop) e mobile-briefing.tsx (/m): prima
// era duplicata carattere per carattere in entrambi i file.
export const NON_IGNORABILI = new Set<string>([
  "fatturato_mancante",
  "costo_personale_mancante",
  "incasso_mancante",
  "fatture_mancanti",
  "uncategorized_rows",
]);
