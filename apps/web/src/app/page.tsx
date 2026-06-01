import { Logo } from "@/components/brand/logo";

export default function Home() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-8 p-8">
      <div className="flex flex-col items-center gap-4 text-center">
        <Logo variant="full" size={56} glow />
        <p className="text-muted-foreground text-sm max-w-sm">
          Nuova interfaccia — in costruzione.
          <br />
          L&apos;app attuale è disponibile su{" "}
          <a href="#" className="text-primary underline underline-offset-4">
            app.oneflux.it
          </a>
        </p>
      </div>

      <div className="flex gap-3">
        <a
          href="/login"
          className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90"
        >
          Accedi
        </a>
        <a
          href="#"
          className="inline-flex h-10 items-center justify-center rounded-md border border-input bg-background px-6 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          Torna a Streamlit
        </a>
      </div>

      <p className="text-xs text-muted-foreground">Fase 1 — scheletro attivo</p>
    </div>
  );
}
