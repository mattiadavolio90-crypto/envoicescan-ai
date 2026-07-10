import Link from "next/link";
import { ChevronDown, ArrowRight, Check, MessageCircle, Mail } from "lucide-react";

import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";
import { WHATSAPP_NUMERO } from "@/lib/assistenza";
import { LANDING, WHATSAPP_LANDING_MSG } from "@/lib/landing-content";
import { Scene, Reveal, BlurBg, Kicker } from "@/components/landing/scene-kit";
import { ChatScene } from "@/components/landing/chat-scene";
import { StructuredData } from "@/components/landing/structured-data";
import { ServiziModal } from "@/components/landing/servizi-modal";

function waLink(msg: string = WHATSAPP_LANDING_MSG): string {
  return `https://wa.me/${WHATSAPP_NUMERO}?text=${encodeURIComponent(msg)}`;
}

const CTA = LANDING.cta;

// "Recoma System" cliccabile verso il sito Recoma. Usato sia in cima alla
// scena 0 sia nel footer: un solo punto di verita' per colore e link.
// Colore smorzato (non più rosso brand Recoma): il rosso era il primo elemento
// cromaticamente dominante della pagina e portava FUORI dal sito prima ancora
// dell'h1. L'avallo resta, il richiamo visivo no.
function RecomaLink({ className }: { className?: string }) {
  return (
    <a
      href={LANDING.footer.recomaHref}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "font-semibold text-foreground/80 underline-offset-2 transition-colors hover:text-foreground hover:underline",
        className,
      )}
    >
      {LANDING.footer.recomaNome}
    </a>
  );
}

// Hint "scorri" con freccetta, in basso alla scena. Presente su tutte le scene
// tranne l'ultima (l'invito) — invita a proseguire lo scrollytelling.
function ScrollHint({ label = "scorri" }: { label?: string }) {
  return (
    <div className="absolute bottom-28 flex flex-col items-center gap-1 text-muted-foreground sm:bottom-10">
      <span className="text-xs uppercase tracking-[0.2em]">{label}</span>
      <ChevronDown className="size-5 animate-bounce" />
    </div>
  );
}

function CtaButton({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-col items-center gap-2.5", className)}>
      <a
        href={waLink()}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-7 py-3.5 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/30 transition-all hover:bg-primary/90 hover:shadow-primary/50"
      >
        {CTA.label}
        <ArrowRight className="size-5" />
      </a>
      <span className="text-center text-sm text-muted-foreground">{CTA.nota}</span>
      <span className="-mt-1 text-center text-sm text-muted-foreground/80">{CTA.nota2}</span>
    </div>
  );
}

