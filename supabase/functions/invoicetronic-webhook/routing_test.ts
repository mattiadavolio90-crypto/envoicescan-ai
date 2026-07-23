// ═══════════════════════════════════════════════════════════════════════════════
// Unit test: routing multi-sede (estrazione indirizzo + similarità)
// ═══════════════════════════════════════════════════════════════════════════════
// Logica pura, nessun server/DB richiesto:
//   deno test routing_test.ts
//
// Copre le funzioni che decidono a quale sede (ristorante) assegnare una fattura
// quando più ristoranti condividono la stessa P.IVA.
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'

// Impedisce a index.ts di avviare Deno.serve quando lo importiamo per testare le
// funzioni pure (deve precedere l'import statico → usiamo un import dinamico sotto).
Deno.env.set('WEBHOOK_TEST_MODE', '1')

const {
  extractIndirizzoDestinatario,
  extractIndirizzoCandidati,
  normalizeIndirizzo,
  indirizzoSimilarity,
} = await import('./index.ts')

// ─── normalizeIndirizzo: deve restare allineata alla SQL normalizza_indirizzo_match ─

Deno.test('normalizeIndirizzo: lowercase + solo alfanumerici + spazi singoli', () => {
  assertEquals(normalizeIndirizzo('Via Roma 1'), 'via roma 1')
  assertEquals(normalizeIndirizzo('VIA ROMA 1/A'), 'via roma 1 a')
  assertEquals(normalizeIndirizzo('Corso Italia 22,  20100   Milano'),
    'corso italia 22 20100 milano')
})

Deno.test('normalizeIndirizzo: espande abbreviazioni toponomastiche', () => {
  assertEquals(normalizeIndirizzo('V.le Roma 1'), 'viale roma 1')
  assertEquals(normalizeIndirizzo('C.so Buenos Aires 5'), 'corso buenos aires 5')
  assertEquals(normalizeIndirizzo('P.zza Duomo'), 'piazza duomo')
  assertEquals(normalizeIndirizzo('V. Verdi 3'), 'via verdi 3')
})

// ─── indirizzoSimilarity: punteggio fra indirizzi normalizzati ────────────────

Deno.test('indirizzoSimilarity: identici → 1', () => {
  assertEquals(indirizzoSimilarity('via roma 1 20100 milano', 'via roma 1 20100 milano'), 1)
})

Deno.test('indirizzoSimilarity: varianti della stessa via → alto', () => {
  // "Via Roma 1" vs "V.le Roma, 1" — stesso posto, scritture diverse
  const a = normalizeIndirizzo('Via Roma 1 20100 Milano')
  const b = normalizeIndirizzo('V.le Roma, 1 - 20100 Milano')
  assert(indirizzoSimilarity(a, b) >= 0.6,
    `atteso >=0.6, ottenuto ${indirizzoSimilarity(a, b)}`)
})

Deno.test('indirizzoSimilarity: sedi completamente diverse → basso', () => {
  const sedeA = normalizeIndirizzo('Via Garibaldi 10 20100 Milano')
  const sedeB = normalizeIndirizzo('Corso Francia 250 10100 Torino')
  assert(indirizzoSimilarity(sedeA, sedeB) < 0.2,
    `atteso <0.2, ottenuto ${indirizzoSimilarity(sedeA, sedeB)}`)
})

Deno.test('indirizzoSimilarity: stringa vuota → 0 (no falsi match)', () => {
  assertEquals(indirizzoSimilarity('', 'via roma 1'), 0)
  assertEquals(indirizzoSimilarity('via roma 1', ''), 0)
})

// ─── Scenario realistico: fattura per OFFSIDE sede A vs sede B ─────────────────
// Verifica che, con due sedi distinte, l'indirizzo in fattura distacchi nettamente
// la sede giusta (gap ben sopra la soglia MIN_GAP=0.20 usata nel webhook).

Deno.test('scenario multi-sede: distacco netto verso la sede corretta', () => {
  const sedeCentro  = normalizeIndirizzo('Via Garibaldi 10 20100 Milano')
  const sedeNavigli = normalizeIndirizzo('Via Vigevano 33 20144 Milano')

  // Fattura indirizzata alla sede Centro (con piccole differenze ortografiche)
  const fattura = normalizeIndirizzo('VIA GARIBALDI, 10 - 20100 MILANO (MI)')

  const scoreCentro  = indirizzoSimilarity(fattura, sedeCentro)
  const scoreNavigli = indirizzoSimilarity(fattura, sedeNavigli)

  assert(scoreCentro > scoreNavigli, 'la sede Centro deve vincere')
  assert(scoreCentro - scoreNavigli >= 0.20,
    `gap atteso >=0.20, ottenuto ${(scoreCentro - scoreNavigli).toFixed(2)}`)
})

// ─── extractIndirizzoDestinatario: parsing XML FatturaPA ──────────────────────

const XML_SAMPLE = `<?xml version="1.0"?>
<p:FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <Sede>
        <Indirizzo>Via del Fornitore</Indirizzo>
        <NumeroCivico>99</NumeroCivico>
        <CAP>00100</CAP>
        <Comune>Roma</Comune>
      </Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>07863990961</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Via Garibaldi</Indirizzo>
        <NumeroCivico>10</NumeroCivico>
        <CAP>20100</CAP>
        <Comune>Milano</Comune>
        <Provincia>MI</Provincia>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
</p:FatturaElettronica>`

