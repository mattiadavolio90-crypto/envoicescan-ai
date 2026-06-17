"use client";

import {
  BarChart3,
  Building2,
  CalendarCheck,
  CalendarDays,
  Check,
  ChevronsUpDown,
  FileText,
  Home,
  LifeBuoy,
  LogOut,
  MapPin,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  ShieldQuestion,
  Tags,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Logo } from "@/components/brand/logo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const navMain = [
  { title: "Home", url: "/dashboard", icon: Home, flag: null },
  { title: "Analisi Fatture", url: "/analisi-fatture", icon: FileText, flag: "analisi_fatture" },
  { title: "Ricavi e Margini", url: "/margini", icon: BarChart3, flag: "margini" },
  { title: "Analisi e Tag", url: "/analisi-e-tag", icon: Tags, flag: "analisi_e_tag" },
  { title: "Osservatorio", url: "/prezzi", icon: Search, flag: "prezzi" },
  { title: "Gestione Fatture", url: "/scadenziario", icon: CalendarCheck, flag: "scadenziario" },
  { title: "Agenda e Personale", url: "/agenda", icon: CalendarDays, flag: "agenda" },
  { title: "Strumenti", url: "/workspace", icon: Wrench, flag: "workspace" },
];

const navSecondary = [
  { title: "Impostazioni", url: "/impostazioni", icon: Settings },
  { title: "Servizi", url: "/assistenza", icon: LifeBuoy },
];

type AppSidebarProps = {
  userEmail?: string;
  userInitials?: string;
  ristoranteNome?: string;
  isAdmin?: boolean;
  pagineAbilitate?: string[] | null;
};

type Sede = {
  id: string;
  nome: string;
  indirizzo: string | null;
  comune: string | null;
  attiva: boolean;
};

