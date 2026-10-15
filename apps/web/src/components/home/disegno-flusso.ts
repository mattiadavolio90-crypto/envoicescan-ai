// Il disegno del flusso su un <canvas> 2D (fase L). Porta nell'app il mockup approvato da
// Mattia il 15/10/2026 (versione 9): stessa geometria, stessi colori, stessi movimenti.
// Niente React qui dentro: lo guidano AvatarFlusso (Home) e BenvenutoAssistente.
import {
  BASE_FLUSSO,
  GIRI,
  NASTRI,
  PALETTE,
  ampiezza,
  avvicina,
  centroNastro,
  conOpacita,
  generatore,
  nascitaFili,
  nodiDiTaglio,
  velocita,
  type ModoAvatar,
  type Spinta,
  type VarianteAvatar,
} from "@/lib/avatar-flusso";

export type Puntatore = { x: number; y: number; dentro: boolean };

export type Ingresso = {
  t: number;
  dt: number;
  modo: ModoAvatar;
  /** Livello della voce già smorzato, 0-1. */
  voce: number;
  /** Dove guarda: il cursore rispetto all'avatar, -1..1 sui due assi. */
  mx: number;
  my: number;
  puntatore: Puntatore | null;
  scuro: boolean;
  /** Il sistema chiede meno animazioni: tutto fermo. */
  fermo: boolean;
};

type Filo = { u: number; n: number; p: number; vita: number; h: number };
type Luce = { x: number; y: number; r: number; f: number; v: number };

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

export class DisegnoFlusso {
  /** 0 → 1 durante il benvenuto: i punti arrivano da ogni parte e formano i nastri. */
  assemble = 1;
  /** 0 → 1: i fili di luce cominciano a nascere solo quando il flusso è formato. */
  cresce = 1;
  private ctx: CanvasRenderingContext2D;
  private fili: Filo[] = [];
  private daNascere = 0;
  private luci: Luce[] = [];
  private rnd: () => number;
  private s = { l: 0, t: 0, p: 0, yaw: 0, pitch: 0.12, fase: 0, giro: 0, uc: 0.5, vicino: 0, verso: 0 };
  private readonly filiPerNastro: number;
  private readonly campioni: number;
  private partenza: Float32Array;
  private ritardo: Float32Array;
  private px: Float32Array;
  private py: Float32Array;
  private pz: Float32Array;
  private pa: Float32Array;

