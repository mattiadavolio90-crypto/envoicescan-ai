"use client";

// Scena 3 (la rivelazione): la conversazione reale appare UN MESSAGGIO ALLA VOLTA,
// con indicatore "sta scrivendo" tra l'uno e l'altro. Il wow è nel RITMO, non nella
// grafica: se i messaggi comparissero insieme, la magia si perde (brief §5/§8).
// Parte quando la scena entra in viewport. Rispetta prefers-reduced-motion.

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";

export type ChatMsg = {
  da: "ai" | "user";
  testo: string;
  // dato sensibile (es. nome fornitore) da oscurare: reso come barretta sfocata
  // al posto del nome, stesso trattamento dei nomi nella slide variazioni prezzo.
  // `coda` = eventuale testo dopo la parte censurata (es. il punto finale).
  censura?: string;
  coda?: string;
};

// ms di "sta scrivendo" prima che il messaggio dell'AI compaia.
const TYPING_AI = 1400;
// ms di pausa prima che l'utente "scriva" il suo messaggio.
const PAUSA_USER = 700;

export function ChatScene({ sequenza }: { sequenza: readonly ChatMsg[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [avviato, setAvviato] = useState(false);
  const [n, setN] = useState(0); // quanti messaggi mostrati
  const [typing, setTyping] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // avvia quando la scena entra in viewport (una volta sola)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ridotto = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (ridotto) {
      setN(sequenza.length);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setAvviato(true);
          io.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [sequenza.length]);

  // orchestrazione dei messaggi a ritmo
  useEffect(() => {
    if (!avviato) return;
    const push = (fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      timers.current.push(t);
    };
    const passo = (i: number) => {
      if (i >= sequenza.length) return;
      const msg = sequenza[i];
      if (msg.da === "ai") {
        setTyping(true);
        push(() => {
          setTyping(false);
          setN(i + 1);
          push(() => passo(i + 1), 900);
        }, TYPING_AI);
      } else {
        push(() => {
          setN(i + 1);
          push(() => passo(i + 1), 900);
        }, PAUSA_USER);
      }
    };
    push(() => passo(0), 400);
    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [avviato, sequenza]);

  return (
    <div ref={ref} className="mx-auto w-full max-w-md">
      <div className="rounded-3xl border border-border bg-card/80 p-4 shadow-2xl ring-1 ring-primary/10 backdrop-blur-sm sm:p-5">
        {/* header chat */}
        <div className="mb-4 flex items-center gap-3 border-b border-border/60 pb-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-primary/10">
            <Logo variant="icon" size={20} />
          </span>
          <div className="text-left">
            <p className="text-sm font-semibold">Assistente ONEFLUX</p>
            <p className="text-xs text-emerald-400">● online</p>
          </div>
        </div>

        {/* messaggi */}
        <div className="flex min-h-[280px] flex-col justify-start gap-3">
          {sequenza.slice(0, n).map((m, i) => (
            <Bolla key={i} msg={m} />
          ))}
          {typing ? <TypingBubble /> : null}
        </div>
      </div>
    </div>
  );
}

function Bolla({ msg }: { msg: ChatMsg }) {
  const isUser = msg.da === "user";
  return (
    <div className={cn("flex items-end gap-2", isUser ? "justify-end" : "justify-start")}>
      {!isUser ? (
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Logo variant="icon" size={14} />
        </span>
      ) : null}
      <p
        className={cn(
          "max-w-[82%] animate-in fade-in slide-in-from-top-2 rounded-2xl px-4 py-2.5 text-left text-sm leading-relaxed duration-300",
          isUser
            ? "rounded-br-md bg-primary text-primary-foreground"
            : "rounded-bl-md border border-border bg-background/70",
        )}
      >
        {msg.testo}
        {msg.censura ? (
          <>
            {/* nome fornitore oscurato: barretta sfocata, dato sensibile non leggibile */}
            <span
              aria-label="dato oscurato"
              className="mx-0.5 select-none rounded bg-foreground/45 px-2 align-middle text-transparent blur-[3px]"
            >
              {msg.censura}
            </span>
            {msg.coda}
          </>
        ) : null}
      </p>
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="flex items-end gap-2">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <Logo variant="icon" size={14} />
      </span>
      <span className="flex items-center gap-1 rounded-2xl rounded-bl-md border border-border bg-background/70 px-4 py-3">
        <Dot d="0ms" />
        <Dot d="160ms" />
        <Dot d="320ms" />
      </span>
    </div>
  );
}

function Dot({ d }: { d: string }) {
  return (
    <span
      className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60"
      style={{ animationDelay: d }}
    />
  );
}
