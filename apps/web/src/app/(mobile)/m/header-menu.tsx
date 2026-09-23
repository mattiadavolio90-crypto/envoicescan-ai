"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MoreVertical, LogOut, MapPin, Check, Building2, Monitor } from "lucide-react";
import { toast } from "sonner";
import { cambiaSedeEAttendi } from "@/lib/cambia-sede";
import { scegliVersioneDesktop, dimenticaPreferenzaAlLogout } from "@/lib/device";

function writeViewCookie(v: "chain" | "pv") {
  if (typeof document === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; secure" : "";
  document.cookie = `oneflux_view=${v}; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax${secure}`;
}
function isChainCookie(): boolean {
  if (typeof document === "undefined") return false;
  return /(?:^|;\s*)oneflux_view=chain/.test(document.cookie);
}
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
  const [inChain, setInChain] = useState(false);

  useEffect(() => {
    let alive = true;
    setInChain(isChainCookie());
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

  // Entra nella vista di gruppo: modalità catena + torna alla home mobile.
  function vaiAllaCatena() {
    writeViewCookie("chain");
    setInChain(true);
    router.push("/m/briefing");
    router.refresh();
  }

  async function cambiaSede(id: string) {
    if (switching) return;
    setSwitching(true);
    try {
      // Scegliere una sede = SCENDERE in quel PV: modalità PV.
      writeViewCookie("pv");
      setInChain(false);
      setSedi((prev) => prev.map((s) => ({ ...s, attiva: s.id === id })));
      const confermato = await cambiaSedeEAttendi(id);
      router.refresh();
      if (confermato) toast.success("Punto vendita aperto");
      else toast.message("Punto vendita in apertura, un attimo…");
    } catch {
      toast.error("Impossibile cambiare sede");
    } finally {
      setSwitching(false);
    }
  }

  // Via d'uscita da /m verso l'app completa. Senza memorizzare la scelta il
  // link non funzionerebbe: con la finestra ancora stretta MobileRedirect
  // rispedirebbe subito su /m. Full reload (non router.push) perche' si cambia
  // layout, come per il login.
  function vaiAlDesktop() {
    scegliVersioneDesktop();
    window.location.href = "/dashboard";
  }

  async function logout() {
    try {
      // Il logout chiude anche la preferenza desktop: la prossima persona che
      // entra su questo dispositivo riparte dalla scelta automatica.
      dimenticaPreferenzaAlLogout();
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
            <DropdownMenuItem onClick={vaiAllaCatena} className="flex items-center gap-2 py-2.5">
              <Building2 className="size-4 shrink-0 text-sky-500" />
              <span className="flex flex-1 flex-col leading-tight">
                <span className="text-sm font-medium">Vista catena</span>
                <span className="text-xs text-muted-foreground">Tutti i punti vendita</span>
              </span>
              {inChain && <Check className="ml-auto size-4 shrink-0 text-sky-500" />}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground">
              <MapPin className="size-3.5" />
              Sedi
            </DropdownMenuLabel>
            {sedi.map((s) => {
              const corrente = s.attiva && !inChain;
              return (
              <DropdownMenuItem
                key={s.id}
                disabled={switching || corrente}
                onClick={() => cambiaSede(s.id)}
                className="flex items-start gap-2 py-2.5"
              >
                <Check className={`mt-0.5 size-4 shrink-0 ${corrente ? "text-sky-500 opacity-100" : "opacity-0"}`} />
                <span className="flex flex-col leading-tight">
                  <span className="text-sm font-medium">{s.nome}</span>
                  {(s.indirizzo || s.comune) && (
                    <span className="max-w-[180px] truncate text-xs text-muted-foreground">
                      {[s.indirizzo, s.comune].filter(Boolean).join(" · ")}
                    </span>
                  )}
                </span>
              </DropdownMenuItem>
              );
            })}
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onClick={vaiAlDesktop} className="flex items-center gap-2 py-2.5">
          <Monitor className="size-4 shrink-0 text-muted-foreground" />
          <span className="flex flex-1 flex-col leading-tight">
            <span className="text-sm font-medium">Versione desktop</span>
            <span className="text-xs text-muted-foreground">App completa</span>
          </span>
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
