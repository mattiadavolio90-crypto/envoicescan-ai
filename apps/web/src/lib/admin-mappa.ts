// Admin → Clienti, vista Mappa: clienti, sedi e canali ad albero, con lo stato
// di ogni nodo (13/10/2026). Lo stato viene dalle stesse voci della pagina Oggi
// piu' l'ultimo caricamento di ogni sede, cosi' mappa e Oggi non si
// contraddicono. Logica pura: l'unica rete sul frontend esegue lib/.

import type { Voce } from "@/lib/admin-oggi";
import { giorniDa, testoGiorni, GIORNI_FERMO } from "@/lib/admin-clienti";

export type StatoNodo = "ok" | "oggi" | "critico" | "spento" | "ignoto";
export type TipoNodo = "radice" | "cliente" | "sede" | "canale";
export type IconaNodo = "rete" | "catena" | "locale" | "negozio" | "sdi" | "cassa" | "commercialista" | "utenti";

export type NodoMappa = {
  id: string;
  tipo: TipoNodo;
  icona: IconaNodo;
  nome: string;
  sub: string | null;
  // Il peggiore fra il suo stato e quello dei figli.
  stato: StatoNodo;
  // Cosa non va in questo nodo e nei suoi figli (canali esclusi: ripetono la sede).
  motivi: string[];
  link: string | null;
  figli: NodoMappa[];
};

export type SedeMappa = {
  id: string;
  nome_ristorante: string;
  piano: string | null;
  sdi_attivo?: boolean;
  tipo_attivita?: string;
  ultimo_caricamento_at?: string | null;
  ricavi_collegati?: boolean | null;
  commercialista_attivo?: boolean | null;
};

export type ClienteMappa = {
  id: string;
  email: string;
  nome_ristorante: string;
  nome_gruppo: string | null;
  attivo: boolean;
  salute_incompleta?: boolean;
  n_sotto_utenti?: number | null;
  sedi: SedeMappa[];
};

const PESO: Record<StatoNodo, number> = { ok: 0, spento: 0, ignoto: 0, oggi: 1, critico: 2 };

export function peggiore(stati: StatoNodo[]): StatoNodo {
  return stati.reduce<StatoNodo>((m, s) => (PESO[s] > PESO[m] ? s : m), stati[0] ?? "ok");
}

/** Motivi uguali diventano uno solo col conteggio: «Fattura da assegnare a una sede (5)». */
export function raggruppaMotivi(motivi: string[]): string[] {
  const conta = new Map<string, number>();
  for (const m of motivi) conta.set(m, (conta.get(m) ?? 0) + 1);
  return [...conta].map(([m, n]) => (n > 1 ? `${m} (${n})` : m));
}

function gravita(voci: Voce[]): StatoNodo {
  return voci.reduce<StatoNodo>((m, v) => peggiore([m, v.gravita]), "ok");
}

const PIANI: Record<string, string> = { free: "Free", base: "Base", plus: "Plus", pro: "Pro" };

function canale(id: string, icona: IconaNodo, nome: string, stato: StatoNodo, link: string): NodoMappa {
  return { id, tipo: "canale", icona, nome, sub: null, stato, motivi: [], link, figli: [] };
}

/** Un canale acceso prende lo stato delle voci che lo riguardano; spento e'
 *  grigio; null (il worker non l'ha potuto leggere) e' «non so», non spento. */
function statoCanale(acceso: boolean | null | undefined, voci: Voce[]): StatoNodo {
  if (acceso === null || acceso === undefined) return "ignoto";
  return acceso ? gravita(voci) : "spento";
}

function nodoSede(c: ClienteMappa, s: SedeMappa, voci: Voce[], adesso: number): NodoMappa {
  const base = `/admin/clienti/${c.id}`;
  const proprie = voci.filter((v) => v.ristorante_id === s.id);
  const motivi = proprie.map((v) => v.titolo);
  let stato = gravita(proprie);
  const noto = !c.salute_incompleta;
  const g = noto ? giorniDa(s.ultimo_caricamento_at, adesso) : null;
  // «Fermo» come nella lista; non si ripete se lo dice gia' la voce dello SDI.
  if (c.attivo && noto && !proprie.some((v) => v.chiave.startsWith("sdi:"))) {
    if (g === null) {
      motivi.push("Non ha mai caricato una fattura");
      stato = peggiore([stato, "oggi"]);
    } else if (g >= GIORNI_FERMO) {
      motivi.push(`Nessuna fattura da ${g} giorni`);
      stato = peggiore([stato, "oggi"]);
    }
  }
  const piano = PIANI[(s.piano || "base").toLowerCase()] ?? s.piano;
  const figli = [
    canale(`${s.id}:sdi`, "sdi", s.sdi_attivo ? "SDI attivo" : "SDI spento",
      statoCanale(s.sdi_attivo ?? false, proprie.filter((v) => v.chiave.startsWith("sdi:"))), `${base}?tab=sedi`),
    canale(`${s.id}:ricavi`, "cassa",
      s.ricavi_collegati === null || s.ricavi_collegati === undefined ? "Ricavi: non letto"
        : s.ricavi_collegati ? "Ricavi dalla cassa" : "Ricavi a mano",
      statoCanale(s.ricavi_collegati, proprie.filter((v) => v.chiave.startsWith("ricavi:"))), `${base}?tab=sedi`),
    canale(`${s.id}:comm`, "commercialista",
      s.commercialista_attivo === null || s.commercialista_attivo === undefined ? "Commercialista: non letto"
        : s.commercialista_attivo ? "Invio al commercialista" : "Commercialista spento",
      statoCanale(s.commercialista_attivo, []), `${base}?tab=invii`),
  ];
  return {
    id: s.id,
    tipo: "sede",
    icona: s.tipo_attivita === "retail" ? "negozio" : "locale",
    nome: s.nome_ristorante || "—",
    sub: `${piano} · ${noto ? testoGiorni(s.ultimo_caricamento_at, adesso).toLowerCase() : "—"}`,
    // I canali leggono le stesse voci della sede: il loro stato e' gia' qui.
    stato,
    motivi: motivi.map((m) => `${s.nome_ristorante}: ${m}`),
    link: `${base}?tab=sedi`,
    figli,
  };
}

