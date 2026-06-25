"use client";

// Demo "viva" dell'assistente: la barra del chiedi si digita da sola, l'AI
// "sta scrivendo…" e poi risponde, in loop sulle domande. È scriptata (nessun
// backend), ma comunica dal vivo il vero differenziatore: con ONEFLUX si parla.
// Rispetta prefers-reduced-motion: se l'utente lo chiede, mostra tutto fermo.

import { useEffect, useRef, useState } from "react";
import { Sparkles, Send } from "lucide-react";

import { Logo } from "@/components/brand/logo";

export type DemoScambio = { q: string; a: string };

type Fase = "typing" | "thinking" | "answering" | "hold";

const VEL_DIGITAZIONE = 45; // ms per carattere domanda
const VEL_RISPOSTA = 16; // ms per carattere risposta
const PAUSA_PENSIERO = 900; // ms "sta scrivendo…"
const PAUSA_LETTURA = 2600; // ms con la risposta visibile prima di cambiare

export function ChatDemo({ scambi }: { scambi: readonly DemoScambio[] }) {
  const [idx, setIdx] = useState(0);
  const [fase, setFase] = useState<Fase>("typing");
  const [domanda, setDomanda] = useState("");
  const [risposta, setRisposta] = useState("");
  const ridotto = useRef(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const corrente = scambi[idx];

  useEffect(() => {
    ridotto.current =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const push = (fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      timers.current.push(t);
      return t;
    };
    const clearAll = () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };

    clearAll();

    // Movimento ridotto: niente animazione, mostra domanda+risposta complete.
    if (ridotto.current) {
      setDomanda(corrente.q);
      setRisposta(corrente.a);
      setFase("hold");
      push(() => setIdx((i) => (i + 1) % scambi.length), 5000);
      return clearAll;
    }

    setDomanda("");
    setRisposta("");
    setFase("typing");

    // 1) digita la domanda carattere per carattere
    let i = 0;
    const digita = () => {
      i += 1;
      setDomanda(corrente.q.slice(0, i));
      if (i < corrente.q.length) {
        push(digita, VEL_DIGITAZIONE);
      } else {
        push(() => setFase("thinking"), 350);
      }
    };
    push(digita, 500);

    return clearAll;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  // transizioni dopo "thinking" e "answering"
  useEffect(() => {
    if (ridotto.current) return;
    const push = (fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      timers.current.push(t);
    };

    if (fase === "thinking") {
      push(() => setFase("answering"), PAUSA_PENSIERO);
    }

    if (fase === "answering") {
      let j = 0;
      const scrivi = () => {
        j += 1;
        setRisposta(corrente.a.slice(0, j));
        if (j < corrente.a.length) {
          push(scrivi, VEL_RISPOSTA);
        } else {
          push(() => setFase("hold"), PAUSA_LETTURA);
        }
      };
      push(scrivi, 0);
    }

    if (fase === "hold") {
      push(() => setIdx((i) => (i + 1) % scambi.length), 200);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fase]);

  const mostraRisposta = fase === "answering" || fase === "hold";

  return (
    <div className="mx-auto max-w-xl">
      {/* barra del chiedi: la domanda si scrive qui dentro */}
      <div className="flex items-center gap-2 rounded-2xl border border-border bg-card p-2 pl-4 shadow-xl ring-1 ring-foreground/5">
        <Sparkles className="size-5 shrink-0 text-primary" />
        <span className="flex-1 truncate text-left text-base">
          {domanda ? (
            <span className="text-foreground">{domanda}</span>
          ) : (
            <span className="text-muted-foreground">Chiedi qualsiasi cosa sui tuoi numeri…</span>
          )}
          {fase === "typing" ? (
            <span className="ml-0.5 inline-block h-5 w-px translate-y-1 animate-pulse bg-primary align-middle" />
          ) : null}
        </span>
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Send className="size-4" />
        </span>
      </div>

      {/* area risposta: "sta scrivendo…" poi la risposta dell'AI */}
      <div className="mt-3 min-h-[92px]">
        {fase === "thinking" ? (
          <div className="flex items-center gap-2.5">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Logo variant="icon" size={14} />
            </span>
            <span className="flex items-center gap-1 rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3">
              <Dot delay="0ms" />
              <Dot delay="160ms" />
              <Dot delay="320ms" />
            </span>
          </div>
        ) : null}

        {mostraRisposta ? (
          <div className="flex items-start gap-2.5">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
              <Logo variant="icon" size={14} />
            </span>
            <p className="max-w-[88%] rounded-2xl rounded-bl-md border border-border bg-card px-4 py-3 text-left text-sm leading-relaxed shadow-sm">
              {risposta}
              {fase === "answering" ? (
                <span className="ml-0.5 inline-block h-4 w-px translate-y-0.5 animate-pulse bg-primary align-middle" />
              ) : null}
            </p>
          </div>
        ) : null}
      </div>

      {/* indicatore: quale domanda del giro */}
      <div className="mt-4 flex justify-center gap-1.5" aria-hidden>
        {scambi.map((s, i) => (
          <span
            key={s.q}
            className={
              "h-1.5 rounded-full transition-all duration-300 " +
              (i === idx ? "w-6 bg-primary" : "w-1.5 bg-border")
            }
          />
        ))}
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60"
      style={{ animationDelay: delay }}
    />
  );
}
