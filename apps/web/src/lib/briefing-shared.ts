// Se una card del briefing puo' mostrare "Ignora".
//
// La verita' la decide il BACKEND e viaggia nel campo `dismissible` dell'azione
// (services/daily_briefing_service.py::_action_for, lista canonica
// TOPIC_LIVE_NON_IGNORABILI): un topic ricalcolato live sparisce da solo quando
// inserisci il dato e torna al refresh finche' manca, quindi offrire "Ignora"
// sarebbe ingannevole.
//
// Prima questa lista viveva QUI, duplicata a mano, e il 2/9/2026 era gia'
// divergente dal backend: le mancava `coperti_anomalia`, che infatti mostrava un
// "Ignora" che non ignorava (la card tornava al refresh successivo). Ora resta
// solo come fallback per gli snapshot messi in cache PRIMA del campo nuovo: quelli
// hanno un briefing senza `dismissible`, e vivono al massimo quanto il TTL.
const NON_IGNORABILI_LEGACY = new Set<string>([
  "fatturato_mancante",
  "costo_personale_mancante",
  "incasso_mancante",
  "fatture_mancanti",
  "uncategorized_rows",
  "coperti_anomalia",
]);

export function puoIgnorare(azione: {
  topic_key: string;
  dismissible?: boolean;
}): boolean {
  if (typeof azione.dismissible === "boolean") return azione.dismissible;
  return !NON_IGNORABILI_LEGACY.has(azione.topic_key);
}
