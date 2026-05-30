"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  LogIn, Mail, KeyRound, Trash2, Plus, X, Clock, CheckCircle, XCircle, AlertTriangle
} from "lucide-react";
import { ClienteDettaglio, Sede, PIANO_LABEL, PIANO_COLOR, fmtDate, fmtDateTime } from "@/lib/admin";

type Props = { cliente: ClienteDettaglio };

const SIDEBAR_FLAGS: { key: string; label: string; desc: string }[] = [
  { key: "analisi_fatture", label: "Analisi Fatture", desc: "Visualizza e gestisci fatture" },
  { key: "prezzi", label: "Controllo Prezzi", desc: "Variazioni prezzi, sconti, note credito" },
  { key: "margini", label: "Ricavi e Margini", desc: "Calcolo marginalità e analisi avanzate" },
  { key: "foodcost", label: "Foodcost", desc: "Analisi foodcost" },
  { key: "analisi_e_tag", label: "Analisi e Tag", desc: "Tag personalizzati e analytics" },
  { key: "scadenziario", label: "Scadenziario", desc: "Gestione scadenze e pagamenti" },
  { key: "blocco_anno_precedente", label: "Blocca anno precedente", desc: "Impedisce caricamento fatture dell'anno scorso" },
  { key: "blocco_mesi_precedenti", label: "Blocca mesi precedenti", desc: "Consente solo mese corrente e precedente" },
];

