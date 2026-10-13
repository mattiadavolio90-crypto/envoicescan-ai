"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Search, Plus, ChevronRight, Clock, MapPin } from "lucide-react";
import { Cliente } from "@/lib/admin";
import { FILTRI, clientiVisibili, contaFiltri, eFermo, testoGiorni, type Filtro } from "@/lib/admin-clienti";

function Giorni({ iso, adesso, allarme }: { iso: string | null | undefined; adesso: number; allarme: boolean }) {
  return (
    <span className={`text-xs font-medium ${allarme ? "text-red-600" : "text-muted-foreground"}`}>
      {testoGiorni(iso, adesso)}
    </span>
  );
}

// `problemiNoti` false: la lista di Oggi non si e' potuta leggere, quindi la
// colonna Problemi direbbe «0» senza saperlo. Si mostra il trattino.
type Props = { clientiIniziali: Cliente[]; problemiNoti: boolean };

export function ClientiClient({ clientiIniziali, problemiNoti }: Props) {
  const router = useRouter();
  const [clienti, setClienti] = useState<Cliente[]>(clientiIniziali);
  const [search, setSearch] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("tutti");
  const [adesso] = useState(() => Date.now());
  const [dialogOpen, setDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // form nuovo cliente: solo identità account (email + etichetta). P.IVA, piano e
  // dati operativi si aggiungono come SEDI dal dettaglio cliente.
  const [nEmail, setNEmail] = useState("");
  const [nNome, setNNome] = useState("");

  const filtered = useMemo(() => clientiVisibili(clienti, search, filtro, adesso), [clienti, search, filtro, adesso]);
  const conteggi = useMemo(() => contaFiltri(clienti, adesso), [clienti, adesso]);

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
        const problemi = Object.fromEntries(clienti.map((c) => [c.id, c.n_problemi ?? 0]));
        setClienti(((await refresh.json()) as Cliente[]).map((c) => ({ ...c, n_problemi: problemi[c.id] ?? 0 })));
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

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
        <div className="relative w-full sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Cerca per nome, email, P.IVA…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="size-4 mr-1" /> Nuovo cliente
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTRI.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFiltro(f.key)}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              filtro === f.key ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted"
            }`}
          >
            {f.label} <span className="tabular-nums opacity-70">{conteggi[f.key]}</span>
          </button>
        ))}
      </div>

      <div className="rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left">
              <th className="px-4 py-3 font-medium">Cliente</th>
              <th className="px-4 py-3 font-medium">Problemi</th>
              <th className="px-4 py-3 font-medium">Ultimo caricamento</th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">Fatture del mese</th>
              <th className="px-4 py-3 font-medium hidden md:table-cell">Ultimo accesso</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  Nessun cliente trovato
                </td>
              </tr>
            )}
            {filtered.map((c) => {
              const fermo = eFermo(c, adesso);
              const sopra = c.limite_mese != null && (c.fatture_mese ?? 0) > c.limite_mese;
              return (
                <tr
                  key={c.id}
                  className="hover:bg-muted/30 transition-colors cursor-pointer"
                  onClick={() => router.push(`/admin/clienti/${c.id}`)}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-medium truncate max-w-[220px]">
                        {c.nome_gruppo || c.nome_ristorante || "—"}
                      </span>
                      {c.n_sedi > 1 && (
                        <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-sky-700 bg-sky-100 rounded px-1.5 py-0.5 shrink-0">
                          <MapPin className="size-2.5" /> {c.n_sedi} sedi
                        </span>
                      )}
                      {c.trial?.active && (
                        <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-amber-700 bg-amber-100 rounded px-1.5 py-0.5 shrink-0">
                          <Clock className="size-2.5" /> Prova {c.trial.days_remaining ?? 0}gg
                        </span>
                      )}
                      {!c.attivo && (
                        <span className="text-[10px] font-semibold text-red-600 bg-red-500/10 rounded px-1.5 py-0.5 shrink-0">
                          Disattivo
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground truncate max-w-[240px]">{c.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    {!problemiNoti ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (c.n_problemi ?? 0) > 0 ? (
                      <Link
                        href="/admin"
                        onClick={(e) => e.stopPropagation()}
                        className="rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-semibold text-red-600 hover:bg-red-500/20"
                      >
                        {c.n_problemi} da fare
                      </Link>
                    ) : (
                      <span className="text-xs text-muted-foreground">Nessuno</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {c.salute_incompleta ? (
                      <span className="text-muted-foreground" title="Il server non ha potuto leggere questo dato">—</span>
                    ) : (
                      <Giorni iso={c.ultimo_caricamento_at} adesso={adesso} allarme={fermo} />
                    )}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell tabular-nums">
                    {c.limite_mese != null ? (
                      <span className={sopra ? "font-semibold text-red-600" : undefined}>
                        {(c.fatture_mese ?? 0).toLocaleString("it-IT")} / {c.limite_mese.toLocaleString("it-IT")}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    <Giorni iso={c.last_seen_at} adesso={adesso} allarme={false} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/admin/clienti/${c.id}`}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Apri ${c.nome_gruppo || c.nome_ristorante || c.email}`}
                      className="inline-flex items-center justify-center size-8 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                    >
                      <ChevronRight className="size-5" />
                    </Link>
                  </td>
                </tr>
              );
            })}
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
