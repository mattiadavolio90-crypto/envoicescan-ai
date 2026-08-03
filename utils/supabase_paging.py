"""Paginazione delle select PostgREST.

PostgREST applica `max_rows` (1000 su questo progetto) a OGNI select senza
`.range()`: ritorna le prime 1000 righe **senza errore, senza warning e senza
log**. Una query troncata cosi' non sembra rotta, sembra un dato piu' piccolo —
ed e' il modo peggiore di sbagliare, perche' nessuno se ne accorge.

Su ONEFLUX e' gia' successo: il filtro categorie di Analisi Fatture perdeva
"Da Classificare" su 4 sedi (la categoria che la regola di dominio #1 esiste
per rendere visibile), e il briefing di catena sottostimava le fatture del
giorno quando i punti vendita insieme superavano le 1000 righe.

Uso:
    from utils.supabase_paging import fetch_all

    rows = fetch_all(
        sb.table("fatture").select("categoria")
          .eq("ristorante_id", rid).is_("deleted_at", "null")
    )

`builder` e' la query gia' filtrata e ordinata, SENZA `.range()` e senza
`.execute()`: ci pensa `fetch_all`.

Dettaglio non ovvio, verificato e non dedotto: lo stesso builder viene riusato a
ogni pagina, e `range()` **non** riscrive i parametri — usa `params.add()`, che
li ACCUMULA. Dopo due pagine la richiesta porta letteralmente
`offset=0&offset=1000&limit=1000&limit=1000`. Funziona lo stesso perche' e'
**PostgREST a onorare l'ultimo valore duplicato**: e' una garanzia del server,
non del client. Verificato contro l'API reale: 9.612 righe paginate col builder
riusato coincidono ID per ID con le stesse pagine chieste da builder nuovi.
Se un domani si cambia client HTTP o quel comportamento del server, questo e' il
punto che si rompe per primo — e si romperebbe in silenzio, restituendo dati
sovrapposti invece di un errore.

Non usarlo per leggere tabelle intere senza filtri: paginare 50.000 righe resta
lento anche se corretto. Se il risultato serve solo aggregato, la strada giusta
e' una RPC che aggrega lato database (vedi `dashboard_stats_aggregata`).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("supabase_paging")

PAGE_SIZE = 1000

# Rete di sicurezza: oltre questa soglia smettiamo di paginare. Serve a non
# trasformare un filtro sbagliato (o una tabella cresciuta oltre le attese) in
# una richiesta infinita che tiene occupato un thread del worker.
MAX_ROWS = 50000


def fetch_all(builder, page_size: int = PAGE_SIZE, max_rows: int = MAX_ROWS) -> List[Dict[str, Any]]:
    """Esegue `builder` a pagine e ritorna TUTTE le righe, non solo le prime 1000."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        resp = builder.range(offset, offset + page_size - 1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
        if offset >= max_rows:
            # Tronchiamo, ma NON in silenzio: un troncamento muto e' esattamente
            # il difetto che questo modulo esiste per impedire.
            logger.warning(
                "fetch_all: raggiunto il cap di %d righe, risultato TRONCATO", max_rows
            )
            break
    return rows
