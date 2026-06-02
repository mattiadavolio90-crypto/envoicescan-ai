import { Bell } from "lucide-react";
import { fetchNotifiche } from "@/lib/notifiche";
import { PageHeader } from "@/components/ui/page-header";
import { NotificheList } from "./notifiche-list";

export default async function NotifichePage() {
  const data = await fetchNotifiche(false);

  const notifiche = data?.notifiche ?? [];
  const unread = data?.unread ?? 0;

  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader
        icon="bell"
        title="Notifiche"
        hint={unread > 0 ? `${unread} ${unread === 1 ? "avviso" : "avvisi"} da gestire` : "Nessuna notifica da gestire"}
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
          <p className="text-sm">Nessuna notifica attiva</p>
        </div>
      ) : (
        <NotificheList notifiche={notifiche} />
      )}
    </div>
  );
}
