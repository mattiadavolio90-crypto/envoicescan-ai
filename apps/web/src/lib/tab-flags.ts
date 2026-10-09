// Flag per-tab: l'admin puo' spegnere le singole tab dentro una sezione, non
// solo la sezione intera (che resta governata da `pagine_abilitate` + requirePagina).
//
// CONVENZIONE INVERSA (come TRIGGER_OFF_FLAG in trigger-servizi.ts, e per lo
// stesso motivo): la chiave e' PRESENTE quando la tab e' SPENTA. Assente = accesa.
// I flag arrivano al client come lista delle sole chiavi ATTIVE, quindi "assente"
// e "mai configurato" sono indistinguibili: con la convenzione diretta i clienti
// esistenti — che non hanno nessuna chiave tab — si vedrebbero sparire tutte le
// tab al primo deploy (e' il bug OFFSIDE, un piano piu' in basso).
//
// Questo modulo e' l'unica fonte: sia gli switcher (rendering) sia il pannello
// admin (toggle) leggono TAB_SEZIONI da qui. Il worker riconosce le chiavi dal
// PREFISSO (`_is_tab_off_key` in fastapi_worker.py), non da un elenco duplicato,
// cosi' aggiungere una tab qui non richiede una modifica gemella in Python.
//
// NOTA per chi estende: TAB_SEZIONI e' indicizzata per chiave-PAGINA (le 7 di
// _PAGINE_FLAG). Il mobile (/m) ha tab proprie su un dominio diverso — se un
// giorno serviranno anche li', va una seconda mappa, non un allargamento di questa.

export type SezioneConTab =
  | "analisi_fatture"
  | "prezzi"
  | "margini"
  | "agenda"
  | "workspace"
  | "scadenziario";

export type TabDef = { key: string; label: string };

// L'ORDINE conta: definisce sia il rendering sia quale sia la "prima tab attiva"
// su cui ricade chi apre una tab spenta. Il primo elemento di ogni sezione e' il
// default storico della pagina (articoli/variazioni/calcolo/tutto/foodcost/agenda).
// `analisi_e_tag` non compare: e' pagina unica, non ha tab.
export const TAB_SEZIONI: Record<SezioneConTab, readonly TabDef[]> = {
  analisi_fatture: [
    { key: "articoli", label: "Articoli" },
    { key: "categorie", label: "Categorie" },
    { key: "fornitori", label: "Fornitori" },
  ],
  prezzi: [
    { key: "variazioni", label: "Variazioni Prezzo" },
    { key: "sconti", label: "Sconti e Omaggi" },
    { key: "nc", label: "Note di Credito" },
    { key: "score", label: "Score Fornitori" },
  ],
  margini: [
    { key: "calcolo", label: "Marginalità" },
    { key: "coperti", label: "Coperti" },
    { key: "analisi", label: "Analisi Avanzate" },
  ],
  // «Calendario» ha chiave `tutto`: si chiamava cosi' fino al 09/10/2026, quando
  // ha assorbito la scheda «Appuntamenti» (Mattia, fase H2). La chiave resta
  // per non cambiare i link salvati e gli eventuali `tab_off_agenda_tutto`.
  agenda: [
    { key: "tutto", label: "Calendario" },
    { key: "spese", label: "Spese" },
    { key: "personale", label: "Personale" },
  ],
  workspace: [
    { key: "foodcost", label: "Foodcost" },
    { key: "inventario", label: "Inventario" },
  ],
  // La vista «Scadenzario» ha chiave tecnica `agenda` per ragioni storiche (si
  // chiamava «Lista» fino al 22/09/2026, «Da pagare» fino al 09/10/2026): e' il
  // valore del type View in scadenziario-client.tsx e di `users.vista_fatture`,
  // non un refuso. Archivio prima (Mattia, 09/10): e' anche la vista d'apertura.
  scadenziario: [
    { key: "lista_mensile", label: "Archivio fatture" },
    { key: "agenda", label: "Scadenzario" },
    { key: "calendario", label: "Calendario" },
  ],
};

