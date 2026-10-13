// Admin → Oggi (riordino del 13/10/2026): la lista delle cose da fare. Le voci
// le compone il worker (services/admin_attenzione_service.py); qui solo cio'
// che serve alla pagina per mostrarle. Logica pura: l'unica rete sul frontend
// esegue lib/ e non i .tsx.

export type AzioneVoce =
  | { tipo: "riprova"; queue_id: number }
  | { tipo: "assegna_sede"; queue_id: number; user_id: string | null }
  | { tipo: "assegna_piva"; queue_id: number; piva: string | null }
  | { tipo: "collega_mittente" }
  | { tipo: "richiesta"; id: string };

export type Voce = {
  chiave: string;
  gravita: "critico" | "oggi";
  titolo: string;
  dettaglio: string | null;
  da: string | null;
  cliente_id: string | null;
  cliente: string | null;
  link: string | null;
  azione: AzioneVoce | null;
};

export type SedeOggi = { id: string; nome: string; partita_iva: string | null; user_id: string; cliente: string };

export type DatiOggi = {
  voci: Voce[];
  numeri: {
    fatture_ieri: number | null;
    fatture_mese: number | null;
    costo_ai_mese: number | null;
    clienti_attivi: number;
    clienti: number;
  };
  problemi_per_cliente: Record<string, number>;
  sedi: SedeOggi[];
  _errors: string[];
};

export const OGGI_VUOTO: DatiOggi = {
  voci: [],
  numeri: { fatture_ieri: null, fatture_mese: null, costo_ai_mese: null, clienti_attivi: 0, clienti: 0 },
  problemi_per_cliente: {},
  sedi: [],
  _errors: [],
};

/** Una risposta del worker che non ha la forma attesa non diventa «Tutto a
 *  posto»: torna null e la pagina dice che non ha potuto leggere. */
export function leggiOggi(data: unknown): DatiOggi | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Partial<DatiOggi>;
  if (!Array.isArray(d.voci) || !d.numeri || typeof d.numeri !== "object") return null;
  return {
    voci: d.voci,
    numeri: { ...OGGI_VUOTO.numeri, ...d.numeri },
    problemi_per_cliente: d.problemi_per_cliente ?? {},
    sedi: Array.isArray(d.sedi) ? d.sedi : [],
    _errors: Array.isArray(d._errors) ? d._errors : [],
  };
}

export function raggruppa(voci: Voce[]): { urgenti: Voce[]; daFare: Voce[] } {
  return {
    urgenti: voci.filter((v) => v.gravita === "critico"),
    daFare: voci.filter((v) => v.gravita !== "critico"),
  };
}

/** Le sedi fra cui scegliere: per smistare una fattura solo quelle del suo
 *  cliente (la P.IVA e' gia' sua), per una P.IVA sconosciuta tutte. */
export function sediPerAzione(azione: AzioneVoce, sedi: SedeOggi[]): { id: string; label: string }[] {
  const scelte = azione.tipo === "assegna_sede" ? sedi.filter((s) => s.user_id === azione.user_id) : sedi;
  return scelte.map((s) => ({
    id: s.id,
    label: azione.tipo === "assegna_sede"
      ? `${s.nome}${s.partita_iva ? ` — ${s.partita_iva}` : ""}`
      : `${s.nome} (${s.cliente})`,
  }));
}

/** «Ieri 3 fatture · 56 nel mese · costo AI $ 0,10 · 7 clienti attivi su 7». */
export function rigaNumeri(n: DatiOggi["numeri"]): string {
  const parti: string[] = [];
  if (n.fatture_ieri != null) parti.push(`Ieri ${n.fatture_ieri} fattur${n.fatture_ieri === 1 ? "a" : "e"}`);
  if (n.fatture_mese != null) parti.push(`${n.fatture_mese} nel mese`);
  if (n.costo_ai_mese != null) parti.push(`costo AI del mese $ ${n.costo_ai_mese.toFixed(2).replace(".", ",")}`);
  parti.push(`${n.clienti_attivi} clienti attivi su ${n.clienti}`);
  return parti.join(" · ");
}
