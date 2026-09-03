// Card grande "Righe da classificare" della Home (Fase 4bis, decisione Mattia
// 1/9): se dei costi restano fuori dai margini il cliente DEVE saperlo, sennò
// vede numeri calare senza spiegazione. Qui vive la sola logica di stato, pura,
// così l'harness node la esegue davvero (il rendering non è testabile).
//
// Regola ereditata da catena/card-segnali.tsx: un errore NON può diventare
// "tutto sotto controllo" — se il dato manca si mostra l'errore, mai il verde.
import { formatEuro } from "@/lib/format";
// `import type` (non `import { type ... }`): l'harness node esegue questo
// modulo davvero, e home.ts a runtime trascina worker.ts e react — un import
// solo-tipi viene eliso e il modulo resta eseguibile senza frontend.
import type { Salute, SaluteVoce } from "@/lib/home";

export const DA_CLASSIFICARE_HREF = "/analisi-fatture?tab=articoli&verifica=1";

export type CardDaClassificare =
  | { stato: "errore" }
  | { stato: "ok"; titolo: string }
  | { stato: "righe"; titolo: string; sottotitolo: string; href: string };

export function statoCardDaClassificare(
  salute: Pick<Salute, "da_classificare"> | null,
): CardDaClassificare {
  // salute assente = worker giù; da_classificare assente = query fallita lato
  // worker o backend vecchio. In tutti i casi: errore, mai il verde.
  const dati = salute?.da_classificare;
  if (!dati || dati.righe < 0) return { stato: "errore" };
  if (dati.righe === 0) {
    return { stato: "ok", titolo: "Tutte le righe sono classificate" };
  }
  const una = dati.righe === 1;
  return {
    stato: "righe",
    titolo: una
      ? "1 riga da classificare"
      : `${dati.righe.toLocaleString("it-IT")} righe da classificare`,
    sottotitolo: `${formatEuro(dati.importo)} esclusi da margini e food cost finché non ${una ? "la sistemi" : "le sistemi"}`,
    href: DA_CLASSIFICARE_HREF,
  };
}

// Promozione della voce (decisione Mattia 1/9): sulla Home desktop la voce
// "Righe classificate" esce dall'elenco puntato della card Salute e diventa la
// card grande — il dato si vede UNA volta, nel posto giusto. Solo presentazione:
// l'indice è calcolato dal backend e non si muove; il mobile (che la card grande
// non ce l'ha) continua a mostrare la voce nell'elenco.
export function vociSenzaClassificate(voci: SaluteVoce[]): SaluteVoce[] {
  return voci.filter((v) => v.key !== "classificate");
}
