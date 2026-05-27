"use client";

import { useCallback, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  FileText,
  Info,
  Loader2,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type FileStatus = "waiting" | "uploading" | "success" | "error" | "skipped";

type FileEntry = {
  id: string;
  file: File;
  status: FileStatus;
  righe?: number;
  righe_preesistenti?: number;
  fornitore?: string;
  data_documento?: string;
  needs_review?: number;
  error?: string;
  skip_motivo?: string;
};

const ACCEPTED_EXTS = [".xml", ".p7m"];
const MAX_SIZE_MB = 50;

function StatusIcon({ status }: { status: FileStatus }) {
  if (status === "uploading") return <Loader2 className="size-4 animate-spin text-primary shrink-0" />;
  if (status === "success") return <CheckCircle className="size-4 text-emerald-500 shrink-0" />;
  if (status === "skipped") return <Info className="size-4 text-sky-500 shrink-0" />;
  if (status === "error") return <XCircle className="size-4 text-destructive shrink-0" />;
  return <FileText className="size-4 text-muted-foreground shrink-0" />;
}

function humanSize(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadModal() {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const valid = arr.filter((f) => {
      const ext = "." + f.name.split(".").pop()?.toLowerCase();
      return ACCEPTED_EXTS.includes(ext) && f.size <= MAX_SIZE_MB * 1024 * 1024;
    });
    setFiles((prev) => {
      const existing = new Set(prev.map((e) => e.file.name));
      const ne = valid
        .filter((f) => !existing.has(f.name))
        .map((f) => ({ id: crypto.randomUUID(), file: f, status: "waiting" as const }));
      return [...prev, ...ne];
    });
  }, []);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  function removeFile(id: string) {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }

  async function uploadAll() {
    const toUpload = files.filter((f) => f.status === "waiting" || f.status === "error");
    if (!toUpload.length) return;
    setUploading(true);

    // Recupera il session token dal server per chiamare direttamente il worker
    // (bypass del limite 4.5MB delle Vercel API routes).
    let workerUrl = "";
    let token = "";
    try {
      const tokRes = await fetch("/api/upload/session-token");
      if (!tokRes.ok) throw new Error("Sessione non valida");
      const tokData = await tokRes.json();
      workerUrl = tokData.worker_url;
      token = tokData.token;
    } catch {
      setFiles((prev) =>
        prev.map((f) =>
          toUpload.find((t) => t.id === f.id)
            ? { ...f, status: "error", error: "Sessione non valida — rifai login" }
            : f,
        ),
      );
      setUploading(false);
      return;
    }

    // Segnala al worker l'inizio sessione: aggiorna nuovi_da = now().
    // I prodotti di questa sessione avranno created_at >= nuovi_da → badge "Nuovo".
    // I prodotti delle sessioni precedenti perderanno il badge.
    await fetch(`${workerUrl}/api/upload/start-session`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => null); // non bloccare l'upload se fallisce

    for (const entry of toUpload) {
      setFiles((prev) => prev.map((f) => (f.id === entry.id ? { ...f, status: "uploading" } : f)));
      const form = new FormData();
      form.append("file", entry.file);
      try {
        const res = await fetch(`${workerUrl}/api/upload/invoice`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === entry.id
                ? { ...f, status: "error", error: data.detail ?? data.error ?? `HTTP ${res.status}` }
                : f,
            ),
          );
        } else {
          const errStr = String(data.error ?? "");
          const isAlreadyLoaded = errStr.startsWith("ALREADY_LOADED:");
          setFiles((prev) =>
            prev.map((f) =>
              f.id === entry.id
                ? {
                    ...f,
                    status: data.success
                      ? "success"
                      : isAlreadyLoaded
                        ? "skipped"
                        : "error",
                    righe: data.righe_salvate,
                    righe_preesistenti: data.righe_preesistenti ?? 0,
                    fornitore: data.fornitore,
                    data_documento: data.data_documento,
                    needs_review: data.needs_review_count,
                    error: data.success || isAlreadyLoaded ? undefined : data.error,
                    skip_motivo: isAlreadyLoaded
                      ? errStr.slice("ALREADY_LOADED:".length) || "fattura già presente"
                      : undefined,
                  }
                : f,
            ),
          );
        }
      } catch {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === entry.id ? { ...f, status: "error", error: "Errore di rete" } : f,
          ),
        );
      }
    }
    setUploading(false);
  }

  function closeAndRefresh() {
    setOpen(false);
    setTimeout(() => window.location.reload(), 80);
  }

  const pending = files.filter((f) => f.status === "waiting" || f.status === "error").length;
  const success = files.filter((f) => f.status === "success").length;
  const skipped = files.filter((f) => f.status === "skipped").length;
  const totRighe = files.reduce((sum, f) => sum + (f.righe ?? 0), 0);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm">
            <Upload className="size-4" />
            Carica fatture
          </Button>
        }
      />
      <DialogContent className="!max-w-2xl">
        <DialogTitle>Carica fatture</DialogTitle>
        <DialogDescription>
          Formati accettati: XML, P7M · ricaricando lo stesso file le righe vengono sostituite, non duplicate.
        </DialogDescription>

        <div
          className={`border-2 border-dashed rounded-lg cursor-pointer transition-colors py-8 flex flex-col items-center gap-2 ${
            dragging
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/30 hover:border-primary/50"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
        >
          <Upload
            className={`size-7 ${dragging ? "text-primary" : "text-muted-foreground/60"}`}
          />
          <p className="text-sm font-medium">
            {dragging ? "Rilascia qui" : "Trascina file XML o P7M"}
          </p>
          <p className="text-xs text-muted-foreground">o clicca per scegliere</p>
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".xml,.p7m"
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />

        {files.length > 0 && (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {files.map((entry) => (
              <div
                key={entry.id}
                className="flex items-start gap-2 rounded-md border p-2 text-xs"
              >
                <StatusIcon status={entry.status} />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{entry.file.name}</p>
                  <p className="text-muted-foreground">{humanSize(entry.file.size)}</p>
                  {entry.status === "success" && (
                    <p className="text-emerald-600 mt-0.5">
                      {entry.fornitore ? `${entry.fornitore} · ` : ""}
                      {entry.righe} righe
                      {entry.data_documento ? ` · ${entry.data_documento}` : ""}
                      {(entry.needs_review ?? 0) > 0 && (
                        <span className="text-amber-500 ml-1">
                          <AlertTriangle className="size-3 inline mr-0.5" />
                          {entry.needs_review} {entry.needs_review === 1 ? "riga ha" : "righe hanno"} categoria da verificare
                        </span>
                      )}
                    </p>
                  )}
                  {entry.status === "skipped" && (
                    <p className="text-amber-600 mt-0.5">
                      Fattura scartata perché già caricata in precedenza.
                    </p>
                  )}
                  {entry.status === "error" && (
                    <p className="text-destructive mt-0.5">{entry.error}</p>
                  )}
                </div>
                {entry.status !== "uploading" && (
                  <button
                    onClick={() => removeFile(entry.id)}
                    className="text-muted-foreground hover:text-foreground shrink-0"
                  >
                    <X className="size-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between gap-2 -mx-4 -mb-4 mt-2 px-4 py-3 border-t bg-muted/50 rounded-b-xl">
          <span className="text-xs text-muted-foreground">
            {success > 0 && (
              <span className="text-emerald-600 font-medium">
                {success === 1 ? "1 caricata" : `${success} caricate`} · {totRighe} righe
              </span>
            )}
            {skipped > 0 && (
              <span className="text-amber-600 font-medium ml-2">
                · {skipped} {skipped === 1 ? "scartata" : "scartate"}
              </span>
            )}
          </span>
          <div className="flex gap-2">
            {(success > 0 || skipped > 0) && (
              <Button variant="outline" size="sm" onClick={closeAndRefresh}>
                Chiudi e aggiorna
              </Button>
            )}
            <Button
              size="sm"
              onClick={uploadAll}
              disabled={uploading || pending === 0}
            >
              {uploading ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Caricamento...
                </>
              ) : (
                <>
                  <Upload className="size-4" />
                  {pending > 0 ? `Carica ${pending} file` : "Tutto caricato"}
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
