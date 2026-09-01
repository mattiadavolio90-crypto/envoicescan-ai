// Logica del tag di gruppo — estratta da `(app)/catena/gruppo-tag-section.tsx`.
//
// Stessa ragione di `catena-confronti.ts`: finche' queste espressioni stavano
// dentro un componente di 721 righe, fra hook e JSX, `tests/helpers_ts.py` non
// poteva raggiungerle. Qui l'esposizione non e' astratta: catena/ aggrega i punti
// vendita dei 2 account piu' grandi del parco.
//
// Copiate byte per byte dai .tsx, SENZA correzioni. Se una si comporta in modo
// sorprendente e' perche' si comportava gia' cosi' in produzione: il test la
// fotografa, non la sistema. Le anomalie sono annotate una per una qui sotto.
//
// Attenzione al rischio specifico di questa estrazione: quasi tutte queste
// funzioni producono stringhe che finiscono in uno `style` o in un `className`.
// Un "miglioramento" scritto mentre si copia (un Math.round che prima non c'era)
// passa tsc, passa i test scritti dopo sul codice gia' estratto, e arriva in
// produzione. Le formule qui sono quelle originali, non quelle giuste.

// `import type` (non `import { type ... }`): la forma type-only sparisce del
// tutto allo strip dei tipi, mentre l'altra lascia in piedi la import statement
// e node andrebbe a caricare lib/gruppo.ts -> ./worker, un import relativo che
// il resolve hook di helpers_ts.py non riscrive. Verificato: rompe l'harness.
import type { GruppoTagAnalisi, TagAnalisiPV, TagFornitore } from "@/lib/gruppo";
// Ri-usata, non ri-dichiarata: il commento di MIN_VALORI_CONFRONTO elenca i 5
// posti dove la soglia "servono almeno 2 valori per confrontare" ricorre, e
// tag-section era uno di quelli col letterale. Verificato che l'harness risolve
// l'import incrociato fra due moduli lib/ sotto test.
import { MIN_VALORI_CONFRONTO } from "@/lib/catena-confronti";

/* ─── Estremi di prezzo e colore della cella ─────────────────────────────── */

export type EstremiPrezzo = { minPrezzo: number | null; maxPrezzo: number | null };

/**
 * Prezzo minimo e massimo fra i PV che hanno il dato, per evidenziare chi paga
 * meno (verde) e chi di piu' (rosso).
 *
 * Sotto `MIN_VALORI_CONFRONTO` prezzi entrambi `null`: con un solo PV il
 * confronto non esiste e l'evidenza sarebbe rumore. I `null` si scartano PRIMA
 * di contare, quindi 3 PV di cui 2 senza prezzo non superano la soglia.
 */
export function estremiPrezzo(
  perPv: readonly Pick<TagAnalisiPV, "prezzo_medio">[] | null | undefined,
): EstremiPrezzo {
  const prezzi = (perPv ?? []).map((p) => p.prezzo_medio).filter((v): v is number => v != null);
  return {
    minPrezzo: prezzi.length >= MIN_VALORI_CONFRONTO ? Math.min(...prezzi) : null,
    maxPrezzo: prezzi.length >= MIN_VALORI_CONFRONTO ? Math.max(...prezzi) : null,
  };
}

export const CLASSE_PREZZO_MIN = "text-emerald-600 dark:text-emerald-500";
export const CLASSE_PREZZO_MAX = "text-rose-600 dark:text-rose-500";

