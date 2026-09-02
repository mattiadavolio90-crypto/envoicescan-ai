import { cache } from "react";
import { WORKER_URL, WORKER_TIMEOUT_MS, getToken, workerHeaders } from "./worker-config";

// Il tipo e' definito in notifiche-shared.ts (modulo puro, senza worker-config)
// e ri-esportato qui perche' e' da "@/lib/notifiche" che lo importano le pagine.
import { type Notifica } from "./notifiche-shared";
export { type Notifica };

export type NotificheResponse = {
  notifiche: Notifica[];
  total: number;
  unread: number;
};

// cache(): nello stesso render il layout (badge header) e la dashboard
// (count widget) chiamano entrambi fetchNotifiche() -> un solo round-trip al
// worker, niente doppia lettura. Default (senza dismissed) condiviso.
export const fetchNotifiche = cache(
  async (includeDismissed = false): Promise<NotificheResponse | null> => {
    const token = await getToken();
    if (!token) return null;

    try {
      const url = `${WORKER_URL}/api/notifiche${includeDismissed ? "?include_dismissed=true" : ""}`;
      const res = await fetch(url, {
        headers: workerHeaders(token),
        cache: "no-store",
        signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
      });
      if (!res.ok) return null;
      return (await res.json()) as NotificheResponse;
    } catch {
      return null;
    }
  },
);

// Somma il carico di un topic dalle notifiche attive. Usato dai trigger
// contestuali per leggere segnali GIA' calcolati dal worker (es.
// uncategorized_rows, price_alert) senza query nuove: fetchNotifiche e' gia'
// cache()-ata, quindi nello stesso render non aggiunge round-trip.
// Restituisce 0 se non disponibile (mai throw): un segnale assente = niente
// trigger, che e' il fallback corretto.
//
// `totale` PRIMA di `count` (02/09/2026): da quando la card "da controllare"
// mostra solo le NOVITA' degli ultimi giorni, `count` non e' piu' il carico
// complessivo — il totale sta in `totale` e l'arretrato in `arretrato`. I
// trigger devono guardare il carico VERO: una sede con 112 prodotti sospesi da
// luglio (0 novita') e' esattamente il profilo per cui il trigger Check-up
// esiste, e leggendo `count` sarebbe passata a 0 spegnendolo. I topic che non
// hanno `totale` continuano a cadere su `count` come prima.
export async function contaTopicAttivo(topicKey: string): Promise<number> {
  const res = await fetchNotifiche();
  if (!res) return 0;
  let totale = 0;
  for (const n of res.notifiche) {
    if (n.topic_key !== topicKey) continue;
    const p = n.payload ?? {};
    const raw =
      (p.totale as number | undefined) ??
      (p.count as number | undefined) ??
      (p.uncategorized_rows as number | undefined) ??
      parseCountFromTitle(n.title);
    if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) totale += raw;
  }
  return totale;
}

// Estrae il numero tra parentesi da titoli come "Scadenze superate (300)".
// Allineato a _parse_count_from_title del worker (fallback quando il payload
// non porta il conteggio).
function parseCountFromTitle(title: string): number | undefined {
  const m = /\((\d+)\)/.exec(title);
  return m ? Number(m[1]) : undefined;
}