  constructor(
    private canvas: HTMLCanvasElement,
    private variante: VarianteAvatar,
    seme = 11,
  ) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas 2d non disponibile");
    this.ctx = ctx;
    this.rnd = generatore(seme);
    // Sul telefono la fascia è piccola: meno fili, stesso disegno.
    this.filiPerNastro = variante === "fascia" ? 20 : 30;
    this.campioni = variante === "fascia" ? 76 : 100;
    const np = NASTRI.length * this.filiPerNastro * this.campioni;
    this.partenza = new Float32Array(np * 2);
    this.ritardo = new Float32Array(np);
    for (let i = 0; i < np; i++) {
      this.partenza[i * 2] = this.rnd() * 1.6 - 0.3;
      this.partenza[i * 2 + 1] = this.rnd() * 1.6 - 0.3;
      this.ritardo[i] = this.rnd() * 0.4;
    }
    for (let i = 0; i < 14; i++) {
      this.luci.push({ x: this.rnd(), y: this.rnd(), r: 4 + this.rnd() * 13, f: this.rnd() * 6.283, v: 0.15 + this.rnd() * 0.35 });
    }
    this.px = new Float32Array(np);
    this.py = new Float32Array(np);
    this.pz = new Float32Array(np);
    this.pa = new Float32Array(np);
  }

  disegna(ing: Ingresso): void {
    const r = this.canvas.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round(r.width * dpr), h = Math.round(r.height * dpr);
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    const W = r.width, H = r.height;
    const { ctx, s, px, py, pz, pa } = this;
    const P = PALETTE[ing.scuro ? "scuro" : "chiaro"];
    const dt = ing.fermo ? 0 : ing.dt;
    const tt = ing.fermo ? 0 : ing.t;
    const vivo = ing.fermo ? 0 : 1;

    s.l = avvicina(s.l, ing.modo === "ascolta" ? 1 : 0, 4, ing.dt);
    s.t = avvicina(s.t, ing.modo === "pensa" ? 1 : 0, 3.5, ing.dt);
    s.p = avvicina(s.p, ing.modo === "parla" ? 1 : 0, 5, ing.dt);
    const pesi = { ascolta: s.l, pensa: s.t, parla: s.p };
    s.yaw = avvicina(s.yaw, ing.mx * (0.42 + 0.1 * s.l) + Math.sin(tt * 0.21) * 0.14 * vivo * (1 - s.l), 2.5, ing.dt);
    s.pitch = avvicina(s.pitch, 0.12 + ing.my * 0.16 - s.l * 0.05, 2.5, ing.dt);
    const vel = velocita(pesi);
    s.fase += dt * vel.fase;
    s.giro += dt * vel.giro;

    // Il cursore vicino al flusso lo piega verso di sé.
    const base_y = BASE_FLUSSO[this.variante];
    let vicinoTg = 0, versoTg = 0;
    const pt = ing.puntatore;
    if (pt && pt.dentro && this.variante !== "palco") {
      const ux = (pt.x - r.left) / r.width, yb = r.top + r.height * base_y;
      const dy = Math.max(0, Math.abs(pt.y - yb) - r.height * 0.25);
      const dx = Math.max(0, -ux, ux - 1) * r.width;
      vicinoTg = Math.exp(-(dx + dy) / 110);
      versoTg = clamp((yb - pt.y) / (r.height * 0.25), -1, 1);
      s.uc = avvicina(s.uc, clamp(ux, 0, 1), 6, ing.dt);
    }
    s.vicino = avvicina(s.vicino, vicinoTg, 3, ing.dt);
    s.verso = avvicina(s.verso, versoTg, 3, ing.dt);

    const voce = ing.voce * s.p, A = this.assemble;
    const q: Spinta = { fase: s.fase, amp: ampiezza(pesi, tt), voce, pensa: s.t, uc: s.uc, vicino: s.vicino, verso: s.verso };
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const k = Math.min(W * 0.8, H * 1.6) * (1 + 0.05 * s.l), cx = W / 2, by = H * base_y;
    const altezzaFili = H * (this.variante === "colonna" ? 0.5 : 0.48);
    const cY = Math.cos(s.yaw), sY = Math.sin(s.yaw), cP = Math.cos(s.pitch), sP = Math.sin(s.pitch);
    const proietta = (x: number, y: number, z: number): [number, number, number] => {
      const X = x * cY + z * sY, Z1 = -x * sY + z * cY;
      const Y2 = y * cP + Z1 * sP, Z2 = -y * sP + Z1 * cP, f = 1.6 / (1.6 - Z2);
      return [cx + X * k * f, by - Y2 * k * f, Z2];
    };
    ctx.globalCompositeOperation = P.composizione;

    // Luci sfocate di fondo, molto tenui.
    for (const l of this.luci) {
      const lx = (l.x + 0.03 * Math.sin(tt * l.v + l.f)) * W;
      const ly = H * (0.1 + l.y * 0.75) + 6 * Math.sin(tt * l.v * 1.3 + l.f);
      const rl = l.r * (1 + 0.2 * s.l);
      const g = ctx.createRadialGradient(lx, ly, 0, lx, ly, rl);
      g.addColorStop(0, conOpacita(P.alone, P.forzaAlone * A * (0.5 + 0.5 * Math.sin(tt * 0.7 + l.f))));
      g.addColorStop(1, conOpacita(P.alone, 0));
      ctx.fillStyle = g;
      ctx.fillRect(lx - rl, ly - rl, rl * 2, rl * 2);
    }

    // I nastri: ogni filo corre a distanza w dall'asse, ruotato dell'angolo phi(u).
    const larghezza = 0.13 * (1 + 0.3 * s.l + 0.35 * voce * (0.6 + 0.4 * Math.sin(tt * 9)));
    const gruppi: number[][] = Array.from({ length: 12 }, () => []);
    const punti: number[][] = [[], [], []];
    let i = 0;
    for (const n of NASTRI) {
      for (let fi = 0; fi < this.filiPerNastro; fi++) {
        const w = (fi / (this.filiPerNastro - 1)) * 2 - 1;
        for (let c = 0; c < this.campioni; c++, i++) {
          const u = c / (this.campioni - 1), env = Math.pow(Math.sin(Math.PI * u), 0.5);
          const phi = u * 2 * Math.PI * GIRI + s.giro + n.fase;
          const hw = larghezza * n.larg * (0.55 + 0.45 * Math.sin(Math.PI * u));
          let [sx, sy, dz] = proietta((u - 0.5) * 1.35, centroNastro(u, tt, q, n) + w * hw * Math.cos(phi), w * hw * Math.sin(phi));
          let a = 1;
          if (A < 1) {
            const pr = clamp((A - this.ritardo[i]) / 0.6, 0, 1), e = 1 - Math.pow(1 - pr, 3);
            const x0 = this.partenza[i * 2] * W, y0 = this.partenza[i * 2 + 1] * H;
            sx = x0 + (sx - x0) * e;
            sy = y0 + (sy - y0) * e;
            a = pr;
          }
          px[i] = sx; py[i] = sy; pz[i] = dz;
          let al = a * P.alfa * clamp(0.6 + dz * 3, 0.3, 1.15) * env * (1 + 0.3 * s.l + 0.4 * voce);
          if (s.vicino > 0.01) al *= 1 + 0.5 * s.vicino * Math.exp(-((u - s.uc) ** 2) / 0.01);
          pa[i] = al;
          if (c === 0 || al < 0.03) continue;
          const piano = dz > 0.03 ? 2 : dz > -0.03 ? 1 : 0;
          gruppi[piano * 4 + Math.min(3, Math.floor(Math.min(1, al) * 4))].push(i);
          if ((c + fi * 2) % 5 === 0) punti[piano].push(i);
        }
      }
    }
    const spessore = Math.max(0.7, Math.min(W, H * 1.6) / 400);
    ctx.lineCap = "round";
    gruppi.forEach((lista, gi) => {
      if (!lista.length) return;
      const piano = Math.floor(gi / 4), liv = gi % 4;
      ctx.globalAlpha = ((liv + 0.5) / 4) * 0.5;
      ctx.strokeStyle = P.piani[piano];
      ctx.lineWidth = spessore * (0.3 + 0.12 * piano);
      ctx.beginPath();
      for (const j of lista) {
        ctx.moveTo(px[j - 1], py[j - 1]);
        ctx.lineTo(px[j], py[j]);
      }
      ctx.stroke();
    });
    punti.forEach((lista, piano) => {
      ctx.fillStyle = P.piani[piano];
      const rp = spessore * (0.6 + 0.3 * piano);
      for (const j of lista) {
        ctx.globalAlpha = Math.min(1, pa[j]) * 0.8;
        ctx.fillRect(px[j] - rp / 2, py[j] - rp / 2, rp, rp);
      }
    });

    // Nodi di luce dove un nastro si mostra di taglio.
    ctx.globalAlpha = 1;
    for (const n of NASTRI) {
      for (const u of nodiDiTaglio(s.giro, n.fase)) {
        const [nx, ny] = proietta((u - 0.5) * 1.35, centroNastro(u, tt, q, n), 0);
        const forza = A * Math.sin(Math.PI * u) * (0.7 + 0.5 * s.t + 0.4 * voce + 0.2 * s.l);
        const rn = spessore * (8 + 6 * s.t + 6 * voce);
        const g = ctx.createRadialGradient(nx, ny, 0, nx, ny, rn);
        g.addColorStop(0, conOpacita(P.nodo, P.forzaNodo * forza));
        g.addColorStop(1, conOpacita(P.nodo, 0));
        ctx.fillStyle = g;
        ctx.fillRect(nx - rn, ny - rn, rn * 2, rn * 2);
      }
    }

    // I fili di luce nascono di continuo dal flusso (più spesso quando ascolta, pensa o
    // parla, e vicino al cursore), salgono, si staccano dalla base e si dissolvono.
    const cresce = clamp(this.cresce, 0, 1) * clamp((A - 0.55) / 0.45, 0, 1);
    if (cresce > 0 && vivo) {
      this.daNascere += dt * nascitaFili(pesi, voce) * cresce;
      while (this.daNascere >= 1 && this.fili.length < 110) {
        this.daNascere -= 1;
        const vicinoCursore = s.vicino > 0.2 && this.rnd() < 0.45 * s.vicino;
        const u = clamp(vicinoCursore ? s.uc + (this.rnd() - 0.5) * 0.12 : 0.5 + (this.rnd() + this.rnd() + this.rnd() - 1.5) * 0.33, 0.04, 0.96);
        const env = Math.pow(Math.sin(Math.PI * u), 1.4);
        this.fili.push({ u, n: Math.floor(this.rnd() * NASTRI.length), p: 0, vita: 2 + this.rnd() * 1.8, h: (0.3 + 0.7 * env) * (0.45 + 0.55 * this.rnd()) });
      }
      if (this.daNascere > 1) this.daNascere = 1;
    }
    for (const fl of this.fili) fl.p += (dt / fl.vita) * (1 + 0.6 * s.t + 0.5 * voce);
    this.fili = this.fili.filter((fl) => fl.p < 1);
    for (const fl of this.fili) {
      const [fx, fy] = proietta((fl.u - 0.5) * 1.35, centroNastro(fl.u, tt, q, NASTRI[fl.n]), 0);
      const e = 1 - (1 - fl.p) ** 2, sale = e * fl.h * altezzaFili, coda = altezzaFili * 0.2 * fl.h;
      const testa = fy - sale, piede = fy - Math.max(0, sale - coda), lx = ing.mx * sale * (0.12 + 0.06 * s.l);
      const vis = Math.pow(Math.sin(Math.PI * fl.p), 0.8) * cresce;
      const g = ctx.createLinearGradient(fx, piede, fx + lx, testa);
      g.addColorStop(0, conOpacita(P.luce, 0));
      g.addColorStop(1, conOpacita(P.luce, 0.6 * vis));
      ctx.globalAlpha = 1;
      ctx.strokeStyle = g;
      ctx.lineWidth = 0.9;
      ctx.beginPath();
      ctx.moveTo(fx + (lx * (piede - fy)) / (testa - fy || 1), piede);
      ctx.lineTo(fx + lx, testa);
      ctx.stroke();
      ctx.globalAlpha = 0.9 * vis;
      ctx.fillStyle = P.punta;
      ctx.beginPath();
      ctx.arc(fx + lx, testa, spessore * (1.25 + 0.4 * s.l + 0.5 * voce), 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }
}
