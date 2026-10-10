// «Da fare oggi» — una forma sola per le due Home (Mattia, 28/9: «una Home
// sola, uguale per il punto vendita e per la catena, cambiano solo i dati»).
//
// Il punto vendita riceve le azioni gia' decise dal briefing (backend, con cache
// giornaliera). La catena le compone qui dai segnali di gruppo, dalle
// osservazioni, dagli avvisi delle sedi e dalle fatture da collocare, una riga
// per punto vendita (fase G, 9/10/2026): i segnali escono dal render
// bloccante di proposito (il primo calcolo del giorno costa), quindi non
// possono entrare nel briefing di gruppo che la Home aspetta.
//
// Logica pura, fuori dai .tsx: sotto node si esegue davvero
// (tests/test_home_da_fare_frontend.py).
import type { Osservazione, Segnale } from "./gruppo";
import { chiaveAvviso, destinazioneAvviso, pulisci, type Notifica } from "@/lib/notifiche-shared";
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
  // Solo per gli avvisi di catena: l'id della notifica da archiviare.
  rif?: string | null;
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

// Quanti punti vendita si vedono prima di «Altri N punti vendita»: lo stesso
// tetto delle card del briefing del punto vendita (`_MAX_CARD` in
// daily_briefing_service).
export const MAX_SEDI_VISIBILI = 4;

export type SedeDaFare = {
  ristoranteId: string;
  nome: string;
  // La piu' grave fra le sue voci: e' l'icona della riga chiusa.
  severity: SeveritaVoce;
  voci: VoceDaFare[];
  // «1 avviso», «3 avvisi»: la riga chiusa dice quanti ne nasconde.
  conteggio: string;
};

export type DaFareCatena = {
  // Senza sede: le fatture di gruppo da collocare, «non e' stato possibile
  // controllare». Restano righe aperte sopra le sedi.
  generali: VoceDaFare[];
  // Una per punto vendita, le piu' gravi prima.
  sedi: SedeDaFare[];
  totale: number;
  // I segnali o gli avvisi non sono ancora arrivati, o i segnali non sono
  // arrivati affatto. In entrambi i casi mai il verde.
  avviso: "caricamento" | "errore" | null;
  // Gli avvisi delle sedi non letti, tutti o in parte: detto, mai taciuto.
  notaAvvisi: string | null;
  verde: boolean;
};

// Il segnale «Mancano le fatture costo» della catena parla del mese chiuso;
// l'avviso della sede «Mancano le fatture costo di settembre» dice lo stesso, e
// in piu' il mese: nell'elenco unico si tiene l'avviso. Ma lo stesso topic ha
// anche avvisi che dicono ALTRO: «Nessuna fattura caricata nell'ultima
// settimana» (fatture), «Costo del personale mancante in luglio e agosto» senza
// il mese chiuso (personale). Quelli non coprono il segnale (revisore, 9/10:
// tre sedi vere perdevano «Mancano le fatture costo» di settembre).
function voceDetta(voce: string, mese: number | null | undefined, avvisi: Notifica[]): boolean {
  return avvisi.some((a) => {
    const p = (a.payload ?? {}) as { tipo?: unknown; mesi?: unknown };
    if (voce === "fatturato") return a.topic_key === "fatturato_mancante";
    if (voce === "fatture") return a.topic_key === "fatture_mancanti" && p.tipo === "mese_senza_costi";
    if (voce === "personale") {
      // Senza `mese` (null) nessun elenco di mesi lo contiene: resta il segnale.
      return a.topic_key === "costo_personale_mancante" && Array.isArray(p.mesi) && p.mesi.includes(mese);
    }
    return false;
  });
}

// Solo se OGNI voce del segnale e' gia' detta: altrimenti si perderebbe un
// dato. Senza `manca` (snapshot vecchio) il segnale resta.
function giaDettoDallaSede(s: Segnale, avvisi: Notifica[]): boolean {
  if (s.tipo !== "dati_mancanti" || !Array.isArray(s.manca) || s.manca.length === 0) return false;
  return s.manca.every((v) => voceDetta(v, s.mese, avvisi));
}

/**
 * Il «Da fare» della catena: segnali, osservazioni e avvisi di ogni punto
 * vendita in un elenco solo, una riga per sede (Mattia, screen 12: «in catena
 * le card sono sempre tante… comprimerle per poi espanderle, unificando card e
 * avvisi sotto»). Prima erano due elenchi: il «Da fare» e «Vedi tutti gli
 * avvisi», con lo stesso fatto in tutti e due.
 *
 * - `segnali` null = non ancora letti o non letti per errore (`errore`): il
 *   verde resta spento, perche' non sappiamo se c'e' qualcosa. Stessa regola
 *   per `avvisi`.
 * - Le fatture da collocare si contano dal briefing di gruppo, che la Home ha
 *   gia': compaiono anche mentre i segnali caricano o se falliscono.
 * - Le osservazioni sono fatti sull'andamento, non compiti, ma stanno qui come
 *   nella Home del punto vendita (fase 4): una positiva e' una voce, e basta la
 *   sua presenza a non dichiarare «tutto in ordine».
 * - `archiviati`: gli id delle voci archiviate in questa visita (l'avviso
 *   sparisce solo dopo che il worker ha risposto).
 */
