# ONEFLUX — Piano Web Marketing & Visibilità Online

> **Documento vivo.** Fotografa cosa è stato fatto, cosa resta da fare e come questa
> parte del progetto si evolve nel tempo. Si aggiorna a ogni avanzamento (vedi
> **Changelog** in fondo). Non è un brief one-shot: è la mappa di un lavoro continuo.
>
> **Owner:** Mattia D'Avolio · **Avvio:** 29/06/2026 · **Ultimo aggiornamento:** 29/06/2026

---

## 0. In una riga

La landing `oneflux.it` **converte bene ma è quasi invisibile a Google**. Questo piano
costruisce la visibilità organica e a pagamento attorno a una landing che resta
emozionale, in **4 pilastri** eseguibili nel tempo. Il Pilastro 1 (fondamenta tecniche)
è **fatto e verificato**; il resto è roadmap.

---

## 1. Contesto e diagnosi di partenza

### Il prodotto e dove vive
- **Landing pubblica:** `oneflux.it` — scrollytelling a 8 scene, tono "misterioso ma
  sicuro", una promessa per scena. Codice in `apps/web/src/components/landing/`, copy
  centralizzato in `apps/web/src/lib/landing-content.ts`.
- **App:** `app.oneflux.it` (dietro login). Stesso progetto Next.js, separato per
  hostname dal proxy (`apps/web/src/proxy.ts`).
- **Brief di riferimento della landing:** `BRIEF_LANDING_ONEFLUX_1.md` (copy validato,
  stile approvato).

### Il problema strutturale
La landing fa promesse emotive ("Tutto sotto controllo. Mentre pensi ad altro") ma
**non contiene le parole che un ristoratore digita su Google** (food cost, fatture
elettroniche, controllo di gestione, marginalità). È giusto per la conversione di chi
è già arrivato — **letale per farsi trovare** da chi non ti conosce. Il brief vieta
esplicitamente i buzzword nella landing (principio §2.1): la tensione brand-vs-SEO è
reale e va gestita, non ignorata.

### Decisione architetturale di fondo (presa con Mattia, 29/06)
> **Landing intatta + hub di contenuti separato.** La landing `/` resta emozionale e
> pulita. Le parole-chiave vivono SOLO in: (a) metadata e JSON-LD invisibili
> all'utente, (b) un futuro hub `/risorse` (blog) scritto per Google. **Zero
> compromessi estetici sulla landing.**

### Panorama competitivo (Italia, rilevato 29/06)
| Concorrente | Angolo | Note SEO |
|---|---|---|
| **Qubi Software** | "50 KPI", cassetto fiscale | contenuti educativi, affermato |
| **Tomato AI** | AI + cassetto fiscale (**il nostro stesso angolo**) | **ha un blog attivo** |
| **Food Cost in Cloud** | gestionale F&B cloud | brand affermato |
| **TeamSystem (Cassa in Cloud)** | modulo magazzino+food cost | dominante, generico |
| **Bacco / Cooki / QUADRA** | gestionali/food cost | presidiano keyword generiche |

**Implicazione:** non possiamo battere frontalmente le keyword grosse subito. La nostra
arma differenziante è il **doppio cuore "lui ti parla (briefing) + tu gli parli (chat)"**
— nessun concorrente ce l'ha. Va trasformato in contenuto cercabile (Pilastro 2).

---

## 2. I 4 Pilastri (visione d'insieme)

| # | Pilastro | Cosa fa | Priorità | Costo | Orizzonte ROI |
|---|---|---|---|---|---|
| **1** | **SEO Tecnico** | la "porta" del sito: rende indicizzabile e condivisibile | 🔴 MASSIMA | basso (codice) | immediato |
| **2** | **SEO di Contenuto** | il motore di traffico organico gratuito | 🟠 ALTA | medio (scrittura) | 3-6 mesi |
| **3** | **Conversione & Trust (CRO)** | trasforma i visitatori in prove attivate | 🟡 MEDIA | basso-medio | continuo |
| **4** | **Misurazione & Acquisizione** | analytics + Search Console + Ads + LinkedIn | 🟡 MEDIA | variabile (Ads) | immediato (Ads) |

