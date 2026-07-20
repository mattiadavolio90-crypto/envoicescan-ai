"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  FileText,
  Info,
  Loader2,
  MapPin,
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

type FileStatus = "waiting" | "uploading" | "success" | "error" | "skipped" | "queued";

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
  sede_assegnata?: string;
  cross_sede?: boolean;
  queue_created?: boolean;
};

const ACCEPTED_EXTS = [".xml", ".p7m"];
const MAX_SIZE_MB = 50;

function StatusIcon({ status }: { status: FileStatus }) {
  if (status === "uploading") return <Loader2 className="size-4 animate-spin text-primary shrink-0" />;
  if (status === "success") return <CheckCircle className="size-4 text-emerald-500 shrink-0" />;
  if (status === "queued") return <MapPin className="size-4 text-amber-500 shrink-0" />;
  if (status === "skipped") return <Info className="size-4 text-sky-500 shrink-0" />;
  if (status === "error") return <XCircle className="size-4 text-destructive shrink-0" />;
  return <FileText className="size-4 text-muted-foreground shrink-0" />;
}

function humanSize(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

// `contesto` cambia SOLO cosa si dice delle fatture finite in coda, mai come si
// caricano: il worker decide il locale dal documento (P.IVA + indirizzo) e non
// riceve alcun ristorante_id dal client, quindi caricare dalla catena o da un PV
// dà lo stesso identico esito. Ma la coda "da assegnare" vive solo in catena: da
// un PV va detto dove sono finite, altrimenti spariscono in un posto che da lì
// non si vede.
export function UploadModal({ contesto = "pv" }: { contesto?: "pv" | "catena" } = {}) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const estensioneInvalida: string[] = [];
    const troppoGrandi: string[] = [];
    const valid = arr.filter((f) => {
      const ext = "." + f.name.split(".").pop()?.toLowerCase();
      const extOk = ACCEPTED_EXTS.includes(ext);
      const sizeOk = f.size <= MAX_SIZE_MB * 1024 * 1024;
      if (!extOk) estensioneInvalida.push(f.name);
      else if (!sizeOk) troppoGrandi.push(f.name);
      return extOk && sizeOk;
    });
    // Prima questi file sparivano senza traccia: l'utente trascinava N file e ne
    // vedeva meno nella lista senza sapere quali erano stati esclusi o perché.
    if (estensioneInvalida.length > 0) {
      toast.warning(
        `Formato non supportato, ${estensioneInvalida.length === 1 ? "escluso" : "esclusi"}: ${estensioneInvalida.join(", ")}`,
      );
    }
    if (troppoGrandi.length > 0) {
      toast.warning(
        `Oltre ${MAX_SIZE_MB}MB, ${troppoGrandi.length === 1 ? "escluso" : "esclusi"}: ${troppoGrandi.join(", ")}`,
      );
    }
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

    await fetch("/api/upload/start-session", { method: "POST" }).catch(() => null);

    for (const entry of toUpload) {
      setFiles((prev) => prev.map((f) => (f.id === entry.id ? { ...f, status: "uploading" } : f)));
      const form = new FormData();
      form.append("file", entry.file);
      try {
        const res = await fetch("/api/upload/invoice", {
          method: "POST",
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
          // Multi-sede AMBIGUO: la P.IVA e' del cliente ma l'indirizzo non distingue
          // la sede. NON piu' scartata: il worker l'ha messa in coda 'da_assegnare'
          // (data.success=true, routing_status='ambiguo', queue_id valorizzato). Il
          // cliente la assegnera' a una sede o la ripartira' sul gruppo dalla coda.
          //
          // queue_created distingue NUOVA (true, appena entrata in coda) da GIA'
          // PRESENTE (false, la RPC l'ha riconosciuta via hash e non ha creato nulla
          // — stesso event_id). Prima entrambe finivano su "queued" col contatore
          // "N da assegnare", indistinguibili a schermo dalle nuove: un ricaricamento
          // dell'intera cartella sembrava aggiungere N fatture quando in realta' non
          // aggiungeva nulla. Ora una duplicata-in-coda e' "skipped", come qualsiasi
          // altro doppione (stesso trattamento di ALREADY_LOADED).
          const isQueuedAmbiguo = data.success === true && data.routing_status === "ambiguo" && data.queue_created !== false;
          const isGiaInCoda = data.success === true && data.routing_status === "ambiguo" && data.queue_created === false;
          // P.IVA non di nessuna sede del cliente: ancora scartata (guardia intatta).
          const isPivaEstranea = errStr === "PIVA_NESSUNA_SEDE";
          const isSkip = isAlreadyLoaded || isPivaEstranea || isGiaInCoda;
          setFiles((prev) =>
            prev.map((f) =>
              f.id === entry.id
                ? {
                    ...f,
                    status: isQueuedAmbiguo
                      ? "queued"
                      : data.success
                        ? "success"
                        : isSkip
                          ? "skipped"
                          : "error",
                    righe: data.righe_salvate,
                    righe_preesistenti: data.righe_preesistenti ?? 0,
                    fornitore: data.fornitore,
                    data_documento: data.data_documento,
                    needs_review: data.needs_review_count,
                    sede_assegnata: data.sede_assegnata,
                    cross_sede: data.cross_sede ?? false,
                    queue_created: data.queue_created ?? undefined,
                    error: data.success || isSkip ? undefined : data.error,
                    skip_motivo: isAlreadyLoaded
                      ? errStr.slice("ALREADY_LOADED:".length) || "fattura già presente"
                      : isPivaEstranea
                        ? "PIVA_NESSUNA_SEDE"
                        : isGiaInCoda
                          ? "GIA_IN_CODA"
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
  const queued = files.filter((f) => f.status === "queued").length;
  const errored = files.filter((f) => f.status === "error").length;
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
          Formati accettati: XML, P7M · ricaricando lo stesso file viene scartato e non duplicato.
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
                      {entry.sede_assegnata && (
                        <span
                          className={`ml-1 ${entry.cross_sede ? "text-amber-600 font-medium" : "text-sky-600"}`}
                        >
                          → {entry.sede_assegnata}
                          {entry.cross_sede && " (altra sede)"}
                        </span>
                      )}
                      {(entry.needs_review ?? 0) > 0 && (
                        <span className="text-amber-500 ml-1">
                          <AlertTriangle className="size-3 inline mr-0.5" />
                          {entry.needs_review} {entry.needs_review === 1 ? "riga ha" : "righe hanno"} categoria da verificare
                        </span>
                      )}
                    </p>
                  )}
                  {entry.status === "queued" && (
                    <p className="text-amber-600 mt-0.5">
                      Intestata alla società, non a un locale: è in attesa che tu scelga dove va.
                    </p>
                  )}
                  {entry.status === "skipped" && (
                    <p className="text-amber-600 mt-0.5">
                      {entry.skip_motivo === "PIVA_NESSUNA_SEDE"
                        ? "Questa fattura è intestata a una partita IVA che non corrisponde a nessuna tua sede: non è stata caricata."
                        : entry.skip_motivo === "GIA_IN_CODA"
                          ? "Fattura scartata perché già caricata. In coda da assegnare."
                          : entry.sede_assegnata
                            ? `Già caricata in precedenza su ${entry.sede_assegnata}.`
                            : "Fattura scartata perché già caricata in precedenza."}
                    </p>
                  )}
                  {entry.status === "error" && (
                    <p className="text-destructive mt-0.5">
                      {entry.error === "NESSUNA_SEDE_CONFIGURATA"
                        ? "Nessuna sede configurata su questo account: aggiungi una sede dal pannello prima di caricare le fatture."
                        : entry.error}
                    </p>
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

        {/* Fatture finite in coda: l'istruzione su cosa fare va data UNA volta, qui,
            non ripetuta su ogni riga. Dal PV la coda non è raggiungibile (vive solo
            in catena): senza questo avviso le fatture sparirebbero in un posto che
            da qui non si vede. */}
        {queued > 0 && !uploading && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
            <MapPin className="size-4 shrink-0 text-amber-500" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-amber-700 dark:text-amber-400">
                {queued === 1
                  ? "1 fattura è intestata alla società, non a un locale"
                  : `${queued} fatture sono intestate alla società, non a un locale`}
              </p>
              <p className="mt-0.5 text-muted-foreground">
                {contesto === "catena"
                  ? "Le trovi qui sotto in “Gestione fatture di gruppo”: assegnale a un locale o dividile tra i locali."
                  : "Per assegnarle a un locale o dividerle tra i locali, vai nella vista del gruppo."}
              </p>
              {contesto === "pv" && (
                <Link
                  href="/catena"
                  className="mt-1.5 inline-flex items-center gap-1 font-medium text-amber-700 underline underline-offset-2 hover:text-amber-800 dark:text-amber-400"
                >
                  Vai alla vista del gruppo
                  <ArrowRight className="size-3" />
                </Link>
              )}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between gap-2 -mx-4 -mb-4 mt-2 px-4 py-3 border-t bg-muted/50 rounded-b-xl">
          <span className="text-xs text-muted-foreground">
            {success > 0 && (
              <span className="text-emerald-600 font-medium">
                {success === 1 ? "1 caricata" : `${success} caricate`} · {totRighe} righe
              </span>
            )}
            {queued > 0 && (
              <span className="text-amber-600 font-medium ml-2">
                · {queued} da assegnare
              </span>
            )}
            {skipped > 0 && (
              <span className="text-amber-600 font-medium ml-2">
                · {skipped} {skipped === 1 ? "scartata" : "scartate"}
              </span>
            )}
            {errored > 0 && (
              <span className="text-destructive font-medium ml-2">
                · {errored} {errored === 1 ? "non caricata" : "non caricate"}
              </span>
            )}
          </span>
          <div className="flex gap-2">
            {/* `queued` va incluso: caricando SOLO fatture che finiscono in coda
                (tipico di OFFSIDE, che ha la sede legale su quasi tutte) il bottone
                non compariva e restava la sola X del Dialog, che non ricarica —
                l'utente tornava a una pagina che non sapeva del nuovo caricamento. */}
            {(success > 0 || skipped > 0 || queued > 0) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  // Chiudere qui fa un reload completo (vedi closeAndRefresh): lo stato
                  // dei file in errore (nome, motivo) va perso. Se ce ne sono ancora,
                  // meglio far confermare esplicitamente piuttosto che farli sparire
                  // senza che l'utente li abbia notati.
                  if (
                    errored === 0 ||
                    confirm(
                      `${errored} ${errored === 1 ? "file non è stato caricato" : "file non sono stati caricati"}. Chiudendo perderai l'elenco di quali. Continuare?`,
                    )
                  ) {
                    closeAndRefresh();
                  }
                }}
              >
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
