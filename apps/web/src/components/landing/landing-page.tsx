import Link from "next/link";
import {
  Sparkles,
  Receipt,
  BarChart3,
  Bell,
  Check,
  CheckCircle2,
  ArrowRight,
  MessageCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";
import { WHATSAPP_NUMERO } from "@/lib/assistenza";
import { LANDING, WHATSAPP_LANDING_MSG } from "@/lib/landing-content";

const FEATURE_ICONS = {
  Sparkles,
  Receipt,
  BarChart3,
  Bell,
} as const;

function waLink(msg: string = WHATSAPP_LANDING_MSG): string {
  return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(msg)}`;
}

// CTA primario (verde WhatsApp) e secondario (outline brand), riusati ovunque.
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
            className={cn(
              "rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted",
            )}
          >
            {c.nav.accediLabel}
          </Link>
        </div>
      </header>

      <main>
        {/* ---- Hero ---- */}
        <section className="relative overflow-hidden">
          {/* glow di sfondo */}
          <div
            aria-hidden
            className="pointer-events-none absolute -top-40 left-1/2 size-[600px] -translate-x-1/2 rounded-full bg-primary/20 blur-[120px]"
          />
          <div className="relative mx-auto max-w-6xl px-5 pt-20 pb-16 text-center sm:pt-28">
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
              <Sparkles className="size-4" />
              {c.hero.eyebrow}
            </span>
            <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              {c.hero.title}
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
              {c.hero.subtitle}
            </p>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
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

        {/* ---- Anteprima app (mockup) ---- */}
        <section className="mx-auto max-w-6xl px-5 pb-20">
          <AppPreview />
        </section>

        {/* ---- Problema ---- */}
        <section className="border-y border-border/60 bg-muted/30">
          <div className="mx-auto max-w-4xl px-5 py-20 text-center">
            <h2 className="text-3xl font-bold tracking-tight">{c.problema.title}</h2>
            <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
              {c.problema.paragrafo}
            </p>
            <ul className="mx-auto mt-8 grid max-w-2xl gap-3 text-left sm:grid-cols-1">
              {c.problema.bullets.map((b) => (
                <li
                  key={b}
                  className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3"
                >
                  <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-destructive/15 text-destructive">
                    ✕
                  </span>
                  <span className="text-sm">{b}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---- Funzionalità ---- */}
        <section className="mx-auto max-w-6xl px-5 py-20">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">{c.features.title}</h2>
            <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
              {c.features.subtitle}
            </p>
          </div>
          <div className="mt-12 grid gap-5 sm:grid-cols-2">
            {c.features.items.map((f) => {
              const Icon = FEATURE_ICONS[f.icon as keyof typeof FEATURE_ICONS];
              return (
                <div
                  key={f.title}
                  className="rounded-2xl border border-border bg-card p-6 ring-1 ring-foreground/5 transition-colors hover:border-primary/40"
                >
                  <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    {Icon ? <Icon className="size-6" /> : null}
                  </div>
                  <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm text-muted-foreground">{f.text}</p>
                </div>
              );
            })}
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
            <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
              {c.offerta.text}
            </p>
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
              <h2 className="text-3xl font-bold tracking-tight">{c.prezzi.title}</h2>
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
            <a
              href={waLink()}
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors hover:text-foreground"
            >
              WhatsApp
            </a>
            <a
              href={`mailto:${c.footer.email}`}
              className="transition-colors hover:text-foreground"
            >
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

// Mockup stilizzato dell'app (non uno screenshot reale): mostra a colpo d'occhio
// il "buongiorno" + un KPI + un alert prezzi. Da sostituire con screenshot veri
// quando li avremo.
function AppPreview() {
  return (
    <div className="relative mx-auto max-w-3xl">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-8 -top-6 bottom-0 rounded-3xl bg-primary/20 blur-2xl"
      />
      <div className="relative rounded-3xl border border-border bg-card p-4 shadow-2xl ring-1 ring-foreground/10 sm:p-6">
        {/* finta barra finestra */}
        <div className="mb-4 flex items-center gap-1.5">
          <span className="size-3 rounded-full bg-destructive/40" />
          <span className="size-3 rounded-full bg-amber-400/40" />
          <span className="size-3 rounded-full bg-emerald-400/40" />
          <span className="ml-3 text-xs text-muted-foreground">{LANDING.preview.title}</span>
        </div>

        {/* briefing */}
        <div className="rounded-2xl border border-border bg-background/60 p-5">
          <p className="text-sm font-semibold text-primary">Buongiorno, Marco 👋</p>
          <p className="mt-2 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">🔥 Maggio chiuso con €&nbsp;12.480 di margine</span>, +14% rispetto ad aprile. Oggi c&apos;è un rincaro da tenere d&apos;occhio.
          </p>
        </div>

        {/* riga KPI + alert */}
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="rounded-2xl border border-border bg-background/60 p-4">
            <p className="text-xs text-muted-foreground">Food cost</p>
            <p className="mt-1 text-2xl font-bold">28,4%</p>
            <p className="mt-1 text-xs text-emerald-500">in linea</p>
          </div>
          <div className="rounded-2xl border border-border bg-background/60 p-4">
            <p className="text-xs text-muted-foreground">Margine mese</p>
            <p className="mt-1 text-2xl font-bold">€ 12.480</p>
            <p className="mt-1 text-xs text-emerald-500">▲ +14%</p>
          </div>
          <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4">
            <p className="flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
              <Bell className="size-3.5" /> Alert prezzi
            </p>
            <p className="mt-1 text-sm font-semibold">Olio EVO +9%</p>
            <p className="mt-1 text-xs text-muted-foreground">~ €&nbsp;120/mese in più</p>
          </div>
        </div>
      </div>
    </div>
  );
}
