// ═══════════════════════════════════════════════════════════════════════════════
// Unit test: riconoscimento tipo evento webhook Invoicetronic
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test event_recognition_test.ts
//
// Copre il bug del 21/7/2026: fatture reali scartate con 200 senza salvarle
// perché il match `endpoint === 'receive'` era troppo stretto rispetto al naming
// reale del payload live di Invoicetronic. Qui verifichiamo che isReceiveWebhook
// riconosca le varianti reali di endpoint e che isOtherWebhook non le confonda
// con eventi send/status.
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const { isReceiveWebhook, isOtherWebhook } = await import('./index.ts')

// Helper: costruisce un NormalizedWebhookEvent minimale con override.
type Ev = Parameters<typeof isReceiveWebhook>[0]
function ev(overrides: Partial<Ev>): Ev {
  return {
    eventId: 1, userId: 60, companyId: 1756, resourceId: 84532,
    endpoint: null, eventName: null, method: 'POST',
    statusCode: 200, success: true, dateTime: null, apiVersion: 1,
    ...overrides,
  }
}

// ─── isReceiveWebhook: forme reali di endpoint ────────────────────────────────

Deno.test('receive: endpoint secco "receive" (forma dei test/replay)', () => {
  assert(isReceiveWebhook(ev({ endpoint: 'receive' })))
})

Deno.test('receive: endpoint con id "receive/86940" (forma live sospetta)', () => {
  assert(isReceiveWebhook(ev({ endpoint: 'receive/86940' })))
})

Deno.test('receive: endpoint con prefisso "/v1/receive"', () => {
  assert(isReceiveWebhook(ev({ endpoint: '/v1/receive' })))
})

Deno.test('receive: endpoint "api/v1/receive/84532"', () => {
  assert(isReceiveWebhook(ev({ endpoint: 'api/v1/receive/84532' })))
})

Deno.test('receive: alias storico via eventName "receive.add"', () => {
  assert(isReceiveWebhook(ev({ endpoint: null, eventName: 'receive.add' })))
})

Deno.test('receive: eventName "receive.update" (prefisso receive)', () => {
  assert(isReceiveWebhook(ev({ endpoint: null, eventName: 'receive.update' })))
})

// ─── isReceiveWebhook: NON deve matchare parole che contengono "receive" ──────

Deno.test('receive: NON matcha "received_notification" (receive come sottostringa)', () => {
  assertEquals(isReceiveWebhook(ev({ endpoint: 'received_notification' })), false)
})

Deno.test('receive: NON matcha "send" / "status"', () => {
  assertEquals(isReceiveWebhook(ev({ endpoint: 'send' })), false)
  assertEquals(isReceiveWebhook(ev({ endpoint: 'status' })), false)
})

// ─── isOtherWebhook: eventi legittimi non-ricezione ───────────────────────────

Deno.test('other: "send" con endpoint valorizzato e nessun eventName receive', () => {
  assert(isOtherWebhook(ev({ endpoint: 'send', eventName: 'send.add' })))
})

Deno.test('other: NON considera "other" un vero receive', () => {
  assertEquals(isOtherWebhook(ev({ endpoint: 'receive/86940' })), false)
})

Deno.test('other: endpoint null NON è classificabile come "altro" (va alla rete di sicurezza)', () => {
  // endpoint assente → non sappiamo cos'è → NON lo trattiamo come "altro"
  // ignorabile, deve finire nella rete di sicurezza (registrato, mai perso).
  assertEquals(isOtherWebhook(ev({ endpoint: null, eventName: null })), false)
})

// ─── Coerenza: un evento non può essere insieme receive e other ───────────────

Deno.test('coerenza: receive e other sono mutuamente esclusivi sulle forme note', () => {
  const forms = ['receive', 'receive/86940', '/v1/receive', 'send', 'status', 'received_x']
  for (const endpoint of forms) {
    const e = ev({ endpoint })
    assert(
      !(isReceiveWebhook(e) && isOtherWebhook(e)),
      `endpoint="${endpoint}" classificato come receive E other insieme`,
    )
  }
})
