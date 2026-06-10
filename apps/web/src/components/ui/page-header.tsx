"use client";

import {
  BarChart3,
  Bell,
  CalendarDays,
  FileText,
  LifeBuoy,
  Search,
  Settings,
  Tags,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// Le icone sono indicizzate per nome: un Server Component non può passare una
// funzione/componente a un Client Component, ma può passare una stringa. Il
// PageHeader risolve qui il nome nell'icona lucide corrispondente.
const ICONS = {
  "bar-chart": BarChart3,
  bell: Bell,
  calendar: CalendarDays,
  file: FileText,
  lifebuoy: LifeBuoy,
  search: Search,
  settings: Settings,
  tags: Tags,
  wrench: Wrench,
} satisfies Record<string, LucideIcon>;

export type PageHeaderIcon = keyof typeof ICONS;

type PageHeaderProps = {
  icon: PageHeaderIcon;
  title: string;
  /** Descrizione mostrata in un tooltip al passaggio del mouse sul titolo. */
  hint?: string;
  /**
   * Contenuto vivo accanto al titolo (es. un conteggio): a differenza di `hint`
   * resta sempre visibile, perché è un dato, non una descrizione.
   */
  badge?: React.ReactNode;
  /** Azioni a destra (es. pulsante upload). */
  actions?: React.ReactNode;
  /**
   * Sottotitolo visibile sotto il titolo. A differenza di `hint` (tooltip al
   * hover) resta sempre in pagina: usalo quando la frase fa parte del
   * posizionamento e deve essere letta, non scoperta.
   */
  subtitle?: string;
};

/**
 * Intestazione di pagina condivisa: icona + titolo, con la descrizione spostata
 * in un tooltip al hover (così non occupa spazio fisso sotto al titolo).
 * Il blocco icona+titolo è il trigger del tooltip.
 */
export function PageHeader({ icon, title, hint, badge, actions, subtitle }: PageHeaderProps) {
  const Icon = ICONS[icon];
  const heading = (
    <div className="flex items-center gap-3">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-sky-500/15 text-sky-600 dark:text-sky-400">
        <Icon className="size-5" />
      </div>
      <h1 className="text-2xl font-bold tracking-tight leading-none">{title}</h1>
      {badge}
    </div>
  );

  const top = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      {hint ? (
        <Tooltip>
          <TooltipTrigger render={<div className="cursor-default">{heading}</div>} />
          <TooltipContent side="bottom" align="start">
            {hint}
          </TooltipContent>
        </Tooltip>
      ) : (
        heading
      )}
      {actions}
    </div>
  );

  if (!subtitle) return top;

  return (
    <div className="space-y-2">
      {top}
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{subtitle}</p>
    </div>
  );
}
