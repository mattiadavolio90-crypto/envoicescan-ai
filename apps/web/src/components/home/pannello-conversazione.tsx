"use client";

import { createContext, useContext, useEffect, useRef } from "react";
import { Loader2, Send, SquarePen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type VoceChat } from "@/lib/home-chat";
import { CardCifraDettata } from "./card-cifra";

// Il disegno della conversazione dentro il riquadro dell'assistente: lo usano
// la Home vera (ConversazioneAssistente) e il Demo Tour (DemoConversazione),
// cosi' la demo non puo' mostrare un prodotto diverso da quello vero.

/** Dentro il riquadro dell'assistente da computer (fase L, 15-16/10/2026) il riquadro ha
 *  un'altezza fissa e scorre tutto insieme, briefing e conversazione: chattando il briefing sale
 *  e lascia spazio ai messaggi, la casella resta ferma in fondo. Lo scorrimento e' del contenitore
 *  `[data-scorre-conversazione]` del riquadro, non della lista. Vale anche nel Demo Tour, che usa
 *  lo stesso riquadro; sotto `lg` e fuori dal riquadro resta com'era. */
export const ConversazioneAltezzaFissa = createContext(false);

export function PannelloConversazione({
  voci,
  attesa,
  suggerimenti,
  onSuggerimento,
  valore,
  onCambia,
  onInvia,
  placeholder,
  bloccato,
  stato,
  statoAvviso = false,
  onNuova,
  onConferma,
  onAnnulla,
  ancoraDemo,
}: {
  voci: VoceChat[];
  /** Testo d'attesa mentre l'assistente risponde; null = nessuna attesa. */
  attesa: string | null;
  suggerimenti: readonly string[] | null;
  onSuggerimento?: (s: string) => void;
  valore: string;
  onCambia?: (v: string) => void;
  onInvia?: () => void;
  placeholder: string;
  bloccato: boolean;
  /** La riga del contatore: «Ti restano 640 crediti». */
  stato: string;
  statoAvviso?: boolean;
  onNuova?: () => void;
  /** Le card delle cifre dettate; senza (il Demo Tour) sono da leggere. */
  onConferma?: (cardId: string) => void;
  onAnnulla?: (cardId: string) => void;
  ancoraDemo?: string;
}) {
  const lista = useRef<HTMLDivElement>(null);
  const altezzaFissa = useContext(ConversazioneAltezzaFissa);

  // In fondo a ogni messaggio, scorrendo la lista (o il riquadro, se ad altezza fissa) e non
  // la pagina: scrollIntoView portava giu' tutta la Home appena si apriva.
  // Ad altezza fissa il riquadro scende solo quando si chatta (domanda partita o risposta
  // arrivata), non quando si riapre la Home con una conversazione salvata: li' si vede prima
  // il briefing di oggi, e la conversazione di ieri si ritrova scorrendo.
  const attesaPrima = useRef(attesa);
  useEffect(() => {
    const eraInAttesa = attesaPrima.current !== null;
    attesaPrima.current = attesa;
    const el = lista.current;
    if (!el) return;
    const riquadro = altezzaFissa ? el.closest<HTMLElement>("[data-scorre-conversazione]") : null;
    if (riquadro) {
      if (attesa !== null || eraInAttesa) riquadro.scrollTop = riquadro.scrollHeight;
      return;
    }
    el.scrollTop = el.scrollHeight;
  }, [voci.length, attesa, altezzaFissa]);

  return (
    <div
      data-demo-anchor={ancoraDemo}
      className={cn(
        "relative mt-5 space-y-3 border-t border-primary/15 pt-4",
        altezzaFissa && "lg:flex lg:flex-1 lg:flex-col lg:[&>*:first-child]:mt-auto",
      )}
    >
      {(voci.length > 0 || attesa) && (
        <div
          ref={lista}
          className={cn(
            "max-h-[26rem] space-y-2.5 overflow-y-auto pr-1",
            altezzaFissa && "lg:max-h-none lg:overflow-visible",
          )}
          aria-live="polite"
        >
          {voci.map((v, i) => (
            <div key={i} className="space-y-2">
              <div
                className={cn(
                  "w-fit max-w-[85%] whitespace-pre-line rounded-xl px-3 py-2 text-sm leading-relaxed",
                  v.role === "user"
                    ? "ml-auto bg-primary text-primary-foreground"
                    : "mr-auto border border-border bg-card text-foreground",
                )}
              >
                {v.content}
              </div>
              {v.card?.map((c) => (
                <CardCifraDettata key={c.id} card={c} onConferma={onConferma} onAnnulla={onAnnulla} />
              ))}
            </div>
          ))}
          {attesa && (
            <div className="mr-auto flex w-fit items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              <span>{attesa}</span>
            </div>
          )}
        </div>
      )}

      {suggerimenti && suggerimenti.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {/* Senza onSuggerimento (il Demo Tour) sono solo da leggere: non
              spente, che in vetrina sembrerebbe un prodotto rotto. */}
          {suggerimenti.map((s) =>
            onSuggerimento ? (
              <button
                key={s}
                type="button"
                onClick={() => onSuggerimento(s)}
                disabled={bloccato}
                className="rounded-full border border-primary/30 bg-card px-3 py-1 text-xs text-primary-text transition-colors hover:bg-primary/10 disabled:opacity-50"
              >
                {s}
              </button>
            ) : (
              <span key={s} className="rounded-full border border-primary/30 bg-card px-3 py-1 text-xs text-primary-text">
                {s}
              </span>
            ),
          )}
        </div>
      )}

      {/* Casella e contatore insieme: ad altezza fissa restano fermi in fondo mentre sopra
          scorrono briefing e messaggi. */}
      <div
        className={cn(
          "space-y-3",
          altezzaFissa && "lg:sticky lg:bottom-0 lg:z-10 lg:bg-background lg:pb-5 lg:pt-3",
        )}
      >
        <div className="flex items-end gap-2">
          <textarea
            value={valore}
            onChange={(e) => onCambia?.(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onInvia?.();
              }
            }}
            readOnly={!onCambia}
            rows={1}
            aria-label="Scrivi una domanda all'assistente"
            placeholder={placeholder}
            disabled={bloccato}
            className="max-h-24 flex-1 resize-none rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
          />
          <Button
            size="icon"
            className="size-9 shrink-0"
            disabled={bloccato || !valore.trim()}
            onClick={() => onInvia?.()}
            aria-label="Invia la domanda"
          >
            <Send className="size-4" />
          </Button>
        </div>

        <div className="flex items-center justify-between gap-2 text-[11px]">
          <span className={statoAvviso ? "text-incerto" : "text-muted-foreground"}>{stato}</span>
          {onNuova && voci.length > 0 && (
            <button
              type="button"
              onClick={onNuova}
              disabled={attesa !== null}
              className="inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
            >
              <SquarePen className="size-3.5" />
              Nuova conversazione
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
