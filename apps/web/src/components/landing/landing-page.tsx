import Link from "next/link";
import { Check, X, ArrowRight, MessageCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";
import { WHATSAPP_NUMERO } from "@/lib/assistenza";
import { LANDING, WHATSAPP_LANDING_MSG } from "@/lib/landing-content";
import { ChatDemo } from "@/components/landing/chat-demo";

function waLink(msg: string = WHATSAPP_LANDING_MSG): string {
  return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(msg)}`;
}

const CTA_PRIMARY =
  "inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:bg-primary/90 hover:shadow-primary/40";
const CTA_SECONDARY =
  "inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-background/40 px-6 py-3 text-base font-semibold text-foreground transition-colors hover:bg-muted";

export function LandingPage() {
  const c = LANDING;

  return (
    <div className="min-h-dvh bg-background text-foreground">
      {/* ---- Nav ---- */}
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Logo size={30} />
          <Link
            href={c.nav.accediHref}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted"
          >
            {c.nav.accediLabel}
          </Link>
        </div>
      </header>

      <main>
        {/* ---- Hero: titolo + demo VIVA dell'assistente ---- */}
        <section className="relative overflow-hidden">
          <div
            aria-hidden
            className="pointer-events-none absolute -top-40 left-1/2 size-[640px] -translate-x-1/2 rounded-full bg-primary/20 blur-[130px]"
          />
          <div className="relative mx-auto max-w-3xl px-5 pt-20 pb-16 text-center sm:pt-28">
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
              {c.hero.eyebrow}
            </span>
            <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-[1.08] tracking-tight sm:text-6xl">
              {c.hero.title}
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground sm:text-xl">
              {c.hero.subtitle}
            </p>

            {/* la prova: la barra del chiedi si scrive da sola e l'AI risponde */}
            <div className="mt-10">
              <ChatDemo scambi={c.hero.scambi} />
            </div>

            <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a href={waLink()} target="_blank" rel="noopener noreferrer" className={CTA_PRIMARY}>
                <MessageCircle className="size-5" />
                {c.hero.ctaPrimary}
              </a>
              <Link href={c.nav.accediHref} className={CTA_SECONDARY}>
                {c.hero.ctaSecondary}
              </Link>
            </div>
            <p className="mt-5 text-sm text-muted-foreground">{c.hero.note}</p>
          </div>
        </section>

        {/* ---- Contrasto: gli altri vs ONEFLUX ---- */}
        <section className="border-y border-border/60 bg-muted/30">
          <div className="mx-auto max-w-5xl px-5 py-20">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{c.contrasto.title}</h2>
              <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
                {c.contrasto.subtitle}
              </p>
            </div>
            <div className="mt-12 space-y-4">
              {c.contrasto.righe.map((r) => (
                <div key={r.tema} className="grid items-stretch gap-3 sm:grid-cols-[1fr_1fr_1fr]">
                  <div className="flex items-center justify-center rounded-xl border border-border bg-card px-4 py-4 text-center font-semibold sm:justify-start sm:text-left">
                    {r.tema}
                  </div>
                  <div className="flex items-start gap-3 rounded-xl border border-border bg-background/40 px-4 py-4">
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
                      <X className="size-3.5" />
                    </span>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Gli altri
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">{r.altri}</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 rounded-xl border border-primary/30 bg-primary/5 px-4 py-4">
                    <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                      <Check className="size-3.5" />
                    </span>
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-primary">
                        ONEFLUX
                      </p>
                      <p className="mt-1 text-sm font-medium">{r.oneflux}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-10 text-center text-base font-medium text-primary">
              {c.contrasto.nota}
            </p>
          </div>
        </section>

        {/* ---- Come funziona (3 step) + strip "cosa ottieni" ---- */}
        <section className="mx-auto max-w-6xl px-5 py-20">
          <h2 className="text-center text-3xl font-bold tracking-tight sm:text-4xl">
            {c.comeFunziona.title}
          </h2>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {c.comeFunziona.step.map((s) => (
              <div
                key={s.n}
                className="relative rounded-2xl border border-border bg-card p-6 ring-1 ring-foreground/5"
              >
                <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-lg font-bold text-primary">
                  {s.n}
                </span>
                <h3 className="mt-4 text-lg font-semibold">{s.titolo}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{s.testo}</p>
              </div>
            ))}
          </div>

          {/* strip compatta: cosa ottieni in cambio (assorbe l'ex sezione "controllo") */}
          <div className="mt-10 rounded-2xl border border-border bg-muted/30 px-6 py-6 text-center">
            <p className="text-sm font-medium text-muted-foreground">{c.controllo.title}</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2.5">
              {c.controllo.chips.map((chip) => (
                <span
                  key={chip}
                  className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-sm"
                >
                  <Check className="size-4 text-primary" />
                  {chip}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* ---- Offerta Recoma ---- */}
        <section className="mx-auto max-w-6xl px-5 pb-20">
          <div className="relative overflow-hidden rounded-3xl border border-primary/30 bg-gradient-to-br from-primary/15 via-card to-card p-8 text-center sm:p-12">
            <span className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground">
              {c.offerta.badge}
            </span>
            <h2 className="mx-auto mt-5 max-w-2xl text-3xl font-bold tracking-tight">
              {c.offerta.title}
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">{c.offerta.text}</p>
            <a
              href={waLink()}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(CTA_PRIMARY, "mt-8")}
            >
              {c.offerta.cta}
              <ArrowRight className="size-5" />
            </a>
          </div>
        </section>

        {/* ---- Prezzi ---- */}
        <section className="border-y border-border/60 bg-muted/30">
          <div className="mx-auto max-w-6xl px-5 py-20">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{c.prezzi.title}</h2>
              <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
                {c.prezzi.subtitle}
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              {c.prezzi.piani.map((p) => (
                <div
                  key={p.nome}
                  className={cn(
                    "relative flex flex-col rounded-2xl border bg-card p-6",
                    p.evidenza
                      ? "border-primary ring-2 ring-primary/40 lg:-translate-y-2 lg:scale-[1.02]"
                      : "border-border ring-1 ring-foreground/5",
                  )}
                >
                  {p.evidenza ? (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
                      Il più scelto
                    </span>
                  ) : null}
                  <h3 className="text-lg font-semibold">{p.nome}</h3>
                  <div className="mt-3 flex items-baseline gap-1">
                    <span className="text-4xl font-bold">{p.prezzo}</span>
                    <span className="text-muted-foreground">{p.periodo}</span>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{p.descrizione}</p>
                  <ul className="mt-6 flex flex-1 flex-col gap-3">
                    {p.features.map((feat) => (
                      <li key={feat} className="flex items-start gap-2.5 text-sm">
                        <Check className="mt-0.5 size-4 shrink-0 text-primary" />
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                  <a
                    href={waLink(
                      `Ciao! Sono interessato al piano ${p.nome} di ONEFLUX per il mio ristorante.`,
                    )}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                      "mt-7 inline-flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors",
                      p.evidenza
                        ? "bg-primary text-primary-foreground hover:bg-primary/90"
                        : "border border-border hover:bg-muted",
                    )}
                  >
                    Scegli {p.nome}
                  </a>
                </div>
              ))}
            </div>
            <p className="mt-8 text-center text-sm text-muted-foreground">{c.prezzi.nota}</p>
          </div>
        </section>

        {/* ---- FAQ ---- */}
        <section className="mx-auto max-w-3xl px-5 py-20">
          <h2 className="text-center text-3xl font-bold tracking-tight">{c.faq.title}</h2>
          <div className="mt-10 space-y-4">
            {c.faq.items.map((item) => (
              <details
                key={item.q}
                className="group rounded-xl border border-border bg-card px-5 py-4 [&_summary]:cursor-pointer"
              >
                <summary className="flex items-center justify-between gap-4 font-medium marker:content-['']">
                  {item.q}
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
                </summary>
                <p className="mt-3 text-sm text-muted-foreground">{item.a}</p>
              </details>
            ))}
          </div>
        </section>

        {/* ---- CTA finale ---- */}
        <section className="mx-auto max-w-6xl px-5 pb-24">
          <div className="rounded-3xl border border-border bg-gradient-to-br from-primary/10 via-card to-card p-10 text-center sm:p-14">
            <h2 className="mx-auto max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">
              {c.ctaFinale.title}
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-lg text-muted-foreground">
              {c.ctaFinale.text}
            </p>
            <a
              href={waLink()}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(CTA_PRIMARY, "mt-8")}
            >
              <MessageCircle className="size-5" />
              {c.ctaFinale.cta}
            </a>
          </div>
        </section>
      </main>

      {/* ---- Footer ---- */}
      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-5 py-10 sm:flex-row sm:justify-between">
          <div className="flex flex-col items-center gap-2 sm:items-start">
            <Logo size={26} />
            <p className="text-sm text-muted-foreground">{c.footer.tagline}</p>
          </div>
          <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
            <a href={waLink()} target="_blank" rel="noopener noreferrer" className="transition-colors hover:text-foreground">
              WhatsApp
            </a>
            <a href={`mailto:${c.footer.email}`} className="transition-colors hover:text-foreground">
              {c.footer.email}
            </a>
            <Link href={c.footer.privacyHref} className="transition-colors hover:text-foreground">
              Privacy
            </Link>
            <Link href={c.footer.terminiHref} className="transition-colors hover:text-foreground">
              Termini
            </Link>
          </nav>
        </div>
        <div className="border-t border-border/60 py-5 text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} ONEFLUX
        </div>
      </footer>
    </div>
  );
}
