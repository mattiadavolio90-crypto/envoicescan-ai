// Raggruppamento dei segnali di catena. Vive fuori da `gruppo.ts` perche'
// quello importa `react` e `./worker`: sotto node non si carica, e la rete
// frontend (tests/test_*_frontend.py) non potrebbe eseguirlo. Qui la logica e'
// pura e si prova davvero — vedi tests/test_catena_segnali_raggruppati_frontend.py.
import type { Segnale } from "./gruppo";

export type SegnaleRaggruppato = {
  tipo: Segnale["tipo"];
  severity: Segnale["severity"];
  testo: string;
  pv: { ristorante_id: string; pv_nome: string; cta_page: string }[];
};

// Lo stesso avviso ripetuto una volta per punto vendita e' rumore, non
// informazione: il 21/09/2026 la card di un gruppo da 5 PV mostrava 13 righe di
// cui 5 con "Mancano le fatture costo e il costo del personale — vai a
// completare nel punto vendita", identiche parola per parola.
//
// Si raggruppa per (tipo, testo) tenendo TUTTI i PV: il bottone "Vedi PV" e' una
// destinazione, e cinque PV hanno cinque pagine diverse — comprimere a una riga
// sola con un solo id manderebbe l'utente su un PV arbitrario. L'ordine di
// arrivo e' quello deciso dal backend (per severita' e tipo) e non si tocca: il
// gruppo prende il posto della sua PRIMA occorrenza.
//
// I segnali senza ristorante_id (l'avviso "non e' stato possibile controllare")
// restano righe a se': non sono destinazioni e non si sommano a niente.
export function raggruppaSegnali(segnali: Segnale[]): SegnaleRaggruppato[] {
  const out: SegnaleRaggruppato[] = [];
  const indice = new Map<string, number>();
  for (const s of segnali) {
    const pv = { ristorante_id: s.ristorante_id, pv_nome: s.pv_nome, cta_page: s.cta_page };
    const chiave = s.ristorante_id ? `${s.tipo}\u0000${s.testo}` : null;
    const gia = chiave === null ? undefined : indice.get(chiave);
    if (gia === undefined) {
      if (chiave !== null) indice.set(chiave, out.length);
      out.push({ tipo: s.tipo, severity: s.severity, testo: s.testo, pv: [pv] });
    } else {
      out[gia].pv.push(pv);
      // Un gruppo vale per la sua severita' piu' alta: se un solo PV e' in
      // errore, la riga non puo' restare un warning.
      if (s.severity === "error") out[gia].severity = "error";
    }
  }
  return out;
}

