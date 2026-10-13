"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UnderlineTabs } from "@/components/ui/underline-tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AlertTriangle, CheckCircle, ChevronLeft, Clock, LogIn, MoreHorizontal, Trash2, XCircle } from "lucide-react";
import { type ClienteDettaglio, PIANO_COLOR, PIANO_LABEL, SETTORE_LABEL } from "@/lib/admin";
import { TAB_CLIENTE, eliminazioneConfermata, type TabCliente } from "@/lib/admin-clienti";
import type { Voce } from "@/lib/admin-oggi";
import { chiamaAdmin, messaggioErrore } from "./tabs/comune";
import { PanoramicaTab } from "./tabs/panoramica";
import { SediTab } from "./tabs/sedi";
import { FunzioniTab } from "./tabs/funzioni";
import { InviiTab } from "./tabs/invii";
import { AccountTab } from "./tabs/account";

// `problemi` null: la lista di Oggi non si e' potuta leggere.
type Props = { cliente: ClienteDettaglio; tabIniziale: TabCliente; problemi: Voce[] | null };

function Etichetta({ className, children }: { className: string; children: React.ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}

export function ClienteDettaglioClient({ cliente: iniziale, tabIniziale, problemi }: Props) {
  const router = useRouter();
  const [c, setC] = useState<ClienteDettaglio>(iniziale);
  const [tab, setTab] = useState<TabCliente>(tabIniziale);
  const [eliminaAperto, setEliminaAperto] = useState(false);
  const [confermaEmail, setConfermaEmail] = useState("");
  const [eliminazione, setEliminazione] = useState(false);

  // La tab sta nell'URL (?tab=) cosi' un link porta dritto al punto giusto e un
  // ricarico non riporta alla Panoramica. replaceState: cambiare tab non e' una
  // navigazione, non deve riempire la cronologia ne' rifare la pagina server.
  function cambiaTab(t: TabCliente) {
    setTab(t);
    const url = new URL(window.location.href);
    if (t === "panoramica") url.searchParams.delete("tab");
    else url.searchParams.set("tab", t);
    window.history.replaceState(null, "", url.toString());
  }

  const nome = c.nome_gruppo || c.nome_ristorante || c.email;
  const piani = Array.from(new Set(c.sedi.map((s) => (s.piano || "base").toLowerCase())));
  const retail = c.sedi.some((s) => s.tipo_attivita === "retail");

  async function entraComeCliente() {
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/impersona`, "POST");
      toast.success(`Accesso come ${c.email}`);
      router.push("/dashboard");
      router.refresh();
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function cambiaAttivo() {
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/account`, "PATCH", { attivo: !c.attivo });
      setC((prev) => ({ ...prev, attivo: !prev.attivo }));
      toast.success(c.attivo ? "Account disattivato" : "Account attivato");
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function attivaProva() {
    try {
      const data = await chiamaAdmin(`/api/admin/clienti/${c.id}/trial`, "POST");
      toast.success(data.message || "Prova attivata");
      router.refresh();
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function eliminaAccount() {
    setEliminazione(true);
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}`, "DELETE");
      toast.success("Account eliminato");
      router.push("/admin/clienti");
      router.refresh();
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setEliminazione(false);
    }
  }

  const emailConfermata = eliminazioneConfermata(confermaEmail, c.email);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Link href="/admin/clienti" className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-3.5" /> Clienti
        </Link>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <h1 className="text-2xl font-bold tracking-tight truncate">{nome}</h1>
            <p className="text-sm text-muted-foreground break-all">{c.email}</p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {c.attivo ? (
                <Etichetta className="bg-emerald-500/10 text-emerald-700"><CheckCircle className="size-3" /> Attivo</Etichetta>
              ) : c.last_seen_at === null ? (
                <Etichetta className="bg-amber-500/10 text-amber-700"><AlertTriangle className="size-3" /> Attivazione in sospeso</Etichetta>
              ) : (
                <Etichetta className="bg-red-500/10 text-red-600"><XCircle className="size-3" /> Disattivo</Etichetta>
              )}
              {c.trial?.active && (
                <Etichetta className="bg-amber-100 text-amber-700"><Clock className="size-3" /> Prova: {c.trial.days_remaining ?? 0} giorni</Etichetta>
              )}
              {piani.map((p) => (
                <Etichetta key={p} className={PIANO_COLOR[p] || ""}>{PIANO_LABEL[p] || p}</Etichetta>
              ))}
              {c.sedi.length > 1 && <Etichetta className="bg-muted text-muted-foreground">{c.sedi.length} sedi</Etichetta>}
              {retail && <Etichetta className="bg-amber-100 text-amber-700">{SETTORE_LABEL.retail}</Etichetta>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button onClick={entraComeCliente}>
              <LogIn className="size-4 mr-1" /> Entra come cliente
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="outline" size="icon" aria-label="Altre azioni sul cliente" title="Altre azioni">
                    <MoreHorizontal />
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-52">
                <DropdownMenuItem onClick={cambiaAttivo}>
                  {c.attivo ? <><XCircle /> Disattiva account</> : <><CheckCircle /> Attiva account</>}
                </DropdownMenuItem>
                {!c.trial?.active && (
                  <DropdownMenuItem onClick={attivaProva}>
                    <Clock /> Attiva prova 7 giorni
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={() => { setConfermaEmail(""); setEliminaAperto(true); }}>
                  <Trash2 /> Elimina account
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>

      <UnderlineTabs
        value={tab}
        onChange={cambiaTab}
        tabs={TAB_CLIENTE.map((t) => ({ value: t.key, label: t.label }))}
        className="overflow-x-auto"
      />

      {tab === "panoramica" && <PanoramicaTab c={c} setC={setC} onVaiA={cambiaTab} problemi={problemi} />}
      {tab === "sedi" && <SediTab c={c} setC={setC} />}
      {tab === "funzioni" && <FunzioniTab c={c} setC={setC} />}
      {tab === "invii" && <InviiTab c={c} setC={setC} />}
      {tab === "account" && <AccountTab c={c} setC={setC} />}

      <Dialog open={eliminaAperto} onOpenChange={setEliminaAperto}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-destructive">Elimina account</DialogTitle>
            <DialogDescription>
              Stai per eliminare definitivamente <strong>{c.email}</strong> e tutti i suoi dati:
              fatture e righe prodotto, caricamenti, ricette, ingredienti e tutte le sedi. Non si torna indietro.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label htmlFor="conferma-email">Per confermare scrivi l&apos;email del cliente</Label>
            <Input id="conferma-email" value={confermaEmail} onChange={(e) => setConfermaEmail(e.target.value)} placeholder={c.email} autoComplete="off" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEliminaAperto(false)} disabled={eliminazione}>Annulla</Button>
            <Button variant="destructive" onClick={eliminaAccount} disabled={eliminazione || !emailConfermata}>
              {eliminazione ? "Eliminazione…" : "Elimina definitivamente"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