// Titolo di scena con font display (Sora). Supporta "\n" come a-capo forzato.
// `as`: la scena 0 (apertura) usa <h1> — è il titolo principale della pagina e
// SEO vuole un solo h1; tutte le altre scene restano <h2>. Stile identico in
// entrambi i casi: nessun cambiamento visivo.
function SceneTitle({
  children,
  className,
  as: Tag = "h2",
}: {
  children: string;
  className?: string;
  as?: "h1" | "h2";
}) {
  return (
    <Tag
      className={cn(
        "mx-auto max-w-3xl whitespace-pre-line font-display text-3xl font-bold leading-[1.12] tracking-tight sm:text-5xl",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

// Sottotitolo di scena UNIFORME: bianco attenuato (~72%, non grigio spento), misura
// e spaziatura identiche tra tutte le scene. `parolaChiave` (opzionale) viene resa
// in azzurro OneFlux per dare ritmo (una keyword per slide). Match case-insensitive
// sulla prima occorrenza; se assente, testo invariato.
function SceneSub({
  children,
  parolaChiave,
  className,
}: {
  children: string;
  parolaChiave?: string;
  className?: string;
}) {
  let content: React.ReactNode = children;
  if (parolaChiave) {
    const i = children.toLowerCase().indexOf(parolaChiave.toLowerCase());
    if (i >= 0) {
      content = (
        <>
          {children.slice(0, i)}
          <span className="font-medium text-primary">
            {children.slice(i, i + parolaChiave.length)}
          </span>
          {children.slice(i + parolaChiave.length)}
        </>
      );
    }
  }
  return (
    <p className={cn("mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-white/[0.72]", className)}>
      {content}
    </p>
  );
}

export function LandingPage() {
  const s = LANDING.scene;

  return (
    // Contenitore di scroll a tutta altezza. data-scroll-root: lo usa Reveal come
    // root dell'IntersectionObserver (le animazioni vivono dentro QUESTO div, non
    // nel viewport). Snap: PROXIMITY su mobile (lo scorrimento col dito resta
    // fluido e non viene "strappato" al ricentraggio di mandatory) e MANDATORY da
    // sm in su (desktop, dove l'aggancio preciso funziona bene). overscroll-contain
    // evita il rimbalzo della pagina sotto. reduced-motion disattiva snap/smooth.
    <div
      data-scroll-root
      className="h-dvh snap-y snap-proximity overflow-y-scroll overscroll-y-contain scroll-smooth bg-background text-foreground sm:snap-mandatory motion-reduce:snap-none motion-reduce:scroll-auto"
    >
      {/* JSON-LD per i motori (invisibile): Organization + SoftwareApplication + FAQ */}
      <StructuredData />
      <main>
        {/* ===== SCENA 0 — Aggancio + Specchio (FUSE, niente kicker) ===== */}
        <Scene className="bg-[#05070A]">
          <BlurBg src={s.aggancio.bg} />
          {/* Co-branding in alto: l'avallo Recoma da' autorevolezza subito, prima
              dello scroll. Minuscolo, spaziatura ridotta; "Recoma System" rosso e
              cliccabile. z-10 sopra il BlurBg; top-8/10 non finisce sotto la barra. */}
          <div className="absolute inset-x-0 top-8 z-10 flex justify-center px-4 sm:top-10">
            <span className="text-xs tracking-tight text-foreground/70 sm:text-sm">
              {LANDING.footer.recomaPrefisso} <RecomaLink />
            </span>
          </div>
          <Reveal>
            <Logo size={84} glow />
          </Reveal>
          <Reveal delay={150}>
            <SceneTitle as="h1" className="mt-9">
              {s.aggancio.title}
            </SceneTitle>
          </Reveal>
          {/* sotto: stile sottotitolo standard (bianco attenuato, come le altre
              scene), su due righe. sotto2: azzurro OneFlux, su due righe. */}
          <Reveal delay={300}>
            <SceneSub className="max-w-xl whitespace-pre-line leading-snug">
              {s.aggancio.sotto}
            </SceneSub>
          </Reveal>
          <Reveal delay={400}>
            <p className="mx-auto mt-4 max-w-xl whitespace-pre-line text-lg font-medium leading-snug text-primary">
              {s.aggancio.sotto2}
            </p>
          </Reveal>
          {/* CTA primaria dell'hero = la DEMO (frizione minima, fa il selling
              lei). WhatsApp resta come via secondaria testuale: chi vuole il
              contatto diretto lo trova, chi esita ha il gradino da 1 minuto.
              Il vecchio pill nell'angolo era facile da mancare su desktop. */}
          <Reveal delay={520}>
            <div className="mt-9 flex flex-col items-center gap-2.5">
              <a
                href={LANDING.nav.demoHref}
                className="group relative inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-7 py-3.5 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/30 transition-all hover:bg-primary/90 hover:shadow-primary/50"
              >
                <span
                  aria-hidden
                  className="pointer-events-none absolute -inset-1.5 -z-10 rounded-2xl bg-primary/25 blur-xl transition-opacity group-hover:bg-primary/40"
                />
                {LANDING.nav.demoLabel}
                <ArrowRight className="size-5" />
              </a>
              <a
                href={waLink()}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-muted-foreground transition-colors hover:text-primary"
              >
                {LANDING.nav.demoAltWhatsapp}
              </a>
            </div>
          </Reveal>
          <ScrollHint label={s.aggancio.scrollHint} />
        </Scene>

        {/* ===== SCENA 1 — Chat (tu gli parli, la rivelazione): subito dopo l'hero,
             così il differenziatore AI colpisce per primo ===== */}
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
            <SceneSub parolaChiave="assistente" className="max-w-xl">
              {s.chat.sotto}
            </SceneSub>
          </Reveal>
        </Scene>

        {/* ===== SCENA 2 — Briefing (lui ti parla) ===== */}
        <Scene className="bg-[#05070A]">
          <Reveal>
            <Kicker>{s.briefing.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.briefing.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <SceneSub parolaChiave="andamento">{s.briefing.sotto}</SceneSub>
          </Reveal>
          <Reveal delay={420} variant="zoom">
            <HeroShot src={s.briefing.hero} alt="Il briefing del mattino di ONEFLUX" wide />
          </Reveal>
        </Scene>

        {/* ===== SCENA 3 — Categorizzazione ===== */}
        <Scene>
          <Reveal>
            <Kicker>{s.categorie.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.categorie.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <SceneSub parolaChiave="assistente">{s.categorie.sotto}</SceneSub>
          </Reveal>
          <Reveal delay={420} variant="zoom">
            <HeroShot src={s.categorie.hero} alt="Migliaia di prodotti categorizzati in automatico" wide />
          </Reveal>
          {/* chiusura sotto l'immagine: il ribaltamento "niente data entry" */}
          <Reveal delay={560}>
            <SceneSub parolaChiave="automatizzato" className="mt-7 text-base">
              {s.categorie.chiusura}
            </SceneSub>
          </Reveal>
        </Scene>

        {/* ===== SCENA 4 — Alert prezzi ===== */}
        <Scene>
          <Reveal>
            <Kicker>{s.prezzi.kicker}</Kicker>
          </Reveal>
          <Reveal delay={120}>
            <SceneTitle>{s.prezzi.title}</SceneTitle>
          </Reveal>
          <Reveal delay={260}>
            <SceneSub parolaChiave="ti avvisa">{s.prezzi.sotto}</SceneSub>
          </Reveal>
          <Reveal delay={420} variant="zoom">
            <HeroShot src={s.prezzi.hero} alt="Avviso rincari prezzi" wide />
          </Reveal>
        </Scene>

        {/* ===== SCENA 5 — Il potere (mobile, 2 colonne) ===== */}
        <Scene>
          <BlurBg src={s.invito.hero} />
          <div className="mx-auto grid w-full max-w-5xl items-center gap-10 md:grid-cols-2 md:text-left">
            <div className="md:pr-6">
              <Reveal>
                <Kicker>{s.potere.kicker}</Kicker>
              </Reveal>
              <Reveal delay={120}>
                <h2 className="font-display text-3xl font-bold leading-[1.12] tracking-tight sm:text-5xl">
                  {s.potere.title}
                </h2>
              </Reveal>
              <Reveal delay={260}>
                <SceneSub parolaChiave="consulente" className="mx-0 mt-6 max-w-none">
                  {s.potere.sotto}
                </SceneSub>
              </Reveal>
            </div>
            <Reveal delay={420} variant="zoom" className="flex justify-center md:justify-end">
              <PhoneShot src={s.potere.heroMobile} alt="L'assistente ONEFLUX sul telefono" />
            </Reveal>
          </div>
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
            <SceneSub>{s.invito.sotto}</SceneSub>
          </Reveal>
          <Reveal delay={420} variant="zoom">
            <HeroShot src={s.invito.hero} alt="I conti del locale: tutto verde, MOL positivo" wide />
          </Reveal>
          {/* CTA al picco emotivo (audit CRO 10/07): "Provalo, adesso" + conti
              tutto verde senza bottone era una perdita secca — chi si convinceva
              qui doveva attraversare i PREZZI prima di trovare l'azione. Il
              secondo "Inizia ora" resta sotto i piani, a più di una viewport
              di distanza: non competono. */}
          <Reveal delay={520}>
            <CtaButton className="mt-10" />
          </Reveal>
          {/* La firma chiude la scena: momento emotivo del finale, con respiro
              e presenza (grande, alone azzurro dietro), non una riga sussurrata. */}
          <Reveal delay={640}>
            <p className="relative mx-auto mt-10 max-w-2xl font-display text-2xl font-semibold leading-snug tracking-tight text-primary sm:text-3xl">
              <span
                aria-hidden
                className="pointer-events-none absolute -inset-x-8 -inset-y-6 -z-10 rounded-full bg-primary/15 blur-3xl"
              />
              {s.invito.firma}
            </p>
          </Reveal>
        </Scene>

        {/* Coda finale (piani + footer): un unico blocco snap-start. Mandatory ci
            aggancia (cosi' lo raggiungi dall'ultima scena), ed essendo piu' alto
            del viewport si scorre dentro fino al footer. scroll-snap-stop normal
            non blocca il proseguimento. */}
        <div className="snap-start">
        {/* ===== SCENA 7 — Piani ===== */}
        {/* id="piani": ancora raggiunta dal link "Guarda i piani" in chiusura
            della demo (/#piani). */}
        <section id="piani" className="border-t border-border/60 px-5 py-24">
          <div className="mx-auto max-w-5xl">
            <Reveal>
              <h2 className="text-center font-display text-3xl font-bold tracking-tight sm:text-4xl">
                {LANDING.piani.title}
              </h2>
            </Reveal>
            <Reveal delay={120}>
              <p className="mx-auto mt-4 max-w-2xl text-center text-base text-muted-foreground">
                {LANDING.piani.sottotitolo}
              </p>
            </Reveal>
            {/* Secondo ingresso alla demo, prima delle card: intercetta chi è
                interessato ma esita sul prezzo. Gradino a bassa frizione ("guarda
                prima di scegliere"), non un bottone che compete con "Inizia ora"
                (quello resta unico, sotto i piani). L'unico altro link demo è
                nell'hero (scena 0), che qui è ormai fuori scroll. */}
            <Reveal delay={200}>
              <div className="mt-6 flex justify-center">
                <Link
                  href={LANDING.nav.demoHref}
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary transition-colors hover:text-primary/80"
                >
                  {LANDING.piani.demoNota}
                  <ArrowRight className="size-4" />
                </Link>
              </div>
            </Reveal>
            {/* Card tutte uguali: nessun piano in risalto (cambia solo il volume).
                variant zoom: entrano con la stessa dissolvenza percepibile delle
                immagini (richiesto: animazione anche sui blocchi prezzi). */}
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {LANDING.piani.lista.map((p, i) => (
                <Reveal key={p.nome} delay={i * 120} variant="zoom">
                  <div className="relative flex h-full flex-col items-center rounded-2xl border border-primary bg-card/60 p-6 text-center ring-1 ring-primary/30">
                    <p className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                      {p.nome}
                    </p>
                    <p className="mt-2 font-display text-4xl font-bold">
                      {p.prezzo}
                      <span className="ml-1 align-top text-sm font-medium text-muted-foreground">
                        {LANDING.piani.iva}
                      </span>
                      <span className="text-base font-medium text-muted-foreground"> /mese</span>
                    </p>
                    {/* voci con spunta blu (uguali per tutti): fatture, crediti,
                        SDI, check-up. La richieste/giorno NON è una spunta: è la
                        spiegazione dei crediti, piccola e rientrata sotto la riga. */}
                    <div className="mt-5 w-full space-y-2.5 text-left text-sm">
                      <p className="flex items-center gap-2">
                        <Check className="size-4 shrink-0 text-primary" />
                        {p.fatture}
                      </p>
                      <div>
                        <p className="flex items-center gap-2">
                          <Check className="size-4 shrink-0 text-primary" />
                          {p.crediti}
                        </p>
                        <p className="ml-6 text-xs text-white/55">{p.creditiNota}</p>
                      </div>
                      <p className="flex items-center gap-2">
                        <Check className="size-4 shrink-0 text-primary" />
                        {LANDING.piani.sdi}
                      </p>
                      <div>
                        <p className="flex items-center gap-2">
                          <Check className="size-4 shrink-0 text-primary" />
                          {LANDING.piani.checkup}
                        </p>
                        <p className="ml-6 text-xs">
                          <ServiziModal
                            triggerLabel={LANDING.piani.checkupDettaglio}
                            triggerClassName="text-xs font-medium"
                          />
                        </p>
                      </div>
                    </div>
                    <a
                      href={waLink(`Ciao! Vorrei provare ONEFLUX, piano ${p.nome}.`)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-6 inline-flex w-full items-center justify-center rounded-xl border border-border px-5 py-2.5 text-sm font-semibold transition-colors hover:bg-muted"
                    >
                      Inizia
                    </a>
                  </div>
                </Reveal>
              ))}
            </div>
            <p className="mt-8 text-center text-sm text-muted-foreground">{LANDING.piani.catena}</p>
            <p className="mt-1.5 text-center text-xs text-muted-foreground/70">
              {LANDING.piani.perPuntoVendita}
            </p>
            {/* Attivazione in 3 passi sopra la CTA finale: l'obiezione "sarà
                complicato" riaffiora esattamente qui, davanti al bottone. */}
            {/* Su mobile lista in colonna allineata a sinistra (col testo su due
                righe il numerino centrato restava disancorato); da sm in su riga
                unica centrata. */}
            <div className="mx-auto mt-12 flex w-fit flex-col gap-2.5 text-sm text-foreground/85 sm:w-auto sm:max-w-2xl sm:flex-row sm:justify-center sm:gap-6">
              {LANDING.piani.attivazione.map((passo, i) => (
                <span key={passo} className="inline-flex items-start gap-2 text-left sm:items-center">
                  <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary sm:mt-0">
                    {i + 1}
                  </span>
                  {passo}
                </span>
              ))}
            </div>
            <div className="mt-8">
              <CtaButton />
            </div>
            <p className="mt-6 text-center text-xs text-muted-foreground/70">
              {LANDING.piani.trust}
            </p>
          </div>
        </section>

        {/* I servizi NON sono elencati in pagina: si aprono in overlay cliccando
            "Guarda i nostri servizi" nel footer (ServiziModal). */}

        {/* ===== Footer completo ===== */}
        <Footer />
        </div>
      </main>
    </div>
  );
}

// Screenshot orizzontale (eroe), in cornice scura con bordo glow.
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
    <div className={cn("relative mx-auto mt-7", wide ? "max-w-3xl" : "max-w-2xl", className)}>
      {/* alone azzurro diffuso dietro l'immagine: dà profondità e accento brand */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-6 -z-10 rounded-[2rem] bg-primary/25 blur-3xl"
      />
      <div className="overflow-hidden rounded-2xl border border-primary/30 bg-card shadow-2xl shadow-primary/30 ring-1 ring-primary/20">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="w-full" loading="lazy" />
      </div>
    </div>
  );
}

// Screenshot verticale del telefono: cornice stretta, bordo glow, alone azzurro.
function PhoneShot({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="relative w-[260px] sm:w-[300px]">
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-8 -z-10 rounded-[3rem] bg-primary/30 blur-3xl"
      />
      <div className="overflow-hidden rounded-[2rem] border-4 border-card bg-card shadow-2xl shadow-primary/40 ring-1 ring-primary/30">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="w-full" loading="lazy" />
      </div>
    </div>
  );
}

// Footer: logo leggibile, contatti (WhatsApp + email), legali, Recoma + P.IVA.
function Footer() {
  const f = LANDING.footer;
  return (
    <footer className="border-t border-border/60 px-5 py-14">
      <div className="mx-auto flex max-w-5xl flex-col gap-10">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-3">
            <Logo size={36} />
            <p className="max-w-xs text-sm text-muted-foreground">{f.tagline}</p>
            <p className="max-w-sm text-sm text-foreground/80">
              {f.umanoPre}
              <ServiziModal triggerLabel={f.umanoServizi} />
            </p>
          </div>

          {/* contatti: entrambi i canali */}
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Contatti
            </p>
            <a
              href={waLink()}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm font-medium transition-colors hover:text-primary"
            >
              <MessageCircle className="size-4 text-primary" />
              {f.whatsappLabel}
            </a>
            <a
              href={`mailto:${f.email}`}
              className="inline-flex items-center gap-2 text-sm transition-colors hover:text-primary"
            >
              <Mail className="size-4 text-primary" />
              {f.email}
            </a>
          </div>

          {/* legali */}
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Legale
            </p>
            <Link href={f.privacyHref} className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              Privacy
            </Link>
            <Link href={f.terminiHref} className="text-sm text-muted-foreground transition-colors hover:text-foreground">
              Termini
            </Link>
          </div>
        </div>

        <div className="flex flex-col gap-4 border-t border-border/60 pt-6 text-xs text-muted-foreground sm:flex-row sm:items-end sm:justify-between">
          {/* sinistra: collaborazione + dati legali Recoma */}
          <div className="flex flex-col gap-1">
            <span>
              {f.recomaPrefisso} <RecomaLink />
            </span>
            <span className="text-muted-foreground/80">{f.recomaRagione}</span>
            <span className="text-muted-foreground/80">{f.recomaIndirizzo}</span>
            <span className="text-muted-foreground/80">{f.recomaPiva}</span>
          </div>
          {/* destra: copyright OneFlux */}
          <span className="text-muted-foreground/80">{f.copyrightOneflux}</span>
        </div>
      </div>
    </footer>
  );
}