export function daFareCatena(input: {
  segnali: { segnali?: Segnale[]; osservazioni?: Osservazione[] } | null;
  errore: boolean;
  avvisi: { notifiche?: Notifica[]; sedi_non_lette?: string[] } | null;
  erroreAvvisi: boolean;
  nDaCollocare: number | null | undefined;
  archiviati?: Iterable<string>;
  // false = scheda «Da collocare» spenta dall'admin (`tab_off_catena_collocare`,
  // Mattia 10/10/2026: OFFSIDE la usa, le catene con P.IVA diverse no). Niente
  // riga: il «Colloca» porterebbe a una scheda che non c'e'.
  codaAccesa?: boolean;
}): DaFareCatena {
  const generali: VoceDaFare[] = [];
  const n = input.nDaCollocare ?? 0;
  if (n > 0 && input.codaAccesa !== false) {
    generali.push({
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

  const perSede = new Map<string, { nome: string; voci: VoceDaFare[] }>();
  const aggiungi = (rid: string, nome: string, voce: VoceDaFare) => {
    const sede = perSede.get(rid);
    if (sede) sede.voci.push(voce);
    else perSede.set(rid, { nome, voci: [voce] });
  };

  const archiviati = new Set(input.archiviati ?? []);
  const avvisi = (input.avvisi?.notifiche ?? []).filter(
    (a) => !a.dismissed_at && !archiviati.has(`avviso-${chiaveAvviso(a)}`),
  );
  const avvisiDellaSede = new Map<string, Notifica[]>();
  for (const a of avvisi) {
    const rid = (a.ristorante_id ?? "").trim();
    if (!rid) continue;
    avvisiDellaSede.set(rid, [...(avvisiDellaSede.get(rid) ?? []), a]);
  }

  if (input.segnali) {
    (input.segnali.segnali ?? []).forEach((s, i) => {
      const rid = (s.ristorante_id ?? "").trim();
      const voce: VoceDaFare = {
        id: `segnale-${s.tipo}-${i}`,
        severity: s.severity,
        testo: s.testo,
        sede: null,
        azione: rid ? { tipo: "sede", ristoranteId: rid, pagina: s.cta_page, etichetta: "Vedi PV" } : null,
        ignorabile: false,
      };
      if (!rid) generali.push(voce);
      else if (!giaDettoDallaSede(s, avvisiDellaSede.get(rid) ?? [])) aggiungi(rid, s.pv_nome, voce);
    });
  }

  for (const a of avvisi) {
    const rid = (a.ristorante_id ?? "").trim();
    const dest = destinazioneAvviso(a, "gruppo");
    const voce: VoceDaFare = {
      id: `avviso-${chiaveAvviso(a)}`,
      severity: a.severity,
      testo: pulisci(a.title),
      dettaglio: a.body ? pulisci(a.body) : null,
      sede: null,
      azione:
        dest?.tipo === "sede"
          ? { tipo: "sede", ristoranteId: dest.ristoranteId, pagina: dest.href, etichetta: dest.label }
          : null,
      // Un avviso LIVE non si archivia: si chiude da solo quando arriva il dato.
      ignorabile: a.dismissible !== false,
      rif: a.id,
    };
    if (rid) aggiungi(rid, a.sede_nome || rid, voce);
    else generali.push(voce);
  }

  if (input.segnali) {
    osservazioniDaMostrare(input.segnali).forEach((o, i) => {
      const voce: VoceDaFare = {
        id: `osservazione-${o.tipo}-${o.ristorante_id}-${i}`,
        severity: o.severity,
        testo: o.testo,
        sede: null,
        azione: haDestinazione(o)
          ? { tipo: "sede", ristoranteId: o.ristorante_id, pagina: o.cta_page, etichetta: "Vedi PV" }
          : null,
        ignorabile: false,
      };
      if (haDestinazione(o)) aggiungi(o.ristorante_id.trim(), o.pv_nome, voce);
      else generali.push({ ...voce, sede: o.pv_nome || null });
    });
  }

  // `sort` e' stabile: a parita' di gravita' resta l'ordine di arrivo (coda,
  // segnali nell'ordine del backend, avvisi, osservazioni).
  const perGravita = (a: VoceDaFare, b: VoceDaFare) => RANGO[a.severity] - RANGO[b.severity];
  generali.sort(perGravita);
  const sedi: SedeDaFare[] = [...perSede.entries()].map(([ristoranteId, s]) => {
    const voci = [...s.voci].sort(perGravita);
    const conteggio = voci.length === 1 ? "1 avviso" : `${voci.length} avvisi`;
    return { ristoranteId, nome: s.nome, severity: voci[0].severity, voci, conteggio };
  });
  sedi.sort(
    (a, b) =>
      RANGO[a.severity] - RANGO[b.severity] ||
      b.voci.length - a.voci.length ||
      a.nome.localeCompare(b.nome, "it"),
  );

  const totale = generali.length + sedi.reduce((t, s) => t + s.voci.length, 0);
  const avvisiInArrivo = input.avvisi === null && !input.erroreAvvisi;
  const avviso = !input.segnali
    ? input.errore
      ? "errore"
      : "caricamento"
    : avvisiInArrivo
      ? "caricamento"
      : null;
  const nonLette = input.avvisi?.sedi_non_lette ?? [];
  const notaAvvisi = input.erroreAvvisi
    ? "Non è stato possibile leggere gli avvisi dei punti vendita."
    : nonLette.length > 0
      ? `Avvisi non letti per: ${nonLette.join(", ")}.`
      : null;
  return {
    generali,
    sedi,
    totale,
    avviso,
    notaAvvisi,
    verde: avviso === null && notaAvvisi === null && totale === 0,
  };
}
