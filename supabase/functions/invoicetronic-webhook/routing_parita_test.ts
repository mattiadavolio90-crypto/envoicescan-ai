// ═══════════════════════════════════════════════════════════════════════════════
// Parità fra il routing del webhook e il suo gemello Python (passo 0-bis, 25/9/2026)
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test --allow-env --allow-net routing_parita_test.ts
//
// Il worker decide il cliente delle fatture che il webhook non ha potuto leggere
// (services/routing_coda.py) e deve decidere ESATTAMENTE come il webhook.
// routing_parita.json contiene input e risultati: questo test lo ancora al
// TypeScript, tests/test_routing_coda.py al Python. Se uno dei due cambia,
// uno dei due test diventa rosso.
// ═══════════════════════════════════════════════════════════════════════════════

import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import parita from './routing_parita.json' with { type: 'json' }

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const w = await import('./index.ts')

Deno.test('parità: normalizePivaForMatch', () => {
  for (const c of parita.normalizza_piva) assertEquals(w.normalizePivaForMatch(c.input), c.atteso, c.input)
})

Deno.test('parità: extractPivaDestinatario', () => {
  for (const c of parita.piva_destinatario) assertEquals(w.extractPivaDestinatario(c.xml), c.atteso, c.nome)
})

Deno.test('parità: extractIndirizzoDestinatario', () => {
  for (const c of parita.indirizzo_destinatario) assertEquals(w.extractIndirizzoDestinatario(c.xml), c.atteso, c.nome)
})

Deno.test('parità: extractIndirizzoCandidati', () => {
  for (const c of parita.indirizzo_candidati) assertEquals(w.extractIndirizzoCandidati(c.xml), c.atteso, c.nome)
})

Deno.test('parità: normalizeIndirizzo', () => {
  for (const c of parita.normalizza_indirizzo) assertEquals(w.normalizeIndirizzo(c.input), c.atteso, c.input)
})

Deno.test('parità: indirizzoSimilarity', () => {
  for (const c of parita.similarita) assertEquals(w.indirizzoSimilarity(c.a, c.b), c.atteso, `${c.a} | ${c.b}`)
})

Deno.test('parità: extractDocMeta (come finisce nel JSON)', () => {
  for (const c of parita.meta_documento) {
    assertEquals(JSON.parse(JSON.stringify(w.extractDocMeta(c.xml))), c.atteso, c.nome)
  }
})
