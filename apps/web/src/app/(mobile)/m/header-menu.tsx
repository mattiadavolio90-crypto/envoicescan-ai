"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MoreVertical, LogOut, MapPin, Check } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type Sede = {
  id: string;
  nome: string;
  indirizzo: string | null;
  comune: string | null;
  attiva: boolean;
};

// Menu a 3 puntini: selettore sede (clienti multi-sede) + "Esci". Impostazioni e'
// una tab della bottom nav. Sia il cambio sede sia il logout sono POST + refresh
// (NON navigazioni di pagina), quindi sicuri da dentro il dropdown anche in PWA
// standalone (router.push di pagina invece si mangiava la navigazione).
export function HeaderMenu() {
  const router = useRouter();
  const [sedi, setSedi] = useState<Sede[]>([]);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch("/api/account/sedi", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d?.sedi) setSedi(d.sedi as Sede[]);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  async function cambiaSede(id: string) {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: id }),
      });
      if (!res.ok) throw new Error();
      setSedi((prev) => prev.map((s) => ({ ...s, attiva: s.id === id })));
      router.refresh();
      toast.success("Sede cambiata");
    } catch {
      toast.error("Impossibile cambiare sede");
    } finally {
      setSwitching(false);
    }
  }

  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch {
      toast.error("Errore durante il logout");
    }
  }

  const multiSede = sedi.length > 1;

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
      <DropdownMenuContent side="bottom" align="end" className="w-60">
        {multiSede && (
          <>
            <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground">
              <MapPin className="size-3.5" />
              Sedi
            </DropdownMenuLabel>
            {sedi.map((s) => (
              <DropdownMenuItem
                key={s.id}
                disabled={switching || s.attiva}
                onClick={() => cambiaSede(s.id)}
                className="flex items-start gap-2 py-2.5"
              >
                <Check className={`mt-0.5 size-4 shrink-0 ${s.attiva ? "text-sky-500 opacity-100" : "opacity-0"}`} />
                <span className="flex flex-col leading-tight">
                  <span className="text-sm font-medium">{s.nome}</span>
                  {(s.indirizzo || s.comune) && (
                    <span className="max-w-[180px] truncate text-xs text-muted-foreground">
                      {[s.indirizzo, s.comune].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </span>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
          <LogOut className="size-4" />
          Esci
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