export function AppSidebar({
  userEmail = "utente@oneflux.it",
  userInitials = "U",
  ristoranteNome = "Ristorante",
  isAdmin = false,
  pagineAbilitate,
}: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const visibleNav = pagineAbilitate == null
    ? navMain
    : navMain.filter((item) => item.flag === null || pagineAbilitate.includes(item.flag));

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch {
      toast.error("Errore durante il logout");
    }
  }

  // ── Sedi (clienti multi-ristorante) ───────────────────────────────────────
  // Il selettore di sede appare SOLO se l'account ha più di una sede. Per i
  // clienti mono-sede (la stragrande maggioranza) il menu resta com'era.
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

  async function handleCambiaSede(ristoranteId: string) {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: ristoranteId }),
      });
      if (!res.ok) throw new Error();
      // Sposta subito il ✓ sulla nuova sede senza aspettare il refetch: il selettore
      // dava un feedback ritardato e sembrava "tornare sempre alla prima sede".
      setSedi((prev) => prev.map((s) => ({ ...s, attiva: s.id === ristoranteId })));
      // Ricarica i dati della pagina con la nuova sede attiva (KPI, fatture, margini
      // sono filtrati per ristorante_id lato server → serve un refresh completo).
      // La testata si aggiorna perche' /api/auth/me ora risolve la sede attiva.
      router.refresh();
      toast.success("Sede cambiata");
    } catch {
      toast.error("Impossibile cambiare sede");
    } finally {
      setSwitching(false);
    }
  }

  const hasMultiSede = sedi.length > 1;

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={<Link href="/dashboard" />}
              className="h-auto items-center gap-3 py-3 group-data-[collapsible=icon]:!size-12 group-data-[collapsible=icon]:!p-0 group-data-[collapsible=icon]:justify-center [&_svg]:!size-full"
            >
              <Logo variant="icon" size={40} glow className="shrink-0" />
              <span className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
                <span className="block whitespace-normal text-xs font-medium leading-snug text-primary">
                  Un unico flusso
                  <br />
                  per tutta la gestione
                </span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Menu principale</SidebarGroupLabel>
          <SidebarMenu>
            {/* Catena: solo account multi-sede. È la plancia di gruppo (vista
                superiore di analisi), separata dalle pagine del singolo PV. */}
            {hasMultiSede && (
              <SidebarMenuItem>
                <SidebarMenuButton
                  render={<Link href="/catena" />}
                  isActive={pathname === "/catena"}
                  className="data-active:!bg-sky-500/15 data-active:!text-sky-600 dark:data-active:!text-sky-400 data-active:!font-semibold data-active:!border-l-2 data-active:!border-sky-500"
                >
                  <Building2 />
                  <span>Catena</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
            {visibleNav.map((item) => (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  render={<Link href={item.url} />}
                  isActive={pathname === item.url}
                  className="data-active:!bg-sky-500/15 data-active:!text-sky-600 dark:data-active:!text-sky-400 data-active:!font-semibold data-active:!border-l-2 data-active:!border-sky-500"
                >
                  <item.icon />
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>

        <SidebarSeparator />

        <SidebarGroup>
          <SidebarGroupLabel>Altro</SidebarGroupLabel>
          <SidebarMenu>
            {isAdmin && (
              <SidebarMenuItem>
                <SidebarMenuButton
                  render={<Link href="/admin" />}
                  isActive={pathname.startsWith("/admin")}
                  className="data-active:!bg-sky-500/15 data-active:!text-sky-600 dark:data-active:!text-sky-400 data-active:!font-semibold data-active:!border-l-2 data-active:!border-sky-500"
                >
                  <ShieldCheck />
                  <span>Admin</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
            {navSecondary.map((item) => (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  render={<Link href={item.url} />}
                  isActive={pathname === item.url}
                  className="data-active:!bg-sky-500/15 data-active:!text-sky-600 dark:data-active:!text-sky-400 data-active:!font-semibold data-active:!border-l-2 data-active:!border-sky-500"
                >
                  <item.icon />
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
            <SidebarMenuItem>
              <SidebarMenuButton render={<Link href="/privacy" target="_blank" />}>
                <ShieldQuestion />
                <span>Privacy & Cookie</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton render={<Link href="/termini" target="_blank" />}>
                <Scale />
                <span>Termini di Servizio</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <SidebarMenuButton size="lg">
                    <Avatar className="size-8">
                      <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">
                        {userInitials}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col gap-0.5 leading-none flex-1 text-left">
                      <span className="text-sm font-medium truncate">{ristoranteNome}</span>
                      <span className="text-xs text-muted-foreground truncate">{userEmail}</span>
                    </div>
                    <ChevronsUpDown className="ml-auto size-4" />
                  </SidebarMenuButton>
                }
              />
              <DropdownMenuContent
                side="top"
                align="start"
                className="w-64"
              >
                {hasMultiSede && (
                  <>
                    <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground">
                      <MapPin className="size-3.5" />
                      Sedi
                    </DropdownMenuLabel>
                    {sedi.map((s) => (
                      <DropdownMenuItem
                        key={s.id}
                        disabled={switching || s.attiva}
                        onClick={() => handleCambiaSede(s.id)}
                        className="flex items-start gap-2 py-2.5"
                      >
                        <Check
                          className={`size-4 mt-0.5 shrink-0 ${s.attiva ? "opacity-100 text-sky-500" : "opacity-0"}`}
                        />
                        <span className="flex flex-col leading-tight">
                          <span className="text-sm font-medium">{s.nome}</span>
                          {(s.indirizzo || s.comune) && (
                            <span className="text-xs text-muted-foreground truncate max-w-[180px]">
                              {[s.indirizzo, s.comune].filter(Boolean).join(" · ")}
                            </span>
                          )}
                        </span>
                      </DropdownMenuItem>
                    ))}
                    <DropdownMenuSeparator />
                  </>
                )}
                <DropdownMenuItem variant="destructive" onClick={handleLogout} className="text-base py-3">
                  <LogOut className="size-5" />
                  Esci
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
