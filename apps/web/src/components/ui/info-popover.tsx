"use client";

import * as React from "react";
import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface InfoPopoverProps {
  /** Titolo in grassetto in cima al popover. */
  title: string;
  /** Contenuto della spiegazione. */
  children: React.ReactNode;
  /** Allineamento del popover rispetto all'icona. Default "start". */
  align?: "start" | "center" | "end";
  /** Classi extra per il contenuto (es. larghezza diversa da w-96). */
  contentClassName?: string;
  /** Label accessibile del bottone. Default "Come funziona". */
  ariaLabel?: string;
}

/**
 * Icona ⓘ con popover di spiegazione, riusabile in tab/pagine complesse.
 * Pattern unico per tutta l'app: stesso bottone ghost, stessa larghezza.
 */
export function InfoPopover({
  title,
  children,
  align = "start",
  contentClassName,
  ariaLabel = "Come funziona",
}: InfoPopoverProps) {
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="icon" className="size-8 text-muted-foreground" aria-label={ariaLabel}>
            <Info className="size-4" />
          </Button>
        }
      />
      <PopoverContent className={cn("w-96 text-sm space-y-3", contentClassName)} align={align}>
        <p className="font-semibold">{title}</p>
        {children}
      </PopoverContent>
    </Popover>
  );
}
