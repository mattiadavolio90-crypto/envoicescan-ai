"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGERIMENTI = [
  "Qual è il mio food cost?",
  "Cosa devo pagare?",
  "Com'è andato il MOL?",
  "Chi è il mio fornitore più caro?",
];

export function MobileChat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(testoParam?: string) {
    const testo = (testoParam ?? input).trim();
    if (!testo || loading) return;

    const nuovi: Msg[] = [...messages, { role: "user", content: testo }];
    setMessages(nuovi);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nuovi }),
      });
      const data = (await res.json()) as { reply?: string; error?: string };
      const reply = data.reply || data.error || "Non ho capito, riprova.";
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Errore di connessione. Riprova." }]);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    // Altezza fissa = viewport meno header (56px) meno bottom-nav (~72px + safe area).
    // L'area messaggi scrolla, l'input resta ancorato sopra la bottom nav.
    <div
      className="flex flex-col"
      style={{ height: "calc(100dvh - 56px - 72px - env(safe-area-inset-bottom) - env(safe-area-inset-top))" }}
    >
      {/* Messaggi */}
      <div className="flex-1 space-y-3 overflow-y-auto pb-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-10 text-center">
            <Logo variant="icon" size={40} className="opacity-40" />
            <p className="text-base font-semibold">Ciao! Sono il tuo assistente.</p>
            <p className="max-w-[280px] text-sm leading-relaxed text-muted-foreground">
              Chiedimi dei tuoi costi, fornitori, food cost, margini o scadenze.
            </p>
            <div className="mt-2 flex flex-col gap-2 self-stretch px-2">
              {SUGGERIMENTI.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="rounded-xl border border-primary/30 bg-primary/5 px-4 py-2.5 text-sm text-primary active:scale-[0.98]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={cn(
              "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
              m.role === "user"
                ? "ml-auto bg-primary text-primary-foreground"
                : "mr-auto bg-muted text-foreground",
            )}
          >
            {m.content}
          </div>
        ))}
        {loading && (
          <div className="mr-auto flex items-center gap-2 rounded-2xl bg-muted px-3.5 py-2.5 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            <span>Sto cercando…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input ancorato */}
      <div className="flex items-end gap-2 border-t border-border pt-2.5">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Scrivi qui…"
          disabled={loading}
          className="flex-1 resize-none rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
          style={{ maxHeight: "100px" }}
        />
        <button
          onClick={() => send()}
          disabled={!input.trim() || loading}
          className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground active:scale-95 disabled:opacity-40"
          aria-label="Invia"
        >
          <Send className="size-5" />
        </button>
      </div>
    </div>
  );
}
