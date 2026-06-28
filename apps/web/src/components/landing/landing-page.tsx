import Link from "next/link";
import { ChevronDown, ArrowRight, Check } from "lucide-react";

import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";
import { WHATSAPP_NUMERO } from "@/lib/assistenza";
import { LANDING, WHATSAPP_LANDING_MSG } from "@/lib/landing-content";
import { Scene, Reveal, BlurBg, Kicker } from "@/components/landing/scene-kit";
import { ChatScene } from "@/components/landing/chat-scene";

function waLink(msg: string = WHATSAPP_LANDING_MSG): string {
  return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(msg)}`;
}

const CTA = LANDING.cta;

function CtaButton({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col items-center", className)}>
      <a
        href={waLink()}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-7 py-3.5 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/30 transition-all hover:bg-primary/90 hover:shadow-primary/50"
      >
        {CTA.label}
        <ArrowRight className="size-5" />
      </a>
      <span className="mt-2.5 text-sm text-muted-foreground">{CTA.nota}</span>
    </div>
  );
}

// Titolo di scena con font display (Sora). Supporta "\n" come a-capo forzato.
function SceneTitle({ children, className }: { children: string; className?: string }) {
  return (
    <h2
      className={cn(
        "mx-auto max-w-3xl whitespace-pre-line font-display text-3xl font-bold leading-[1.12] tracking-tight sm:text-5xl",
        className,
      )}
    >
      {children}
    </h2>
  );
}

export function LandingPage() {
  const s = LANDING.scene;

  return (
    <div className="bg-background text-foreground">
      {/* Accedi discreto, fisso in alto a destra */}
      <header className="fixed inset-x-0 top-0 z-50">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Logo size={26} />
          <Link
            href={LANDING.nav.accediHref}
            className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            {LANDING.nav.accediLabel}
          </Link>
        </div>
      </header>

      <main>
        {/* ===== SCENA 0 — Aggancio ===== */}
        <Scene className="bg-[#05070A]">
          <BlurBg src={s.aggancio.bg} />
          <Reveal>
            <Logo size={84} glow />
          </Reveal>
          <Reveal delay={150}>
            <SceneTitle className="mt-10">{s.aggancio.title}</SceneTitle>
          </Reveal>
          <Reveal delay={300}>
            <p className="mt-6 text-base text-muted-foreground sm:text-lg">{s.aggancio.firma}</p>
          </Reveal>
          <div className="absolute bottom-10 flex flex-col items-center gap-1 text-muted-foreground">
            <span className="text-xs uppercase tracking-[0.2em]">{s.aggancio.scrollHint}</span>
            <ChevronDown className="size-5 animate-bounce" />
          </div>
        </Scene>

        {/* ===== SCENA 1 — Lo specchio ===== */}
        <Scene>
          <BlurBg src={s.specchio.bg} />
          <Reveal>
            <Kicker>{s.specchio.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.specchio.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <p className="mt-6 max-w-xl text-lg text-muted-foreground">{s.specchio.sotto}</p>
          </Reveal>
        </Scene>

        {/* ===== SCENA 2 — Lui ti parla (briefing) ===== */}
        <Scene className="bg-[#05070A]">
          <Reveal>
            <Kicker>{s.briefing.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.briefing.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">{s.briefing.sotto}</p>
          </Reveal>
          <Reveal delay={380}>
            <HeroShot src={s.briefing.hero} alt="Il briefing del mattino di ONEFLUX" wide />
          </Reveal>
        </Scene>

        {/* ===== SCENA 3 — Tu gli parli (chat, la rivelazione) ===== */}
        <Scene className="bg-[#05070A]">
          <Reveal>
            <Kicker>{s.chat.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.chat.title}</SceneTitle>
          </Reveal>
          <div className="mt-10 w-full">
            <ChatScene sequenza={s.chat.sequenza} />
          </div>
          <Reveal delay={200}>
            <p className="mx-auto mt-8 max-w-xl text-lg text-muted-foreground">{s.chat.sotto}</p>
          </Reveal>
        </Scene>

        {/* ===== SCENA 4 — La prova (automazioni) ===== */}
        <Scene>
          <Reveal>
            <Kicker>{s.prova.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.prova.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">{s.prova.sotto}</p>
          </Reveal>
          {/* rettifica: una sola immagine, l'eroe prezzi nitido (jolly mail rimosso) */}
          <Reveal delay={380}>
            <HeroShot src={s.prova.hero} alt="Avviso rincari prezzi" wide />
          </Reveal>
          <Reveal delay={520}>
            <p className="mt-10 font-display text-2xl font-bold text-primary sm:text-3xl">
              {s.prova.chiusura}
            </p>
          </Reveal>
        </Scene>

        {/* ===== SCENA 5 — Il potere ===== */}
        <Scene>
          <BlurBg src={s.potere.bg} />
          <Reveal>
            <Kicker>{s.potere.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.potere.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <p className="mt-6 max-w-xl text-lg text-muted-foreground">{s.potere.sotto}</p>
          </Reveal>
        </Scene>

        {/* ===== SCENA 6 — Invito + rivelazione ===== */}
        <Scene className="bg-[#05070A]">
          <Reveal>
            <Kicker>{s.invito.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.invito.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <p className="mt-6 text-lg text-muted-foreground">{s.invito.sotto}</p>
          </Reveal>
          <Reveal delay={380}>
            <HeroShot src={s.invito.hero} alt="I conti del locale: tutto verde, MOL positivo" wide />
          </Reveal>
          <Reveal delay={520}>
            <CtaButton className="mt-10" />
          </Reveal>
          <Reveal delay={640}>
            <p className="mt-8 font-display text-base text-muted-foreground">{s.invito.firma}</p>
          </Reveal>
        </Scene>

        {/* ===== SCENA 7 — Piani ===== */}
        <section className="border-t border-border/60 px-5 py-24">
          <div className="mx-auto max-w-5xl">
            <Reveal>
              <h2 className="text-center font-display text-3xl font-bold tracking-tight sm:text-4xl">
                {LANDING.piani.title}
              </h2>
            </Reveal>
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {LANDING.piani.lista.map((p, i) => (
                <Reveal key={p.nome} delay={i * 100}>
                  <div
                    className={cn(
                      "relative flex h-full flex-col items-center rounded-2xl border bg-card/60 p-7 text-center",
                      p.evidenza
                        ? "border-primary ring-2 ring-primary/40"
                        : "border-border ring-1 ring-foreground/5",
                    )}
                  >
                    <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      {p.nome}
                    </p>
                    <p className="mt-3 font-display text-5xl font-bold">{p.prezzo}</p>
                    <p className="text-sm text-muted-foreground">/mese</p>
                    <div className="mt-6 space-y-2 text-sm">
                      <p className="flex items-center justify-center gap-2">
                        <Check className="size-4 text-primary" />
                        {p.fatture}
                      </p>
                      <p className="flex items-center justify-center gap-2">
                        <Check className="size-4 text-primary" />
                        {p.ai}
                      </p>
                    </div>
                    <a
                      href={waLink(`Ciao! Vorrei provare ONEFLUX, piano ${p.nome}.`)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={cn(
                        "mt-7 inline-flex w-full items-center justify-center rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors",
                        p.evidenza
                          ? "bg-primary text-primary-foreground hover:bg-primary/90"
                          : "border border-border hover:bg-muted",
                      )}
                    >
                      Inizia
                    </a>
                  </div>
                </Reveal>
              ))}
            </div>
            <p className="mt-6 text-center text-xs text-muted-foreground">{LANDING.piani.iva}</p>
            <p className="mt-4 text-center text-sm text-muted-foreground">{LANDING.piani.catena}</p>
            <div className="mt-12">
              <CtaButton />
            </div>
          </div>
        </section>

        {/* ===== Footer ===== */}
        <footer className="border-t border-border/60 px-5 py-10">
          <div className="mx-auto flex max-w-5xl flex-col items-center gap-5 sm:flex-row sm:justify-between">
            <div className="flex flex-col items-center gap-2 sm:items-start">
              <Logo size={24} />
              <p className="text-sm text-muted-foreground">{LANDING.footer.tagline}</p>
            </div>
            <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
              <a href={`mailto:${LANDING.footer.email}`} className="transition-colors hover:text-foreground">
                {LANDING.footer.email}
              </a>
              <Link href={LANDING.footer.privacyHref} className="transition-colors hover:text-foreground">
                Privacy
              </Link>
              <Link href={LANDING.footer.terminiHref} className="transition-colors hover:text-foreground">
                Termini
              </Link>
            </nav>
          </div>
          <p className="mt-8 text-center text-xs text-muted-foreground">© {new Date().getFullYear()} ONEFLUX</p>
        </footer>
      </main>
    </div>
  );
}

// Screenshot nitido protagonista (eroe), in cornice scura con bordo glow.
function HeroShot({
  src,
  alt,
  wide = false,
  className,
}: {
  src: string;
  alt: string;
  wide?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto mt-10 overflow-hidden rounded-2xl border border-primary/20 bg-card shadow-2xl shadow-primary/10 ring-1 ring-foreground/10",
        wide ? "max-w-4xl" : "max-w-2xl",
        className,
      )}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} className="w-full" loading="lazy" />
    </div>
  );
}
