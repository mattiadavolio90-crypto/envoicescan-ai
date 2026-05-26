"use client";

import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const mockFatture = [
  { fornitore: "Birra & Co srl", data: "15/05/2026", importo: "€ 1.240,00", categoria: "Bevande", stato: "pagata" },
  { fornitore: "Ortofrutta Rossi", data: "18/05/2026", importo: "€ 340,50", categoria: "Materie prime", stato: "da pagare" },
  { fornitore: "Pulizie Nettuno", data: "20/05/2026", importo: "€ 180,00", categoria: "Pulizie", stato: "scaduta" },
];

const statoColore: Record<string, string> = {
  pagata: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  "da pagare": "bg-amber-500/15 text-amber-400 border-amber-500/30",
  scaduta: "bg-red-500/15 text-red-400 border-red-500/30",
};

export default function StyleGuidePage() {
  return (
    <div className="max-w-4xl space-y-10">
      <div>
        <h1 className="text-2xl font-bold">Style Guide — ONEFLUX 2.0</h1>
        <p className="text-muted-foreground mt-1">Componenti base del design system dark.</p>
      </div>

      <Separator />

      {/* Colori */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Palette colori</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Background", className: "bg-background border border-border" },
            { label: "Card", className: "bg-card" },
            { label: "Primary (blu)", className: "bg-primary" },
            { label: "Muted", className: "bg-muted" },
            { label: "Accent", className: "bg-accent" },
            { label: "Destructive", className: "bg-destructive" },
            { label: "Sidebar", className: "bg-sidebar" },
            { label: "Border", className: "bg-border" },
          ].map((c) => (
            <div key={c.label} className="space-y-1.5">
              <div className={`h-12 rounded-md ${c.className}`} />
              <p className="text-xs text-muted-foreground">{c.label}</p>
            </div>
          ))}
        </div>
      </section>

      <Separator />

      {/* Tipografia */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Tipografia</h2>
        <div className="space-y-2">
          <p className="text-3xl font-bold">Titolo H1 — Analisi Costi</p>
          <p className="text-xl font-semibold">Titolo H2 — Fatture Fornitori</p>
          <p className="text-base">Testo normale — Importo totale del mese selezionato</p>
          <p className="text-sm text-muted-foreground">Testo secondario — Aggiornato il 20/05/2026</p>
          <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Label campo — Categoria</p>
        </div>
      </section>

      <Separator />

      {/* Pulsanti */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Pulsanti</h2>
        <div className="flex flex-wrap gap-3">
          <Button>Primario</Button>
          <Button variant="secondary">Secondario</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Elimina</Button>
          <Button disabled>Disabilitato</Button>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button size="sm">Piccolo</Button>
          <Button size="default">Default</Button>
          <Button size="lg">Grande</Button>
        </div>
      </section>

      <Separator />

      {/* Badge */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Badge</h2>
        <div className="flex flex-wrap gap-3">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="destructive">Errore</Badge>
          <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statoColore["pagata"]}`}>Pagata</span>
          <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statoColore["da pagare"]}`}>Da pagare</span>
          <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statoColore["scaduta"]}`}>Scaduta</span>
        </div>
      </section>

      <Separator />

      {/* Form */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Campi form</h2>
        <div className="grid sm:grid-cols-2 gap-4 max-w-lg">
          <div className="space-y-1.5">
            <Label htmlFor="fornitore">Fornitore</Label>
            <Input id="fornitore" placeholder="Nome fornitore..." />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="importo">Importo (€)</Label>
            <Input id="importo" type="number" placeholder="0,00" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="disabled">Campo disabilitato</Label>
            <Input id="disabled" disabled value="Non modificabile" />
          </div>
        </div>
      </section>

      <Separator />

      {/* Card KPI */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Card KPI</h2>
        <div className="grid sm:grid-cols-3 gap-4">
          {[
            { title: "Fatture del mese", value: "€ 12.450", delta: "+8% vs mese prec.", positive: false },
            { title: "Ricavi del mese", value: "€ 34.800", delta: "+12% vs mese prec.", positive: true },
            { title: "Margine lordo", value: "64,2%", delta: "+2,1pp vs mese prec.", positive: true },
          ].map((kpi) => (
            <Card key={kpi.title}>
              <CardHeader className="pb-2">
                <CardDescription>{kpi.title}</CardDescription>
                <CardTitle className="text-2xl font-bold">{kpi.value}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className={`text-xs font-medium ${kpi.positive ? "text-emerald-400" : "text-red-400"}`}>
                  {kpi.delta}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      {/* Tabella */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Tabella fatture</h2>
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fornitore</TableHead>
                <TableHead>Data</TableHead>
                <TableHead>Importo</TableHead>
                <TableHead>Categoria</TableHead>
                <TableHead>Stato</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockFatture.map((f) => (
                <TableRow key={f.fornitore}>
                  <TableCell className="font-medium">{f.fornitore}</TableCell>
                  <TableCell className="text-muted-foreground">{f.data}</TableCell>
                  <TableCell>{f.importo}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{f.categoria}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statoColore[f.stato]}`}>
                      {f.stato}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </section>

      <Separator />

      {/* Interazioni */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Interazioni</h2>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => toast.success("Fattura caricata con successo!")}>
            Toast successo
          </Button>
          <Button variant="outline" onClick={() => toast.error("Errore nel caricamento file")}>
            Toast errore
          </Button>
          <Dialog>
            <DialogTrigger render={<Button variant="secondary" />}>
              Apri Dialog
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Conferma operazione</DialogTitle>
                <DialogDescription>
                  Vuoi eliminare questa fattura? L&apos;operazione non può essere annullata.
                </DialogDescription>
              </DialogHeader>
              <div className="flex justify-end gap-2 mt-4">
                <Button variant="outline">Annulla</Button>
                <Button variant="destructive">Elimina</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </section>

      {/* Avatar */}
      <Separator />
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Avatar</h2>
        <div className="flex gap-3 items-center">
          {["R", "MF", "PO", "GC"].map((initials) => (
            <Avatar key={initials}>
              <AvatarFallback className="bg-primary text-primary-foreground font-semibold text-sm">
                {initials}
              </AvatarFallback>
            </Avatar>
          ))}
        </div>
      </section>

      <div className="pb-12" />
    </div>
  );
}
