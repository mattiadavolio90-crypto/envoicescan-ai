"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  emailValida,
  etichettaPiva,
  etichettaRecupero,
  rigaStato,
  rigaUltimoInvio,
  testoAutorizzazione,
  type Frequenza,
  type StatoFattureCommercialista,
  type Tono,
  type VocePiva,
} from "@/lib/fatture-commercialista";

const CLASSE_TONO: Record<Tono, string> = {
  positivo: "text-positivo",
  incerto: "text-incerto",
  neutro: "text-muted-foreground",
};

// L'invio delle fatture al commercialista: lo attiva il titolare, e
// quell'attivazione e' il suo consenso. Collegamento a Invoicetronic e primo
// invio li fa il sistema.
export function FattureCommercialistaCard({ statoIniziale }: { statoIniziale: StatoFattureCommercialista }) {
  const [stato, setStato] = useState(statoIniziale);
  // Dopo router.refresh() la pagina rilegge lo stato dal server: lo si riprende,
  // altrimenti useState terrebbe quello vecchio.
  useEffect(() => setStato(statoIniziale), [statoIniziale]);
  const multiple = stato.pive.length > 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Fatture al commercialista</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">
          Inviamo al tuo commercialista le fatture che ricevi tramite OneFlux, nei file originali.
          Gli arriva un&apos;email con un link per scaricarle, valido 30 giorni.
        </p>
        {stato.pive.map((voce) => (
          <BloccoPiva
            key={voce.piva}
            voce={voce}
            stato={stato}
            conIntestazione={multiple}
            onStato={setStato}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function BloccoPiva({
  voce,
  stato,
  conIntestazione,
  onStato,
}: {
  voce: VocePiva;
  stato: StatoFattureCommercialista;
  conIntestazione: boolean;
  onStato: (s: StatoFattureCommercialista) => void;
}) {
  const [modifica, setModifica] = useState(!voce.attivo && !voce.sospeso);
  const [email, setEmail] = useState(voce.email ?? "");
  const [frequenza, setFrequenza] = useState<Frequenza>(voce.frequenza);
  const [includi, setIncludi] = useState(false);
  const [autorizzo, setAutorizzo] = useState(false);
  const [occupato, setOccupato] = useState(false);
  const [confermaSpegni, setConfermaSpegni] = useState(false);
  const router = useRouter();
  const riga = rigaStato(voce, stato.frequenze);
  const ultimo = rigaUltimoInvio(voce.ultimo_invio);
  const recupero = voce.attivo ? null : etichettaRecupero(voce);
  const emailOk = emailValida(email);

  async function invia(percorso: string, corpo: object, messaggio: string): Promise<boolean> {
    setOccupato(true);
    try {
      const res = await fetch(percorso, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(typeof data?.detail === "string" ? data.detail : "Non è andata: riprova più tardi.");
        // Le scritture sono tre: dopo un errore a metà la scheda mostrerebbe lo
        // stato di prima. Si rilegge dal server.
        router.refresh();
        return false;
      }
      onStato(data as StatoFattureCommercialista);
      toast.success(messaggio);
      return true;
    } catch {
      toast.error("Non è andata: riprova più tardi.");
      return false;
    } finally {
      setOccupato(false);
    }
  }

  async function attiva() {
    const ok = await invia(
      "/api/account/invio-commercialista",
      { piva: voce.piva, email, frequenza, autorizzo, includi_precedenti: includi },
      voce.attivo ? "Salvato" : "Invio al commercialista attivato",
    );
    if (ok) {
      setModifica(false);
      setAutorizzo(false);
      setIncludi(false);
    }
  }

  async function disattiva() {
    setConfermaSpegni(false);
    if (await invia("/api/account/invio-commercialista/disattiva", { piva: voce.piva }, "Invio disattivato")) {
      setModifica(true);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border p-3">
      {conIntestazione && <p className="font-medium">{etichettaPiva(voce)}</p>}
      <p className={CLASSE_TONO[riga.tono]}>{riga.testo}</p>
      {ultimo && <p className="text-muted-foreground">{ultimo}</p>}

      {!modifica && voce.attivo && (
        <div className="flex flex-wrap gap-2">
          {!voce.sospeso && (
            <Button size="sm" variant="outline" disabled={occupato} onClick={() => setModifica(true)}>
              Modifica
            </Button>
          )}
          {/* Anche da sospeso: il testo autorizzato promette che si disattiva in qualsiasi momento. */}
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => setConfermaSpegni(true)}>
            Disattiva
          </Button>
        </div>
      )}

      {modifica && !voce.sospeso && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor={`email-commercialista-${voce.piva}`}>Email del commercialista</Label>
              <Input
                id={`email-commercialista-${voce.piva}`}
                type="email"
                placeholder="studio@esempio.it"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`frequenza-commercialista-${voce.piva}`}>Ogni quanto</Label>
              <NativeSelect
                id={`frequenza-commercialista-${voce.piva}`}
                value={frequenza}
                onValueChange={(v) => setFrequenza(v as Frequenza)}
              >
                {(Object.keys(stato.frequenze) as Frequenza[]).map((f) => (
                  <option key={f} value={f}>{stato.frequenze[f]}</option>
                ))}
              </NativeSelect>
            </div>
          </div>
          {recupero && (
            <label className="flex items-start gap-2">
              <input type="checkbox" className="mt-0.5" checked={includi} onChange={(e) => setIncludi(e.target.checked)} />
              <span>{recupero}</span>
            </label>
          )}
          <label className="flex items-start gap-2 rounded-md bg-muted/50 p-2">
            <input type="checkbox" className="mt-0.5" checked={autorizzo} onChange={(e) => setAutorizzo(e.target.checked)} />
            <span>
              {testoAutorizzazione(stato.testo_autorizzazione, email, stato.frequenze[frequenza], voce.piva)}
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={occupato || !emailOk || !autorizzo} onClick={attiva}>
              {voce.attivo ? "Salva" : "Attiva"}
            </Button>
            {voce.attivo && (
              <Button size="sm" variant="outline" disabled={occupato} onClick={() => setModifica(false)}>
                Annulla
              </Button>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confermaSpegni}
        titolo="Disattivare l'invio al commercialista?"
        messaggio="Il commercialista non riceverà più le fatture. Puoi riattivarlo quando vuoi."
        confermaLabel="Disattiva"
        onConferma={disattiva}
        onClose={() => setConfermaSpegni(false)}
      />
    </div>
  );
}
