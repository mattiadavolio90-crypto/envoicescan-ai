"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  type Configurazione, type Invio, type StatoInvioCommercialista, type Tono,
  ETICHETTA_STATO, ETICHETTA_TIPO, TONO_STATO,
  erroreDelPeriodo, formattaByte, formattaData, rigaConsenso, spostaGiorni,
  statoConfigurazione, testoMotivo,
} from "@/lib/invio-commercialista";

const CLASSE_TONO: Record<Tono, string> = {
  positivo: "text-positivo",
  negativo: "text-negativo",
  incerto: "text-incerto",
  neutro: "text-muted-foreground",
};

type Chiarimento = { cfg: string; invio: Invio; esito: "arrivata" | "non_arrivata" };
type RichiestaPeriodo = { config: Configurazione; tipo: "prova" | "reinvio"; dal: string; al: string };
type Chiama = (path: string, metodo: "POST" | "PATCH", body?: object, ok?: string) => Promise<boolean>;

async function leggi(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || "Errore");
  return data;
}

// Scheda cliente → «Invio al commercialista». L'invio lo attiva il cliente dalle
// sue Impostazioni (e' il suo consenso); qui l'admin vede chi, quando e per chi,
// prova a vuoto, reinvia, spegne in emergenza. Ogni pulsante scrive una richiesta:
// l'esecutore del queue-worker la prende entro un minuto, e il registro qui
// sotto si aggiorna da solo finche' c'e' un invio in coda o in corso.
export function InvioCommercialistaCard({ clienteId }: { clienteId: string }) {
  const base = `/api/admin/clienti/${clienteId}/invio-commercialista`;
  const [dati, setDati] = useState<StatoInvioCommercialista | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [occupato, setOccupato] = useState(false);
  const [periodo, setPeriodo] = useState<RichiestaPeriodo | null>(null);
  const [chiarimento, setChiarimento] = useState<Chiarimento | null>(null);

  const carica = useCallback(async () => {
    try {
      setDati(await leggi(await fetch(base, { cache: "no-store" })));
      setErrore(null);
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore");
    }
  }, [base]);

  useEffect(() => {
    carica();
  }, [carica]);

  const inVolo = dati?.configurazioni.some((c) => c.invii.some((i) => i.stato === "richiesto" || i.stato === "in_corso")) ?? false;
  useEffect(() => {
    if (!inVolo) return;
    const timer = setInterval(carica, 15000);
    return () => clearInterval(timer);
  }, [inVolo, carica]);

  const chiama: Chiama = async (path, metodo, body, ok) => {
    setOccupato(true);
    try {
      await leggi(await fetch(`${base}${path}`, {
        method: metodo,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      }));
      if (ok) toast.success(ok);
      await carica();
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
      return false;
    } finally {
      setOccupato(false);
    }
  };

  // Prova a vuoto su una P.IVA che il cliente non ha ancora attivato: prima la
  // si collega a Invoicetronic (il company_id lo trova il worker), poi si chiede
  // il periodo.
  async function provaSenzaConfigurazione(piva: string) {
    setOccupato(true);
    try {
      const config = await leggi(await fetch(base, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ piva }),
      }));
      await carica();
      const oggiIso = dati?.oggi ?? "";
      setPeriodo({ config, tipo: "prova", dal: spostaGiorni(oggiIso, -30), al: spostaGiorni(oggiIso, -1) });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setOccupato(false);
    }
  }

  const oggi = dati?.oggi ?? "";
  const erroreRichiesta = periodo ? erroreDelPeriodo(periodo.dal, periodo.al, oggi) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Invio al commercialista</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {errore && <p className="text-negativo">{errore}</p>}
        {!dati && !errore && <p className="text-muted-foreground">Caricamento…</p>}
        {dati && dati.configurazioni.length === 0 && dati.piva_disponibili.length === 0 && (
          <p className="text-muted-foreground">Nessuna sede di questo cliente ha una P.IVA di 11 cifre.</p>
        )}
        {dati?.piva_disponibili.map((piva) => (
          <div key={piva} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2">
            <div>
              <p className="tabular-nums">P.IVA {piva}</p>
              <p className="text-muted-foreground">Il cliente non l&apos;ha attivato dalle sue Impostazioni</p>
            </div>
            <Button size="sm" variant="outline" disabled={occupato} onClick={() => provaSenzaConfigurazione(piva)}>
              Prova a vuoto
            </Button>
          </div>
        ))}
        {dati?.configurazioni.map((c) => (
          <BloccoConfigurazione
            key={`${c.id}-${c.aggiornata_at}`}
            c={c}
            occupato={occupato}
            chiama={chiama}
            onPeriodo={(tipo) => setPeriodo({
              config: c,
              tipo,
              dal: tipo === "prova" ? spostaGiorni(oggi, -30) : (c.ultimo_giorno_inviato ?? spostaGiorni(oggi, -1)),
              al: tipo === "prova" ? spostaGiorni(oggi, -1) : (c.ultimo_giorno_inviato ?? spostaGiorni(oggi, -1)),
            })}
            onChiarisci={(invio, esito) => setChiarimento({ cfg: `/${c.id}`, invio, esito })}
          />
        ))}
      </CardContent>

      <Dialog open={periodo !== null} onOpenChange={(v) => !v && setPeriodo(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{periodo?.tipo === "prova" ? "Prova a vuoto" : "Reinvio"}</DialogTitle>
            <DialogDescription>
              {periodo?.tipo === "prova"
                ? "Scarica, controlla e prepara lo ZIP, poi si ferma: nessuna email, nessun link. Nel registro restano le misure."
                : `Rispedisce al commercialista un periodo già inviato${periodo?.config.ultimo_giorno_inviato ? ` (fino al ${formattaData(periodo.config.ultimo_giorno_inviato)})` : ""}.`}
            </DialogDescription>
          </DialogHeader>
          {periodo && (
            <div className="grid grid-cols-2 gap-3 py-2">
              <div className="space-y-1.5">
                <Label htmlFor="periodo-dal">Dal</Label>
                <Input id="periodo-dal" type="date" value={periodo.dal} onChange={(e) => setPeriodo({ ...periodo, dal: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="periodo-al">Al</Label>
                <Input id="periodo-al" type="date" value={periodo.al} onChange={(e) => setPeriodo({ ...periodo, al: e.target.value })} />
              </div>
              {erroreRichiesta && <p className="col-span-2 text-negativo">{erroreRichiesta}</p>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPeriodo(null)}>Annulla</Button>
            <Button
              disabled={occupato || erroreRichiesta !== null}
              onClick={async () => {
                if (periodo && await chiama(`/${periodo.config.id}/invii`, "POST",
                  { tipo: periodo.tipo, dal: periodo.dal, al: periodo.al }, "Richiesta registrata")) {
                  setPeriodo(null);
                }
              }}
            >
              {periodo?.tipo === "prova" ? "Avvia la prova" : "Reinvia"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={chiarimento !== null} onOpenChange={(v) => !v && setChiarimento(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{chiarimento?.esito === "arrivata" ? "L'email è arrivata" : "L'email non è arrivata"}</DialogTitle>
            <DialogDescription>
              {chiarimento?.esito === "arrivata"
                ? "Il periodo resta inviato e l'invio automatico riparte dal giorno dopo. Solo se nei log di Brevo risulta consegnata."
                : "Il periodo torna da inviare: il prossimo invio lo rispedisce. Solo se nei log di Brevo risulta non partita o rifiutata: se è arrivata, il commercialista riceverebbe le stesse fatture due volte."}
            </DialogDescription>
          </DialogHeader>
          {chiarimento && (
            <p className="py-2">
              {ETICHETTA_TIPO[chiarimento.invio.tipo]} del periodo {formattaData(chiarimento.invio.periodo_dal)} – {formattaData(chiarimento.invio.periodo_al)}.
              Non si torna indietro.
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setChiarimento(null)}>Annulla</Button>
            <Button
              disabled={occupato}
              onClick={async () => {
                if (chiarimento && await chiama(`${chiarimento.cfg}/invii/${chiarimento.invio.id}/chiarisci`, "POST",
                  { esito: chiarimento.esito }, chiarimento.esito === "arrivata" ? "Segnato come arrivato" : "Il periodo si rispedirà")) {
                  setChiarimento(null);
                }
              }}
            >
              Conferma
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </Card>
  );
}

function BloccoConfigurazione({ c, occupato, chiama, onPeriodo, onChiarisci }: {
  c: Configurazione;
  occupato: boolean;
  chiama: Chiama;
  onPeriodo: (tipo: "prova" | "reinvio") => void;
  onChiarisci: (invio: Invio, esito: "arrivata" | "non_arrivata") => void;
}) {
  const stato = statoConfigurazione(c);
  const consenso = rigaConsenso(c);
  const occupata = c.invii.some((i) => i.stato === "richiesto" || i.stato === "in_corso" || i.stato === "esito_incerto");
  const cfg = `/${c.id}`;

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div>
        <p className="font-medium">{c.invoicetronic_nome || "—"}</p>
        <p className="text-xs text-muted-foreground tabular-nums">
          P.IVA {c.piva} · azienda Invoicetronic {c.invoicetronic_company_id ?? "—"}
        </p>
        <p className={`mt-1 ${CLASSE_TONO[stato.tono]}`}>{stato.testo}</p>
        {consenso && <p className="mt-1 text-muted-foreground">{consenso}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t pt-3">
        {c.attivo && (
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => chiama(cfg, "PATCH", { attivo: false }, "Spento")}>
            Spegni
          </Button>
        )}
        {c.sospesa_at && (
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => chiama(cfg, "PATCH", { riprendi: true }, "Ripresa")}>
            Riprendi dopo la verifica
          </Button>
        )}
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={occupato || occupata} onClick={() => onPeriodo("prova")}>
            Prova a vuoto
          </Button>
          <Button size="sm" variant="outline" disabled={occupato || occupata || !c.ultimo_giorno_inviato} onClick={() => onPeriodo("reinvio")}>
            Reinvio
          </Button>
        </div>
      </div>

      {c.invii.length > 0 && (
        <div className="space-y-1.5 border-t pt-3">
          <p className="text-xs font-medium text-muted-foreground">Registro (ultimi {c.invii.length})</p>
          {c.invii.map((i) => (
            <RigaRegistro key={i.id} i={i} occupato={occupato} chiama={chiama} cfg={cfg} onChiarisci={onChiarisci} />
          ))}
        </div>
      )}
    </div>
  );
}

function RigaRegistro({ i, occupato, chiama, cfg, onChiarisci }: {
  i: Invio;
  occupato: boolean;
  chiama: Chiama;
  cfg: string;
  onChiarisci: (invio: Invio, esito: "arrivata" | "non_arrivata") => void;
}) {
  const motivo = testoMotivo(i.motivo);
  return (
    <div className="rounded-md border px-2.5 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-medium">{ETICHETTA_TIPO[i.tipo]}</span>
        <span className="tabular-nums text-muted-foreground">
          {formattaData(i.periodo_dal)} – {formattaData(i.periodo_al)}
        </span>
        <span className={CLASSE_TONO[TONO_STATO[i.stato]]}>{ETICHETTA_STATO[i.stato]}</span>
        {i.n_file != null && (
          <span className="text-muted-foreground">{i.n_file} file · {formattaByte(i.byte_totali)}</span>
        )}
        <span className="ml-auto text-muted-foreground">
          {i.richiesto_da === "notturno" ? "notte" : "admin"} · {formattaData(i.creata_at)}
        </span>
      </div>
      {motivo && <p className="mt-1 text-muted-foreground">{motivo}</p>}
      {i.stato === "esito_incerto" && (
        <div className="mt-1.5 flex gap-2">
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => onChiarisci(i, "arrivata")}>
            È arrivata
          </Button>
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => onChiarisci(i, "non_arrivata")}>
            Non è arrivata
          </Button>
        </div>
      )}
      {i.stato === "richiesto" && (
        <Button size="sm" variant="ghost" className="mt-1.5" disabled={occupato} onClick={() => chiama(`${cfg}/invii/${i.id}/annulla`, "POST", undefined, "Annullato")}>
          Annulla
        </Button>
      )}
    </div>
  );
}
