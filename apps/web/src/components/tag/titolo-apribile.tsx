"use client";

// Titolo di una sezione che si apre e si chiude cliccandolo (il grafico dei
// tag, in punto vendita e in catena). Il bottone e' il titolo stesso, non una
// freccina a parte: e' piu' facile da colpire e dice cosa apre.

import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function TitoloApribile({
  titolo, aperto, onCambia,
}: {
  titolo: string;
  aperto: boolean;
  onCambia: (aperto: boolean) => void;
}) {
  return (
    <h3 className="text-sm font-semibold">
      <Button
        variant="ghost"
        size="default"
        aria-expanded={aperto}
        className="-ml-2 gap-1.5 font-semibold aria-expanded:bg-transparent hover:aria-expanded:bg-muted"
        onClick={() => onCambia(!aperto)}
      >
        {titolo}
        <ChevronDown aria-hidden className={cn("text-muted-foreground transition-transform", aperto && "rotate-180")} />
      </Button>
    </h3>
  );
}
