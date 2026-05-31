import { Bell } from "lucide-react";
import { fetchNotifiche } from "@/lib/notifiche";
import { NotificheList } from "./notifiche-list";

export default async function NotifichePage() {
  const data = await fetchNotifiche(false);

  const notifiche = data?.notifiche ?? [];
  const unread = data?.unread ?? 0;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Notifiche</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {unread > 0 ? `${unread} non lette` : "Nessuna notifica da leggere"}
        </p>
      </div>

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
