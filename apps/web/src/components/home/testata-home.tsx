import { Building2, Store } from "lucide-react";

// Testata delle due Home (Mattia, 28/9): nome, «Carica fatture», «Configura
// assistente». Prima il punto vendita non l'aveva (solo il bottone di
// configurazione, allineato a destra) e la catena ne aveva una sua.
export function TestataHome({
  vista,
  nome,
  dettaglio,
  azioni,
}: {
  vista: "pv" | "catena";
  nome: string | null | undefined;
  /** Accanto al nome, attenuato: in catena il numero di punti vendita. */
  dettaglio?: string | null;
  azioni?: React.ReactNode;
}) {
  const Icona = vista === "catena" ? Building2 : Store;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2 text-xl font-semibold">
        <Icona className="size-6 shrink-0 text-primary" />
        {nome && <span className="truncate" title={nome}>{nome}</span>}
        {dettaglio && (
          <span className="shrink-0 text-base font-normal text-muted-foreground">· {dettaglio}</span>
        )}
      </div>
      {azioni && <div className="flex items-center gap-2">{azioni}</div>}
    </div>
  );
}
