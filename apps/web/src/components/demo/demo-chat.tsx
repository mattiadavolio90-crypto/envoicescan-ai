"use client";

import { useEffect, useRef, useState } from "react";
import { X, Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/brand/logo";
import { demoChatScambio, demoChatSuggerimenti } from "@/lib/demo-data";

// Chat AI del Demo Tour: stessa veste del ChatWidget reale (pannello, header con
// il contatore domande, bolle, pillola flottante), ma NIENTE fetch a /api/chat,
// niente sessionStorage, niente quota vera. Quando lo step chat è attivo il
// pannello si apre da solo e "recita" DUE scambi in sequenza: domanda →
// l'assistente pensa → risposta, poi il follow-up (il messaggio di trattativa
// preparato per il fornitore). Pillola e input restano inerti.

// Fase = quanti "eventi" della sceneggiatura sono avvenuti:
//   0 vuota · 1 domanda1 · 2 pensa1 · 3 risposta1 · 4 domanda2 · 5 pensa2 · 6 risposta2
type Fase = 0 | 1 | 2 | 3 | 4 | 5 | 6;

const TEMPI: { fase: Fase; ms: number }[] = [
  { fase: 1, ms: 500 },
  { fase: 2, ms: 1300 },
  { fase: 3, ms: 2900 },
  { fase: 4, ms: 5200 },
  { fase: 5, ms: 6000 },
  { fase: 6, ms: 7600 },
];

export function DemoChat({ open }: { open: boolean }) {
  const [fase, setFase] = useState<Fase>(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setFase(0);
      return;
    }
    const timers = TEMPI.map((t) => setTimeout(() => setFase(t.fase), t.ms));
    return () => timers.forEach(clearTimeout);
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [fase]);

  const [domanda1, risposta1, domanda2, risposta2] = demoChatScambio;
  const pensando = fase === 2 || fase === 5;
  const rimanenti = 15 - (fase >= 6 ? 2 : fase >= 3 ? 1 : 0);

  return (
    <div className="fixed bottom-6 right-6 z-30 flex flex-col items-end gap-3">
      {open && (
        // Altezza responsiva: su finestre basse il pannello non deve superare lo
        // spazio disponibile e finire sotto la barra-guida in alto. Cap a 420px ma
        // mai oltre l'altezza del viewport meno un margine per header+barra.
        <div
          data-demo-anchor="chat"
          className="flex h-[min(420px,calc(100svh-11rem))] w-[340px] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl"
        >
          {/* Header */}
          <div className="flex items-center gap-2.5 border-b bg-primary/5 px-4 py-3">
            <Logo variant="icon" size={20} className="shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold leading-none">Assistente ONEFLUX</p>
              <p className="text-[11px] mt-0.5 text-muted-foreground">
                Ti restano {rimanenti} domande oggi
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 text-muted-foreground pointer-events-none"
              aria-hidden
            >
              <X className="size-4" />
            </Button>
          </div>

          {/* Messaggi */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {fase === 0 && (
              <div className="flex flex-col items-center gap-3 py-6 text-center">
                <Logo variant="icon" size={32} className="opacity-40" />
                <p className="text-sm font-medium">Ciao! Sono il tuo assistente.</p>
                <p className="text-xs leading-relaxed text-muted-foreground max-w-[240px]">
                  Chiedimi dei tuoi costi, fornitori, food cost, margini o scadenze. Posso anche
                  confrontare i prezzi tra fornitori.
                </p>
                <div className="mt-1 flex flex-wrap justify-center gap-1.5">
                  {demoChatSuggerimenti.map((s) => (
                    <span
                      key={s}
                      className="rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] text-primary"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {fase >= 1 && <BollaUtente testo={domanda1.content} />}
            {fase >= 3 && <BollaAssistente testo={risposta1.content} />}
            {fase >= 4 && <BollaUtente testo={domanda2.content} />}
            {fase >= 6 && <BollaAssistente testo={risposta2.content} />}

            {pensando && (
              <div className="mr-auto flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                <span>{fase === 2 ? "Sto leggendo le tue fatture..." : "Preparo la bozza..."}</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input (inerte, solo veste) */}
          <div className="border-t px-3 py-2.5 flex items-end gap-2">
            <div className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm text-muted-foreground">
              Es. Qual è il mio food cost?
            </div>
            <Button size="icon" className="size-9 shrink-0 pointer-events-none" aria-hidden>
              <Send className="size-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Pillola flottante identica al prodotto */}
      <div
        className={cn(
          "flex items-center justify-center gap-2 rounded-full bg-primary text-primary-foreground shadow-lg",
          open ? "size-14" : "h-14 px-5",
        )}
        aria-hidden
      >
        {open ? (
          <X className="size-6" />
        ) : (
          <>
            <Logo variant="mono" size={26} className="shrink-0" />
            <span className="text-sm font-semibold whitespace-nowrap">Chiedi a ONEFLUX</span>
          </>
        )}
      </div>
    </div>
  );
}

function BollaUtente({ testo }: { testo: string }) {
  return (
    <div className="ml-auto max-w-[85%] rounded-xl bg-primary px-3 py-2 text-sm leading-relaxed text-primary-foreground animate-in fade-in slide-in-from-bottom-1 duration-300">
      {testo}
    </div>
  );
}

function BollaAssistente({ testo }: { testo: string }) {
  return (
    <div className="mr-auto max-w-[85%] rounded-xl bg-muted px-3 py-2 text-sm leading-relaxed text-foreground animate-in fade-in slide-in-from-bottom-1 duration-300">
      {testo}
    </div>
  );
}
