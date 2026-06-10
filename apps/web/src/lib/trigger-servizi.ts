// Trigger soft dei Servizi: suggerimenti contestuali, discreti e RARI che
// rimandano alla card giusta di /assistenza quando in pagina c'e' un segnale
// reale (food cost alto, prezzi in aumento, righe da classificare...).
//
// FILOSOFIA (non negoziabile, vedi PAGINA_SERVIZI_MARKETING.md):
//  - mai popup, mai bloccante: un banner leggero in fondo alla pagina;
//  - MASSIMO 1 trigger per pagina;
//  - si mostra SOLO se il segnale e' reale (niente "vendi sempre");
//  - dismissibile e ricordato: se l'utente lo chiude non torna subito;
//  - canale SEPARATO da briefing/notifiche operative (quelle restano pulite).
//
// Questo file e' l'UNICA fonte di verita': mappa trigger -> servizio + valuta
// se mostrarlo. Il gating "segnale reale" lo fa la pagina che passa i dati;
// qui decidiamo solo SE e QUALE, e al massimo uno.

import type { Servizio } from "@/lib/assistenza";

// Le quattro chiavi triggerabili. Le card 5-6 (partner/Recoma) NON si triggerano
// mai: sono fuori dal core dell'app. Union type: un refuso e' errore a
// compile-time.
export type TriggerKey = "checkup" | "consulenza" | "assistenza" | "analisi";

// Pagine dove un trigger puo' comparire. Stringa = flag pagina / route, cosi'
// la valutazione e' per-pagina e "1 per pagina" e' garantito dal chiamante.
export type TriggerPagina = "analisi-fatture" | "margini" | "prezzi";

// Segnali che la pagina passa al valutatore. Tutti OPZIONALI e gia' calcolati
// altrove (KPI Home, conteggi notifiche): qui non si calcola nulla di pesante.
// Un campo assente = "non lo so", quindi il trigger relativo non scatta.
export type TriggerSignals = {
  // Check-up: dati incompleti / gestione poco monitorata.
  righeDaClassificare?: number; // uncategorized_rows
  fattureTotali?: number; // poche fatture recenti -> dati magri
  // Consulenza: i numeri peggiorano.
  foodCostPct?: number | null; // % food cost del periodo
  foodCostSoglia?: number; // soglia oltre cui e' "alto" (default sotto)
  molNegativo?: boolean; // MOL sotto zero nel periodo
  // Analisi: c'e' una criticita' puntuale da approfondire.
  alertPrezziAttivi?: number; // numero prodotti/categorie in aumento
};

export type TriggerDef = {
  key: TriggerKey;
  // Chiave del servizio in SERVIZI (1:1 con Servizio.key): il deep-link
  // /assistenza?servizio=<servizioKey> evidenzia e apre quella card.
  servizioKey: Servizio["key"];
  // Messaggio mostrato nel banner: tono ONEFLUX, mai da agenzia.
  messaggio: string;
  // Etichetta del bottone che porta al servizio.
  cta: string;
};

// Definizioni statiche: il copy vive qui, allineato al tono delle card.
export const TRIGGERS: Record<TriggerKey, TriggerDef> = {
  checkup: {
    key: "checkup",
    servizioKey: "checkup_operativo",
    messaggio:
      "Vuoi un check-up rapido dei tuoi dati per capire cosa manca e cosa controllare subito?",
    cta: "Scopri il Check-up",
  },
  consulenza: {
    key: "consulenza",
    servizioKey: "consulenza_gestionale",
    messaggio:
      "I tuoi numeri stanno cambiando: vuoi una lettura piu' approfondita per capire dove intervenire?",
    cta: "Scopri la Consulenza",
  },
  assistenza: {
    key: "assistenza",
    servizioKey: "assistenza_continuativa",
    messaggio:
      "Se preferisci, possiamo gestire noi l'app e i dati al posto tuo.",
    cta: "Scopri l'Assistenza",
  },
  analisi: {
    key: "analisi",
    servizioKey: "analisi_su_richiesta",
    messaggio:
      "Hai un dubbio preciso? Possiamo prepararti un'analisi scritta sui tuoi numeri o sul mercato.",
    cta: "Richiedi un'analisi",
  },
};

// Soglia food cost di default oltre cui consideriamo "alto" il costo: usata solo
// se la pagina non passa una soglia propria. 38% e' un riferimento prudente per
// la ristorazione; resta sovrascrivibile dai dati reali del cliente.
const FOOD_COST_SOGLIA_DEFAULT = 38;

// Sotto questa quantita' di fatture i dati sono troppo magri per analisi serie:
// e' il caso d'uso del Check-up ("dati incompleti / poche fatture recenti").
const POCHE_FATTURE = 5;

// Quante righe da classificare bastano a giustificare un Check-up. Tenuta alta
// di proposito: il trigger deve essere RARO, non scattare al primo refuso.
const SOGLIA_RIGHE_DA_CLASSIFICARE = 15;

// Valuta i trigger possibili in una pagina e ne restituisce AL MASSIMO UNO
// (il piu' pertinente), o null. Pura e testabile: nessun effetto collaterale,
// nessuna lettura di stato. La regola "1 per pagina" e' garantita qui.
//
// Ordine di precedenza dentro la stessa pagina: si sceglie il segnale piu' forte
// e specifico. In /margini, una perdita (MOL negativo) batte un food cost alto;
// l'Assistenza ("facciamo noi") e' l'ultima spiaggia, la piu' soft.
export function valutaTrigger(
  pagina: TriggerPagina,
  signals: TriggerSignals,
): TriggerDef | null {
  if (pagina === "analisi-fatture") {
    const righe = signals.righeDaClassificare ?? 0;
    const fatture = signals.fattureTotali;
    const datiMagri =
      righe >= SOGLIA_RIGHE_DA_CLASSIFICARE ||
      (fatture !== undefined && fatture > 0 && fatture <= POCHE_FATTURE);
    return datiMagri ? TRIGGERS.checkup : null;
  }

  if (pagina === "prezzi") {
    const alert = signals.alertPrezziAttivi ?? 0;
    return alert > 0 ? TRIGGERS.analisi : null;
  }

  if (pagina === "margini") {
    // 1) MOL negativo = segnale piu' forte: si offre una lettura approfondita.
    if (signals.molNegativo) return TRIGGERS.consulenza;
    // 2) Food cost oltre soglia = i numeri stanno cambiando -> Consulenza.
    const fc = signals.foodCostPct;
    const soglia = signals.foodCostSoglia ?? FOOD_COST_SOGLIA_DEFAULT;
    if (fc != null && fc > soglia) return TRIGGERS.consulenza;
    // 3) Nessun segnale forte: niente trigger qui. L'Assistenza ("facciamo
    //    noi") resta volutamente RARA e non si forza su un margine sano.
    return null;
  }

  return null;
}