export const TAB_OFF_PREFIX = "tab_off_";

// Unica fonte del formato chiave. Il worker valida lo stesso formato per
// prefisso: se cambia qui va cambiato anche in fastapi_worker.py, ed e' quello
// che il test di coerenza TS<->Python presidia.
export function tabOffKey(sezione: SezioneConTab, tab: string): string {
  return `${TAB_OFF_PREFIX}${sezione}_${tab}`;
}

// `pagine` e' SessionUser.pagine_abilitate: null = admin / nessuna restrizione.
export function tabAbilitata(
  pagine: string[] | null | undefined,
  sezione: SezioneConTab,
  tab: string,
): boolean {
  if (pagine == null) return true;
  return !pagine.includes(tabOffKey(sezione, tab));
}

export function tabAttive(
  pagine: string[] | null | undefined,
  sezione: SezioneConTab,
): TabDef[] {
  return TAB_SEZIONI[sezione].filter((t) => tabAbilitata(pagine, sezione, t.key));
}

/**
 * Le viste di Gestione Fatture nell'ordine delle schede, ristrette a quelle
 * che l'admin consente. L'ordine e' quello di TAB_SEZIONI: Archivio prima.
 */
export function visteFattureOrdinate(attive: readonly string[]): string[] {
  return TAB_SEZIONI.scadenziario.map((t) => t.key).filter((k) => attive.includes(k));
}

/**
 * La vista su cui si apre Gestione Fatture. In ordine: quella chiesta dal link
 * (`?vista=`, gli avvisi sulle scadenze aprono lo Scadenzario anche a chi ha
 * salvato Archivio), quella salvata sull'account (`users.vista_fatture`), la
 * prima consentita. Ognuna vale solo se consentita: con una vista spenta
 * dall'admin il cliente non deve restare su una pagina vuota senza il bottone
 * per uscirne. `null` = tutte spente.
 */
export function vistaFattureIniziale(
  attive: readonly string[],
  salvata: string | null | undefined,
  richiesta?: string | null,
): string | null {
  const consentite = visteFattureOrdinate(attive);
  if (richiesta != null && consentite.includes(richiesta)) return richiesta;
  if (salvata != null && consentite.includes(salvata)) return salvata;
  return consentite[0] ?? null;
}

// null se sono tutte spente: il chiamante decide (le pagine fanno notFound()).
export function primaTabAttiva(
  pagine: string[] | null | undefined,
  sezione: SezioneConTab,
): string | null {
  return tabAttive(pagine, sezione)[0]?.key ?? null;
}

export function sezioneHaTabAttive(
  pagine: string[] | null | undefined,
  sezione: string,
): boolean {
  if (!(sezione in TAB_SEZIONI)) return true; // sezione senza tab (analisi_e_tag): sempre visibile
  return primaTabAttiva(pagine, sezione as SezioneConTab) != null;
}

/**
 * Quale tab mostrare, dato cio' che l'utente ha chiesto in URL.
 *
 * Unifica tre cose che prima erano sparse e incoerenti: il default della tab,
 * la validazione del parametro (esisteva SOLO in workspace/page.tsx) e la
 * ricaduta su una tab consentita. Prima di questo, `?tab=pippo` su
 * /analisi-fatture renderizzava header e filtri con il corpo vuoto.
 *
 * Idempotente: risolviTab(p, s, risolviTab(p, s, x)) === risolviTab(p, s, x).
 * Ci si appoggia il guard per non entrare in un ciclo di redirect.
 */
export function risolviTab(
  pagine: string[] | null | undefined,
  sezione: SezioneConTab,
  richiesta: string | null | undefined,
): string | null {
  const nota = TAB_SEZIONI[sezione].some((t) => t.key === richiesta);
  const voluta = nota ? (richiesta as string) : TAB_SEZIONI[sezione][0].key;
  if (tabAbilitata(pagine, sezione, voluta)) return voluta;
  return primaTabAttiva(pagine, sezione);
}
