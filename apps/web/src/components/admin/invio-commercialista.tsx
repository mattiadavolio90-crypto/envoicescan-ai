"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { NativeSelect } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  type Configurazione, type Frequenza, type Invio, type StatoInvioCommercialista, type Tono,
  ETICHETTA_FREQUENZA, ETICHETTA_STATO, ETICHETTA_TIPO, TONO_STATO,
  erroreDelPeriodo, formattaByte, formattaData, periodoInviaOra, spostaGiorni, statoConfigurazione, testoMotivo,
} from "@/lib/invio-commercialista";

const CLASSE_TONO: Record<Tono, string> = {
  positivo: "text-positivo",
  negativo: "text-negativo",
  incerto: "text-incerto",
  neutro: "text-muted-foreground",
};

type Azienda = { piva: string; company_id: number; nome: string | null; vat: string | null; gia_viste: number[] };
type RichiestaPeriodo = { config: Configurazione; tipo: "prova" | "reinvio"; dal: string; al: string };
type Chiama = (path: string, metodo: "POST" | "PATCH", body?: object, ok?: string) => Promise<boolean>;

async function leggi(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || "Errore");
  return data;
}

// Scheda cliente → «Invio al commercialista». Ogni pulsante scrive una richiesta:
// l'esecutore del queue-worker la prende entro un minuto, e il registro qui
// sotto si aggiorna da solo finche' c'e' un invio in coda o in corso.
export function InvioCommercialistaCard({ clienteId }: { clienteId: string }) {
  const base = `/api/admin/clienti/${clienteId}/invio-commercialista`;
  const [dati, setDati] = useState<StatoInvioCommercialista | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [occupato, setOccupato] = useState(false);
  const [azienda, setAzienda] = useState<Azienda | null>(null);
  const [periodo, setPeriodo] = useState<RichiestaPeriodo | null>(null);
  const [inviaOra, setInviaOra] = useState<Configurazione | null>(null);

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

  async function cercaAzienda(piva: string) {
    setOccupato(true);
    try {
      setAzienda({ piva, ...(await leggi(await fetch(`${base}/azienda?piva=${piva}`, { cache: "no-store" }))) });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setOccupato(false);
    }
  }

  const oggi = dati?.oggi ?? "";
  const erroreRichiesta = periodo ? erroreDelPeriodo(periodo.dal, periodo.al, oggi) : null;
  const periodoOra = inviaOra ? periodoInviaOra(inviaOra, oggi) : null;

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
          <div key={piva} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2">
            <span className="tabular-nums">P.IVA {piva}</span>
            <Button size="sm" variant="outline" disabled={occupato} onClick={() => cercaAzienda(piva)}>
              Collega a Invoicetronic
            </Button>
          </div>
        ))}
        {dati?.configurazioni.map((c) => (
          <BloccoConfigurazione
            key={`${c.id}-${c.aggiornata_at}`}
            c={c}
            oggi={oggi}
            occupato={occupato}
            chiama={chiama}
            onPeriodo={(tipo) => setPeriodo({
              config: c,
              tipo,
              dal: tipo === "prova" ? spostaGiorni(oggi, -30) : (c.ultimo_giorno_inviato ?? spostaGiorni(oggi, -1)),
              al: tipo === "prova" ? spostaGiorni(oggi, -1) : (c.ultimo_giorno_inviato ?? spostaGiorni(oggi, -1)),
            })}
            onInviaOra={() => setInviaOra(c)}
          />
        ))}
      </CardContent>

      <Dialog open={azienda !== null} onOpenChange={(v) => !v && setAzienda(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Collega a Invoicetronic</DialogTitle>
            <DialogDescription>Controlla che sia l&apos;azienda giusta: il collegamento non si cambia più.</DialogDescription>
          </DialogHeader>
          {azienda && (
            <div className="space-y-1 py-2">
              <p><span className="text-muted-foreground">Ragione sociale:</span> {azienda.nome || "—"}</p>
              <p className="tabular-nums"><span className="text-muted-foreground">P.IVA:</span> {azienda.vat}</p>
              <p className="tabular-nums"><span className="text-muted-foreground">Azienda Invoicetronic:</span> {azienda.company_id}</p>
              <p className="text-muted-foreground">
                {azienda.gia_viste.length
                  ? "Coincide con quella delle fatture già arrivate."
                  : "Nessuna fattura di questa P.IVA è ancora arrivata a OneFlux: non c'è uno storico con cui confrontarla."}
              </p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setAzienda(null)}>Annulla</Button>
            <Button
              disabled={occupato}
              onClick={async () => {
                if (azienda && await chiama("", "POST", { piva: azienda.piva, company_id: azienda.company_id }, "Collegata")) {
                  setAzienda(null);
                }
              }}
            >
              Collega
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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

      <Dialog open={inviaOra !== null} onOpenChange={(v) => !v && setInviaOra(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{periodoOra?.tipo === "primo" ? "Primo invio" : "Invia ora"}</DialogTitle>
            <DialogDescription>
              L&apos;email parte davvero al commercialista, se l&apos;interruttore generale del queue-worker è acceso.
            </DialogDescription>
          </DialogHeader>
          {inviaOra && (
            <div className="space-y-1 py-2">
              {periodoOra ? (
                <p>Fatture arrivate dal <strong>{formattaData(periodoOra.dal)}</strong> al <strong>{formattaData(periodoOra.al)}</strong></p>
              ) : (
                <p className="text-muted-foreground">Niente da inviare: fino a ieri è già stato tutto inviato.</p>
              )}
              <p><span className="text-muted-foreground">A:</span> {inviaOra.email_destinatario}</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setInviaOra(null)}>Annulla</Button>
            <Button
              disabled={occupato || !periodoOra}
              onClick={async () => {
                if (inviaOra && await chiama(`/${inviaOra.id}/invii`, "POST", { tipo: "invia_ora" }, "Invio richiesto")) {
                  setInviaOra(null);
                }
              }}
            >
              Invia
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function BloccoConfigurazione({ c, oggi, occupato, chiama, onPeriodo, onInviaOra }: {
  c: Configurazione;
  oggi: string;
  occupato: boolean;
  chiama: Chiama;
  onPeriodo: (tipo: "prova" | "reinvio") => void;
  onInviaOra: () => void;
}) {
  const [email, setEmail] = useState(c.email_destinatario ?? "");
  const [frequenza, setFrequenza] = useState<Frequenza>(c.frequenza);
  const [partenza, setPartenza] = useState(c.data_partenza ?? "");
  const [dataConsenso, setDataConsenso] = useState(oggi);
  const stato = statoConfigurazione(c);
  const consensoValido = c.consenso_ricevuto && !!c.email_destinatario && c.consenso_email === c.email_destinatario;
  const emailCambiata = email.trim().toLowerCase() !== (c.email_destinatario ?? "");
  const modificata = emailCambiata || frequenza !== c.frequenza || partenza !== (c.data_partenza ?? "");
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
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="space-y-1.5 sm:col-span-3">
          <Label htmlFor={`email-${c.id}`}>Email del commercialista</Label>
          <Input id={`email-${c.id}`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          {emailCambiata && c.email_destinatario && (
            <p className="text-xs text-incerto">Cambiare l&apos;email toglie consenso e attivazione: il consenso vale per un indirizzo.</p>
          )}
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor={`freq-${c.id}`}>Frequenza</Label>
          <NativeSelect id={`freq-${c.id}`} value={frequenza} onValueChange={(v) => setFrequenza(v as Frequenza)}>
            {(Object.keys(ETICHETTA_FREQUENZA) as Frequenza[]).map((f) => (
              <option key={f} value={f}>{ETICHETTA_FREQUENZA[f]}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`partenza-${c.id}`}>Fatture arrivate dal</Label>
          <Input id={`partenza-${c.id}`} type="date" value={partenza} onChange={(e) => setPartenza(e.target.value)} />
        </div>
      </div>
      {modificata && (
        <Button
          size="sm"
          disabled={occupato}
          onClick={() => chiama(cfg, "PATCH", {
            email_destinatario: email,
            frequenza,
            ...(partenza ? { data_partenza: partenza } : {}),
          }, "Salvato")}
        >
          Salva
        </Button>
      )}

      <div className="flex flex-wrap items-end gap-2 border-t pt-3">
        {consensoValido ? (
          <>
            <p className="flex-1">Consenso del {formattaData(c.consenso_data)} per {c.consenso_email}</p>
            <Button size="sm" variant="outline" disabled={occupato} onClick={() => chiama(cfg, "PATCH", { revoca_consenso: true }, "Consenso revocato")}>
              Revoca
            </Button>
          </>
        ) : (
          <>
            <div className="space-y-1.5">
              <Label htmlFor={`consenso-${c.id}`}>Consenso firmato il</Label>
              <Input id={`consenso-${c.id}`} type="date" value={dataConsenso} max={oggi} onChange={(e) => setDataConsenso(e.target.value)} />
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={occupato || !c.email_destinatario || modificata || !dataConsenso}
              title={modificata ? "Prima salva l'email" : undefined}
              onClick={() => chiama(cfg, "PATCH", { consenso_data: dataConsenso }, "Consenso registrato")}
            >
              Registra il consenso
            </Button>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t pt-3">
        <label className="flex items-center gap-2">
          <Switch
            checked={c.attivo}
            disabled={occupato}
            onCheckedChange={(v) => chiama(cfg, "PATCH", { attivo: v }, v ? "Attivato" : "Spento")}
          />
          Invio automatico
        </label>
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
          <Button size="sm" disabled={occupato || occupata || !c.attivo || !!c.sospesa_at} onClick={onInviaOra}>
            {c.ultimo_giorno_inviato ? "Invia ora" : "Primo invio"}
          </Button>
        </div>
      </div>

      {c.invii.length > 0 && (
        <div className="space-y-1.5 border-t pt-3">
          <p className="text-xs font-medium text-muted-foreground">Registro (ultimi {c.invii.length})</p>
          {c.invii.map((i) => (
            <RigaRegistro key={i.id} i={i} occupato={occupato} chiama={chiama} cfg={cfg} />
          ))}
        </div>
      )}
    </div>
  );
}

function RigaRegistro({ i, occupato, chiama, cfg }: { i: Invio; occupato: boolean; chiama: Chiama; cfg: string }) {
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
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => chiama(`${cfg}/invii/${i.id}/chiarisci`, "POST", { esito: "arrivata" }, "Segnato come arrivato")}>
            È arrivata
          </Button>
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => chiama(`${cfg}/invii/${i.id}/chiarisci`, "POST", { esito: "non_arrivata" }, "Il periodo si rispedirà")}>
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
