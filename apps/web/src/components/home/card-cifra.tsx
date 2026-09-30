"use client";

import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { confermabile, testoCard, type CardCifra } from "@/lib/home-chat";
import { oggiARoma } from "@/lib/oggi-roma";

// La cifra dettata all'assistente, sotto la sua risposta (fase 3): si scrive
// solo con Conferma. Senza onConferma (il Demo Tour) la card e' da leggere.
export function CardCifraDettata({
  card,
  onConferma,
  onAnnulla,
}: {
  card: CardCifra;
  onConferma?: (id: string) => void;
  onAnnulla?: (id: string) => void;
}) {
  const t = testoCard(card.proposta, oggiARoma().getFullYear());
  const aperta = confermabile(card);
  const chiusa = card.stato === "registrata" || card.stato === "annullata" || card.stato === "errore";

  return (
    <div
      className={cn(
        "mr-auto w-full max-w-[85%] space-y-2 rounded-xl border bg-card px-3 py-2.5 text-sm",
        chiusa ? "border-border" : "border-primary/40",
      )}
    >
      <div>
        <p className="font-medium text-foreground">{t.titolo}</p>
        {t.sede && <p className="text-xs text-muted-foreground">{t.sede}</p>}
      </div>

      <dl className="space-y-0.5 tabular-nums">
        {t.righe.map(([etichetta, valore]) => (
          <div key={etichetta} className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{etichetta}</dt>
            <dd className="text-foreground">{valore}</dd>
          </div>
        ))}
        {t.totale && (
          <div className="flex justify-between gap-4 border-t border-border pt-0.5 font-medium">
            <dt className="text-foreground">Totale</dt>
            <dd className="text-foreground">{t.totale}</dd>
          </div>
        )}
      </dl>

      {t.nota && card.stato !== "registrata" && <p className="text-xs text-muted-foreground">{t.nota}</p>}

      {card.messaggio && (
        <p
          className={cn(
            "flex items-center gap-1 text-xs",
            card.stato === "registrata"
              ? "text-positivo"
              : card.stato === "errore"
                ? "text-negativo"
                : card.stato === "annullata"
                  ? "text-muted-foreground"
                  : "text-incerto",
          )}
        >
          {card.stato === "registrata" && <Check className="size-3.5" />}
          {card.messaggio}
        </p>
      )}

      {onConferma && (aperta || card.stato === "invio") && (
        <div className="flex justify-end gap-2 pt-0.5">
          <Button
            variant="ghost"
            size="sm"
            disabled={card.stato === "invio"}
            onClick={() => onAnnulla?.(card.id)}
          >
            Annulla
          </Button>
          <Button size="sm" disabled={card.stato === "invio"} onClick={() => onConferma(card.id)}>
            {card.stato === "invio" && <Loader2 className="size-3.5 animate-spin" />}
            Conferma
          </Button>
        </div>
      )}
    </div>
  );
}
