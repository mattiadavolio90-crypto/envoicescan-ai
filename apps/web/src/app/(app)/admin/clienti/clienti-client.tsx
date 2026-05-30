"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Plus, ChevronRight, CheckCircle, XCircle, Clock } from "lucide-react";
import { Cliente, PIANO_LABEL, PIANO_COLOR, fmtDateTime } from "@/lib/admin";

function StatusBadge({ attivo }: { attivo: boolean }) {
  return attivo ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
      <CheckCircle className="size-3" /> Attivo
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
      <XCircle className="size-3" /> Disattivo
    </span>
  );
}

function AttivitaLabel({ lastSeen }: { lastSeen: string | null }) {
  if (!lastSeen) return <span className="text-xs text-muted-foreground">Mai</span>;
  const days = Math.floor((Date.now() - new Date(lastSeen).getTime()) / 86400000);
  const color = days === 0 ? "text-emerald-600" : days < 7 ? "text-emerald-600" : days < 30 ? "text-amber-600" : "text-red-500";
  const label = days === 0 ? "Oggi" : `${days}g fa`;
  return <span className={`text-xs font-medium ${color}`}>{label}</span>;
}

type Props = { clientiIniziali: Cliente[] };

export function ClientiClient({ clientiIniziali }: Props) {
  const router = useRouter();
  const [clienti, setClienti] = useState<Cliente[]>(clientiIniziali);
  const [search, setSearch] = useState("");
  const [filtroStato, setFiltroStato] = useState<"tutti" | "attivi" | "disattivi">("tutti");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // form nuovo cliente
  const [nEmail, setNEmail] = useState("");
  const [nNome, setNNome] = useState("");
  const [nPiva, setNPiva] = useState("");
  const [nRagione, setNRagione] = useState("");
  const [nPiano, setNPiano] = useState("base");

  const filtered = useMemo(() => {
    return clienti.filter((c) => {
      const matchSearch =
        !search ||
        c.email.toLowerCase().includes(search.toLowerCase()) ||
        c.nome_ristorante.toLowerCase().includes(search.toLowerCase()) ||
        (c.partita_iva || "").includes(search);
      const matchStato =
        filtroStato === "tutti" ||
        (filtroStato === "attivi" && c.attivo) ||
        (filtroStato === "disattivi" && !c.attivo);
      return matchSearch && matchStato;
    });
  }, [clienti, search, filtroStato]);

  async function handleCreaCliente() {
    if (!nEmail || !nNome || !nPiva) {
      toast.error("Email, nome ristorante e P.IVA sono obbligatori");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/admin/clienti", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: nEmail.trim().toLowerCase(),
          nome_ristorante: nNome.trim(),
          partita_iva: nPiva.trim(),
          ragione_sociale: nRagione.trim() || undefined,
          piano: nPiano,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || "Errore creazione cliente");
        return;
      }
      toast.success(
        data.email_inviata
          ? `Account creato. Email inviata a ${data.email}`
          : `Account creato. Email NON inviata — link: ${data.link_attivazione}`
      );
      setDialogOpen(false);
      setNEmail(""); setNNome(""); setNPiva(""); setNRagione(""); setNPiano("base");
      router.refresh();
      // aggiorna lista localmente
      const refresh = await fetch("/api/admin/clienti");
      if (refresh.ok) setClienti(await refresh.json());
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setSaving(false);
    }
  }

  async function handleImpersona(c: Cliente) {
    try {
      const res = await fetch(`/api/admin/clienti/${c.id}/impersona`, { method: "POST" });
      if (!res.ok) {
        const d = await res.json();
        toast.error(d.detail || "Errore impersonazione");
        return;
      }
      toast.success(`Accesso come ${c.email}`);
      router.push("/dashboard");
      router.refresh();
    } catch {
      toast.error("Errore di connessione");
    }
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="flex gap-2 flex-1">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <Input
              placeholder="Cerca per email, nome, P.IVA…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={filtroStato} onValueChange={(v) => setFiltroStato(v as typeof filtroStato)}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tutti">Tutti</SelectItem>
              <SelectItem value="attivi">Attivi</SelectItem>
              <SelectItem value="disattivi">Disattivi</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="size-4 mr-1" /> Nuovo cliente
        </Button>
      </div>

      {/* Contatore */}
      <p className="text-sm text-muted-foreground">{filtered.length} clienti</p>

      {/* Tabella */}
      <div className="rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left">
              <th className="px-4 py-3 font-medium">Ristorante</th>
              <th className="px-4 py-3 font-medium hidden md:table-cell">P.IVA</th>
              <th className="px-4 py-3 font-medium">Stato</th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">Piano</th>
              <th className="px-4 py-3 font-medium hidden lg:table-cell">Attività</th>
              <th className="px-4 py-3 font-medium hidden lg:table-cell">Fatture/mese</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                  Nessun cliente trovato
                </td>
              </tr>
            )}
            {filtered.map((c) => (
              <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                <td className="px-4 py-3">
                  <div className="font-medium truncate max-w-[180px]">{c.nome_ristorante || "—"}</div>
                  <div className="text-xs text-muted-foreground truncate max-w-[180px]">{c.email}</div>
                  {c.trial?.active && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-amber-700 bg-amber-100 rounded px-1.5 py-0.5 mt-0.5">
                      <Clock className="size-2.5" /> Trial {c.trial.days_remaining ?? 0}gg
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 hidden md:table-cell text-muted-foreground tabular-nums">{c.partita_iva || "—"}</td>
                <td className="px-4 py-3"><StatusBadge attivo={c.attivo} /></td>
                <td className="px-4 py-3 hidden sm:table-cell">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${PIANO_COLOR[c.piano] || "bg-slate-100 text-slate-700"}`}>
                    {PIANO_LABEL[c.piano] || c.piano}
                  </span>
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  <AttivitaLabel lastSeen={c.last_seen_at} />
                </td>
                <td className="px-4 py-3 hidden lg:table-cell tabular-nums text-muted-foreground">
                  {c.fatture_mese}/{c.limite_fatture_mese}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 justify-end">
                    <Button size="sm" variant="outline" onClick={() => handleImpersona(c)}>
                      Entra
                    </Button>
                    <Button size="sm" variant="ghost" asChild>
                      <Link href={`/admin/clienti/${c.id}`}>
                        <ChevronRight className="size-4" />
                      </Link>
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Dialog Nuovo cliente */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Nuovo cliente</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="n-email">Email *</Label>
                <Input id="n-email" type="email" placeholder="cliente@esempio.it" value={nEmail} onChange={(e) => setNEmail(e.target.value)} />
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="n-nome">Nome ristorante *</Label>
                <Input id="n-nome" placeholder="Es: Trattoria Da Mario" value={nNome} onChange={(e) => setNNome(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="n-piva">P.IVA * (11 cifre)</Label>
                <Input id="n-piva" placeholder="12345678901" maxLength={11} value={nPiva} onChange={(e) => setNPiva(e.target.value.replace(/\D/g, ""))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="n-piano">Piano</Label>
                <Select value={nPiano} onValueChange={setNPiano}>
                  <SelectTrigger id="n-piano"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="base">Base (50 fatture)</SelectItem>
                    <SelectItem value="plus">Plus (100 fatture)</SelectItem>
                    <SelectItem value="pro">Pro (200 fatture)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="n-ragione">Ragione sociale</Label>
                <Input id="n-ragione" placeholder="Mario Rossi S.r.l. (opzionale)" value={nRagione} onChange={(e) => setNRagione(e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Il cliente riceverà un&apos;email con il link per impostare la propria password (valido 24 ore).
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>Annulla</Button>
            <Button onClick={handleCreaCliente} disabled={saving || !nEmail || !nNome || !nPiva}>
              {saving ? "Creazione…" : "Crea account e invia email"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
