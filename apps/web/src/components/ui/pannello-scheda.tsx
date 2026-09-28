// Contenitore delle schede di pagina nate da una finestra (catena: Gestione
// Fatture e Analisi catena, 28/9/2026). La testata della finestra (titolo,
// filtri, Esporta) resta, dentro una card di pagina invece che in un Dialog.
export function PannelloScheda({
  titolo,
  azioni,
  children,
}: {
  titolo: React.ReactNode;
  azioni?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
        <h2 className="flex items-center gap-2 text-base font-semibold">{titolo}</h2>
        {azioni && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">{azioni}</div>
        )}
      </div>
      <div className="px-5 pb-5 pt-3">{children}</div>
    </section>
  );
}

// Le tabelle larghe scorrono dentro la card, non con la pagina: cosi' la
// testata e la prima colonna (sticky) restano ferme come nelle finestre.
export const AREA_TABELLA = "max-h-[70vh] overflow-auto";