/**
 * Classi Tailwind del prezzo medio di un PV. Restituisce la stringa gia'
 * concatenata; il `cn()` con le classi di base resta nel .tsx.
 *
 * ANOMALIA FOTOGRAFATA: quando tutti i PV con dato hanno lo STESSO prezzo,
 * min === max e la cella prende ENTRAMBE le classi — ogni PV e' insieme il piu'
 * economico e il piu' caro. `cellTone` in catena-confronti.ts risolve lo stesso
 * problema 15 righe piu' in la' con la guardia `v !== ex.worst`; qui la guardia
 * non c'e' mai stata. Non si aggiunge in questa passata: cambierebbe cio' che si
 * vede a schermo, e un cambio di comportamento vuole la sua finestra di deploy.
 * A schermo vince il rosso (tailwind-merge tiene l'ultima), quindi oggi un
 * gruppo a prezzo uniforme si mostra tutto "caro".
 */
export function classePrezzo(
  prezzo: number | null,
  minPrezzo: number | null,
  maxPrezzo: number | null,
): string {
  const classi: string[] = [];
  if (prezzo != null && prezzo === minPrezzo) classi.push(CLASSE_PREZZO_MIN);
  if (prezzo != null && prezzo === maxPrezzo) classi.push(CLASSE_PREZZO_MAX);
  return classi.join(" ");
}

/* ─── Barre proporzionali ────────────────────────────────────────────────── */

/**
 * Larghezza della barra spesa, come percentuale del massimo di colonna.
 *
 * ANOMALIA FOTOGRAFATA: `spesa` e' netta delle note di credito (gruppo.py:2233
 * lo dice esplicitamente) e puo' essere negativa. Con un valore negativo esce
 * "-30%", che il browser tratta come larghezza 0: la riga c'e' ma la barra
 * sparisce, senza distinguersi da una spesa nulla.
 */
export function larghezzaBarra(v: number, max: number): string {
  return max > 0 ? `${(v / max) * 100}%` : "0%";
}

/**
 * Altezza della barra nel trend mensile. Divergente da `larghezzaBarra` per il
 * pavimento a 4%, che esiste perche' un mese a spesa quasi nulla resti visibile
 * come colonnina invece di sparire.
 *
 * ANOMALIA FOTOGRAFATA: il pavimento si applica anche ai valori NEGATIVI, che
 * `Math.max(4, ...)` alza a 4%. Un mese chiuso in negativo (nota di credito piu'
 * grande degli acquisti) si disegna quindi come una barra positiva bassa,
 * indistinguibile da un mese di spesa minima. Le due formule restano due
 * funzioni distinte: unificarle cambierebbe i pixel di una delle due.
 */
export function altezzaBarraTrend(v: number, max: number): string {
  return max > 0 ? `${Math.max(4, (v / max) * 100)}%` : "0%";
}

/**
 * Massimo di una colonna di spesa, con pavimento a 0.
 *
 * Lo `0` iniziale di `Math.max` fa due cose che non si vedono con dati positivi:
 * su lista vuota evita `-Infinity` (che finirebbe in uno `style` come
 * "-Infinity%"), e su spese tutte negative restituisce 0 — un valore che non e'
 * nella lista. Il secondo caso e' reale: `spesa` e' netta delle note di credito.
 */
export function massimoSpesa(righe: readonly { spesa: number }[]): number {
  return Math.max(0, ...righe.map((r) => r.spesa));
}

/* ─── Stati vuoti e hint ─────────────────────────────────────────────────── */

/**
 * Il tag non ha niente da mostrare: nessun dato, o tutti i PV a spesa zero.
 *
 * L'uguaglianza `=== 0` su denaro e' esatta qui e non e' un caso fortunato:
 * `spesa` arriva gia' `round(spesa, 2)` dal worker (gruppo.py:2242), quindi un
 * residuo tipo 0.00000001 non puo' arrivare al client. E' pero' una proprieta'
 * del backend, non di questa funzione: se un domani la spesa arrivasse grezza,
 * un tag "vuoto" con un centesimo di residuo si direbbe pieno.
 *
 * Nota: un tag con SOLE note di credito ha spesa negativa, quindi non e' vuoto —
 * corretto, c'e' qualcosa da mostrare, ed e' il motivo per cui `=== 0` non va
 * riscritto in `<= 0`.
 */
