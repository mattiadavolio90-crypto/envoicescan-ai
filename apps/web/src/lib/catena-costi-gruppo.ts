// Quello che le finestre di catena MANDANO al backend — estratto da
// `(app)/catena/finestra-costi-gruppo.tsx` e `config-assistente-catena.tsx`.
//
// I due file stanno nello stesso modulo per una ragione di dominio, non di
// comodita': sono le due schermate dell'area che scrivono. Un errore nelle
// funzioni di `catena-tag.ts` sbaglia dei pixel; un errore qui persiste — un
// importo scritto storto, o dei punti vendita riattivati che l'utente aveva
// escluso. Chi apre questo file deve saperlo dalla prima riga.
//
// Copiate byte per byte dai .tsx, SENZA correzioni: il test fotografa, non
// sistema. Le anomalie sono annotate una per una col loro perche'.

/* ─── finestra-costi-gruppo.tsx: il costo manuale che si scrive ──────────── */

/**
 * Importo digitato a mano nel dialog "Aggiungi costo".
 *
 * ANOMALIA FOTOGRAFATA: il `replace` NON e' globale, quindi sostituisce solo la
 * PRIMA virgola e non tocca i punti. "1.234,56" diventa "1..234.56" -> NaN.
 * L'utente che scrive il separatore delle migliaia si vede rifiutare un importo
 * valido con il messaggio "Inserisci descrizione, importo e categoria", che non
 * dice cosa sia andato storto davvero.
 *
 * Non si corregge qui: lo stesso pattern esiste in ~25 punti dell'app
 * (carica-ricavi-dialog, margini/calcolo-tab, config-assistente...). Sistemarlo
 * in un punto solo creerebbe due comportamenti diversi per lo stesso input a
 * seconda della schermata. E' una dimensione a se', con la sua finestra di
 * deploy.
 *
 * Il danno e' comunque contenuto da `importoValido`: il NaN viene respinto e non
 * arriva al backend. E' un errore di messaggio, non di dato — ed e' il motivo
 * per cui la severita' non e' alta.
 */
export function parseImportoManuale(testo: string): number {
  return Number(testo.replace(",", "."));
}

/**
 * L'importo e' accettabile.
 *
 * Scritto come `imp > 0` e usato negato: `!(imp > 0)` e' VOLUTO e cattura anche
 * `NaN`, perche' ogni confronto con NaN e' false. La riscrittura "equivalente"
 * `imp <= 0` lascerebbe passare il NaN di `parseImportoManuale` fino al POST.
 * Provato per mutazione: e' la differenza fra respingere e scrivere spazzatura.
 */
export function importoValido(imp: number): boolean {
  return imp > 0;
}

/** I tre campi obbligatori del costo manuale sono compilati. */
export function datiCostoValidi(descrizione: string, imp: number, categoria: string): boolean {
  return Boolean(descrizione.trim()) && importoValido(imp) && Boolean(categoria);
}

/* ─── L'avviso "quote non classificate" ─────────────────────────────────── */

/** L'avviso ambra si mostra solo se c'e' un importo non classificato. */
export function mostraAvvisoDaClassificare(importo: number | null | undefined): boolean {
  return (importo ?? 0) > 0;
}

/**
 * Frammento " (3 costi)" accanto all'importo, vuoto se il conteggio manca o e'
 * zero. Il markup resta nel .tsx: qui si decide solo il testo.
 */
export function frammentoConteggioCosti(n: number | null | undefined): string {
  if ((n ?? 0) <= 0) return "";
  return ` (${n} ${n === 1 ? "costo" : "costi"})`;
}

/**
 * Frase sui costi che non si possono correggere dal dettaglio righe, o `null`
 * se non ce ne sono. Va dentro uno <strong> nel .tsx.
 *
 * Il confronto `nonCorreggibili === costi` distingue "nessuno di questi costi ha
 * righe" da "N di questi non ce le hanno": e' raggiungibile solo dopo la guardia
 * `> 0`, quindi due `undefined` non possono farlo scattare a vuoto.
 */
export function frammentoNonCorreggibili(
  nonCorreggibili: number | null | undefined,
  costi: number | null | undefined,
): string | null {
  if ((nonCorreggibili ?? 0) <= 0) return null;
  if (nonCorreggibili === costi) return "Nessuno di questi costi ha righe";
  return `${nonCorreggibili} di questi costi ${
    nonCorreggibili === 1 ? "non ha righe" : "non hanno righe"
  }`;
}

