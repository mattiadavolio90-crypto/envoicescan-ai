"use client";

import { useRouter } from "next/navigation";
import { MoreVertical, LogOut } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// Menu a 3 puntini: ora contiene SOLO "Esci". Impostazioni e' diventata una tab
// della bottom nav (<Link> SPA): navigare con router.push da dentro questo
// dropdown, in PWA standalone, si mangiava la navigazione ("page couldn't
// load"). Il logout NON e' una navigazione di pagina ma una POST + redirect,
// quindi qui router.push va bene.
export function HeaderMenu() {
  const router = useRouter();

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch {
      toast.error("Errore durante il logout");
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            className="flex size-9 items-center justify-center rounded-md text-muted-foreground active:bg-accent"
            aria-label="Menu"
          >
            <MoreVertical className="size-5" />
          </button>
        }
      />
      <DropdownMenuContent side="bottom" align="end" className="w-52">
        <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
          <LogOut className="size-4" />
          Esci
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
