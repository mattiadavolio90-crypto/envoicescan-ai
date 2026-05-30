"use client";

import { useState, useCallback } from "react";
import { toast } from "sonner";
import { ArchiveRestore, Loader2, Trash2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import type { FatturaInCestino } from "./page";

function formatEuro(val: number) {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(val);
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function daysRemaining(deleted_at: string): number {
  const expiry = new Date(deleted_at);
  expiry.setDate(expiry.getDate() + 30);
  const diff = Math.ceil((expiry.getTime() - Date.now()) / 86400000);
  return Math.max(0, diff);
}

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
};

function ConfirmDialog({ open, title, description, confirmLabel = "Conferma", onConfirm, onCancel, loading }: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onCancel} disabled={loading}>Annulla</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={loading}>
            {loading && <Loader2 className="size-4 animate-spin mr-1.5" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type CestinoRowProps = {
  item: FatturaInCestino;
  onRipristina: (item: FatturaInCestino) => void;
  onElimina: (item: FatturaInCestino) => void;
  loading: boolean;
};

function CestinoRow({ item, onRipristina, onElimina, loading }: CestinoRowProps) {
  const days = daysRemaining(item.deleted_at);
  const urgent = days <= 5;

  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg border bg-card hover:bg-muted/30 transition-colors">
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm truncate">{item.fornitore || item.file_origine}</span>
          <span className="text-xs text-muted-foreground">
            {item.num_righe} prodott{item.num_righe === 1 ? "o" : "i"}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
          {item.data_documento && <span>Data fattura: {formatDate(item.data_documento)}</span>}
          <span>Eliminata: {formatDate(item.deleted_at)}</span>
          <span className={`font-medium ${urgent ? "text-rose-600" : "text-muted-foreground"}`}>
            {days === 0 ? "Eliminazione imminente" : `${days} giorn${days === 1 ? "o" : "i"} al 30°`}
          </span>
        </div>
        <p className="text-[11px] text-muted-foreground/60 font-mono truncate">{item.file_origine}</p>
      </div>

      <div className="text-right flex-shrink-0">
        <p className="font-semibold text-sm">{formatEuro(item.totale)}</p>
      </div>

      <div className="flex gap-1.5 flex-shrink-0">
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1.5 text-xs"
          onClick={() => onRipristina(item)}
          disabled={loading}
          title="Ripristina fattura"
        >
          <ArchiveRestore className="size-3.5" /> Ripristina
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-8 text-muted-foreground hover:text-destructive"
          onClick={() => onElimina(item)}
          disabled={loading}
          title="Elimina definitivamente"
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
    </div>
  );
}

export function CestinoClient({ initialCestino }: { initialCestino: FatturaInCestino[] }) {
  const [cestino, setCestino] = useState<FatturaInCestino[]>(initialCestino);
  const [loading, setLoading] = useState(false);
  const [confirmElimina, setConfirmElimina] = useState<FatturaInCestino | null>(null);
  const [confirmSvuota, setConfirmSvuota] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/cestino");
      if (res.ok) {
        const data = await res.json();
        setCestino(data.cestino ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  async function handleRipristina(item: FatturaInCestino) {
    setLoading(true);
    try {
      const res = await fetch("/api/cestino/ripristina", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origine: item.file_origine }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || "Errore nel ripristino");
        return;
      }
      toast.success(`Fattura ripristinata (${data.righe_ripristinate} prodotti)`);
      await reload();
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setLoading(false);
    }
  }

  async function handleEliminaConferma() {
    if (!confirmElimina) return;
    setActionLoading(true);
    try {
      const res = await fetch("/api/cestino/elimina", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_origine: confirmElimina.file_origine }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || "Errore nell'eliminazione");
        return;
      }
      toast.success(`Fattura eliminata definitivamente (${data.righe_eliminate} prodotti)`);
      setConfirmElimina(null);
      await reload();
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleSvuotaConferma() {
    setActionLoading(true);
    try {
      const res = await fetch("/api/cestino/svuota", { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || "Errore durante lo svuotamento");
        return;
      }
      toast.success(`Cestino svuotato: ${data.righe_eliminate} righe eliminate`);
      setConfirmSvuota(false);
      setCestino([]);
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setActionLoading(false);
    }
  }

  const totaleInCestino = cestino.reduce((s, i) => s + (i.totale || 0), 0);

  return (
    <div className="space-y-5">
      {/* Banner info */}
      <div className="flex items-center gap-3 rounded-lg border border-muted bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
        <TriangleAlert className="size-4 flex-shrink-0" />
        <span className="flex-1">
          Le fatture eliminate vengono conservate per <strong>30 giorni</strong>, poi rimosse automaticamente.
          Puoi ripristinarle o eliminarle definitivamente in qualsiasi momento.
        </span>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        {cestino.length > 0 && (
          <>
            <div className="text-sm text-muted-foreground">
              <strong>{cestino.length}</strong> fattur{cestino.length === 1 ? "a" : "e"} nel cestino
              {totaleInCestino > 0 && ` · ${formatEuro(totaleInCestino)} totale`}
            </div>
            <Button
              variant="destructive"
              size="sm"
              className="h-8 gap-1.5 text-xs ml-auto"
              onClick={() => setConfirmSvuota(true)}
              disabled={loading}
            >
              <Trash2 className="size-3.5" /> Svuota cestino
            </Button>
          </>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-8 text-xs"
          onClick={reload}
          disabled={loading}
        >
          {loading ? <Loader2 className="size-3.5 animate-spin" /> : "Aggiorna"}
        </Button>
      </div>

      {/* List */}
      {cestino.length === 0 ? (
        <div className="rounded-lg border bg-card p-10 text-center space-y-2">
          <ArchiveRestore className="size-12 mx-auto opacity-20" />
          <p className="text-sm font-medium text-muted-foreground">Cestino vuoto</p>
          <p className="text-xs text-muted-foreground">Le fatture eliminate appariranno qui.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {cestino.map((item) => (
            <CestinoRow
              key={item.file_origine}
              item={item}
              onRipristina={handleRipristina}
              onElimina={setConfirmElimina}
              loading={loading}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmElimina}
        title="Eliminazione definitiva"
        description={`Stai per eliminare definitivamente la fattura "${confirmElimina?.fornitore || confirmElimina?.file_origine}". Questa operazione è irreversibile.`}
        confirmLabel="Elimina definitivamente"
        onConfirm={handleEliminaConferma}
        onCancel={() => setConfirmElimina(null)}
        loading={actionLoading}
      />

      <ConfirmDialog
        open={confirmSvuota}
        title="Svuota cestino"
        description={`Stai per eliminare definitivamente tutte le ${cestino.length} fatture nel cestino. Questa operazione è irreversibile e non può essere annullata.`}
        confirmLabel="Svuota tutto"
        onConfirm={handleSvuotaConferma}
        onCancel={() => setConfirmSvuota(false)}
        loading={actionLoading}
      />
    </div>
  );
}
