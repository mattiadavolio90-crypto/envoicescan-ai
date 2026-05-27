"use client";

import { useState, useRef } from "react";
import { Upload, FileSpreadsheet, X, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { RicaviImportXlsResponse } from "@/lib/ricavi";

type Props = {
  onImported?: () => void;
  trigger?: React.ReactNode;
};

export function UploadXlsModal({ onImported, trigger }: Props) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RicaviImportXlsResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setResult(null);
    setLoading(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/ricavi/import-xls", { method: "POST", body: fd });
      if (!res.ok) throw new Error();
      const data: RicaviImportXlsResponse = await res.json();
      setResult(data);
      if (data.inserted + data.updated > 0) {
        toast.success(`${data.inserted + data.updated} righe importate`);
        onImported?.();
      } else {
        toast.warning("Nessuna riga valida importata");
      }
    } catch {
      toast.error("Errore nell'import del file");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger
        render={
          (trigger as React.ReactElement) ?? (
            <Button variant="outline" size="sm" className="gap-1.5">
              <Upload className="size-3.5" />
              Carica XLS
            </Button>
          )
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="size-5 text-primary" />
            Importa ricavi da Excel
          </DialogTitle>
          <DialogDescription>
            Carica un file <code className="text-xs">.xlsx</code> / <code className="text-xs">.csv</code> con
            colonne: <strong>data</strong> + <strong>iva10</strong> + <strong>iva22</strong> +{" "}
            <strong>altri</strong> (opz.).
          </DialogDescription>
        </DialogHeader>

        {!result && (
          <div className="space-y-3">
            <label
              htmlFor="xls-file"
              className={`flex flex-col items-center justify-center rounded-md border-2 border-dashed py-8 cursor-pointer transition-colors ${
                file ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
              }`}
            >
              <Upload className="size-8 text-muted-foreground/60 mb-2" />
              {file ? (
                <>
                  <p className="text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {(file.size / 1024).toFixed(1)} KB · cambia file
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-medium">Clicca per selezionare</p>
                  <p className="text-xs text-muted-foreground mt-1">.xlsx, .xls, .csv</p>
                </>
              )}
              <input
                ref={inputRef}
                id="xls-file"
                type="file"
                accept=".xlsx,.xls,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>

            <div className="flex gap-2 justify-end">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                Annulla
              </Button>
              <Button size="sm" disabled={!file || loading} onClick={handleUpload}>
                {loading ? "Caricamento…" : "Importa"}
              </Button>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-3">
            <div className="rounded-md border border-border p-3 space-y-1.5">
              <div className="flex items-center gap-2 font-medium text-sm">
                <CheckCircle2 className="size-4 text-emerald-500" />
                Import completato
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                <div>Righe nel file: <strong className="text-foreground">{result.parsed_rows}</strong></div>
                <div>Inserite: <strong className="text-emerald-600">{result.inserted}</strong></div>
                <div>Aggiornate: <strong className="text-sky-600">{result.updated}</strong></div>
                <div>Scartate: <strong className="text-muted-foreground">{result.skipped}</strong></div>
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 max-h-32 overflow-y-auto">
                <div className="flex items-center gap-2 font-medium text-sm text-amber-700 dark:text-amber-400 mb-1">
                  <AlertCircle className="size-4" />
                  Avvisi ({result.errors.length})
                </div>
                <ul className="text-xs space-y-0.5 text-muted-foreground">
                  {result.errors.slice(0, 10).map((e, i) => (
                    <li key={i}>· {e}</li>
                  ))}
                  {result.errors.length > 10 && (
                    <li className="italic">… e altri {result.errors.length - 10}</li>
                  )}
                </ul>
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <Button variant="ghost" size="sm" onClick={reset}>
                Carica un altro
              </Button>
              <Button size="sm" onClick={() => setOpen(false)}>
                <X className="size-3.5 mr-1" />
                Chiudi
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