function nodoCliente(c: ClienteMappa, voci: Voce[], adesso: number): NodoMappa {
  const base = `/admin/clienti/${c.id}`;
  const sue = voci.filter((v) => v.cliente_id === c.id);
  const generali = sue.filter((v) => !v.ristorante_id || !c.sedi.some((s) => s.id === v.ristorante_id));
  const sedi = c.sedi.map((s) => nodoSede(c, s, sue, adesso));
  const nUtenti = c.n_sotto_utenti;
  const utenti = canale(`${c.id}:utenti`, "utenti",
    nUtenti === null || nUtenti === undefined ? "Utenti: non letto"
      : nUtenti === 0 ? "Solo il titolare" : `${nUtenti} sotto-utent${nUtenti === 1 ? "e" : "i"}`,
    nUtenti === null || nUtenti === undefined ? "ignoto" : nUtenti === 0 ? "spento" : "ok",
    `${base}?tab=account`);
  const catena = c.sedi.length > 1;
  const proprio = c.attivo ? gravita(generali) : peggiore(["spento", gravita(generali)]);
  return {
    id: c.id,
    tipo: "cliente",
    icona: catena ? "catena" : c.sedi[0]?.tipo_attivita === "retail" ? "negozio" : "locale",
    nome: c.nome_gruppo || c.nome_ristorante || c.email,
    sub: !c.attivo ? "disattivo" : catena ? `catena · ${c.sedi.length} sedi` : c.sedi.length === 0 ? "nessuna sede" : "punto vendita",
    stato: peggiore([proprio, ...sedi.map((s) => s.stato)]),
    motivi: raggruppaMotivi([...generali.map((v) => v.titolo), ...sedi.flatMap((s) => s.motivi)]),
    link: base,
    figli: [...sedi, utenti],
  };
}

export function costruisciMappa(clienti: ClienteMappa[], voci: Voce[], adesso: number): NodoMappa {
  const ids = new Set(clienti.map((c) => c.id));
  // Voci di nessun cliente noto (P.IVA sconosciute, categorie, allarmi): stanno sulla radice.
  const diTutti = voci.filter((v) => !v.cliente_id || !ids.has(v.cliente_id));
  const figli = clienti.map((c) => nodoCliente(c, voci, adesso));
  return {
    id: "oneflux",
    tipo: "radice",
    icona: "rete",
    nome: "ONEFLUX",
    sub: `${clienti.length} client${clienti.length === 1 ? "e" : "i"}`,
    stato: peggiore([gravita(diTutti), ...figli.map((f) => f.stato)]),
    motivi: raggruppaMotivi(diTutti.map((v) => v.titolo)),
    link: "/admin",
    figli,
  };
}

const PROBLEMA = (s: StatoNodo) => s === "oggi" || s === "critico";

/** «Solo con problemi»: la radice resta, dei figli solo chi ha qualcosa che non va. */
export function soloProblemi(n: NodoMappa): NodoMappa {
  return { ...n, figli: n.figli.filter((f) => PROBLEMA(f.stato)).map(soloProblemi) };
}

/** I nodi che partono aperti: la radice e i clienti con qualcosa da fare,
 *  cosi' si vedono subito le sedi in difficolta'. Le sedi restano chiuse. */
export function apertiAllInizio(radice: NodoMappa): string[] {
  return [radice.id, ...radice.figli.filter((f) => PROBLEMA(f.stato)).map((f) => f.id)];
}

/** Ogni nodo che ha figli, per «Espandi tutto». */
export function idConFigli(n: NodoMappa): string[] {
  return n.figli.length ? [n.id, ...n.figli.flatMap(idConFigli)] : [];
}

export type Vista = "lista" | "mappa";

export function vistaDaUrl(valore: string | null | undefined): Vista {
  return valore === "mappa" ? "mappa" : "lista";
}
