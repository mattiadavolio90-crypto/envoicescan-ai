# Loghi ONEFLUX

Varianti del marchio. Il segno: **cerchio = la "O" di One**, **X interna = la "X" di fluX** (monogramma OX). La X è vicina al cerchio senza toccarlo; bordo del cerchio più sottile della X (gerarchia), terminali della X netti (tech).

> ⚠️ Questi SVG sono ricostruiti dal bozzetto, fedeli al concetto e alle proporzioni ma **non derivati dal file vettoriale originale**. Quando disponibile il file sorgente del designer, sostituire.

## Quale variante usare

| File | Uso |
|---|---|
| `oneflux-icon-cyan.svg` | Icona, sfondo **scuro** (app, social, favicon dark) |
| `oneflux-icon-dark.svg` | Icona, sfondo **chiaro** (ciano scuro `#0891B2`) |
| `oneflux-icon-black.svg` | Icona, **stampa / B&N**, massima leggibilità |
| `oneflux-horizontal-cyan.svg` | Logo + scritta, sfondo **scuro** |
| `oneflux-horizontal-dark.svg` | Logo + scritta, sfondo **chiaro** (documenti, PDF, email) |
| `oneflux-horizontal-black.svg` | Logo + scritta, **stampa / contratti** |

## Regole

- **Glow neon**: solo sull'icona su sfondo scuro (hero, spinner). Mai sul testo.
- **Colore su chiaro**: il ciano puro `#00FFFF` è illeggibile su bianco → usare le varianti `dark` (`#0891B2`) o `black`.
- **Spazio di rispetto**: lasciare attorno al logo un margine pari ad almeno metà altezza del box.
- **Non**: deformare, ruotare (tranne l'animazione spinner ufficiale), cambiare i colori fuori palette, riempire la X.

## Palette

- Ciano neon (dark): `#22D3EE`
- Ciano scuro (chiaro): `#0891B2`
- Primary app (sky-500): `#0EA5E9`
- Nero: `#0A0A0A` · Testo chiaro: `#F1F5F9`

## In-app

Nell'app Next.js il logo è un componente vivo, non questi file statici:
- `apps/web/src/components/brand/logo.tsx` — `<Logo variant="full|icon|mono" />`
- `apps/web/src/components/brand/logo-spinner.tsx` — `<LogoSpinner />` (caricamenti, login, AI)
