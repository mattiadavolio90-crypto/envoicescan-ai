// Schede delle due pagine di lavoro della catena (decisione Mattia 28/9): la
// Home della catena resta solo recap e assistenza, le funzioni che ci stavano
// come finestre diventano schede di pagina.
//
// Separate da TAB_SEZIONI (lib/tab-flags) di proposito: quella mappa e'
// indicizzata per pagina del PUNTO VENDITA e alimenta gli interruttori admin
// per-tab (`tab_off_*`), che in catena non esistono.

import type { TabDef } from "./tab-flags";

// «Scadenze» prima (Mattia, 28/9): e' la scheda su cui si apre la pagina, e
// stava terza.
export const SCHEDE_FATTURE_CATENA: readonly TabDef[] = [
  { key: "scadenze", label: "Scadenze" },
  { key: "collocare", label: "Da collocare" },
  { key: "costi", label: "Costi di gruppo" },
];

// Chi apre «Gestione Fatture» dal menu ci va quasi sempre per pagare: prima di
// questa pagina a schede la voce apriva lo scadenziario, e resta cosi'. Alla
// coda si arriva col link esplicito (LINK_CODA_GRUPPO) da Home e caricamento.
// Resta dichiarata anche ora che e' la prima: con lo scadenziario spento la
// scheda non c'e', e risolviScheda ricade sulla prima disponibile.
export const SCHEDA_FATTURE_PREDEFINITA = "scadenze";

export const SCHEDE_ANALISI_CATENA: readonly TabDef[] = [
  { key: "spesa", label: "Spesa per PV" },
  { key: "margini", label: "Margini e coperti" },
  { key: "tag", label: "Tag di catena" },
];

export const LINK_CODA_GRUPPO = "/catena/fatture?tab=collocare";
export const LINK_ANALISI_SPESA = "/catena/analisi?tab=spesa";
export const LINK_ANALISI_MARGINI = "/catena/analisi?tab=margini";

/**
 * La scheda da mostrare per il `?tab=` richiesto. Un valore sconosciuto (link
 * vecchio, refuso) ricade sulla predefinita invece di rendere la pagina senza
 * corpo — lo stesso difetto che `risolviTab` ha chiuso sulle pagine del PV.
 */
export function risolviScheda(
  schede: readonly TabDef[],
  richiesta: string | null | undefined,
  predefinita: string = schede[0].key,
): string {
  if (schede.some((s) => s.key === richiesta)) return richiesta as string;
  return schede.some((s) => s.key === predefinita) ? predefinita : schede[0].key;
}

/**
 * Le schede di Gestione Fatture visibili a questo account, con il conteggio
 * della coda sull'etichetta.
 *
 * «Scadenze» e' lo scadenziario, una pagina che l'admin puo' spegnere
 * (`pagine_abilitate`, flag `scadenziario`): spenta quella, sparisce solo la
 * sua scheda. Coda e costi di gruppo prima stavano nella Home di catena, che
 * non ha interruttore: legarli al flag dello scadenziario li avrebbe tolti a
 * chi li usava. `pagine` null = admin / nessuna restrizione.
 *
 * Il numero sulla scheda: da quando la coda non sta piu' in Home e' il segnale
 * visibile, in questa pagina, che ci sono fatture da collocare. `null` =
 * conteggio non letto (worker giu'): niente numero, non uno zero inventato.
 */
export function schedeFattureCatena(
  daCollocare: number | null | undefined,
  pagine: string[] | null | undefined,
): TabDef[] {
  const scadenziario = pagine == null || pagine.includes("scadenziario");
  return SCHEDE_FATTURE_CATENA.filter((s) => s.key !== "scadenze" || scadenziario).map((s) =>
    s.key === "collocare" && daCollocare != null && daCollocare > 0
      ? { ...s, label: `${s.label} (${daCollocare})` }
      : { ...s },
  );
}
