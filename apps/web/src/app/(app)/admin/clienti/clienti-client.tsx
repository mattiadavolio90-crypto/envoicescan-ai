"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Search, Plus, ChevronRight, CheckCircle, XCircle, Clock, MapPin } from "lucide-react";
import { Cliente, PIANO_COLOR, PIANO_LABEL } from "@/lib/admin";

// P.IVA da mostrare in lista: nel modello account/sede la P.IVA vive sulle sedi.
// 1 sede → la sua P.IVA; più sedi → conteggio; nessuna → trattino.
function pivaDisplay(c: Cliente): string {
  if (c.sedi.length === 1) return c.sedi[0].partita_iva || "—";
  if (c.sedi.length > 1) return `${c.sedi.length} P.IVA`;
  return "—";
}

// Piani distinti fra le sedi del cliente (read-only in lista; si modificano nel
// dettaglio sede). Default 'base' per le sedi senza piano esplicito.
function pianiSede(c: Cliente): string[] {
  const set = new Set<string>();
  for (const s of c.sedi) set.add((s.piano || "base").toLowerCase());
  return Array.from(set);
}

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

  // form nuovo cliente: solo identità account (email + etichetta). P.IVA, piano e
  // dati operativi si aggiungono come SEDI dal dettaglio cliente.
  const [nEmail, setNEmail] = useState("");
  const [nNome, setNNome] = useState("");

  const filtered = useMemo(() => {
    return clienti.filter((c) => {
      const q = search.toLowerCase();
      const matchSearch =
        !search ||
        c.email.toLowerCase().includes(q) ||
        c.nome_ristorante.toLowerCase().includes(q) ||
        (c.nome_gruppo || "").toLowerCase().includes(q) ||
        // P.IVA: ora vive sulle sedi → cerca fra tutte le P.IVA delle sedi
        // (più il campo account legacy, per i clienti non ancora migrati).
        c.sedi.some((s) => (s.partita_iva || "").includes(search)) ||
        (c.partita_iva || "").includes(search);
      const matchStato =
        filtroStato === "tutti" ||
        (filtroStato === "attivi" && c.attivo) ||
        (filtroStato === "disattivi" && !c.attivo);
      return matchSearch && matchStato;
    });
  }, [clienti, search, filtroStato]);

  async function handleCreaCliente() {
    if (!nEmail || !nNome) {
      toast.error("Email e nome account sono obbligatori");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(nEmail.trim())) {
      toast.error("Email non valida");
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
      setNEmail(""); setNNome("");
      // Aggiorna la lista in-place (no full reload): il router.refresh ridondante
      // ricaricava l'intera pagina server inutilmente.
      const refresh = await fetch("/api/admin/clienti");
      if (refresh.ok) {
        setClienti(await refresh.json());
      } else {
        // L'account E' stato creato (toast sopra confermato da res.ok): un
        // refresh fallito qui non deve far pensare che la creazione sia fallita,
        // altrimenti si rischia una creazione doppia per lo stesso cliente.
        // Ricarica la pagina intera come fallback per mostrare la lista aggiornata.
        toast.info("Account creato, ma la lista non si e' aggiornata: ricarico la pagina.");
        router.refresh();
      }
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setSaving(false);
    }
  }

  // Piano e P.IVA non si modificano più dalla lista: sono dati di SEDE, gestiti
  // nel dettaglio cliente (sezione Sedi). La lista li mostra in sola lettura.

  // L'impersonazione si avvia dalla pagina di dettaglio cliente
  // (cliente-dettaglio-client.tsx, "Entra come cliente"), non dalla lista.

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
              <th className="px-4 py-3 font-medium">Cliente</th>
              <th className="px-4 py-3 font-medium hidden md:table-cell">P.IVA</th>
              <th className="px-4 py-3 font-medium">Stato</th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">Piano (per sede)</th>
              <th className="px-4 py-3 font-medium hidden lg:table-cell">Attività</th>
              <th className="px-4 py-3 font-medium hidden lg:table-cell">N. Fatture</th>
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
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium truncate max-w-[180px]">
                      {c.nome_gruppo || c.nome_ristorante || "—"}
                    </span>
                    {c.n_sedi > 1 && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-sky-700 bg-sky-100 rounded px-1.5 py-0.5 shrink-0">
                        <MapPin className="size-2.5" /> {c.n_sedi} sedi
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground truncate max-w-[180px]">{c.email}</div>
                  {c.trial?.active && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-amber-700 bg-amber-100 rounded px-1.5 py-0.5 mt-0.5">
                      <Clock className="size-2.5" /> Trial {c.trial.days_remaining ?? 0}gg
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 hidden md:table-cell text-muted-foreground tabular-nums">{pivaDisplay(c)}</td>
                <td className="px-4 py-3"><StatusBadge attivo={c.attivo} /></td>
                <td className="px-4 py-3 hidden sm:table-cell">
                  {pianiSede(c).length === 0 ? (
                    <span className="text-xs text-muted-foreground">—</span>
                  ) : (
                    <span className="inline-flex flex-wrap gap-1">
                      {pianiSede(c).map((p, idx) => (
                        <span key={idx} className={`rounded-full px-2 py-0.5 text-xs font-semibold ${PIANO_COLOR[p] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>
                          {PIANO_LABEL[p] || p}
                        </span>
                      ))}
                    </span>
                  )}
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
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="n-email">Email *</Label>
                <Input id="n-email" type="email" placeholder="cliente@esempio.it" value={nEmail} onChange={(e) => setNEmail(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="n-nome">Nome account / catena *</Label>
                <Input id="n-nome" placeholder="Es: Trattoria Da Mario, oppure SUSHILAND" value={nNome} onChange={(e) => setNNome(e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Crea solo l&apos;account. Dopo, dal dettaglio cliente, aggiungi una o più <strong>sedi</strong> con P.IVA, indirizzo e piano (una per il ristorante singolo, più sedi per una catena).
              Il cliente riceverà un&apos;email con il link per impostare la password (valido 24 ore).
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>Annulla</Button>
            <Button onClick={handleCreaCliente} disabled={saving || !nEmail || !nNome}>
              {saving ? "Creazione…" : "Crea account e invia email"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