**Sequenza consigliata:** 1 → (4 base: misurazione) → 2 → 3, con 4-Ads attivabile in
parallelo quando serve traffico immediato mentre la SEO organica matura.

---

## 3. PILASTRO 1 — SEO Tecnico ✅ FATTO (verificato, non ancora deployato)

> Tutto codice, basso rischio, già implementato e verificato su server di produzione
> locale il 29/06/2026. **Manca solo il deploy.**

### 3.1 Cosa è stato fatto

| Intervento | File | Dettaglio |
|---|---|---|
| `metadataBase` + meta root | `apps/web/src/app/layout.tsx` | era placeholder "Gestione costi ristorante"; ora base URL `https://oneflux.it` + title/description/publisher reali (Recoma System) |
| Metadata landing arricchiti | `apps/web/src/app/page.tsx` | title/description/**keywords** con parole-chiave reali (invisibili all'utente), `canonical`, `openGraph`, `twitter` card |
| **OG image** dinamica 1200×630 | `apps/web/src/app/opengraph-image.tsx` | PNG generato da Next (`ImageResponse`, runtime edge); branding reale: nero `#05070A` + blu `#29B6F6`, mark doppio anello + X |
| `robots.txt` | `apps/web/src/app/robots.ts` | allow pubblico, disallow aree private, dichiara sitemap |
| `sitemap.xml` | `apps/web/src/app/sitemap.ts` | route pubbliche reali: `/`, `/privacy`, `/termini` |
| **JSON-LD** structured data | `apps/web/src/components/landing/structured-data.tsx` | `Organization` + `SoftwareApplication` (3 Offer: 39/59/79€) + `FAQPage` (5 Q&A); server-rendered, invisibile |
| Vero `<h1>` | `apps/web/src/components/landing/landing-page.tsx` | scena 0 ora `<h1>` (era solo `<h2>`); `SceneTitle` ha prop `as`; **stile invisibilmente identico** |
| **Fix proxy critico** | `apps/web/src/proxy.ts` | `/opengraph-image` veniva rediretto a `/login` (path senza estensione → intercettato dal matcher). Aggiunto `SEO_PATHS` a `isPublic`. **Senza questo fix nessun crawler social vedrebbe l'anteprima.** |

### 3.2 Verifica eseguita (server prod locale, 29/06)
- ✅ `/robots.txt` → `200`, contenuto corretto
- ✅ `/sitemap.xml` → `200`, 3 URL
- ✅ `/opengraph-image` → `200 image/png`, ~133 KB (PNG reale, non redirect)
- ✅ JSON-LD presente nell'HTML (server-rendered, ~2.8 KB)
- ✅ `<h1>` = "Un unico flusso operativo. Tutto sotto controllo"
- ✅ Auth intatta: `/dashboard` senza sessione → `307 /login` (il fix proxy ha aperto SOLO i 3 path SEO)
- ✅ `next build` pulito (151 pagine)

### 3.3 Cosa resta sul Pilastro 1
- [x] **Deploy** (commit `35f8a90` + fix www `cfaa9b9`). ✅ Live e verificato.
- [x] **Google Search Console** attiva + sitemap inviata (30/06). ✅
- [ ] **Validare l'OG image** con Facebook Sharing Debugger + LinkedIn Post
      Inspector (forzano il refresh della cache social). — utile fare ora.
- [ ] Validare il JSON-LD con il **Rich Results Test** di Google.
- [ ] (Opzionale) `favicon.ico` oltre all'`icon.svg` già presente, per browser legacy.

---

## 4. PILASTRO 2 — SEO di Contenuto ⏳ DA FARE

> Dove si vince a medio termine. La landing resta intatta; nasce l'hub `/risorse`
> (o `/blog`), indicizzabile, scritto per Google e per il ristoratore — qui SÌ si
> usano le parole vere.

### 4.1 Struttura tecnica da creare
- [ ] Route `apps/web/src/app/(public)/risorse/` (o gruppo dedicato), con layout
      proprio, indicizzabile, fuori dallo scrollytelling.
- [ ] Aggiungere gli articoli alla `sitemap.ts` man mano che escono.
- [ ] Ogni articolo: `<h1>` keyword-rich, metadata propri, OG image, JSON-LD
      `Article` + `BreadcrumbList`, CTA finale verso la prova gratuita.
- [ ] Decidere il sorgente contenuti: MDX in-repo (consigliato, zero dipendenze) vs CMS.

### 4.2 Calendario editoriale (cluster "money keyword", ordine di scrittura)
| # | Articolo | Keyword target | Porta a |
|---|---|---|---|
| 1 | Come calcolare il food cost di un ristorante (formula + esempio) | "calcolo food cost" | prova / Margini |
| 2 | Fatture elettroniche ristorante: riceverle e leggerle senza commercialista | "fatture elettroniche ristorante" | il cuore tecnico |
| 3 | I 5 numeri che ogni ristoratore dovrebbe controllare ogni mattina | "controllo di gestione ristorante" | **è il briefing, fatto contenuto** |
| 4 | Marginalità ristorante: perché il fatturato non basta | "marginalità ristorante" | Ricavi e Margini |
| 5 | Software gestione costi ristorante: come scegliere (confronto onesto) | "software food cost" | pagina comparativa vs Qubi/Tomato |

### 4.3 Stato
- Nessun articolo scritto. Hub non ancora creato. **Prossimo grande blocco dopo il go-live.**

---

## 5. PILASTRO 3 — Conversione & Trust (CRO) ⏳ DA FARE

> La landing converte sull'emozione; un imprenditore che spende 39-79€/mese vuole
> prova. Questi elementi possono vivere sulla landing senza romperne il tono, o
> sull'hub.

- [ ] **Riprova sociale:** 1-2 testimonianze clienti operativi (SUSHILAND/OFFSIDE
      quando pronti) — anche solo frase + nome locale. Oggi: zero.
- [ ] **Sezione FAQ visibile** (oltre al JSON-LD già fatto): "I miei dati sono al
      sicuro?", "Come arrivano le fatture?", "Funziona col mio gestionale di cassa?".
- [x] **Trust signal:** "I tuoi dati restano tuoi · GDPR · server in UE" — esposto
      sotto la CTA finale della landing (10/07).
- [ ] **CTA WhatsApp tracciabile** (vedi Pilastro 4): oggi i link `wa.me` non danno
      nessun segnale di conversione misurabile.

---

## 6. PILASTRO 4 — Misurazione & Acquisizione ⏳ DA FARE

> Senza misurare si naviga al buio. La parte "misurazione" va attivata **subito dopo
> il deploy** per raccogliere dati dal giorno 1.

### 6.1 Misurazione (priorità, dopo deploy)
- [ ] **Google Search Console:** registrare `oneflux.it`, verificare proprietà,
      inviare la sitemap. Gratis. Dice esattamente per cosa Google ci mostra.
- [ ] **Analytics privacy-friendly** (Plausible o GA4 con consenso — cookie banner
      già presente). Tracciare: scroll-depth scene, click CTA WhatsApp, click piani.
- [ ] **Bing Webmaster Tools** (rapido, copre Bing/Edge).

### 6.2 Acquisizione (quando serve traffico)
- [ ] **Google Ads** su keyword commerciali ("software food cost", "gestionale costi
      ristorante"): traffico immediato mentre la SEO organica matura.
- [ ] **LinkedIn organico** (Mattia founder): il target del brief — titolare, F&B
      manager, consulenti — è su LinkedIn, non su TikTok.
- [ ] (Valutare) retargeting su chi ha visitato ma non ha attivato la prova.

---

## 7. Roadmap temporale

```
ADESSO (pre go-live 1/7)   → Pilastro 1: DEPLOY (è già pronto e verificato)
Subito dopo il deploy      → Pilastro 4 (misurazione): Search Console + sitemap + analytics
Mese 1                     → Pilastro 2: creare hub /risorse + Articolo #1 (food cost)
Mese 1-3                   → Pilastro 2: Articoli #2-#5 · Pilastro 3: testimonianze + FAQ visibili + trust
Quando serve volume        → Pilastro 4 (Ads): Google Ads keyword commerciali · LinkedIn founder
Continuo                   → misurare in Search Console, raddoppiare sui contenuti che rendono
```

---

## 8. Principi guida (non negoziabili)

1. **La landing emozionale non si tocca.** Keyword e contenuto SEO vivono in
   metadata/JSON-LD invisibili e nell'hub separato. (Coerente con `BRIEF_LANDING_ONEFLUX_1.md` §2.)
2. **In pagina niente buzzword** ("AI", "machine learning", SDI/Invoicetronic, GPT).
   Negli articoli e nei metadata SÌ: lì la gente li cerca.
3. **Misurare prima di scalare.** Niente Ads serie senza analytics + Search Console attivi.
4. **Deploy solo fuori orario** (clienti in uso di giorno). Pronto e committato, poi si svuota cache se serve.
5. **Onestà nei contenuti.** Il confronto coi concorrenti (Articolo #5) è onesto: è il
   tono del prodotto. Niente claim falsi sui numeri (dipendono dai dati del cliente).

---

## 9. Riferimenti incrociati

- `BRIEF_LANDING_ONEFLUX_1.md` — brief e copy della landing (vincoli di tono/stile).
- `ONEFLUX_MASTER.md` — visione e stato della migrazione Next.js.
- `docs/COMPLIANCE_GDPR.md` — dossier privacy (da sfruttare come trust signal).
- Proxy/hostname split: `apps/web/src/proxy.ts` (commenti su landing vs app).
- Memoria di lavoro: `project_seo_landing_pilastro1` (stato sintetico cross-sessione).

---

## 10. Changelog

> Aggiungere una riga a ogni avanzamento. Questo è ciò che rende il documento "vivo".

| Data | Avanzamento |
|---|---|
| 29/06/2026 | Documento creato. **Pilastro 1 completato e verificato** in prod locale (metadataBase, OG image, sitemap/robots, JSON-LD, h1, fix proxy `/opengraph-image`). Decisione "landing intatta + hub separato" presa con Mattia. Panorama competitivo rilevato. |
| 29/06/2026 | **Pilastro 1 DEPLOYATO** (commit `35f8a90`). Verificato live: robots/sitemap/og-image `200` su produzione. Scoperto che il dominio reale è **`www.oneflux.it`** (oneflux.it → 308). **Fix www** (commit `cfaa9b9`): allineati metadataBase/sitemap/robots/JSON-LD a www. **DNS gestito su Aruba** (nameserver Aruba, sito su Vercel `76.76.21.21`) — il record TXT di verifica Search Console va su Aruba. |
| 30/06/2026 | **Google Search Console ATTIVA.** Proprietà tipo "Dominio" `oneflux.it` (copre landing + app + www) verificata via record TXT su Aruba (`google-site-verification=MK3x...`, NON rimuovere mai). **Sitemap `https://www.oneflux.it/sitemap.xml` inviata ed elaborata correttamente** (3 pagine rilevate). Pilastro 4-misurazione: primo blocco fatto. |
| 10/07/2026 | **Audit CRO landing+demo implementato** (Pilastro 3, calibrato sul target ristoratore medio/catena). Landing: h1 col beneficio ("Il tuo locale sotto controllo. Senza diventare un contabile"), **demo = CTA primaria hero** (bottone centrato, via il pill), CtaButton anche in scena 6 (picco emotivo), note CTA (disdetta con un messaggio + persona vera), attivazione in 3 passi + trust GDPR sopra la CTA finale, riga catena rinforzata, link Recoma smorzato, branzino al posto del salmone in chat scena 1. Demo: cover in voce-assistente con open loop sui soldi, step MOL in lingua da bancone ("su 100 € te ne restano 21"), chiusura col bottone-offerta ("Attiva la prova gratuita — 7 giorni"), bottino annualizzato (2.640 €/anno), frame ROI prezzo + link `/#piani`. **Fix entità legale ovunque: RECOMASYSTEM Srl · P.IVA 12993240154** (era Recoma System S.r.l. IT09599210961 su demo/legali). Restano (Pilastro 3): testimonianze (fine luglio), FAQ visibili, CTA WhatsApp tracciabile; verifica mobile demo + analytics per-step. |

---

*Documento di lavoro · ONEFLUX Web Marketing · si evolve nel tempo.*
