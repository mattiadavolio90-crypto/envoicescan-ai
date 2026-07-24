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

const { isReceiveWebhook, isOtherWebhook, normalizeWebhookEvent, extractEventObject } =
  await import('./index.ts')

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

// ─── END-TO-END bug PascalCase (24/7/2026): body reale → receive riconosciuto ──
// Riproduce ESATTAMENTE la fattura persa: body catturato dal DB live (riga 656,
// resource_id 88509) con tutte le chiavi in PascalCase. Prima del fix
// normalizeWebhookEvent leggeva solo lower/camelCase → endpoint/resource_id/id/
// success tutti null → NON riconosciuto come receive → fattura dead. Questo test
// percorre l'intera catena reale extractEventObject → normalizeWebhookEvent →
// isReceiveWebhook e pretende: endpoint='receive', resourceId/eventId valorizzati,
// success=true, riconosciuto come receive. È il test che, se il parser tornasse
// a leggere case-sensitive, si romperebbe subito.
const bodyLive24_7 = {
  UserId: 60, ApiKeyId: 1, CompanyId: 1756, Method: 'POST', Endpoint: 'receive',
  ApiVersion: 1, StatusCode: 201, DateTime: '2026-07-24T03:54:26.919218Z',
  Error: null, ResourceId: 88509, UserAgent: 'RestSharp/112.1.0.0',
  Success: true, Id: 1572149, Created: '2026-07-24T03:54:27.832046Z', Version: 74358439,
}

Deno.test('e2e PascalCase: body live 24/7 → normalize legge i campi (non più null)', () => {
  const { ev: raw } = extractEventObject(bodyLive24_7)
  const n = normalizeWebhookEvent(raw)
  assertEquals(n.endpoint, 'receive')
  assertEquals(n.resourceId, 88509)
  assertEquals(n.eventId, 1572149)
  assertEquals(n.companyId, 1756)
  assertEquals(n.statusCode, 201)
  assertEquals(n.success, true)
})

Deno.test('e2e PascalCase: body live 24/7 → isReceiveWebhook = true (fattura NON persa)', () => {
  const { ev: raw } = extractEventObject(bodyLive24_7)
  const n = normalizeWebhookEvent(raw)
  assert(isReceiveWebhook(n), 'il body PascalCase reale DEVE essere riconosciuto come receive')
  assertEquals(isOtherWebhook(n), false)
})

// Non-regressione: gli stessi campi in snake_case (payload di test/replay storici)
// continuano a normalizzare identici — il fix è additivo, non sostitutivo.
Deno.test('e2e snake_case: payload storico resta riconosciuto come receive', () => {
  const snake = {
    user_id: 60, company_id: 1756, method: 'POST', endpoint: 'receive',
    status_code: 201, resource_id: 88509, success: true, id: 1572149,
    date_time: '2026-07-24T03:54:26Z', api_version: 1,
  }
  const { ev: raw } = extractEventObject(snake)
  const n = normalizeWebhookEvent(raw)
  assertEquals(n.resourceId, 88509)
  assertEquals(n.eventId, 1572149)
  assert(isReceiveWebhook(n))
})