/* ─── L'esito della correzione di categoria ─────────────────────────────── */

export type EsitoCorrezione = { tipo: "warning" | "success"; messaggio: string };

/**
 * Cosa dire dopo aver corretto la categoria di una riga.
 *
 * `=== false` e' VOLUTO e non va semplificato in `!ricalcolo_quote_ok`: il campo
 * assente (`undefined`) significa "risposta di un backend precedente", non
 * "ricalcolo fallito". Con `!` ogni vecchia risposta farebbe comparire un
 * allarme che non c'e'.
 *
 * ANOMALIA FOTOGRAFATA: `join(" e ")` su tre o piu' sedi produce italiano
 * sgrammaticato — "vale per A e B e C". Cosmetico, ma e' cio' che il cliente
 * legge. Non corretto qui perche' e' un cambio di testo visibile.
 *
 * Nota: le due rotte che rispondono `sedi_impattate` non filtrano allo stesso
 * modo — `riparto.py:275` scarta i nomi vuoti, `:697` no. Da quella seconda puo'
 * arrivare un `null` in lista, che finirebbe nel messaggio come "A e ".
 */
export function esitoCorrezioneCategoria(
  risposta: { ricalcolo_quote_ok?: boolean | null; sedi_impattate?: string[] | null },
): EsitoCorrezione {
  if (risposta.ricalcolo_quote_ok === false) {
    return {
      tipo: "warning",
      messaggio: "Categoria aggiornata, ma il ricalcolo delle quote non è riuscito. Riprova più tardi.",
    };
  }
  const sedi: string[] = risposta.sedi_impattate ?? [];
  return {
    tipo: "success",
    messaggio: sedi.length ? `Categoria aggiornata · vale per ${sedi.join(" e ")}` : "Categoria aggiornata",
  };
}

/* ─── config-assistente-catena.tsx: cosa si esclude ─────────────────────── */

/**
 * Le chiavi dei segnali DISATTIVATI, cioe' l'inverso di cio' che si vede spuntato.
 *
 * ANOMALIA FOTOGRAFATA (la piu' seria dell'area): l'inversione rende il caso
 * "lista vuota" ambiguo. Una lista vuota significa "l'utente non ha escluso
 * niente" per il backend, ma nel frontend e' anche lo stato INIZIALE, quello in
 * cui si resta se il load fallisce. Salvare in quel momento riattiva in silenzio
 * tutto cio' che l'utente aveva escluso.
 *
 * Oggi l'unica difesa e' il `disabled` del pulsante Salva (riga 194 del .tsx):
 * una guardia di INTERFACCIA su una regola di DATI. Non e' stata spostata qui in
 * questa passata perche' chiuderla cambia il comportamento — con un backend che
 * risponde `200 {}` il Salva oggi e' abilitato e domani non lo sarebbe. Il test
 * `test_fotografa_liste_vuote_producono_liste_vuote` tiene il buco visibile e
 * sara' il punto d'aggancio del fix.
 */
export function segnaliDisattivati(segnali: readonly { key: string; enabled: boolean }[]): string[] {
  return segnali.filter((s) => !s.enabled).map((s) => s.key);
}

/** Gli id dei punti vendita ESCLUSI. Stessa ambiguita' di `segnaliDisattivati`. */
export function pvEsclusi(pv: readonly { ristorante_id: string; incluso: boolean }[]): string[] {
  return pv.filter((p) => !p.incluso).map((p) => p.ristorante_id);
}

/**
 * Applica una modifica all'elemento che corrisponde, lasciando gli altri intatti
 * e senza mutare la lista in ingresso (e' uno stato React).
 *
 * Una funzione sola per i due toggle del .tsx, che avevano la stessa forma su
 * chiavi diverse (`key`/`enabled` e `ristorante_id`/`incluso`).
 */
export function applicaToggle<T>(
  lista: readonly T[],
  corrisponde: (x: T) => boolean,
  patch: Partial<T>,
): T[] {
  return lista.map((x) => (corrisponde(x) ? { ...x, ...patch } : x));
}
