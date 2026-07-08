"use client";

import {
  BarChart3,
  CalendarCheck,
  CalendarDays,
  ChevronsUpDown,
  FileText,
  Home,
  LifeBuoy,
  Search,
  Settings,
  Tags,
  Wrench,
} from "lucide-react";

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
import { DEMO_RISTORANTE } from "@/lib/demo-data";
import type { DemoScreen } from "@/lib/demo-steps";

// Replica FEDELE ma INERTE della sidebar dell'app (navMain/navSecondary sono gli
// stessi di app-sidebar.tsx). Nella demo la navigazione è guidata dal tour, non
// dall'utente: ogni voce è disabilitata (nessun Link, nessun fetch di sedi,
// nessun logout/cambio-sede). Riusiamo solo i primitivi ui/sidebar per avere
// pixel identici al prodotto.

const navMain: { title: string; icon: typeof Home; screen: DemoScreen | null }[] = [
  { title: "Home", icon: Home, screen: "home" },
  { title: "Analisi Fatture", icon: FileText, screen: "analisi" },
  { title: "Ricavi e Margini", icon: BarChart3, screen: "margini" },
  { title: "Analisi e Tag", icon: Tags, screen: null },
  { title: "Osservatorio", icon: Search, screen: "prezzi" },
  { title: "Gestione Fatture", icon: CalendarCheck, screen: null },
  { title: "Agenda e Personale", icon: CalendarDays, screen: null },
  { title: "Strumenti", icon: Wrench, screen: null },
];

const navSecondary = [
  { title: "Impostazioni", icon: Settings },
  { title: "Servizi", icon: LifeBuoy },
];

const ACTIVE_CLASS =
  "data-active:!bg-sky-500/15 data-active:!text-sky-600 dark:data-active:!text-sky-400 data-active:!font-semibold data-active:!border-l-2 data-active:!border-sky-500";

export function DemoSidebar({ screen }: { screen: DemoScreen }) {
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              className="h-auto items-center gap-3 py-3 group-data-[collapsible=icon]:!size-12 group-data-[collapsible=icon]:!p-0 group-data-[collapsible=icon]:justify-center [&_svg]:!size-full pointer-events-none"
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
            {navMain.map((item) => (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  isActive={item.screen === screen}
                  aria-disabled
                  className={`${ACTIVE_CLASS} pointer-events-none`}
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
            {navSecondary.map((item) => (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton aria-disabled className="pointer-events-none opacity-70">
                  <item.icon />
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" aria-disabled className="pointer-events-none">
              <Avatar className="size-8">
                <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">
                  MA
                </AvatarFallback>
              </Avatar>
              <div className="flex flex-col gap-0.5 leading-none flex-1 text-left">
                <span className="text-sm font-medium truncate">{DEMO_RISTORANTE}</span>
                <span className="text-xs text-muted-foreground truncate">demo@oneflux.it</span>
              </div>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
