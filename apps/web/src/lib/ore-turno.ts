// Come si ripartiscono le ore di un turno fra ordinarie e straordinario, e
// come si somma il costo di una persona nel mese.
//
// Modello in vigore dal 05/09/2026: le ore extra sono un SOTTOINSIEME delle
// ore del turno, non un addendo. Un 09-17 con 2 extra sono 8 ore totali di cui
// 2 di straordinario, non 10. Prima erano additive: se tocchi questo file, i
// punti da allineare sono il worker (_ore_turno), margini.py, workspace.py,
// personale_export_service.py, il tab desktop e /m — cercali, non fidarti
// di questa lista.
//
// Il clamp non e' difensivo per abitudine: senza, un ore_extra maggiore delle
// ore lavorate fa uscire l'ordinario negativo e gonfia il monte ore totale
// (8 ore con 10 extra diventavano 10 ore e il 25% di costo in piu').
//
// «Lo stipendio del mese vince» (piano consulente, fase C, 04/10/2026). Turni
// giornalieri e riga mensile da busta paga CONVIVONO per lo stesso dipendente
// nello stesso mese (CASATI 14 segna le ore ogni giorno e mette lo stipendio a
// fine mese). Per chi ha la riga mensile:
//   - il costo viene SOLO dalla riga mensile: ordinario = lordo − extra −
//     chiamata (mai negativo), extra e chiamata «di cui» della busta;
//   - i suoi turni giornalieri contano come ORE, non come costo;
//   - le sue assenze a carico non si sommano (sono gia' in busta);
//   - le ore vengono dai turni lavorati se ce ne sono, altrimenti dalle ore
//     dichiarate sulla riga mensile — mai le due insieme.
// Chi non ha la riga mensile resta com'era. E' la stessa regola del worker
// (workspace.py / margini.py / export): cambiarla qui da sola fa divergere il
// tab dai Margini.

export type RipartizioneOre = {
  /** Ore ordinarie: totale meno lo straordinario, mai negative. */
  ordinarie: number;
  /** Straordinario effettivo, mai superiore alle ore del turno. */
  extra: number;
};

/**
 * Divide le ore di un turno fra ordinarie e straordinario.
 *
 * `ordinarie + extra` e' sempre pari a `oreTotali` (a meno di negativi in
 * ingresso, che valgono zero): e' la proprieta' che rende il totale mostrato
 * uguale alle ore davvero lavorate.
 */
export function ripartisciOre(oreTotali: number, oreExtra: number | null | undefined): RipartizioneOre {
  const tot = Math.max(0, oreTotali || 0);
  const extra = Math.min(Math.max(0, oreExtra || 0), tot);
  return { ordinarie: Math.round((tot - extra) * 100) / 100, extra };
}

/** Il minimo che serve per aggregare: il resto della riga turno non conta qui. */
export type TurnoAggregabile = {
  dipendente_id: string;
  tipo_giorno?: string | null;
  mensile?: boolean | null;
  ore_extra?: number | null;
  costo_orario?: number | null;
  costo_orario_extra?: number | null;
  lordo_mensile?: number | null;
  importo_extra?: number | null;
  importo_chiamata?: number | null;
};

export type TotaliPersona = {
  oreStd: Record<string, number>;
  oreExt: Record<string, number>;
  costoStd: Record<string, number>;
  costoExt: Record<string, number>;
  costoChi: Record<string, number>;
  costoTot: Record<string, number>;
};

const arrot2 = (v: number) => Math.round(v * 100) / 100;

/** Giorno lavorato: riposo/ferie/malattia restano fuori da ore e costo lavorato. */
function lavorato(t: { tipo_giorno?: string | null }): boolean {
  return (t.tipo_giorno ?? "turno") === "turno";
}

export type ComponentiStipendio = {
  ordinario: number;
  extra: number;
  chiamata: number;
  totale: number;
};

/**
 * Le tre voci di una riga mensile. `lordo_mensile` e' il TOTALE della busta;
 * extra e chiamata ne sono una parte, quindi l'ordinario e' il resto (mai
 * negativo). Il totale e' la somma delle tre, non il lordo: se extra +
 * chiamata superano il lordo (dato sporco) non si perde nessuna delle due.
 */
