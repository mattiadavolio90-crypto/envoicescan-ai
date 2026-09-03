import { Bell } from "lucide-react";
import { fetchNotifiche, type Notifica } from "@/lib/notifiche";
import { esitoLista } from "@/lib/esito-caricamento";
import { NotificheList } from "@/app/(app)/notifiche/notifiche-list";

export default async function MobileNotifichePage() {
  const data = await fetchNotifiche(false);
  // Stessa distinzione della pagina desktop: `null` = guasto, non "zero avvisi".
  const esito = esitoLista<Notifica>(data, "notifiche");
  const notifiche = esito.righe;
  const fallito = esito.stato === "non_disponibile";
  const unread = data?.unread ?? 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Avvisi</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {fallito
            ? "Avvisi non disponibili in questo momento"
            : unread > 0
              ? `${unread} ${unread === 1 ? "avviso" : "avvisi"} da gestire`
              : "Nessun avviso da gestire"}
        </p>
      </div>

      {notifiche.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
          <Bell className="size-10 opacity-30" />
          <p className="text-sm">
            {fallito
              ? "Non è stato possibile caricare gli avvisi. Riprova fra un momento."
              : "Nessun avviso attivo"}
          </p>
        </div>
      ) : (
        <NotificheList notifiche={notifiche} hideCta />
      )}
    </div>
  );
}
