// Selezione dei candidati nella dialog "associa descrizioni a un tag" di catena.
//
// Estratta da gruppo-tag-section.tsx: era un useMemo anonimo dentro un
// componente di ~740 righe, quindi nessun test poteva raggiungerla. La regola
// che conta ("la saturazione si misura sulla risposta del server, non su cio'
// che resta dopo i filtri") viveva solo in un commento, ed e' esattamente la
// regola che il difetto F7 aveva violato.

// La RPC che alimenta la lista tronca a questo numero. Deve restare allineata a
// `p_limit` in routers/gruppo.py (che lo passa esplicitamente) e al DEFAULT
// della funzione SQL in supabase/migrations/*_gruppo_tag_descrizioni_search.sql:
// il 500 vive in tre posti indipendenti, questo non e' l'unico da toccare.
export const RPC_LIMITE_DESCRIZIONI = 500;

// Quante se ne mostrano in lista prima di troncare.
export const MAX_CANDIDATI_VISIBILI = 60;

// Sotto queste lettere non si interroga il server: si filtra solo il locale.
export const MIN_LETTERE_RICERCA = 2;

export type DescrizioneCandidata = {
  descrizione: string;
  descrizione_key: string;
};

export type EsitoCandidati<T> = {
  candidati: T[];
  nascosti: number;
  poolSaturo: boolean;
};

/**
 * `risposta` e' cio' che il SERVER ha mandato, NON filtrato: e' il primo
 * parametro apposta, perche' `poolSaturo` si misura su quello.
 *
 * Il difetto F7 era misurare la soglia dopo i filtri client: con 67
 * associazioni gia' fatte, 500 ricevute scendevano a 433 e la guardia non
 * scattava piu' — bastava una lettera digitata per far riapparire la cifra
 * falsa. `nascosti` invece si misura sul pool filtrato, perche' li' la domanda
 * e' "quanti ne restano fuori dalla lista che vedi".
 */
export function calcolaCandidati<T extends DescrizioneCandidata>(
  risposta: T[],
  giaAssociate: Set<string>,
  filtro: string,
  inRicerca: boolean,
): EsitoCandidati<T> {
  const testo = filtro.trim().toUpperCase();
  const disponibili = risposta.filter((d) => !giaAssociate.has(d.descrizione_key));
  // In ricerca il server ha gia' applicato il testo: rifiltrarlo qui
  // escluderebbe i risultati che il server considera pertinenti.
  const pool = inRicerca
    ? disponibili
    : disponibili.filter((d) => (testo ? d.descrizione.toUpperCase().includes(testo) : true));

  return {
    candidati: pool.slice(0, MAX_CANDIDATI_VISIBILI),
    nascosti: Math.max(0, pool.length - MAX_CANDIDATI_VISIBILI),
    poolSaturo: risposta.length >= RPC_LIMITE_DESCRIZIONI,
  };
}