Deno.test('extractIndirizzoDestinatario: prende la Sede del CessionarioCommittente, non del Cedente', () => {
  const ind = extractIndirizzoDestinatario(XML_SAMPLE)
  assert(ind !== null)
  // Deve contenere l'indirizzo del DESTINATARIO (Garibaldi/Milano),
  // mai quello del FORNITORE (del Fornitore/Roma).
  assert(ind!.includes('Garibaldi'), `atteso Garibaldi, ottenuto: ${ind}`)
  assert(ind!.includes('Milano'))
  assert(!ind!.includes('Fornitore'), 'NON deve pescare l\'indirizzo del cedente')
  assert(!ind!.includes('Roma'))
})

Deno.test('extractIndirizzoDestinatario: XML senza CessionarioCommittente → null', () => {
  assertEquals(extractIndirizzoDestinatario('<x>niente</x>'), null)
})

// ─── extractIndirizzoCandidati: fallback P2 (indirizzo fuori da <Sede>) ────────
// Caso OFFSIDE reale: la <Sede> del CessionarioCommittente riporta la sede LEGALE
// generica (uguale per tutte le sedi), mentre il locale reale sta in
// AltriDatiGestionali/RiferimentoTesto, in Causale, o dentro le Descrizioni riga.

const XML_SEDE_LEGALE_GENERICA = `<?xml version="1.0"?>
<p:FatturaElettronica>
  <FatturaElettronicaHeader>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>07863990961</IdCodice></IdFiscaleIVA>
      </DatiAnagrafici>
      <Sede>
        <Indirizzo>Viale Fulvio Testi</Indirizzo>
        <NumeroCivico>68</NumeroCivico>
        <CAP>20092</CAP>
        <Comune>Cinisello Balsamo</Comune>
      </Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <Causale>Consegna presso Via Settembrini 15 Milano</Causale>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <Descrizione>Materie prime per punto vendita Losanna</Descrizione>
        <AltriDatiGestionali>
          <TipoDato>CONSEGNA</TipoDato>
          <RiferimentoTesto>Via Losanna 8 20144 Milano</RiferimentoTesto>
        </AltriDatiGestionali>
      </DettaglioLinee>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>`

Deno.test('extractIndirizzoCandidati: la <Sede> è sempre il primo candidato', () => {
  const cands = extractIndirizzoCandidati(XML_SEDE_LEGALE_GENERICA)
  assert(cands.length > 0)
  assert(cands[0].includes('Fulvio Testi'),
    `il primo candidato deve essere la Sede, ottenuto: ${cands[0]}`)
})

Deno.test('extractIndirizzoCandidati: raccoglie RiferimentoTesto, Causale e Descrizione', () => {
  const cands = extractIndirizzoCandidati(XML_SEDE_LEGALE_GENERICA)
  const joined = cands.join(' | ')
  assert(joined.includes('Via Losanna 8 20144 Milano'), `manca RiferimentoTesto: ${joined}`)
  assert(joined.includes('Via Settembrini 15 Milano'), `manca Causale: ${joined}`)
  assert(joined.includes('Losanna'), `manca Descrizione: ${joined}`)
})

Deno.test('extractIndirizzoCandidati: nessun duplicato, scarta frammenti corti', () => {
  const xml = `<CessionarioCommittente><Sede><Indirizzo>Via A</Indirizzo><Comune>X</Comune></Sede></CessionarioCommittente>
    <FatturaElettronicaBody><Causale>ok</Causale><Descrizione>Via A X</Descrizione></FatturaElettronicaBody>`
  const cands = extractIndirizzoCandidati(xml)
  // "ok" (3 char) scartato; "Via A X" compare una sola volta anche se == Sede.
  assert(!cands.includes('ok'), 'frammento troppo corto non deve entrare')
  assertEquals(new Set(cands).size, cands.length, 'nessun duplicato')
})

// Scenario end-to-end del fallback: la <Sede> generica NON distingue le due sedi
// note (score ~ uguale, gap sotto soglia), ma il RiferimentoTesto "Via Losanna"
// distacca nettamente la sede Losanna. Simuliamo lo scoring che fa il routing.
Deno.test('scenario fallback: <Sede> generica indistinta, RiferimentoTesto risolve', () => {
  const sedeLosanna     = normalizeIndirizzo('Via Losanna 8 20144 Milano')
  const sedeSettembrini = normalizeIndirizzo('Via Settembrini 15 20124 Milano')
  const MIN_SCORE = 0.40, MIN_GAP = 0.20

  const cands = extractIndirizzoCandidati(XML_SEDE_LEGALE_GENERICA)

  const decide = (cand: string) => {
    const t = normalizeIndirizzo(cand)
    const s = [
      indirizzoSimilarity(t, sedeLosanna),
      indirizzoSimilarity(t, sedeSettembrini),
    ].sort((a, b) => b - a)
    return { best: s[0], gap: s[0] - s[1] }
  }

  // La Sede (Fulvio Testi) non somiglia a nessuna delle due → non passa le soglie.
  const sede = decide(cands[0])
  assert(!(sede.best >= MIN_SCORE && sede.gap >= MIN_GAP),
    'la sede legale generica non deve risolvere da sola')

  // Fra i candidati fallback c'è quello che risolve Losanna sopra le soglie.
  const risolutore = cands.slice(1).map(decide).find(d => d.best >= MIN_SCORE && d.gap >= MIN_GAP)
  assert(risolutore, 'un candidato fallback deve superare le soglie e risolvere')
})
