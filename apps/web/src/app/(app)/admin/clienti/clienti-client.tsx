"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation"; // usato in handleCreaCliente + handleImpersona
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Search, Plus, ChevronRight, CheckCircle, XCircle, Clock } from "lucide-react";
import { Cliente, PIANO_LABEL, PIANO_COLOR, PIANO_OPTIONS, fmtDateTime } from "@/lib/admin";

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
  const [nPiano, setNPiano] = useState("free");

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
      setNEmail(""); setNNome(""); setNPiva(""); setNRagione(""); setNPiano("free");
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

  async function handleAggiornaPiano(id: string, piano: string) {
    setClienti((prev) => prev.map((c) => c.id === id ? { ...c, piano: piano as Cliente["piano"] } : c));
    try {
      const res = await fetch(`/api/admin/clienti/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ piano }),
      });
      if (!res.ok) {
        const d = await res.json();
        toast.error(d.detail || "Errore aggiornamento piano");
      } else {
        toast.success("Piano aggiornato");
      }
    } catch {
      toast.error("Errore di connessione");
    }
  }

  async function handleAggiornaInizio(id: string, data: string) {
    setClienti((prev) => prev.map((c) => c.id === id ? { ...c, piano_inizio_at: data || null } : c));
    try {
      const res = await fetch(`/api/admin/clienti/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ piano_inizio_at: data || null }),
      });
      if (!res.ok) {
        const d = await res.json();
        toast.error(d.detail || "Errore aggiornamento data");
      }
    } catch {
      toast.error("Errore di connessione");
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
          <NativeSelect value={filtroStato} onValueChange={(v) => setFiltroStato(v as typeof filtroStato)} className="w-32">
            <option value="tutti">Tutti</option>
            <option value="attivi">Attivi</option>
            <option value="disattivi">Disattivi</option>
          </NativeSelect>
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
              <th className="px-4 py-3 font-medium hidden md:table-cell">Inizio piano</th>
              <th className="px-4 py-3 font-medium hidden lg:table-cell">Attività</th>
              <th className="px-4 py-3 font-medium hidden lg:table-cell">N. Fatture</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
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
                <td className="px-4 py-3 hidden sm:table-cell" onClick={(e) => e.stopPropagation()}>
                  <NativeSelect
                    value={c.piano}
                    onValueChange={(v) => handleAggiornaPiano(c.id, v)}
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold border-0 cursor-pointer w-auto ${PIANO_COLOR[c.piano] || "bg-slate-100 text-slate-600"}`}
                  >
                    {PIANO_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </NativeSelect>
                </td>
                <td className="px-4 py-3 hidden md:table-cell" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="date"
                    value={c.piano_inizio_at ? c.piano_inizio_at.slice(0, 10) : ""}
                    onChange={(e) => handleAggiornaInizio(c.id, e.target.value)}
                    className="text-xs bg-transparent border border-input rounded px-2 py-1 text-muted-foreground focus:outline-none focus:border-ring w-[130px]"
                  />
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  <AttivitaLabel lastSeen={c.last_seen_at} />
                </td>
                <td className="px-4 py-3 hidden lg:table-cell tabular-nums font-medium">
                  {c.n_fatture.toLocaleString("it-IT")}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/admin/clienti/${c.id}`}
                    className="inline-flex items-center justify-center size-8 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  >
                    <ChevronRight className="size-5" />
                  </Link>
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
                <NativeSelect value={nPiano} onValueChange={setNPiano}>
                  {PIANO_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </NativeSelect>
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
