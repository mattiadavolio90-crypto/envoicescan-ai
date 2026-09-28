// «Da fare oggi» — una forma sola per le due Home (Mattia, 28/9: «una Home
// sola, uguale per il punto vendita e per la catena, cambiano solo i dati»).
//
// Il punto vendita riceve le azioni gia' decise dal briefing (backend, con cache
// giornaliera). La catena le compone qui dai segnali di gruppo, dalle
// osservazioni e dalle fatture da collocare: i segnali escono dal render
// bloccante di proposito (il primo calcolo del giorno costa), quindi non
// possono entrare nel briefing di gruppo che la Home aspetta.
//
// Logica pura, fuori dai .tsx: sotto node si esegue davvero
// (tests/test_home_da_fare_frontend.py).
import type { Osservazione, Segnale } from "./gruppo";
import { raggruppaSegnali } from "@/lib/catena-segnali";
import { haDestinazione, osservazioniDaMostrare } from "@/lib/catena-osservazioni";
import { LINK_CODA_GRUPPO } from "@/lib/catena-schede";

export type SeveritaVoce = "error" | "warning" | "info" | "success";

export type AzioneVoce =
  | { tipo: "pagina"; href: string; etichetta: string }
  // Una sede diversa da quella aperta: prima si cambia sede, poi si naviga.
  | { tipo: "sede"; ristoranteId: string; pagina: string; etichetta: string };

export type VoceDaFare = {
  id: string;
  severity: SeveritaVoce;
  testo: string;
  dettaglio?: string | null;
  // Solo in catena: di quale punto vendita parla. `sedeCompleta` va nel title
  // quando la riga raggruppa piu' sedi e il nome visibile si tronca.
  sede?: string | null;
  sedeCompleta?: string | null;
  azione: AzioneVoce | null;
  ignorabile: boolean;
};

type AzionePV = {
  id: string;
  severity: SeveritaVoce;
  testo: string;
  dettaglio?: string | null;
  cta_label: string;
  cta_page: string;
  dismissible?: boolean;
};

/** Le azioni del briefing del punto vendita nella forma comune. `ignorabile`
 * lo decide chi rende (puoIgnorare in briefing-shared), come oggi. */
export function vociDaAzioniPV<A extends AzionePV>(azioni: A[], ignorabile: (a: A) => boolean): VoceDaFare[] {
  return azioni.map((a) => ({
    id: a.id,
    severity: a.severity,
    testo: a.testo,
    dettaglio: a.dettaglio ?? null,
    sede: null,
    azione: { tipo: "pagina", href: a.cta_page, etichetta: a.cta_label },
    ignorabile: ignorabile(a),
  }));
}

const RANGO: Record<SeveritaVoce, number> = { error: 0, warning: 1, info: 2, success: 3 };

export type DaFareCatena = {
  voci: VoceDaFare[];
  // Cosa dire oltre alle voci: i segnali non sono ancora arrivati, o non sono
  // arrivati affatto. In entrambi i casi mai il verde.
  avviso: "caricamento" | "errore" | null;
  verde: boolean;
};

/**
 * Il «Da fare» della catena.
 *
 * - `segnali` null = non ancora letti o non letti per errore (`errore` dice
 *   quale): il verde resta spento, perche' non sappiamo se c'e' qualcosa.
 * - Le fatture da collocare si contano dal briefing di gruppo, che la Home ha
 *   gia': compaiono anche mentre i segnali caricano o se falliscono.
 * - Le osservazioni sono fatti sull'andamento, non compiti, ma stanno qui come
 *   nella Home del punto vendita (fase 4): una positiva e' una voce, e basta la
 *   sua presenza a non dichiarare «tutto in ordine» sopra un fatto che il
 *   cliente deve leggere.
 */
export function daFareCatena(input: {
  segnali: { segnali?: Segnale[]; osservazioni?: Osservazione[] } | null;
  errore: boolean;
  nDaCollocare: number | null | undefined;
}): DaFareCatena {
  const voci: VoceDaFare[] = [];
  const n = input.nDaCollocare ?? 0;
  if (n > 0) {
    voci.push({
      id: "coda-gruppo",
      severity: "warning",
      testo: n === 1 ? "1 fattura di gruppo da collocare" : `${n} fatture di gruppo da collocare`,
      dettaglio:
        n === 1
          ? "Assegnala a una sede o dividila fra i locali."
          : "Assegnale a una sede o dividile fra i locali.",
      sede: null,
      azione: { tipo: "pagina", href: LINK_CODA_GRUPPO, etichetta: "Colloca" },
      ignorabile: false,
    });
  }

  if (input.segnali) {
    raggruppaSegnali(input.segnali.segnali ?? []).forEach((s, i) => {
      const nomi = s.pv.map((p) => p.pv_nome).join(" · ");
      const unica = s.pv.length === 1 && s.pv[0].ristorante_id ? s.pv[0] : null;
      voci.push({
        id: `segnale-${s.tipo}-${i}`,
        severity: s.severity,
        testo: s.testo,
        sede: s.pv.length > 1 ? `${s.pv.length} punti vendita · ${nomi}` : nomi || null,
        sedeCompleta: nomi || null,
        // Una destinazione sola: con piu' sedi raggruppate il bottone
        // manderebbe su una sede arbitraria (stessa regola della card di prima).
        azione: unica
          ? { tipo: "sede", ristoranteId: unica.ristorante_id, pagina: unica.cta_page, etichetta: "Vedi PV" }
          : null,
        ignorabile: false,
      });
    });
    osservazioniDaMostrare(input.segnali).forEach((o, i) => {
      voci.push({
        id: `osservazione-${o.tipo}-${o.ristorante_id}-${i}`,
        severity: o.severity,
        testo: o.testo,
        sede: o.pv_nome,
        sedeCompleta: o.pv_nome,
        azione: haDestinazione(o)
          ? { tipo: "sede", ristoranteId: o.ristorante_id, pagina: o.cta_page, etichetta: "Vedi PV" }
          : null,
        ignorabile: false,
      });
    });
  }

  // `sort` e' stabile: a parita' di gravita' resta l'ordine di arrivo (coda,
  // segnali nell'ordine del backend, osservazioni).
  voci.sort((a, b) => RANGO[a.severity] - RANGO[b.severity]);

  const avviso = input.segnali ? null : input.errore ? "errore" : "caricamento";
  return { voci, avviso, verde: avviso === null && voci.length === 0 };
}
