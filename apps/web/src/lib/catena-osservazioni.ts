// Le osservazioni da consulente in catena (fase 6): i fatti sull'andamento di
// ogni punto vendita, calcolati dal backend con le stesse regole e le stesse
// frasi del PV. Non sono segnali: non sono compiti, e non spengono il "tutto
// sotto controllo" della card. Vive fuori da `gruppo.ts` per lo stesso motivo
// di `catena-segnali.ts`: sotto node si carica, e si prova davvero — vedi
// tests/test_catena_osservazioni_frontend.py.
import type { Osservazione } from "./gruppo";

// Il campo puo' mancare: durante un deploy il worker vecchio non lo manda, e
// uno snapshot scritto prima del deploy nemmeno. Assente = nessuna
// osservazione, mai un errore della card. Una riga senza testo non si mostra:
// sarebbe un nome di sede seguito dal nulla.
export function osservazioniDaMostrare(risposta: unknown): Osservazione[] {
  const lista = (risposta as { osservazioni?: unknown } | null | undefined)?.osservazioni;
  if (!Array.isArray(lista)) return [];
  return lista.filter((o): o is Osservazione => {
    if (!o || typeof o !== "object") return false;
    const testo = (o as { testo?: unknown }).testo;
    return typeof testo === "string" && testo.trim() !== "";
  });
}

// Il bottone "Vedi PV" e' una destinazione: senza id cambierebbe la sede
// attiva del cliente su un PV qualunque. Stessa regola dei segnali.
export function haDestinazione(o: Osservazione): boolean {
  return typeof o.ristorante_id === "string" && o.ristorante_id.trim() !== "";
}
