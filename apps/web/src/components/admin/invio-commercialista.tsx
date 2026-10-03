"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  type Frequenza, type StatoInvioCommercialista, type Tono, type VocePiva,
  azioneRiga, emailValida, etichettaPiva, rigaAttivazione, rigaStato, rigaUltimoInvio,
} from "@/lib/invio-commercialista";

const CLASSE_TONO: Record<Tono, string> = {
  positivo: "text-positivo",
  negativo: "text-negativo",
  incerto: "text-incerto",
  neutro: "text-muted-foreground",
};

type Chiama = (path: string, body: object, ok: string) => Promise<boolean>;

// Scheda cliente → «Invio al commercialista». Lo attiva l'admin, su richiesta del
// cliente: una riga per P.IVA (il commercialista segue la societa', non il
// locale), email + ogni quanto + Attiva. Il resto lo fa il sistema.
export function InvioCommercialistaCard({ clienteId }: { clienteId: string }) {
  const base = `/api/admin/clienti/${clienteId}/invio-commercialista`;
  const [dati, setDati] = useState<StatoInvioCommercialista | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [occupato, setOccupato] = useState(false);

  const carica = useCallback(async () => {
    try {
      const res = await fetch(base, { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.error || "Errore");
      setDati(data);
      setErrore(null);
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore");
    }
  }, [base]);

  useEffect(() => {
    carica();
  }, [carica]);

  const chiama: Chiama = async (path, body, ok) => {
    setOccupato(true);
    try {
      const res = await fetch(`${base}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.error || "Errore");
      setDati(data);
      toast.success(ok);
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
      // Le scritture sono piu' d'una: dopo un errore a meta' si rilegge lo stato.
      await carica();
      return false;
    } finally {
      setOccupato(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Invio al commercialista</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {errore && <p className="text-negativo">{errore}</p>}
        {!dati && !errore && <p className="text-muted-foreground">Caricamento…</p>}
        {dati && !dati.interruttore && (
          <p className="text-incerto">
            Interruttore generale spento (INVIO_COMMERCIALISTA_ATTIVO): puoi attivare, ma non parte niente finché non si accende.
          </p>
        )}
        {dati && dati.pive.length === 0 && (
          <p className="text-muted-foreground">Nessuna sede di questo cliente riceve fatture tramite SDI.</p>
        )}
        {dati?.pive.map((v) => (
          <RigaPiva
            key={`${v.piva}-${v.attivo}-${v.email ?? ""}-${v.frequenza}`}
            v={v}
            frequenze={dati.frequenze}
            intestazione={dati.pive.length > 1}
            occupato={occupato}
            chiama={chiama}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function RigaPiva({ v, frequenze, intestazione, occupato, chiama }: {
  v: VocePiva;
  frequenze: Record<Frequenza, string>;
  intestazione: boolean;
  occupato: boolean;
  chiama: Chiama;
}) {
  const [email, setEmail] = useState(v.email ?? "");
  const [frequenza, setFrequenza] = useState<Frequenza>(v.frequenza);
  const [conferma, setConferma] = useState<"disattiva" | "arrivata" | "non_arrivata" | null>(null);
  const azione = azioneRiga(v);
  const stato = rigaStato(v, frequenze);
  const attivazione = rigaAttivazione(v);
  const ultimo = rigaUltimoInvio(v.ultimo_invio);

  return (
    <div className="space-y-2 rounded-lg border p-3">
      {intestazione && <p className="font-medium">{etichettaPiva(v)}</p>}
      <p className={CLASSE_TONO[stato.tono]}>{stato.testo}</p>
      {attivazione && <p className="text-xs text-muted-foreground">{attivazione}</p>}
      {ultimo && <p className="text-xs text-muted-foreground">{ultimo}</p>}

      {v.da_chiarire && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => setConferma("arrivata")}>
            È arrivata
          </Button>
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => setConferma("non_arrivata")}>
            Non è arrivata
          </Button>
        </div>
      )}

      {azione !== "nessuna" && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-56 flex-1 space-y-1.5">
            <Label htmlFor={`email-${v.piva}`}>Email o PEC del commercialista</Label>
            <Input id={`email-${v.piva}`} type="email" placeholder="studio@esempio.it" value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`frequenza-${v.piva}`}>Ogni quanto</Label>
            <NativeSelect id={`frequenza-${v.piva}`} value={frequenza} onValueChange={(f) => setFrequenza(f as Frequenza)}>
              {(Object.keys(frequenze) as Frequenza[]).map((f) => (
                <option key={f} value={f}>{frequenze[f]}</option>
              ))}
            </NativeSelect>
          </div>
          <Button size="sm" disabled={occupato || !emailValida(email)}
            onClick={() => chiama("/attiva", { piva: v.piva, email, frequenza }, azione === "modifica" ? "Salvato" : "Invio attivato")}>
            {azione === "modifica" ? "Salva" : "Attiva"}
          </Button>
          {azione === "modifica" && (
            <Button size="sm" variant="outline" disabled={occupato} onClick={() => setConferma("disattiva")}>
              Disattiva
            </Button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={conferma !== null}
        titolo={conferma === "disattiva" ? "Disattivare l'invio?" : conferma === "arrivata" ? "L'email è arrivata?" : "L'email non è arrivata?"}
        messaggio={conferma === "disattiva"
          ? "Il commercialista non riceverà più le fatture di questa P.IVA. Se lo riattivi, riparte dalle fatture arrivate da quel giorno: quelle del periodo spento non vengono inviate. Per cambiare solo l'email usa Salva."
          : conferma === "arrivata"
            ? "Solo se nei log di Brevo risulta consegnata: il periodo resta inviato e si riparte dal giorno dopo."
            : "Solo se nei log di Brevo risulta non partita o rifiutata: il periodo torna da inviare, e se fosse arrivata il commercialista lo riceverebbe due volte."}
        confermaLabel={conferma === "disattiva" ? "Disattiva" : "Conferma"}
        onConferma={async () => {
          const scelta = conferma;
          setConferma(null);
          if (scelta === "disattiva") await chiama("/disattiva", { piva: v.piva }, "Invio disattivato");
          else if (scelta && v.da_chiarire) {
            await chiama(`/invii/${v.da_chiarire.id}/chiarisci`, { esito: scelta }, "Fatto");
          }
        }}
        onClose={() => setConferma(null)}
      />
    </div>
  );
}