export function componentiStipendio(t: {
  lordo_mensile?: number | null;
  importo_extra?: number | null;
  importo_chiamata?: number | null;
}): ComponentiStipendio {
  const lordo = t.lordo_mensile ?? 0;
  const extra = t.importo_extra ?? 0;
  const chiamata = t.importo_chiamata ?? 0;
  const ordinario = Math.max(0, arrot2(lordo - extra - chiamata));
  return { ordinario, extra, chiamata, totale: arrot2(ordinario + extra + chiamata) };
}

/** Chi ha lo stipendio del mese (una riga mensile): per loro il costo e' quello. */
export function dipendentiConStipendio(turni: TurnoAggregabile[]): Set<string> {
  return new Set(turni.filter(t => t.mensile && lavorato(t)).map(t => t.dipendente_id));
}

/** Chi ha almeno un turno giornaliero LAVORATO: per loro le ore vengono da li'. */
function dipendentiConTurniLavorati(turni: TurnoAggregabile[]): Set<string> {
  return new Set(turni.filter(t => !t.mensile && lavorato(t)).map(t => t.dipendente_id));
}

/**
 * Somma ore e costo per persona, dividendo ordinarie e straordinario.
 *
 * Vive qui e non nel .tsx perche' e' il punto che si e' rotto: la libreria era
 * corretta ma il chiamante leggeva `ore_extra` grezzo, e un test sulla sola
 * `ripartisciOre` restava verde. In `lib/` il TypeScript vero e' eseguibile
 * dai test (tests/helpers_ts.py), quindi il presidio copre il consumatore.
 *
 * Due passate: prima si decide CHI ha lo stipendio e chi ha turni lavorati,
 * poi si somma. In una passata sola il risultato dipenderebbe dall'ordine in
 * cui arrivano le righe (la riga mensile sta sul giorno 1, ma il frontend
 * fonde due fetch e la mette in coda).
 *
 * `oreDi` arriva dal chiamante perche' il calcolo dagli orari sta nel .tsx
 * insieme al parsing dei campi form; qui serve solo il totale gia' risolto.
 *
 * Input di UN solo mese (desktop e /m caricano un mese alla volta): la regola
 * e' per dipendente, mentre il worker la applica per (dipendente, mese). Con
 * due mesi lo stipendio di uno spegnerebbe il costo dei turni dell'altro.
 */
export function aggregaPerPersona(
  turni: TurnoAggregabile[],
  nomeDi: (t: TurnoAggregabile) => string,
  oreDi: (t: TurnoAggregabile) => number,
): TotaliPersona {
  const oreStd: Record<string, number> = {};
  const oreExt: Record<string, number> = {};
  const costoStd: Record<string, number> = {};
  const costoExt: Record<string, number> = {};
  const costoChi: Record<string, number> = {};
  const costoTot: Record<string, number> = {};
  const conStipendio = dipendentiConStipendio(turni);
  const conTurni = dipendentiConTurniLavorati(turni);
  const somma = (acc: Record<string, number>, n: string, v: number) => { acc[n] = (acc[n] ?? 0) + v; };

  for (const t of turni) {
    if (!lavorato(t)) continue;
    const n = nomeDi(t);
    // Ore: dai turni lavorati se ci sono, altrimenti da quelle dichiarate in
    // busta. Mai le due insieme, o le stesse ore si contano due volte.
    const contaOre = !t.mensile || !conTurni.has(t.dipendente_id);
    const { ordinarie, extra } = ripartisciOre(oreDi(t), t.ore_extra);
    if (contaOre) {
      somma(oreStd, n, ordinarie);
      somma(oreExt, n, extra);
    }
    if (t.mensile) {
      // Riga mensile: costo dal lordo reale della busta paga, non da tariffa.
      const c = componentiStipendio(t);
      somma(costoStd, n, c.ordinario);
      somma(costoExt, n, c.extra);
      somma(costoChi, n, c.chiamata);
      somma(costoTot, n, c.totale);
      continue;
    }
    // Lo stipendio del mese vince: il turno di chi ce l'ha non aggiunge costo.
    if (conStipendio.has(t.dipendente_id)) continue;
    const coStd = t.costo_orario ?? null;
    if (coStd == null) continue;   // turno senza tariffa: non inventiamo un costo
    const coExt = t.costo_orario_extra ?? coStd;
    somma(costoStd, n, ordinarie * coStd);
    somma(costoExt, n, extra * coExt);
    somma(costoTot, n, ordinarie * coStd + extra * coExt);
  }
  return { oreStd, oreExt, costoStd, costoExt, costoChi, costoTot };
}