export function ClienteDettaglioClient({ cliente: iniziale }: Props) {
  const router = useRouter();
  const [c, setC] = useState<ClienteDettaglio>(iniziale);

  // Email dialog
  const [emailDialog, setEmailDialog] = useState(false);
  const [nuovaEmail, setNuovaEmail] = useState("");
  const [emailSaving, setEmailSaving] = useState(false);

  // Sede dialog
  const [sedeDialog, setSedeDialog] = useState(false);
  const [sNome, setSNome] = useState("");
  const [sPiva, setSPiva] = useState("");
  const [sRagione, setSRagione] = useState("");
  const [sedeSaving, setSedeSaving] = useState(false);

  // Elimina account dialog
  const [eliminaDialog, setEliminaDialog] = useState(false);
  const [eliminaMemoria, setEliminaMemoria] = useState(false);
  const [eliminaSaving, setEliminaSaving] = useState(false);

  async function patch(url: string, method: string, body?: object) {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Errore");
    return data;
  }

  async function toggleAttivo() {
    try {
      await patch(`/api/admin/clienti/${c.id}/account`, "PATCH", { attivo: !c.attivo });
      setC((prev) => ({ ...prev, attivo: !prev.attivo }));
      toast.success(c.attivo ? "Account disattivato" : "Account attivato");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleResetPassword() {
    try {
      const data = await patch(`/api/admin/clienti/${c.id}/reset-password`, "POST");
      toast.success(data.email_inviata ? "Email reset inviata" : `Email NON inviata. Link: ${data.link}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleCambioEmail() {
    if (!nuovaEmail.trim()) return;
    setEmailSaving(true);
    try {
      await patch(`/api/admin/clienti/${c.id}/email`, "PATCH", { nuova_email: nuovaEmail.trim() });
      setC((prev) => ({ ...prev, email: nuovaEmail.trim().toLowerCase() }));
      toast.success("Email aggiornata");
      setEmailDialog(false);
      setNuovaEmail("");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setEmailSaving(false);
    }
  }

  async function handleImpersona() {
    try {
      await patch(`/api/admin/clienti/${c.id}/impersona`, "POST");
      toast.success(`Accesso come ${c.email}`);
      router.push("/dashboard");
      router.refresh();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleAttivaTrial() {
    try {
      const data = await patch(`/api/admin/clienti/${c.id}/trial`, "POST");
      toast.success(data.message || "Trial attivata");
      router.refresh();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleCreaSedeSubmit() {
    if (!sNome.trim() || !sPiva.trim()) { toast.error("Nome e P.IVA obbligatori"); return; }
    setSedeSaving(true);
    try {
      const sede: Sede = await patch(`/api/admin/clienti/${c.id}/sedi`, "POST", {
        nome_ristorante: sNome.trim(),
        partita_iva: sPiva.trim(),
        ragione_sociale: sRagione.trim() || undefined,
      });
      setC((prev) => ({ ...prev, sedi: [...prev.sedi, sede], n_sedi: prev.n_sedi + 1 }));
      toast.success("Sede creata");
      setSedeDialog(false);
      setSNome(""); setSPiva(""); setSRagione("");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setSedeSaving(false);
    }
  }

  async function handleEliminaSede(sede: Sede) {
    if (!confirm(`Eliminare la sede "${sede.nome_ristorante}"? Tutte le sue fatture verranno eliminate.`)) return;
    try {
      await patch(`/api/admin/clienti/${c.id}/sedi/${sede.id}`, "DELETE");
      setC((prev) => ({ ...prev, sedi: prev.sedi.filter((s) => s.id !== sede.id), n_sedi: prev.n_sedi - 1 }));
      toast.success("Sede eliminata");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleToggleFlag(key: string, enabled: boolean) {
    try {
      await patch(`/api/admin/clienti/${c.id}/flags`, "PATCH", {
        pagine_abilitate: { [key]: enabled },
      });
      setC((prev) => ({ ...prev, pagine_abilitate: { ...prev.pagine_abilitate, [key]: enabled } }));
      toast.success(`${key} ${enabled ? "attivato" : "disattivato"}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleEliminaAccount() {
    setEliminaSaving(true);
    try {
      await fetch(`/api/admin/clienti/${c.id}?elimina_memoria=${eliminaMemoria}`, { method: "DELETE" });
      toast.success("Account eliminato");
      router.push("/admin/clienti");
      router.refresh();
    } catch {
      toast.error("Errore eliminazione");
    } finally {
      setEliminaSaving(false);
    }
  }

  const flags = c.pagine_abilitate || {};

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Colonna sinistra: dati + azioni rapide */}
      <div className="lg:col-span-1 space-y-4">
        {/* Card dati cliente */}
        <Card>
          <CardHeader><CardTitle className="text-base">Dati cliente</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <dl className="space-y-2">
              <div>
                <dt className="text-muted-foreground text-xs">Email</dt>
                <dd className="font-medium break-all">{c.email}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Nome ristorante</dt>
                <dd className="font-medium">{c.nome_ristorante || "—"}</dd>
              </div>
              {c.ragione_sociale && (
                <div>
                  <dt className="text-muted-foreground text-xs">Ragione sociale</dt>
                  <dd className="font-medium">{c.ragione_sociale}</dd>
                </div>
              )}
              <div>
                <dt className="text-muted-foreground text-xs">P.IVA</dt>
                <dd className="font-medium tabular-nums">{c.partita_iva || "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Piano</dt>
                <dd>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${PIANO_COLOR[c.piano] || ""}`}>
                    {PIANO_LABEL[c.piano] || c.piano}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Membro dal</dt>
                <dd className="font-medium">{fmtDate(c.created_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Ultimo accesso</dt>
                <dd className="font-medium">{fmtDateTime(c.last_seen_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Fatture mese</dt>
                <dd className="font-medium tabular-nums">{c.fatture_mese ?? "—"} / {c.limite_fatture_mese}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Stato account</dt>
                <dd>
                  {c.attivo
                    ? <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700"><CheckCircle className="size-3" /> Attivo</span>
                    : <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600"><XCircle className="size-3" /> Disattivo</span>
                  }
                </dd>
              </div>
              {c.trial?.active && (
                <div>
                  <dt className="text-muted-foreground text-xs">Trial</dt>
                  <dd className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700">
                    <Clock className="size-3" /> {c.trial.days_remaining ?? 0} giorni rimasti
                  </dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        {/* Azioni rapide */}
        <Card>
          <CardHeader><CardTitle className="text-base">Azioni</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Button className="w-full justify-start" onClick={handleImpersona}>
              <LogIn className="size-4 mr-2" /> Entra come cliente
            </Button>
            <Button variant="outline" className="w-full justify-start" onClick={handleResetPassword}>
              <KeyRound className="size-4 mr-2" /> Invia reset password
            </Button>
            <Button variant="outline" className="w-full justify-start" onClick={() => setEmailDialog(true)}>
              <Mail className="size-4 mr-2" /> Cambia email
            </Button>
            <Button
              variant={c.attivo ? "outline" : "default"}
              className="w-full justify-start"
              onClick={toggleAttivo}
            >
              {c.attivo
                ? <><XCircle className="size-4 mr-2" /> Disattiva account</>
                : <><CheckCircle className="size-4 mr-2" /> Attiva account</>
              }
            </Button>
            {!c.trial?.active && (
              <Button variant="outline" className="w-full justify-start" onClick={handleAttivaTrial}>
                <Clock className="size-4 mr-2" /> Attiva trial 7 giorni
              </Button>
            )}
          </CardContent>
        </Card>

        {/* Zona pericolosa */}
        <Card className="border-destructive/40">
          <CardHeader><CardTitle className="text-base text-destructive">Zona pericolosa</CardTitle></CardHeader>
          <CardContent>
            <Button
              variant="destructive"
              className="w-full"
              onClick={() => setEliminaDialog(true)}
            >
              <Trash2 className="size-4 mr-2" /> Elimina account
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Colonna destra: feature flags + sedi */}
      <div className="lg:col-span-2 space-y-4">
        {/* Feature flags */}
        <Card>
          <CardHeader><CardTitle className="text-base">Accesso sezioni</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {SIDEBAR_FLAGS.map((f) => {
              const enabled = flags[f.key] !== false;
              return (
                <div key={f.key} className="flex items-center justify-between gap-4 py-1 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium">{f.label}</p>
                    <p className="text-xs text-muted-foreground">{f.desc}</p>
                  </div>
                  <Switch
                    checked={enabled}
                    onCheckedChange={(v) => handleToggleFlag(f.key, v)}
                  />
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Sedi */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Sedi ({c.sedi.length})</CardTitle>
            <Button size="sm" variant="outline" onClick={() => setSedeDialog(true)}>
              <Plus className="size-4 mr-1" /> Aggiungi sede
            </Button>
          </CardHeader>
          <CardContent>
            {c.sedi.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nessuna sede configurata</p>
            ) : (
              <div className="space-y-2">
                {c.sedi.map((sede) => (
                  <div key={sede.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                    <div>
                      <p className="text-sm font-medium">{sede.nome_ristorante}</p>
                      <p className="text-xs text-muted-foreground tabular-nums">{sede.partita_iva || "—"}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-medium ${sede.attivo ? "text-emerald-600" : "text-red-500"}`}>
                        {sede.attivo ? "Attiva" : "Inattiva"}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="size-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => handleEliminaSede(sede)}
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Dialog cambia email */}
      <Dialog open={emailDialog} onOpenChange={setEmailDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Cambia email</DialogTitle>
            <DialogDescription>La sessione corrente del cliente verrà invalidata.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label>Email attuale</Label>
              <p className="text-sm text-muted-foreground">{c.email}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nuova-email">Nuova email</Label>
              <Input
                id="nuova-email"
                type="email"
                value={nuovaEmail}
                onChange={(e) => setNuovaEmail(e.target.value)}
                placeholder="nuova@email.it"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailDialog(false)} disabled={emailSaving}>Annulla</Button>
            <Button onClick={handleCambioEmail} disabled={emailSaving || !nuovaEmail.trim()}>
              {emailSaving ? "Salvataggio…" : "Conferma"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog aggiungi sede */}
      <Dialog open={sedeDialog} onOpenChange={setSedeDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Aggiungi sede</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="s-nome">Nome sede *</Label>
              <Input id="s-nome" placeholder="Es: Trattoria Mario 2" value={sNome} onChange={(e) => setSNome(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-piva">P.IVA * (11 cifre)</Label>
              <Input id="s-piva" placeholder="12345678901" maxLength={11} value={sPiva} onChange={(e) => setSPiva(e.target.value.replace(/\D/g, ""))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-ragione">Ragione sociale</Label>
              <Input id="s-ragione" placeholder="Opzionale" value={sRagione} onChange={(e) => setSRagione(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSedeDialog(false)} disabled={sedeSaving}>Annulla</Button>
            <Button onClick={handleCreaSedeSubmit} disabled={sedeSaving || !sNome.trim() || !sPiva.trim()}>
              {sedeSaving ? "Creazione…" : "Crea sede"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog elimina account */}
      <Dialog open={eliminaDialog} onOpenChange={setEliminaDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-destructive">Elimina account</DialogTitle>
            <DialogDescription>
              Stai per eliminare definitivamente <strong>{c.email}</strong> e tutti i suoi dati. Questa azione è irreversibile.
            </DialogDescription>
          </DialogHeader>
          <div className="py-2 space-y-3">
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive space-y-1">
              <p className="font-medium"><AlertTriangle className="inline size-4 mr-1" />Verranno eliminati:</p>
              <ul className="list-disc list-inside text-xs space-y-0.5 text-destructive/80">
                <li>Account utente</li>
                <li>Tutte le fatture e righe prodotto</li>
                <li>Upload events, ricette, ingredienti</li>
                <li>Tutti i ristoranti/sedi</li>
              </ul>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="elimina-memoria" checked={eliminaMemoria} onCheckedChange={setEliminaMemoria} />
              <Label htmlFor="elimina-memoria" className="text-sm">
                Elimina anche i contributi alla memoria AI globale
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEliminaDialog(false)} disabled={eliminaSaving}>Annulla</Button>
            <Button variant="destructive" onClick={handleEliminaAccount} disabled={eliminaSaving}>
              {eliminaSaving ? "Eliminazione…" : "Sì, elimina definitivamente"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
