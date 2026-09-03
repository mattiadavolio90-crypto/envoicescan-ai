import { Bell } from "lucide-react";
import { fetchNotifiche, type Notifica } from "@/lib/notifiche";
import { esitoLista } from "@/lib/esito-caricamento";
import { PageHeader } from "@/components/ui/page-header";
import { NotificheList } from "./notifiche-list";

export default async function NotifichePage() {
  const data = await fetchNotifiche(false);

  // `data === null` = worker giu'/timeout, non "zero avvisi": prima la pagina
  // scriveva DUE rassicurazioni false su un guasto («Nessun avviso da gestire»
  // nell'intestazione, «Nessun avviso attivo» nel corpo).
  const esito = esitoLista<Notifica>(data, "notifiche");
  const notifiche = esito.righe;
  const fallito = esito.stato === "non_disponibile";
  const unread = data?.unread ?? 0;

  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader
        icon="bell"
        title="Avvisi"
        hint={
          fallito
            ? "Avvisi non disponibili in questo momento"
            : unread > 0
              ? `${unread} ${unread === 1 ? "avviso" : "avvisi"} da gestire`
              : "Nessun avviso da gestire"
        }
        badge={
          unread > 0 ? (
            <span className="inline-flex min-w-6 items-center justify-center rounded-full bg-emerald-600 px-1.5 text-sm font-bold text-white">
              {unread}
            </span>
          ) : null
        }
      />

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
        <NotificheList notifiche={notifiche} />
      )}
    </div>
  );
}
