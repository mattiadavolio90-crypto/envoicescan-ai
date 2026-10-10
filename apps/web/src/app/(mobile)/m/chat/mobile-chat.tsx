"use client";

import { useEffect, useRef } from "react";
import { Send, Loader2, SquarePen } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  domandeDalBriefing,
  mostraSuggerimenti,
  suggerimentiPer,
  type QuotaCrediti,
  type Vista,
} from "@/lib/home-chat";
import { Logo } from "@/components/brand/logo";
import { CardCifraDettata } from "@/components/home/card-cifra";
import { useConversazione } from "@/components/home/use-conversazione";

// La chat del telefono: stessa conversazione della Home (AssistenteProvider, nel
// layout di /m), stesse card con Conferma, stesse domande proposte. Cambia solo
// il disegno: altezza piena, input ancorato sopra la bottom nav.
export function MobileChat({
  vista,
  temi,
  settore,
  quota,
  lettoAlle,
}: {
  vista: Vista;
  /** Di cosa ha parlato il briefing della sede; assente (catena) = domande fisse. */
  temi?: readonly string[];
  settore?: string | null;
  quota: QuotaCrediti;
  lettoAlle: number;
}) {
  const c = useConversazione({ vista, quota, lettoAlle });
  const bottomRef = useRef<HTMLDivElement>(null);

  // Per numero di messaggi e non per elenco: `c.voci` e' un array nuovo a ogni
  // render, e lo scroll partiva a ogni tasto (su iOS la pagina saltava).
  const nVoci = c.voci.length;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [nVoci, c.attesa]);

  const suggerimenti =
    !c.esaurite && mostraSuggerimenti(c.voci, vista)
      ? vista.contesto === "sede" && temi?.length
        ? domandeDalBriefing(temi, settore, { registra: true })
        : suggerimentiPer(vista.contesto, settore)
      : [];

  return (
    // Altezza fissa = viewport meno header (56px) meno bottom-nav (~72px + safe area).
    // L'area messaggi scrolla, l'input resta ancorato sopra la bottom nav.
    <div
      className="flex flex-col"
      style={{ height: "calc(100dvh - 56px - 72px - env(safe-area-inset-bottom) - env(safe-area-inset-top))" }}
    >
      {/* Messaggi */}
      <div className="flex-1 space-y-3 overflow-y-auto pb-3">
        {c.voci.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-10 text-center">
            <Logo variant="icon" size={40} className="opacity-40" />
            <p className="text-base font-semibold">Ciao! Sono il tuo assistente.</p>
            <p className="max-w-[280px] text-sm leading-relaxed text-muted-foreground">
              {vista.contesto === "catena"
                ? "Chiedimi dei tuoi punti vendita: margini, spese, scadenze."
                : "Chiedimi dei tuoi costi, fornitori, food cost, margini o scadenze."}
            </p>
            <div className="mt-2 flex flex-col gap-2 self-stretch px-2">
              {suggerimenti.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => c.manda(s)}
                  disabled={c.bloccato}
                  className="rounded-xl border border-primary/30 bg-primary/5 px-4 py-2.5 text-sm text-primary-text active:scale-[0.98] disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {c.voci.map((m, i) => (
          <div key={i} className="space-y-2">
            <div
              className={cn(
                "max-w-[85%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                m.role === "user"
                  ? "ml-auto bg-primary text-primary-foreground"
                  : "mr-auto bg-muted text-foreground",
              )}
            >
              {m.content}
            </div>
            {m.card?.map((card) => (
              <CardCifraDettata key={card.id} card={card} onConferma={c.conferma} onAnnulla={c.annulla} />
            ))}
          </div>
        ))}
        {c.attesa && (
          <div className="mr-auto flex items-center gap-2 rounded-2xl bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            <span>{c.attesa}</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input ancorato */}
      <div className="space-y-1.5 border-t border-border pt-2.5">
        <div className="flex items-end gap-2">
          <textarea
            value={c.valore}
            onChange={(e) => c.setValore(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                c.manda(c.valore);
              }
            }}
            rows={1}
            aria-label="Scrivi una domanda all'assistente"
            placeholder={
              c.esaurite
                ? c.statoBreve
                : c.inAltraVista
                  ? "Sto rispondendo alla domanda che hai fatto in un'altra vista…"
                  : "Scrivi qui…"
            }
            disabled={c.bloccato}
            className="flex-1 resize-none rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
            style={{ maxHeight: "100px" }}
          />
          <button
            type="button"
            onClick={() => c.manda(c.valore)}
            disabled={!c.valore.trim() || c.bloccato}
            className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground active:scale-95 disabled:opacity-40"
            aria-label="Invia"
          >
            <Send className="size-5" />
          </button>
        </div>
        <div className="flex items-center justify-between gap-2 text-[11px]">
          <span className={c.esaurite ? "text-incerto" : "text-muted-foreground"}>{c.stato}</span>
          {c.voci.length > 0 && (
            <button
              type="button"
              onClick={c.nuova}
              disabled={c.attesa !== null}
              className="inline-flex items-center gap-1 text-muted-foreground active:text-foreground disabled:opacity-50"
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
