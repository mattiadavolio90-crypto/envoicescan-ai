"use client";

import { useRouter } from "next/navigation";
import { MoreVertical, Settings, LogOut } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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
        <DropdownMenuItem onClick={() => router.push("/m/impostazioni")}>
          <Settings className="size-4" />
          Impostazioni
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
          <LogOut className="size-4" />
          Esci
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
