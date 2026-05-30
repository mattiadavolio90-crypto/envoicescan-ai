export type Documento = {
  id: string;
  file_origine: string;
  fornitore: string;
  tipo_documento: string;
  totale_documento: number;
  data_documento: string | null;
  numero_documento: string | null;
  scadenza_effettiva: string | null;
  scadenza_source: string | null;
  pagata: boolean;
  data_pagamento: string | null;
  pagata_at: string | null;
  stato_scadenza: string;
};

export type CalendarGiorno = {
  giorno: number;
  totale: number;
};

export type CalendarResponse = {
  anno: number;
  mese: number;
  giorni: CalendarGiorno[];
  totale_mese: number;
};

export type RegolaPagamento = {
  id: string;
  piva_fornitore: string;
  modalita: string;
  giorni_pagamento: number;
  data_riferimento: string;
  attiva: boolean;
  note: string | null;
  created_at: string | null;
};

export type ScadenzarioKpi = {
  scadute_count: number;
  scadute_totale: number;
  settimana_count: number;
  settimana_totale: number;
  da_pagare_count: number;
  da_pagare_totale: number;
  pagate_mese_count: number;
  pagate_mese_totale: number;
};

export const MODALITA_LABELS: Record<string, string> = {
  rid: "Automatico / RID — già pagato",
  "30gg": "30 giorni dalla data fattura",
  "60gg": "60 giorni dalla data fattura",
  "90gg": "90 giorni dalla data fattura",
  "30gg_fm": "Fine mese successivo",
  "60gg_fm": "Fine del 2° mese successivo",
  "90gg_fm": "Fine del 3° mese successivo",
};

export function computeKpi(documenti: Documento[]): ScadenzarioKpi {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const in7 = new Date(today);
  in7.setDate(in7.getDate() + 7);

  const primoMese = new Date(today.getFullYear(), today.getMonth(), 1);

  let scadute_count = 0, scadute_totale = 0;
  let settimana_count = 0, settimana_totale = 0;
  let da_pagare_count = 0, da_pagare_totale = 0;
  let pagate_mese_count = 0, pagate_mese_totale = 0;

  for (const doc of documenti) {
    const totale = doc.totale_documento || 0;

    if (doc.pagata) {
      const pagata_at = doc.pagata_at ? new Date(doc.pagata_at) : null;
      if (pagata_at && pagata_at >= primoMese) {
        pagate_mese_count++;
        pagate_mese_totale += totale;
      }
      continue;
    }

    da_pagare_count++;
    da_pagare_totale += totale;

    if (!doc.scadenza_effettiva) continue;

    const scad = new Date(doc.scadenza_effettiva);
    scad.setHours(0, 0, 0, 0);

    if (scad < today) {
      scadute_count++;
      scadute_totale += totale;
    } else if (scad <= in7) {
      settimana_count++;
      settimana_totale += totale;
    }
  }

  return {
    scadute_count, scadute_totale,
    settimana_count, settimana_totale,
    da_pagare_count, da_pagare_totale,
    pagate_mese_count, pagate_mese_totale,
  };
}

export function bucketizeDocumenti(documenti: Documento[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const in7 = new Date(today);
  in7.setDate(in7.getDate() + 7);
  const in30 = new Date(today);
  in30.setDate(in30.getDate() + 30);

  const scadute: Documento[] = [];
  const settimana: Documento[] = [];
  const mese: Documento[] = [];
  const oltre: Documento[] = [];
  const senzaScadenza: Documento[] = [];
  const pagate: Documento[] = [];

  for (const doc of documenti) {
    if (doc.pagata) {
      pagate.push(doc);
      continue;
    }
    if (!doc.scadenza_effettiva) {
      senzaScadenza.push(doc);
      continue;
    }
    const scad = new Date(doc.scadenza_effettiva);
    scad.setHours(0, 0, 0, 0);
    if (scad < today) scadute.push(doc);
    else if (scad <= in7) settimana.push(doc);
    else if (scad <= in30) mese.push(doc);
    else oltre.push(doc);
  }

  return { scadute, settimana, mese, oltre, senzaScadenza, pagate };
}

export function formatEuro(val: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
  } catch {
    return iso;
  }
}
