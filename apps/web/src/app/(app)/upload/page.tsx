"use client";

import { useState, useRef, useCallback } from "react";
import { Upload, FileText, CheckCircle, XCircle, AlertTriangle, Loader2, X } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type FileStatus = "waiting" | "uploading" | "success" | "error";

type FileEntry = {
  id: string;
  file: File;
  status: FileStatus;
  righe?: number;
  fornitore?: string;
  data_documento?: string;
  needs_review?: number;
  error?: string;
  elapsed_ms?: number;
};

const ACCEPTED_EXTS = [".xml", ".p7m"];
const MAX_SIZE_MB = 50;

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusIcon({ status }: { status: FileStatus }) {
  if (status === "uploading") return <Loader2 className="size-5 animate-spin text-primary" />;
  if (status === "success") return <CheckCircle className="size-5 text-emerald-500" />;
  if (status === "error") return <XCircle className="size-5 text-destructive" />;
  return <FileText className="size-5 text-muted-foreground" />;
}

export default function UploadPage() {
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
      const existingNames = new Set(prev.map((e) => e.file.name));
      const newEntries: FileEntry[] = valid
        .filter((f) => !existingNames.has(f.name))
        .map((f) => ({ id: crypto.randomUUID(), file: f, status: "waiting" }));
      return [...prev, ...newEntries];
    });
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const uploadAll = async () => {
    const toUpload = files.filter((f) => f.status === "waiting" || f.status === "error");
    if (!toUpload.length) return;
    setUploading(true);

    for (const entry of toUpload) {
      setFiles((prev) =>
        prev.map((f) => (f.id === entry.id ? { ...f, status: "uploading" } : f))
      );

      const form = new FormData();
      form.append("file", entry.file);

      try {
        const res = await fetch("/api/upload", { method: "POST", body: form });
        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === entry.id
                ? { ...f, status: "error", error: data.error ?? `HTTP ${res.status}` }
                : f
            )
          );
        } else {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === entry.id
                ? {
                    ...f,
                    status: data.success ? "success" : "error",
                    righe: data.righe_salvate,
                    fornitore: data.fornitore,
                    data_documento: data.data_documento,
                    needs_review: data.needs_review_count,
                    error: data.success ? undefined : (data.error ?? "Errore sconosciuto"),
                    elapsed_ms: data.elapsed_ms,
                  }
                : f
            )
          );
        }
      } catch {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === entry.id
              ? { ...f, status: "error", error: "Errore di rete" }
              : f
          )
        );
      }
    }

    setUploading(false);
  };

  const pendingCount = files.filter((f) => f.status === "waiting" || f.status === "error").length;
  const successCount = files.filter((f) => f.status === "success").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Carica Documenti</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Formati accettati: XML, P7M — Max {MAX_SIZE_MB}MB per file
        </p>
      </div>

      {/* DROP ZONE */}
      <Card
        className={`border-2 border-dashed cursor-pointer transition-colors ${
          dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
      >
        <CardContent className="py-14 flex flex-col items-center gap-3 text-center">
          <Upload className={`size-10 ${dragging ? "text-primary" : "text-muted-foreground/50"}`} />
          <div>
            <p className="font-medium">
              {dragging ? "Rilascia i file qui" : "Trascina i file qui o clicca per selezionarli"}
            </p>
            <p className="text-sm text-muted-foreground mt-1">XML · P7M · max {MAX_SIZE_MB}MB</p>
          </div>
        </CardContent>
      </Card>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".xml,.p7m"
        className="hidden"
        onChange={(e) => e.target.files && addFiles(e.target.files)}
      />

      {/* FILE LIST */}
      {files.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                {files.length} file — {successCount} elaborati
              </CardTitle>
              <Button
                size="sm"
                onClick={uploadAll}
                disabled={uploading || pendingCount === 0}
              >
                {uploading ? (
                  <>
                    <Loader2 className="size-4 mr-2 animate-spin" />
                    Caricamento...
                  </>
                ) : (
                  <>
                    <Upload className="size-4 mr-2" />
                    {pendingCount > 0 ? `Carica ${pendingCount} file` : "Tutti caricati"}
                  </>
                )}
              </Button>
            </div>
            <CardDescription>
              I file già presenti verranno sostituiti automaticamente (idempotente)
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            {files.map((entry) => (
              <div
                key={entry.id}
                className="flex items-start gap-3 rounded-lg border p-3 text-sm"
              >
                <StatusIcon status={entry.status} />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{entry.file.name}</p>
                  <p className="text-xs text-muted-foreground">{humanSize(entry.file.size)}</p>

                  {entry.status === "success" && (
                    <div className="mt-1.5 space-y-0.5">
                      {entry.fornitore && (
                        <p className="text-xs text-emerald-600">
                          Fornitore: <span className="font-medium">{entry.fornitore}</span>
                        </p>
                      )}
                      <p className="text-xs text-emerald-600">
                        {entry.righe} righe salvate
                        {entry.data_documento ? ` · ${entry.data_documento}` : ""}
                      </p>
                      {(entry.needs_review ?? 0) > 0 && (
                        <p className="text-xs text-amber-500 flex items-center gap-1">
                          <AlertTriangle className="size-3" />
                          {entry.needs_review} righe da verificare (categoria incerta)
                        </p>
                      )}
                      {entry.elapsed_ms && (
                        <p className="text-xs text-muted-foreground">{entry.elapsed_ms}ms</p>
                      )}
                    </div>
                  )}

                  {entry.status === "error" && (
                    <p className="mt-1 text-xs text-destructive">{entry.error}</p>
                  )}
                </div>
                {entry.status !== "uploading" && (
                  <button
                    onClick={() => removeFile(entry.id)}
                    className="text-muted-foreground hover:text-foreground transition-colors"
                    title="Rimuovi"
                  >
                    <X className="size-4" />
                  </button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* EMPTY STATE */}
      {files.length === 0 && (
        <p className="text-sm text-muted-foreground text-center">
          Nessun file selezionato. Trascina le tue fatture XML o P7M nell&apos;area sopra.
        </p>
      )}
    </div>
  );
}
