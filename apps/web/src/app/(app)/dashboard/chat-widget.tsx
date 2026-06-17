"use client";

import { useEffect, useRef, useState } from "react";
import { X, Send, Loader2, SquarePen } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/brand/logo";

type Msg = { role: "user" | "assistant"; content: string };

// Il backend accetta al massimo 20 messaggi (ChatRequest.max_length). Inviamo
// solo la coda piu' recente: senza questo, dopo ~20 scambi ogni invio falliva
// con 422 e l'utente vedeva un errore generico, senza piu' poter chattare.
// La UI conserva comunque l'intera conversazione a schermo.
const MAX_STORICO_INVIATO = 16;

// Domande suggerite: guidano chi non sa cosa chiedere verso le cose utili.
const SUGGERIMENTI = [
  "Qual è il mio food cost?",
  "Cosa devo pagare?",
  "Com'è andato il MOL?",
  "Chi è il mio fornitore più caro?",
];

// In modalità catena la chat parla del gruppo: suggerimenti dedicati.
const SUGGERIMENTI_CATENA = [
  "Quale punto vendita ha il margine peggiore?",
  "Dove si spende di più in pesce?",
  "Cosa c'è da vedere nella catena?",
  "Chi ha lo scontrino medio più alto?",
];

// La conversazione vive in sessionStorage: cosi' chiudere il pannello, ricaricare
// o un router.refresh() (es. l'auto-refresh della Home) non la cancella. Si
// svuota a fine sessione/logout — niente storico permanente, zero impatto privacy.
const STORAGE_KEY = "oneflux:chat-messages";

function caricaStorico(): Msg[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Validazione difensiva: tieni solo voci ben formate.
    return parsed.filter(
      (m): m is Msg =>
        m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    );
  } catch {
    return [];
  }
}

type ChatWidgetProps = {
  // Quota giornaliera per il piano (0 = chat non disponibile, gia' filtrata a monte).
  limiteGiorno: number;
  // Domande gia' consumate oggi all'apertura della Home (dal config).
  domandeOggiIniziali: number;
  // "catena" = chat della vista gruppo (tool di gruppo, pool AI). Default "sede".
  contesto?: "sede" | "catena";
};

export function ChatWidget({ limiteGiorno, domandeOggiIniziali, contesto = "sede" }: ChatWidgetProps) {
  const isCatena = contesto === "catena";
  const suggerimenti = isCatena ? SUGGERIMENTI_CATENA : SUGGERIMENTI;
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Messaggio d'attesa progressivo: l'assistente puo' impiegare diversi secondi
  // (legge le fatture, fa piu' giri di ricerca). Un testo fermo su "Sto cercando"
  // sembra un blocco; farlo avanzare comunica che sta lavorando davvero.
  const [attesa, setAttesa] = useState(0);
  // Domande consumate oggi: parte dal valore del config e si aggiorna ad ogni
  // risposta del backend (fonte di verita'), cosi' il contatore resta esatto
  // anche se l'utente ha chattato da un altro dispositivo.
  const [domandeOggi, setDomandeOggi] = useState(domandeOggiIniziali);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Lo storico si idrata solo dopo il mount (sessionStorage non esiste in SSR):
  // evita un mismatch di hydration tra server (vuoto) e client.
  const idratato = useRef(false);

  const rimanenti = Math.max(0, limiteGiorno - domandeOggi);
  const esaurite = rimanenti <= 0;

  // Carica la conversazione salvata al primo mount.
  useEffect(() => {
    const salvati = caricaStorico();
    if (salvati.length) setMessages(salvati);
    idratato.current = true;
  }, []);

  // Persisti la conversazione ad ogni cambiamento (dopo l'idratazione, per non
  // sovrascrivere lo storico con l'array vuoto iniziale).
  useEffect(() => {
    if (!idratato.current) return;
    try {
      if (messages.length) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* quota/Safari privato: la chat funziona comunque, solo senza persistenza */
    }
  }, [messages]);

  // Scroll al fondo ad ogni nuovo messaggio
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Fa avanzare il messaggio d'attesa mentre si carica; si azzera a fine richiesta.
  useEffect(() => {
    if (!loading) {
      setAttesa(0);
      return;
    }
    const t1 = setTimeout(() => setAttesa(1), 2500);
    const t2 = setTimeout(() => setAttesa(2), 6000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [loading]);

  // Focus sull'input quando si apre
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  async function send(testoParam?: string) {
    const testo = (testoParam ?? input).trim();
    if (!testo || loading || esaurite) return;

    const nuovi: Msg[] = [...messages, { role: "user", content: testo }];
    setMessages(nuovi);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nuovi.slice(-MAX_STORICO_INVIATO), contesto }),
      });
      const data = (await res.json()) as {
        reply?: string;
        error?: string;
        domande_oggi?: number;
        limite_giorno?: number;
      };
      // Sincronizza il contatore con la verita' del backend: la risposta porta
      // quante domande sono state consumate oggi (e il limite del piano).
      if (typeof data.domande_oggi === "number") {
        setDomandeOggi(data.domande_oggi);
      } else if (res.status === 429) {
        // Limite raggiunto: allinea il contatore a "esaurite".
        setDomandeOggi(limiteGiorno);
      }
      let reply: string;
      if (data.reply) {
        reply = data.reply;
      } else if (res.status === 429) {
        reply = data.error || "Hai raggiunto il limite di domande per oggi. Riprova domani.";
      } else if (res.status === 403) {
        reply = data.error || "La chat non è disponibile nel tuo piano attuale.";
      } else if (res.status === 504) {
        reply = "L'assistente ha impiegato troppo tempo. Riprova.";
      } else {
        reply = data.error || "Si è verificato un errore. Riprova.";
      }
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Errore di connessione. Controlla la rete e riprova." },
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
              <p
                className={cn(
                  "text-[11px] mt-0.5",
                  esaurite ? "text-amber-600 dark:text-amber-500" : "text-muted-foreground",
                )}
              >
                {esaurite
                  ? "Limite di oggi raggiunto — torna domani"
                  : `Ti restano ${rimanenti} ${rimanenti === 1 ? "domanda" : "domande"} oggi`}
              </p>
            </div>
            {messages.length > 0 && (
              <Button
                variant="ghost"
                size="icon"
                className="size-7 shrink-0 text-muted-foreground"
                onClick={() => setMessages([])}
                title="Nuova conversazione"
                aria-label="Nuova conversazione"
              >
                <SquarePen className="size-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 text-muted-foreground"
              onClick={() => setOpen(false)}
              aria-label="Chiudi chat"
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
                  {isCatena
                    ? "Chiedimi del confronto tra i punti vendita: margini, spesa, coperti e cosa c'è da tenere d'occhio."
                    : "Chiedimi dei tuoi costi, fornitori, food cost, margini o scadenze. Posso anche confrontare i prezzi tra fornitori."}
                </p>
                {!esaurite && (
                  <div className="mt-1 flex flex-wrap justify-center gap-1.5">
                    {suggerimenti.map((s) => (
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
                )}
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
                <span>
                  {attesa === 0
                    ? "Sto cercando..."
                    : attesa === 1
                      ? "Sto leggendo le tue fatture..."
                      : "Ci sono quasi, un attimo..."}
                </span>
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
              placeholder={esaurite ? "Limite di oggi raggiunto" : "Es. Qual è il mio food cost?"}
              disabled={loading || esaurite}
              className="flex-1 resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              style={{ maxHeight: "80px", overflowY: "auto" }}
            />
            <Button
              size="icon"
              className="size-9 shrink-0"
              disabled={!input.trim() || loading || esaurite}
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