export type OreSegnate = { ordinarie: number; extra: number; nTurni: number };

/**
 * Le ore gia' segnate nei turni giornalieri, per dipendente: quelle che il
 * modulo «Inserisci mese» mostra in sola lettura quando a fine mese si mette
 * lo stipendio (screen 13-14). Solo turni LAVORATI: riposo, ferie e malattia
 * non sono ore; la riga mensile non e' un turno.
 */
export function oreTurniPerDipendente(
  turni: TurnoAggregabile[],
  oreDi: (t: TurnoAggregabile) => number,
): Record<string, OreSegnate> {
  const out: Record<string, OreSegnate> = {};
  for (const t of turni) {
    if (t.mensile || !lavorato(t)) continue;
    const { ordinarie, extra } = ripartisciOre(oreDi(t), t.ore_extra);
    const r = out[t.dipendente_id] ?? { ordinarie: 0, extra: 0, nTurni: 0 };
    r.ordinarie = arrot2(r.ordinarie + ordinarie);
    r.extra = arrot2(r.extra + extra);
    r.nTurni += 1;
    out[t.dipendente_id] = r;
  }
  return out;
}

export type TurnoRiepilogabile = TurnoAggregabile & {
  data_turno: string;
  importo_a_carico?: number | null;
};

export type RiepilogoDipendente<T extends TurnoRiepilogabile> = {
  dipendenteId: string;
  oreLavorate: number;
  giorniLavorati: number;
  giorniFerie: number;
  giorniMalattia: number;
  giorniRiposo: number;
  costoTot: number;
  /** Ha la riga mensile: il costo e' lo stipendio, non i turni. */
  haStipendio: boolean;
  /** Le righe giornaliere (turni e assenze) in ordine di data, senza la mensile. */
  turniGiornalieri: T[];
};

/**
 * Il riepilogo per dipendente della vista «Mese» di /m, con la stessa regola
 * del tab desktop. Era una copia inline nel .tsx, senza test.
 *
 * Differenza voluta col desktop, gia' presente prima: /m somma al costo le
 * assenze a carico (ferie/malattia con `importo_a_carico`) di chi NON ha lo
 * stipendio, perche' per lui sono un costo che altrimenti non compare. Per chi
 * ha lo stipendio no: sono gia' dentro la busta, sommarle le conterebbe due
 * volte (stessa regola del worker).
 */
