"use client";

import {
  BarChart3,
  CalendarDays,
  ChevronsUpDown,
  FileText,
  Home,
  LifeBuoy,
  LogOut,
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
import { Logo, Wordmark } from "@/components/brand/logo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const navMain = [
  { title: "Home", url: "/dashboard", icon: Home },
  { title: "Analisi Fatture", url: "/analisi-fatture", icon: FileText },
  { title: "Ricavi e Margini", url: "/margini", icon: BarChart3 },
  { title: "Prezzi", url: "/prezzi", icon: Search },
  { title: "Analisi e Tag", url: "/analisi-e-tag", icon: Tags },
  { title: "Strumenti", url: "/workspace", icon: Wrench },
  { title: "Gestione Fatture", url: "/scadenziario", icon: CalendarDays },
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
};

export function AppSidebar({
  userEmail = "utente@oneflux.it",
  userInitials = "U",
  ristoranteNome = "Ristorante",
  isAdmin = false,
}: AppSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch {
      toast.error("Errore durante il logout");
    }
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={<Link href="/dashboard" />}
              className="group-data-[collapsible=icon]:!size-12 group-data-[collapsible=icon]:!p-0 group-data-[collapsible=icon]:justify-center [&_svg]:!size-full"
            >
              <Logo variant="icon" size={40} glow className="shrink-0" />
              <div className="flex flex-col gap-0.5 leading-none group-data-[collapsible=icon]:hidden">
                <Wordmark className="text-base tracking-[0.14em]" />
                <span className="text-xs text-muted-foreground">Controllo gestione</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Menu principale</SidebarGroupLabel>
          <SidebarMenu>
            {navMain.map((item) => (
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
                className="w-56"
              >
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
