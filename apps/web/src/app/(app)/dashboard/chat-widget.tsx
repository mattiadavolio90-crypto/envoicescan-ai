"use client";

import { useEffect, useRef, useState } from "react";
import { X, Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/brand/logo";

type Msg = { role: "user" | "assistant"; content: string };

// Domande suggerite: guidano chi non sa cosa chiedere verso le cose utili.
const SUGGERIMENTI = [
  "Qual è il mio food cost?",
  "Cosa devo pagare?",
  "Com'è andato il MOL?",
  "Chi è il mio fornitore più caro?",
];

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll al fondo ad ogni nuovo messaggio
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus sull'input quando si apre
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

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
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Errore di connessione. Riprova." },
      ]);
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
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Pannello chat */}
      {open && (
        <div className="flex h-[420px] w-[340px] flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl">
          {/* Header */}
          <div className="flex items-center gap-2.5 border-b bg-primary/5 px-4 py-3">
            <Logo variant="icon" size={20} className="shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold leading-none">Assistente ONEFLUX</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Chiedimi dei tuoi dati</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 text-muted-foreground"
              onClick={() => setOpen(false)}
            >
              <X className="size-4" />
            </Button>
          </div>

          {/* Messaggi */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {messages.length === 0 && (
              <div className="flex flex-col items-center gap-3 py-6 text-center">
                <Logo variant="icon" size={32} className="opacity-40" />
                <p className="text-sm font-medium">Ciao! Sono il tuo assistente.</p>
                <p className="text-xs leading-relaxed text-muted-foreground max-w-[240px]">
                  Chiedimi dei tuoi costi, fornitori, food cost, margini o scadenze.
                  Posso anche confrontare i prezzi tra fornitori.
                </p>
                <div className="mt-1 flex flex-wrap justify-center gap-1.5">
                  {SUGGERIMENTI.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] text-primary transition-colors hover:bg-primary/10"
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
                  "max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed",
                  m.role === "user"
                    ? "ml-auto bg-primary text-primary-foreground"
                    : "mr-auto bg-muted text-foreground",
                )}
              >
                {m.content}
              </div>
            ))}
            {loading && (
              <div className="mr-auto flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                <span>Sto cercando...</span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="border-t px-3 py-2.5 flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Es. Qual è il mio food cost?"
              disabled={loading}
              className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              style={{ maxHeight: "80px", overflowY: "auto" }}
            />
            <Button
              size="icon"
              className="size-9 shrink-0"
              disabled={!input.trim() || loading}
              onClick={() => send()}
            >
              <Send className="size-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Bottone flottante: solo contorno (no riempimento) col logo ONEFLUX
          dentro, cosi' sembra che "ONEFLUX risponde". */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex size-14 items-center justify-center rounded-full border-2 border-primary bg-background text-primary shadow-lg transition-all",
          "hover:scale-105 hover:bg-primary/5 active:scale-95",
        )}
        aria-label={open ? "Chiudi chat" : "Apri assistente AI"}
      >
        {open ? <X className="size-6" /> : <Logo variant="icon" size={28} />}
      </button>
    </div>
  );
}
