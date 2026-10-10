"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { leggiRicariche, rigaRicarica, testoResiduo, type RicaricheAi } from "@/lib/ricariche-ai";
import { fmtCrediti } from "@/lib/home-chat";

// Boost AI (fase J): Mattia attiva a mano la ricarica dopo la richiesta del
// cliente fra i Servizi. Non si annulla da qui (una ricarica gia' spesa in parte
// non ha un «indietro» pulito): per questo c'e' la conferma.
export function RicaricheAiCliente({ clienteId }: { clienteId: string }) {
  const [stato, setStato] = useState<RicaricheAi | null>(null);
  const [aperto, setAperto] = useState(false);
  const [nota, setNota] = useState("");
  const [invio, setInvio] = useState(false);
  const url = `/api/admin/clienti/${clienteId}/ricariche-ai`;

  useEffect(() => {
    let vivo = true;
    fetch(url)
      .then((r) => r.json())
      .then((d) => { if (vivo) setStato(leggiRicariche(d)); })
      .catch(() => { if (vivo) setStato(null); });
    return () => { vivo = false; };
  }, [url]);

  async function conferma() {
    setInvio(true);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nota: nota.trim() }),
      });
      const d = await res.json().catch(() => null);
      const letto = res.ok ? leggiRicariche(d) : null;
      if (!letto) throw new Error((d && d.detail) || "Ricarica non registrata");
      setStato(letto);
      setAperto(false);
      setNota("");
      toast.success("Ricarica AI aggiunta");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setInvio(false);
    }
  }

  const boost = stato?.crediti_boost ?? 300;
  return (
    <div className="space-y-2 border-t pt-3">
      <Button variant="outline" className="w-full justify-start" onClick={() => setAperto(true)} disabled={!stato}>
        <Zap className="size-4 mr-2" /> Aggiungi ricarica AI ({fmtCrediti(boost)} crediti)
      </Button>
      {stato && <p className="text-xs text-muted-foreground">{testoResiduo(stato)}</p>}
      {stato && stato.ricariche.length > 0 && (
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {stato.ricariche.slice(0, 5).map((r) => <li key={r.id}>{rigaRicarica(r)}</li>)}
        </ul>
      )}
      <Dialog open={aperto} onOpenChange={(v) => { if (!invio) setAperto(v); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Aggiungi ricarica AI</DialogTitle>
            <DialogDescription>
              {fmtCrediti(boost)} crediti in più per l&apos;assistente del cliente (Boost AI, 10€). Non scadono e si
              usano quando finiscono quelli del mese. Non si può annullare da qui.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="ricarica-nota">Nota (facoltativa)</Label>
            <Input
              id="ricarica-nota"
              value={nota}
              maxLength={200}
              placeholder="es. pagata con bonifico il 10/10"
              onChange={(e) => setNota(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAperto(false)} disabled={invio}>Annulla</Button>
            <Button onClick={conferma} disabled={invio}>Aggiungi {fmtCrediti(boost)} crediti</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
