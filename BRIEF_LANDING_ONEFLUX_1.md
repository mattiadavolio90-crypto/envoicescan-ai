# OneFlux — Landing Page · Brief di sviluppo per Claude Code

> Documento di passaggio. Copy **validato e definitivo**. Stile e logica di scorrimento
> **già approvati** su prototipo. Qui dentro: cosa costruire, con quale copy, con quali
> immagini (percorsi e nomi reali), e con che trattamento visivo.

---

## 1. Obiettivo

Rifare la landing pubblica su **oneflux.it** (l'app sta su `app.oneflux.it`). La
precedente non andava: troppo carica, layout rotto sotto l'hero, diceva troppo.
La nuova è **scrollytelling**: scene a tutto schermo, una alla volta, reveal-on-scroll.
Tono **misterioso ma sicuro**. Ogni scena fa UNA promessa, non spiega una funzione.

## 2. Principi non negoziabili

1. **Mai vendere la tecnologia, sempre mostrare cosa permette di fare.** La parola "AI"
   quasi zero. La *sensazione* di AI ovunque. Niente buzzword (intelligenza artificiale,
   machine learning, potenza del cloud): suonano vecchie.
2. **"C'è anche altro" senza dirlo.** Le parole nominano 4-5 funzioni. Gli sfondi
   sfocati mostrano pagine DIVERSE da quella di cui parla il testo. L'occhio coglie un
   mondo che il testo non spiega. Quel disallineamento crea il "cavolo, c'è tanto altro".
3. **Essenziale.** Una frase per scena. Niente paragrafi, niente bullet.
4. **Quality floor:** responsive fino a mobile, focus tastiera visibile,
   `prefers-reduced-motion` rispettato.

## 3. Identità visiva (già definita)

- Sfondo nero profondo (~`#05070A`), pannelli (~`#0A0E14`).
- Blu OneFlux elettrico: `#29B6F6` / `#4FC3F7` (preso dall'app reale).
- Verde solo per numeri positivi/MOL negli screenshot reali.
- Font display deciso e geometrico (nel prototipo: **Sora** — confermare o proporre).
- Logo: cerchio con la **X** stilizzata, glow blu.
- Immagini: **sfocate/atmosferiche** all'inizio → **nitide** sugli eroi → **una nitida**
  alla rivelazione finale.

## 4. Target e posizionamento

- **A chi parla:** testa imprenditoriale — titolare, responsabile F&B, consulente, chi
  gestisce i numeri. Locale singolo strutturato O multi-locale. NON la piccola trattoria.
- **Posizionamento:** *OneFlux è il braccio destro che tiene il tuo locale sotto
  controllo — e te lo dice prima che tu lo chieda.* Controllo senza sforzo.
- **Doppio cuore:** **lui ti parla** (briefing) + **tu gli parli** (chat). Le automazioni
  (fatture in automatico + categorizzazione + alert prezzi) sono la *prova*, non l'eroe.

---

## 5. COPY DEFINITIVO (scena per scena)

### SCENA 0 — Aggancio (mistero)
- Logo X che pulsa, buio. Sfondo: `bg-marginalita.png` (sfocato).
- **Titolo:** Tutto sotto controllo. Senza fare niente.
- **Firma piccola:** Il cervello operativo della tua gestione.
- Hint "scorri" in basso.
- *(Alt titolo se "senza fare niente" suona troppo "per pigri": "Tutto sotto controllo.*
  *Mentre pensi ad altro." — default = "Senza fare niente".)*

### SCENA 1 — Lo specchio (riconoscimento)
- Sfondo: `bg-personale.png` (sfocato — fa intravedere che gestisce anche personale/turni).
- **Kicker:** Tu
- **Titolo:** Il tuo lavoro è gestire. Non compilare.
- **Sotto:** Il tuo posto è nelle decisioni. Non dentro un foglio Excel a notte fonda.

### SCENA 2 — Lui ti parla (briefing · PRIMO CUORE)
- **Immagine NITIDA:** `hero-briefing.png` (su nero pulito, niente sfondo sotto).
- **Kicker:** Ogni mattina
- **Titolo:** Ti dice com'è andata. Prima che tu lo chieda.
- **Sotto:** Ogni giorno: quanto è entrato, com'è lo scontrino medio, cosa controllare.
  Confrontato con la tua media, così sai subito se è un buon segno.
- *(Il briefing reale interpreta i numeri — "scontrino +16% sopra la media", "843 coperti,*
  *+40%" — NON li riporta soltanto. È questo che lo rende un assistente, non un report.)*

### SCENA 3 — Tu gli parli (chat · SECONDO CUORE · la rivelazione)
- **Immagine NITIDA:** `hero-chat.png` (su nero pulito) + animazione typing.
- **Kicker:** Quando vuoi
- **Titolo:** Glielo chiedi. E lo sai.
- **Sequenza chat reale (da rispettare):**
  - OneFlux: *Il salmone è costato € 7,29/kg, comprato il 27/05 da ADC.*
  - Utente: *Pensi che vada bene come prezzo di acquisto?*
  - OneFlux: *Posso confrontarlo con i prezzi degli ultimi 6 mesi dai fornitori.
    Vuoi che faccia il confronto?*
- **Sotto:** Gli scrivi come a una persona. Risponde come il tuo miglior collaboratore.
- ⚠️ **TIMING — CRITICO:** i messaggi NON appaiono tutti insieme. Compaiono uno alla
  volta, con un ritardo tra l'uno e l'altro (effetto "sta scrivendo"). Il wow è nel
  ritmo della conversazione, non nella grafica. Se appaiono tutti insieme, la magia si
  perde. Prevedere indicatore "typing" tra un messaggio e l'altro.
- *(Il vero wow: l'assistente PROPONE un'analisi e prende iniziativa — "vuoi che faccia*
  *il confronto?" — invece di limitarsi a rispondere. Mostra che ragiona.)*

### SCENA 4 — La prova (automazioni: dati che entrano + alert prezzi)
- **Immagine NITIDA:** `hero-prezzi.png` (l'alert rincari, si legge).
- **Immagine SEMI-NITIDA accanto:** `feature-mail-fornitore.png` (l'app scrive già la
  mail di rinegoziazione al fornitore — deve intravedersi che è una mail pronta).
- **Kicker:** Nel frattempo
- **Titolo:** I dati entrano da soli.
- **Sotto:** Le fatture dei fornitori arrivano in automatico. L'assistente le legge, le
  categorizza, e ti segnala se un prezzo cambia.
- **Chiusura staccata (riga a sé, più forte):** Tu non tocchi niente.
- *(Su "in automatico": evitare "via SDI/Invoicetronic". Se serve spiegare, "direttamente*
  *dall'Agenzia delle Entrate" — è vero, SDI = Sistema di Interscambio AdE. Validare.)*
- *(`feature-mail-fornitore.png` è il jolly "c'è anche questo": non solo ti avvisa del*
  *rincaro, ti scrive già la mail per rinegoziare. Mostrarla quanto basta a capirlo.)*

### SCENA 5 — Il potere (LA frase che deve restare)
- Sfondo: `bg-coperti.png` (sfocato). Alternativa di scorta: `bg-efficienza.png`.
  Scegliere in montaggio quale rende meglio; l'altro resta inutilizzato.
- **Kicker:** Ovunque
- **Titolo:** Anche dal telefono. Anche dal tavolo 6.
- **Sotto:** Il tuo locale ti risponde dove sei tu. In sala, dal fornitore, sul divano.

### SCENA 6 — L'invito + rivelazione
- **Immagine NITIDA (rivelazione):** `hero-conti.png` (salute 100% verde, MOL positivo,
  food cost sotto soglia). È il finale che vende: dati pieni, tutto verde.
- **Kicker:** Provalo
- **Titolo:** E questo è solo l'inizio.
- **Sotto:** Sul tuo locale. Da stasera.
- **Bottone:** Inizia ora — 7 giorni gratis
- **Note piccola:** Senza carta. Senza impegno.
- **Firma di chiusura:** La tecnologia che la tua gestione aspettava.

### SCENA 7 — Piani (fondo pagina, minimal)
- Titolo breve (es.: Un prezzo. Zero lavoro in cambio.)
- **Tre piani: Base / Plus / Pro** — senza etichette descrittive.
  - Cifra grande + **2 numeri chiave**: fatture/mese + domande AI/giorno.
  - **Base 39€/mese** · **Plus 59€/mese** · **Pro 79€/mese** (IVA escl.)
  - Domande AI/giorno (reali da prodotto): Base **10** · Plus **20** · Pro **30**.
  - Fatture/mese: ⚠️ usare gli scaglioni reali del listino (CONFERMARE i numeri).
- **Riga catena sotto la griglia:** Più locali? C'è la modalità catena, su ogni piano.
  *(Modello: un abbonamento per locale; il piano si sceglie sul volume di fatture +
  interazioni AI, i costi variabili maggiori. NON spiegare la meccanica in pagina.)*
- CTA prova ripetuta sotto i piani.

---

## 6. IMMAGINI — percorso, scena, trattamento

**Cartella sorgente (Windows):** `C:\Users\matti\Desktop\ONEFLUX\foto-landing-page\`
→ copiare in `apps/web/public/landing/` (servite come `/landing/...`).
I file sono già stati rinominati con i nomi sotto.

### Eroi — NITIDI (protagonisti, si leggono)
| File | Scena | Trattamento |
|------|-------|-------------|
| `hero-briefing.png` | 2 | nitido, su nero pulito |
| `hero-chat.png` | 3 | nitido, su nero pulito + animazione typing |
| `hero-prezzi.png` | 4 | nitido |
| `hero-conti.png` | 6 | nitido (rivelazione finale) |

### Semi-nitida (jolly "c'è anche questo")
| File | Scena | Trattamento |
|------|-------|-------------|
| `feature-mail-fornitore.png` | 4 | semi-nitido, accanto a hero-prezzi |

### Sfondi atmosferici — SFOCATI (texture, NON si leggono)
| File | Scena | Trattamento |
|------|-------|-------------|
| `bg-marginalita.png` | 0 | blur forte |
| `bg-personale.png` | 1 | blur forte |
| `bg-coperti.png` | 5 | blur forte |
| `bg-efficienza.png` | 5 (alt) | blur forte — di scorta |

**Regola sfondi:** lo sfondo di una scena mostra una pagina che il testo di QUELLA
scena NON menziona (così l'occhio scopre funzioni non nominate). Le scene con eroe
nitido (2, 3, 6) NON hanno sfondo sotto: nero pulito, fa risaltare la card.

---

## 7. Cosa fa Claude Code

1. Costruire la landing in **Next.js** (la landing pubblica può vivere su `oneflux.it`,
   separata dall'app su `app.oneflux.it`).
2. Copiare le immagini da `C:\Users\matti\Desktop\ONEFLUX\foto-landing-page\` in
   `apps/web/public/landing/` e assegnarle alle scene come da §6.
3. Reveal-on-scroll, glow blu, font display, responsive + a11y (§2.4).
4. **Scena 3: animazione chat con ritardi tra i messaggi + indicatore typing** (§5, ⚠️).
5. Numeri reali piani (scaglioni fatture/mese) dal listino vero.
6. Confermare dicitura "direttamente dall'Agenzia delle Entrate" (scena 4).

## 8. Cose da NON fare

- Niente testo lungo o bullet nelle scene. Una frase per scena.
- Non nominare SDI/Invoicetronic/GPT/OpenAI in pagina.
- Scena 3: NON far apparire i messaggi chat tutti insieme (perde il wow).
- Non promettere i ricavi-da-cassa come funzione centrale (dipende dal sistema cassa).
- Non spiegare la meccanica di prezzo.
- Non usare screenshot con stati "rosso/dati incompleti" come eroi.

---

*Copy validato con Mattia · giugno 2026. Stile e scroll già approvati su prototipo.*
