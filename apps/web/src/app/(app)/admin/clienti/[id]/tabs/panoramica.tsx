"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertTriangle, Pencil, Send } from "lucide-react";
import { fmtDate } from "@/lib/admin";
import { eFermo, giorniDa, testoGiorni } from "@/lib/admin-clienti";
import { chiamaAdmin, messaggioErrore, type TabProps } from "./comune";

function Dato({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}

export function PanoramicaTab({ c, setC, onVaiA }: TabProps & { onVaiA: (tab: "account") => void }) {
  const [adesso] = useState(() => Date.now());
  const [modifica, setModifica] = useState(false);
  const [nome, setNome] = useState("");
  const [gruppo, setGruppo] = useState("");
  const [salvataggio, setSalvataggio] = useState(false);

  const mai = !c.attivo && c.last_seen_at === null;
  const fermo = eFermo(c, adesso);
  const sopra = c.sedi.filter((s) => s.sopra_soglia);

  function apriModifica() {
    setNome(c.nome_ristorante || "");
    setGruppo(c.nome_gruppo || "");
    setModifica(true);
  }

  async function salva() {
    setSalvataggio(true);
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}`, "PATCH", {
        nome_ristorante: nome.trim() || undefined,
        nome_gruppo: gruppo.trim() || null,
      });
      setC((prev) => ({ ...prev, nome_ristorante: nome.trim() || prev.nome_ristorante, nome_gruppo: gruppo.trim() || null }));
      toast.success("Dati aggiornati");
      setModifica(false);
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setSalvataggio(false);
    }
  }

  async function rinviaAttivazione() {
    try {
      const data = await chiamaAdmin(`/api/admin/clienti/${c.id}/rinvia-attivazione`, "POST");
      toast.success(`Email di attivazione reinviata a ${data.email}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  return (
    <div className="space-y-4">
      {(mai || fermo || sopra.length > 0) && (
        <div className="space-y-2">
          {mai && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              <span className="flex items-center gap-2"><AlertTriangle className="size-4 text-amber-600" /> Non ha mai attivato l&apos;account.</span>
              <Button size="sm" variant="outline" onClick={rinviaAttivazione}><Send className="size-4 mr-1" /> Rinvia email di attivazione</Button>
            </div>
          )}
          {fermo && (
            <div className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              <AlertTriangle className="size-4 text-amber-600" />
              {c.ultimo_caricamento_at ? `Nessuna fattura caricata da ${giorniDa(c.ultimo_caricamento_at, adesso)} giorni.` : "Non ha mai caricato una fattura."}
            </div>
          )}
          {sopra.length > 0 && (
            <div className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm">
              <AlertTriangle className="size-4 text-red-600" />
              Sopra il limite del piano questo mese: {sopra.map((s) => s.nome_ristorante).join(", ")}.
            </div>
          )}
        </div>
      )}

      <Card>
        <CardHeader><CardTitle className="text-base">Questo mese</CardTitle></CardHeader>
        <CardContent>
          {c.sedi.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nessuna sede: aggiungila dalla tab Sedi.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="pb-2 font-medium">Sede</th>
                  <th className="pb-2 font-medium">Fatture / piano</th>
                  <th className="pb-2 font-medium">Ultimo caricamento</th>
                  <th className="pb-2 font-medium hidden sm:table-cell text-right">Costo AI</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {c.sedi.map((s) => (
                  <tr key={s.id}>
                    <td className="py-2 pr-2 truncate max-w-[180px]">{s.nome_ristorante}</td>
                    <td className={`py-2 tabular-nums ${s.sopra_soglia ? "font-semibold text-red-600" : ""}`}>
                      {s.limite_mese != null ? `${s.fatture_mese ?? 0} / ${s.limite_mese}` : "—"}
                    </td>
                    <td className="py-2 text-muted-foreground">{testoGiorni(s.ultimo_caricamento_at, adesso)}</td>
                    <td className="py-2 hidden sm:table-cell text-right tabular-nums text-muted-foreground">
                      {s.ai_costo_mese != null ? `$${s.ai_costo_mese.toFixed(2)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Attività</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Dato label="Ultimo accesso">{testoGiorni(c.last_seen_at, adesso)}</Dato>
              <Dato label="Ultimo caricamento">{testoGiorni(c.ultimo_caricamento_at, adesso)}</Dato>
              <Dato label="Fatture totali"><span className="tabular-nums">{c.n_fatture?.toLocaleString("it-IT") ?? "—"}</span></Dato>
              <Dato label="Cliente dal">{fmtDate(c.created_at)}</Dato>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Dati account</CardTitle>
            <Button variant="ghost" size="sm" onClick={apriModifica}><Pencil className="size-4 mr-1" /> Modifica</Button>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 text-sm">
              <Dato label="Email"><span className="break-all">{c.email}</span></Dato>
              <Dato label="Nome account">{c.nome_ristorante || "—"}</Dato>
              {c.nome_gruppo && <Dato label="Gruppo / catena">{c.nome_gruppo}</Dato>}
            </dl>
            <button type="button" onClick={() => onVaiA("account")} className="mt-3 text-xs text-primary-text hover:underline">
              Password, email di accesso e utenti →
            </button>
          </CardContent>
        </Card>
      </div>

      <Dialog open={modifica} onOpenChange={setModifica}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Modifica dati account</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="m-nome">Nome account</Label>
              <Input id="m-nome" value={nome} onChange={(e) => setNome(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-gruppo">Nome gruppo / catena</Label>
              <Input id="m-gruppo" placeholder="Es: SUSHILAND (opzionale, per clienti multi-sede)" value={gruppo} onChange={(e) => setGruppo(e.target.value)} />
            </div>
            <p className="text-xs text-muted-foreground">
              P.IVA, ragione sociale e piano si gestiscono per <strong>sede</strong>, nella tab Sedi.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModifica(false)} disabled={salvataggio}>Annulla</Button>
            <Button onClick={salva} disabled={salvataggio}>{salvataggio ? "Salvataggio…" : "Salva"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