export function riepilogoPerDipendente<T extends TurnoRiepilogabile>(
  turni: T[],
  oreDi: (t: T) => number,
): RiepilogoDipendente<T>[] {
  const conStipendio = dipendentiConStipendio(turni);
  const conTurni = dipendentiConTurniLavorati(turni);
  const perDip = new Map<string, RiepilogoDipendente<T>>();
  for (const t of turni) {
    let r = perDip.get(t.dipendente_id);
    if (!r) {
      r = {
        dipendenteId: t.dipendente_id, oreLavorate: 0, giorniLavorati: 0, giorniFerie: 0,
        giorniMalattia: 0, giorniRiposo: 0, costoTot: 0,
        haStipendio: conStipendio.has(t.dipendente_id), turniGiornalieri: [],
      };
      perDip.set(t.dipendente_id, r);
    }
    const tipo = t.tipo_giorno ?? "turno";
    if (t.mensile) {
      if (tipo !== "turno") continue;
      if (!conTurni.has(t.dipendente_id)) r.oreLavorate += oreDi(t);
      r.costoTot += componentiStipendio(t).totale;
      continue;
    }
    r.turniGiornalieri.push(t);
    if (tipo === "turno") {
      r.giorniLavorati++;
      const ore = oreDi(t);
      r.oreLavorate += ore;
      if (!r.haStipendio) r.costoTot += costoTurnoGiornaliero(ore, t.ore_extra, t.costo_orario, t.costo_orario_extra);
    } else if (tipo === "ferie" || tipo === "malattia") {
      if (tipo === "ferie") r.giorniFerie++; else r.giorniMalattia++;
      if (!r.haStipendio) r.costoTot += t.importo_a_carico ?? 0;
    } else if (tipo === "riposo") {
      r.giorniRiposo++;
    }
  }
  const righe = [...perDip.values()];
  for (const r of righe) {
    r.oreLavorate = arrot2(r.oreLavorate);
    r.costoTot = arrot2(r.costoTot);
    r.turniGiornalieri.sort((x, y) => x.data_turno.localeCompare(y.data_turno));
  }
  return righe;
}

/**
 * Costo di un turno giornaliero: ordinarie x tariffa + extra x tariffa extra.
 *
 * Estratta perche' la stessa formula viveva in tre punti (tab desktop, /m,
 * riepilogo mensile) e uno di essi e' rimasto indietro per giorni. Ritorna 0
 * senza tariffa: un turno senza costo_orario non vale zero euro "per default",
 * semplicemente non lo sappiamo, e inventarlo falserebbe il MOL.
 */
export function costoTurnoGiornaliero(
  oreTotali: number,
  oreExtra: number | null | undefined,
  costoOrario: number | null | undefined,
  costoOrarioExtra?: number | null,
): number {
  if (costoOrario == null) return 0;
  const { ordinarie, extra } = ripartisciOre(oreTotali, oreExtra);
  const tariffaExtra = costoOrarioExtra ?? costoOrario;
  return ordinarie * costoOrario + extra * tariffaExtra;
}

export type PayloadMensile = {
  ore_totali: number;
  lordo: number;
  ore_extra: number | null;
  importo_extra: number | null;
  importo_chiamata: number | null;
  note: string | null;
};

/**
 * Corpo di POST/PATCH del mensile, uguale per desktop e /m. I tre importi si
 * scrivono separati e si salva il lordo totale della busta (extra e chiamata
 * ne sono «di cui»). Con `oreDaiTurni` le ore le conta il worker dai turni:
 * ore_totali 0 e ore_extra non si manda (il worker le rifiuterebbe).
 */
export function payloadMensile(v: {
  oreOrd: number; oreExtra: number;
  importoOrd: number; importoExtra: number; importoChiamata: number;
  oreDaiTurni: boolean; note: string;
}): { errore: string } | { payload: PayloadMensile } {
  if (v.oreOrd < 0 || v.oreExtra < 0) return { errore: "Le ore non possono essere negative" };
  if (v.importoOrd < 0 || v.importoExtra < 0 || v.importoChiamata < 0) {
    return { errore: "Gli importi non possono essere negativi" };
  }
  const oreTot = arrot2(v.oreOrd + v.oreExtra);
  const lordo = arrot2(v.importoOrd + v.importoExtra + v.importoChiamata);
  if (v.oreDaiTurni) {
    if (lordo <= 0) return { errore: "Inserisci lo stipendio del mese" };
  } else if (oreTot <= 0 && lordo <= 0) {
    return { errore: "Inserisci almeno le ore o il lordo del mese" };
  }
  return {
    payload: {
      ore_totali: v.oreDaiTurni ? 0 : oreTot,
      lordo,
      ore_extra: !v.oreDaiTurni && v.oreExtra > 0 ? v.oreExtra : null,
      importo_extra: v.importoExtra > 0 ? v.importoExtra : null,
      importo_chiamata: v.importoChiamata > 0 ? v.importoChiamata : null,
      note: v.note || null,
    },
  };
}
