// Schede delle due pagine di lavoro della catena (decisione Mattia 28/9): la
// Home della catena resta solo recap e assistenza, le funzioni che ci stavano
// come finestre diventano schede di pagina.
//
// Separate da TAB_SEZIONI (lib/tab-flags) di proposito: quella mappa e'
// indicizzata per pagina del PUNTO VENDITA. In catena non c'e' un interruttore
// di pagina: l'admin spegne le SCHEDE (fase H3, Mattia 09/10/2026) con chiavi
// `tab_off_catena_<scheda>`, stessa convenzione inversa dei `tab_off_*` del PV
// (chiave presente = spenta), riconosciute dal worker in `_is_tab_off_key`.

import { TAB_OFF_PREFIX, type TabDef } from "@/lib/tab-flags";

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

// Non e' una scheda: spegne le colonne dei coperti (e lo spreco per coperto)
// nella scheda dei margini, che senza coperti si chiama «Margini». Per chi non
// registra i coperti (OFFSIDE): spegnere la scheda intera toglierebbe anche i
// margini del gruppo (Mattia, 09/10/2026).
export const COPERTI_CATENA = "coperti";

/** Gli interruttori della catena nel pannello admin, nell'ordine delle pagine. */
export const INTERRUTTORI_CATENA: readonly { pagina: string; voci: readonly TabDef[] }[] = [
  { pagina: "Gestione Fatture", voci: SCHEDE_FATTURE_CATENA },
  { pagina: "Analisi catena", voci: SCHEDE_ANALISI_CATENA },
  { pagina: "Margini", voci: [{ key: COPERTI_CATENA, label: "Colonne dei coperti" }] },
];

export function tabOffKeyCatena(scheda: string): string {
  return `${TAB_OFF_PREFIX}catena_${scheda}`;
}

/** `pagine` null = admin / nessuna restrizione: tutto acceso. */
export function schedaCatenaAccesa(pagine: string[] | null | undefined, scheda: string): boolean {
  return pagine == null || !pagine.includes(tabOffKeyCatena(scheda));
}

export function copertiCatenaAccesi(pagine: string[] | null | undefined): boolean {
  return schedaCatenaAccesa(pagine, COPERTI_CATENA);
}

// Le colonne della tabella dei margini di catena che senza coperti non hanno
// senso: tutte e tre si dividono per i coperti, o li contano.
export const COLONNE_COPERTI_CATENA: readonly string[] = ["coperti", "scontrino_medio", "mp_per_coperto"];

export function colonneMarginiCatena<T extends { key: string }>(colonne: readonly T[], coperti: boolean): T[] {
  return coperti ? [...colonne] : colonne.filter((c) => !COLONNE_COPERTI_CATENA.includes(c.key));
}

/** Le schede di Analisi catena accese per questo account. Senza coperti la
 *  scheda dei margini si chiama «Margini». Vuota = pagina senza schede (404). */
export function schedeAnalisiCatena(pagine: string[] | null | undefined): TabDef[] {
  const coperti = copertiCatenaAccesi(pagine);
  return SCHEDE_ANALISI_CATENA.filter((s) => schedaCatenaAccesa(pagine, s.key)).map((s) =>
    s.key === "margini" && !coperti ? { ...s, label: "Margini" } : { ...s },
  );
}

/**
 * Dove porta un link della Home di catena verso una scheda di Analisi: la
 * scheda chiesta se accesa, altrimenti la prima accesa, altrimenti `null`
 * (niente link: un clic verso una pagina 404 e' peggio di nessun clic).
 */
export function linkAnalisiCatena(pagine: string[] | null | undefined, scheda: string): string | null {
  const schede = schedeAnalisiCatena(pagine);
  if (schede.length === 0) return null;
  return `/catena/analisi?tab=${risolviScheda(schede, scheda, scheda)}`;
}

/**
 * Dove porta «Vedi quali PV» (dati di costo incompleti): solo alla scheda
 * Margini, che li marca «Incompleto». Con la scheda spenta nessun link: «Spesa per
 * PV» non li mostra, e il clic porterebbe a una pagina che non risponde alla frase.
 */
export function linkMarginiIncompleti(pagine: string[] | null | undefined): string | null {
  return schedaCatenaAccesa(pagine, "margini") ? linkAnalisiCatena(pagine, "margini") : null;
}

export const LINK_CODA_GRUPPO = "/catena/fatture?tab=collocare";

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
  return SCHEDE_FATTURE_CATENA.filter(
    (s) => (s.key !== "scadenze" || scadenziario) && schedaCatenaAccesa(pagine, s.key),
  ).map((s) =>
    s.key === "collocare" && daCollocare != null && daCollocare > 0
      ? { ...s, label: `${s.label} (${daCollocare})` }
      : { ...s },
  );
}
