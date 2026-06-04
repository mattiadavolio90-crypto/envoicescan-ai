# LOGO & WORDMARK ONEFLUX

Documento di riferimento per modificare il **logo-icona** e il **wordmark "ONEFLUX"**.
Se in una sessione futura vuoi rigiocare con la composizione della scritta, **parti da qui**.

> Per Claude: quando l'utente dice *"guarda LOGO.md / voglio rigiocare col tool del logo"*,
> apri l'editor (`wordmark_editor.html`), fagli regolare la composizione, poi reincolla
> l'SVG generato dentro `Wordmark` in `apps/web/src/components/brand/logo.tsx`
> (sostituendo `'Quicksand'` con `var(--font-wordmark)`).

---

## Concetto di design

Il logo è l'unione di una **"O"** (doppio anello concentrico) e di una **"X"** (due tratti
curvi "a flusso"). L'idea del wordmark è che la parola **ONEFLUX** *ricomponga il logo*:

```
[ O = doppio anello ]  NEFLU (font)  [ X = flusso ]
```

- La **O** NON contiene la X (sono due lettere separate, non il logo intero).
- La **O** e la **X** sono i path **letterali** del logo-icona, solo scalati/posizionati →
  forma identica al logo, garantita (non ridisegnata a mano).
- **NEFLU** sono testo vero nel font **Quicksand 700**.

---

## File coinvolti

| File | Ruolo |
|---|---|
| `apps/web/src/components/brand/logo.tsx` | `LogoMark` (icona), `Wordmark` (scritta SVG), `Logo` (composito). **Qui si modifica.** |
| `apps/web/src/app/layout.tsx` | Carica il font **Quicksand 700** via `next/font/google`, esposto come `--font-wordmark`. |
| `wordmark_editor.html` (root progetto) | **Editor interattivo** per comporre il wordmark. Aprire nel browser. |

Il `Wordmark` è usato in: login, forgot/reset-password, sidebar (`app-sidebar.tsx`),
header app (`(app)/layout.tsx`), pagine legali (`(legal)/layout.tsx`). **Una modifica si
propaga ovunque.**

---

## Geometria attuale (sistema coordinate `viewBox 0 0 398 100`)

Cap-height lettere = 70 (da y=15 a y=85), mezzeria ottica a y≈50.

**O — doppio anello** (path identici al logo, scala 0.87):
```
transform="translate(8 7) scale(0.87)"
circle cx=50 cy=50 r=42 stroke-width=6
circle cx=50 cy=50 r=31 stroke-width=2.5
```

**NEFLU — testo**:
```
x=100 y=74  font=Quicksand 700  font-size=68  letter-spacing=3.5
```

**X — flusso** (path identici al logo, scala 1.95):
```
transform="translate(265.19 -48.5) scale(1.95)"
path "M36 36 C48 44 48 56 64 64"  stroke-width=3.59   ← 3.59 × 1.95 ≈ 7 visivi (come logo)
path "M64 36 C52 44 52 56 36 64"  stroke-width=3.59
```

L'intero SVG ha `height: 1em` → scala col `font-size` del contenitore. `currentColor`
eredita da `text-primary`. `glow` aggiunge `drop-shadow(0 0 2px currentColor)`.

---

## Come rigiocare con l'editor (per modifiche future)

1. Apri **`wordmark_editor.html`** nel browser (doppio click o `start wordmark_editor.html`).
   Parte già dalla configurazione attuale (Quicksand 700, O e X identiche al logo).
2. Regola con gli slider:
   - **Font / peso / dimensione / tracking / offset** delle lettere NEFLU
   - **Scala / Y / spazio** della O
   - **Scala / Y / spazio** della X
   - La linea cyan è la **mezzeria ottica** per verificare la centratura.
   - La X si riposiziona automaticamente in base alla larghezza reale del testo.
3. Premi **📋 Copia SVG finale**.
4. Incolla l'SVG in chat. Claude lo inserisce dentro `Wordmark` in `logo.tsx`,
   sostituendo `font-family="'Quicksand',sans-serif"` → `var(--font-wordmark), 'Quicksand', sans-serif`.

### Se cambi FONT delle lettere
L'editor ha altri font (Sora, Space Grotesk, Outfit, Montserrat, Poppins, Orbitron, Lexend).
Se scegli un font diverso da Quicksand, va caricato anche in `layout.tsx`:
```ts
import { Inter, Quicksand } from "next/font/google";
const quicksand = Quicksand({ subsets: ["latin"], weight: ["700"], variable: "--font-wordmark" });
// ...e nel className dell'<html>: quicksand.variable
```
Sostituisci `Quicksand` con il nuovo font e aggiorna `--font-wordmark`.

### Se cambi la forma del LOGO-ICONA
Il logo vive in `LogoMark` (stessi path: cerchi r42/r31, X `M36 36 C48 44...`). Se modifichi
quelli, aggiorna **anche** O e X del `Wordmark` per mantenerle identiche (sono gli stessi path).

---

## Storia decisionale (perché è fatto così)

- Tentativi falliti: SVG inline mischiati al testo (collage disallineato), path lettere
  disegnati a mano (grezzi), generazione coordinate "alla cieca" (regressioni di allineamento).
- Soluzione vincente: **editor interattivo nel browser** dove l'allineamento ottico lo decide
  l'occhio umano, non una formula. O e X riusano i **path letterali del logo** così la forma è
  identica per costruzione.
