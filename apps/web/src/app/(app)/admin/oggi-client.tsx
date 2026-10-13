"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { AlertTriangle, CheckCircle, ChevronRight, RefreshCw, RotateCw } from "lucide-react";
import { RagioneSocialeClient } from "@/components/admin/ragione-sociale";
import { leggiOggi, raggruppa, rigaNumeri, sediPerAzione, type AzioneVoce, type DatiOggi, type Voce } from "@/lib/admin-oggi";
import { testoGiorni } from "@/lib/admin-clienti";

type Mapping = { id: string; ragione_sociale: string; ristorante_id: string; created_at: string };

async function invia(url: string, method: string, body: object) {
  const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(d.detail || d.error || "Errore");
  return d;
}

function Gruppo({ titolo, voci, children }: { titolo: string; voci: Voce[]; children: (v: Voce) => React.ReactNode }) {
  if (voci.length === 0) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-muted-foreground">{titolo} ({voci.length})</h2>
      <ul className="divide-y rounded-lg border">{voci.map(children)}</ul>
    </section>
  );
}

export function OggiClient({ iniziale }: { iniziale: DatiOggi | null }) {
  const [dati, setDati] = useState<DatiOggi | null>(iniziale);
  const [adesso] = useState(() => Date.now());
  const [caricamento, setCaricamento] = useState(false);
  const [occupata, setOccupata] = useState<string | null>(null);
  const [daRiprovare, setDaRiprovare] = useState<Voce | null>(null);
  const [scelta, setScelta] = useState<{ voce: Voce; azione: AzioneVoce } | null>(null);
  const [sedeScelta, setSedeScelta] = useState("");
  const [mappature, setMappature] = useState<Mapping[] | null>(null);

  async function ricarica() {
    setCaricamento(true);
    try {
      const res = await fetch("/api/admin/attenzione");
      const letto = leggiOggi(await res.json().catch(() => null));
      if (!res.ok || !letto) { toast.error("Non riesco a rileggere la lista"); return; }
      setDati(letto);
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setCaricamento(false);
    }
  }

  async function esegui(v: Voce, lavoro: () => Promise<string>) {
    setOccupata(v.chiave);
    try {
      toast.success(await lavoro());
      await ricarica();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setOccupata(null);
    }
  }

  function riprova(v: Voce) {
    if (v.azione?.tipo !== "riprova") return;
    const qid = v.azione.queue_id;
    esegui(v, async () => {
      await invia("/api/admin/fatture-queue/riprova", "POST", { queue_id: qid });
      return "Fattura rimessa in coda";
    });
  }

  function confermaSede() {
    if (!scelta || !sedeScelta) return;
    const { voce, azione } = scelta;
    setScelta(null);
    esegui(voce, async () => {
      if (azione.tipo === "assegna_sede") {
        const d = await invia("/api/admin/fatture-queue/assegna-sede", "POST", { queue_id: azione.queue_id, ristorante_id: sedeScelta });
        return d.ok ? "Fattura assegnata alla sede" : "Era già assegnata";
      }
      if (azione.tipo === "assegna_piva") {
        const d = await invia("/api/admin/fatture-queue/assegna-piva", "POST", { piva: azione.piva, ristorante_id: sedeScelta });
        return `${d.sbloccate} fattur${d.sbloccate === 1 ? "a sbloccata" : "e sbloccate"}`;
      }
      return "Fatto";
    });
    setSedeScelta("");
  }

  function richiesta(v: Voce, stato: "gestito" | "archiviato") {
    if (v.azione?.tipo !== "richiesta") return;
    const id = v.azione.id;
    esegui(v, async () => {
      await invia(`/api/admin/marketplace/leads/${id}`, "PATCH", { stato });
      return stato === "gestito" ? "Richiesta segnata come gestita" : "Richiesta archiviata";
    });
  }

  async function apriMappature() {
    setMappature([]);
    try {
      const res = await fetch("/api/admin/ragione-sociale-map");
      setMappature(res.ok ? await res.json() : []);
    } catch {
      setMappature([]);
    }
  }

  function pulsanti(v: Voce) {
    const a = v.azione;
    const ferma = occupata === v.chiave;
    if (a?.tipo === "riprova") {
      return <Button size="sm" variant="outline" disabled={ferma} onClick={() => setDaRiprovare(v)}><RotateCw className="size-4 mr-1" /> Riprova</Button>;
    }
    if (a?.tipo === "assegna_sede" || a?.tipo === "assegna_piva") {
      return (
        <Button size="sm" variant="outline" disabled={ferma} onClick={() => { setSedeScelta(""); setScelta({ voce: v, azione: a }); }}>
          {a.tipo === "assegna_sede" ? "Scegli sede" : "Assegna a…"}
        </Button>
      );
    }
    if (a?.tipo === "collega_mittente") {
      return <Button size="sm" variant="outline" onClick={apriMappature}>Collega a una sede</Button>;
    }
    if (a?.tipo === "richiesta") {
      return (
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={ferma} onClick={() => richiesta(v, "gestito")}>Gestita</Button>
          <Button size="sm" variant="ghost" disabled={ferma} onClick={() => richiesta(v, "archiviato")}>Archivia</Button>
        </div>
      );
    }
    if (v.link) {
      return (
        <Button size="sm" variant="ghost" nativeButton={false} render={<Link href={v.link} />}>
          Apri <ChevronRight className="size-4 ml-0.5" />
        </Button>
      );
    }
    return null;
  }

  function riga(v: Voce) {
    return (
      <li key={v.chiave} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm">
            {v.cliente && (
              v.cliente_id
                ? <Link href={`/admin/clienti/${v.cliente_id}`} className="font-semibold hover:underline">{v.cliente}</Link>
                : <span className="font-semibold">{v.cliente}</span>
            )}
            {v.cliente && <span className="text-muted-foreground"> · </span>}
            <span className={v.gravita === "critico" ? "font-medium text-red-700 dark:text-red-400" : "font-medium"}>{v.titolo}</span>
          </p>
          {(v.dettaglio || v.da) && (
            <p className="text-xs text-muted-foreground break-words">
              {v.dettaglio}
              {v.dettaglio && v.da ? " · " : ""}
              {v.da ? `dal ${new Date(v.da).toLocaleDateString("it-IT", { day: "numeric", month: "short" })} (${testoGiorni(v.da, adesso).toLowerCase()})` : ""}
            </p>
          )}
        </div>
        <div className="shrink-0">{pulsanti(v)}</div>
      </li>
    );
  }

  if (!dati) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
        <span className="flex items-center gap-2"><AlertTriangle className="size-4 text-amber-600" /> Non riesco a leggere lo stato dal server: la lista non è disponibile.</span>
        <Button size="sm" variant="outline" onClick={ricarica} disabled={caricamento}><RefreshCw className={`size-4 mr-1 ${caricamento ? "animate-spin" : ""}`} /> Riprova</Button>
      </div>
    );
  }

  const { urgenti, daFare } = raggruppa(dati.voci);
  const sceltaSedi = scelta ? sediPerAzione(scelta.azione, dati.sedi) : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Oggi</h1>
        <Button variant="ghost" size="sm" onClick={ricarica} disabled={caricamento}>
          <RefreshCw className={`size-4 mr-1 ${caricamento ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
      </div>

      {dati._errors.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-300 space-y-1">
          <p className="font-medium">Alcuni controlli non sono riusciti: la lista potrebbe essere incompleta.</p>
          <ul className="list-disc list-inside">{dati._errors.map((e, i) => <li key={i} className="truncate" title={e}>{e}</li>)}</ul>
        </div>
      )}

      {dati.voci.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-800 dark:text-emerald-300">
          <CheckCircle className="size-4" /> Tutto a posto: niente da fare.
        </div>
      ) : (
        <>
          <Gruppo titolo="Urgenti" voci={urgenti}>{riga}</Gruppo>
          <Gruppo titolo="Da fare" voci={daFare}>{riga}</Gruppo>
        </>
      )}

      <p className="text-xs text-muted-foreground">{rigaNumeri(dati.numeri)}</p>

      <ConfirmDialog
        open={daRiprovare !== null}
        titolo="Rimettere in coda la fattura?"
        messaggio="Verrà riscaricata e rielaborata al prossimo giro del worker."
        confermaLabel="Rimetti in coda"
        onConferma={() => { if (daRiprovare) riprova(daRiprovare); }}
        onClose={() => setDaRiprovare(null)}
      />

      <Dialog open={scelta !== null} onOpenChange={(o) => { if (!o) { setScelta(null); setSedeScelta(""); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{scelta?.azione.tipo === "assegna_sede" ? "A quale sede va?" : "Di chi è questa P.IVA?"}</DialogTitle>
            <DialogDescription>
              {scelta?.azione.tipo === "assegna_sede"
                ? "La fattura viene assegnata alla sede scelta e rielaborata."
                : "Tutte le fatture in attesa con questa P.IVA vengono sbloccate per la sede scelta."}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <NativeSelect value={sedeScelta} onValueChange={setSedeScelta} placeholder="Seleziona la sede…">
              {sceltaSedi.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </NativeSelect>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setScelta(null); setSedeScelta(""); }}>Annulla</Button>
            <Button onClick={confermaSede} disabled={!sedeScelta}>Conferma</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={mappature !== null} onOpenChange={(o) => { if (!o) { setMappature(null); ricarica(); } }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Collega i mittenti dei ricavi</DialogTitle>
            <DialogDescription>
              Scrivi la ragione sociale come appare nell&apos;email del gestionale e scegli la sede: l&apos;import riparte da solo.
            </DialogDescription>
          </DialogHeader>
          {mappature && (
            <RagioneSocialeClient
              key={mappature.length}
              mappingsIniziali={mappature}
              sedi={dati.sedi.map((s) => ({ id: s.id, label: `${s.nome} (${s.cliente})` }))}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