export function analisiVuota(data: GruppoTagAnalisi | null | undefined): boolean {
  return !data || data.per_pv.every((p) => p.spesa === 0);
}

/**
 * Un solo PV ha spesa mentre gli altri sono a zero: le descrizioni del tag sono
 * di quella sede sola, e il confronto prezzi non ha con cosa confrontare.
 * Serve a proporre l'hint giusto ("aggiungi le varianti delle altre sedi")
 * invece di lasciare una tabella muta.
 */
export function soloUnPvConSpesa(perPv: readonly { spesa: number }[]): boolean {
  return perPv.filter((p) => p.spesa > 0).length === 1 && perPv.length > 1;
}

/* ─── Selezione dei candidati ────────────────────────────────────────────── */

/**
 * Tutti i candidati mostrati sono gia' selezionati.
 *
 * `selezionate` e' un parametro e non una closure di proposito: il .tsx la
 * chiama due volte con due stati DIVERSI e non intercambiabili — col valore del
 * render per l'etichetta del pulsante, e con `prev` dentro l'updater di
 * setState, dove il valore del render puo' essere gia' stantio. Passarle lo
 * stesso stato le farebbe divergere in modo invisibile.
 *
 * La guardia `length > 0` evita che `every` su lista vuota (che e' `true`) faccia
 * dire al pulsante "deseleziona tutti" quando non c'e' nulla da deselezionare.
 */
export function tuttiSelezionati(
  candidati: readonly { descrizione_key: string }[],
  selezionate: { has(k: string): boolean },
): boolean {
  return candidati.length > 0 && candidati.every((d) => selezionate.has(d.descrizione_key));
}

/* ─── Export Excel ───────────────────────────────────────────────────────── */

/**
 * Slug per il nome del file esportato. Il `|| ""` copre `periodo_label` assente.
 * Il secondo replace toglie i trattini in testa e in coda lasciati dal primo
 * quando la label inizia o finisce con punteggiatura.
 */
export function slugPeriodo(label: string | null | undefined): string {
  return (label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

/**
 * Nome del file .xlsx.
 *
 * ANOMALIA FOTOGRAFATA: lo slug del NOME del tag non ha il secondo replace che
 * ha quello del periodo, quindi un tag che finisce per punteggiatura ("Pesce!")
 * lascia un trattino appeso prima dell'underscore: "tag_pesce-_gennaio-2026".
 * Cosmetico, ma e' esattamente il tipo di divergenza che un test "contiene lo
 * slug" non vede e un assert sulla stringa intera si'.
 */
export function nomeFileExport(nome: string, periodoLabel: string | null | undefined): string {
  return `tag_${nome.toLowerCase().replace(/[^a-z0-9]+/g, "-")}_${slugPeriodo(periodoLabel)}.xlsx`;
}

/**
 * Righe del foglio "Per punto vendita". Le chiavi sono le intestazioni di
 * colonna che il cliente vede in Excel: rinominarne una e' un cambio visibile.
 */
export function righeExportPv(perPv: readonly TagAnalisiPV[]): Record<string, string | number>[] {
  return perPv.map((p) => ({
    "Punto vendita": p.nome,
    Spesa: Math.round(p.spesa * 100) / 100,
    "Incidenza %": `${p.incidenza_pct}%`,
    "Prezzo medio": p.prezzo_medio ?? "—",
    Quantità: p.quantita,
    Righe: p.n_righe,
    Fornitori: p.n_fornitori,
  }));
}

/** Righe del foglio "Fornitori". */
export function righeExportFornitori(
  fornitori: readonly TagFornitore[],
): Record<string, string | number>[] {
  return fornitori.map((f) => ({
    Fornitore: f.nome,
    Spesa: Math.round(f.spesa * 100) / 100,
    "Incidenza %": `${f.incidenza_pct}%`,
    Righe: f.n_righe,
  }));
}
