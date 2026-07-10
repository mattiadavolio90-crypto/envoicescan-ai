import Link from "next/link";
import { Logo, Wordmark } from "@/components/brand/logo";

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border">
        <div className="mx-auto w-full max-w-3xl px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <Logo variant="icon" size={28} glow />
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/privacy" className="text-muted-foreground hover:text-foreground">
              Privacy
            </Link>
            <Link href="/termini" className="text-muted-foreground hover:text-foreground">
              Termini
            </Link>
            <Link href="/login" className="text-primary hover:underline">
              Accedi
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <div className="mx-auto w-full max-w-3xl px-4 py-10">{children}</div>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto w-full max-w-3xl px-4 py-6 text-xs text-muted-foreground">
          RECOMASYSTEM Srl — P.IVA 12993240154 ·{" "}
          <a href="mailto:md@oneflux.it" className="hover:text-foreground">
            md@oneflux.it
          </a>
        </div>
      </footer>
    </div>
  );
}
