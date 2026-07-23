// ═══════════════════════════════════════════════════════════════════════════════
// Unit test: estrazione dell'oggetto Event dal body grezzo del webhook
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test event_unwrap_test.ts
//
// Copre il bug del 22/7/2026: il webhook nativo arrivava (POST 200, HMAC valido)
// ma resource_id/endpoint/event/id risultavano SEMPRE null dopo il parse diretto.
// Causa: il fix del 21/7 assumeva l'oggetto Event al ROOT del body. Il body live
// reale può invece arrivare come ARRAY di eventi o annidato in un wrapper.
// extractEventObject deve "scavare" fino all'Event reale in tutte queste forme,
// così normalizeWebhookEvent legge i campi giusti e il flusso di recupero parte.
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const { extractEventObject } = await import('./index.ts')

// L'oggetto Event canonico come da doc Invoicetronic (campi al root).
const canonical = {
  id: 12345,
  user_id: 60,
  company_id: 1756,
  resource_id: 87454,
  endpoint: 'receive',
  method: 'GET',
  status_code: 200,
  success: true,
  date_time: '2026-07-22T05:55:00Z',
  api_version: 1,
}

// ─── Forma 1: oggetto Event piatto al root (test/replay + doc ufficiale) ──────

Deno.test('piatto: oggetto Event al root → estratto invariato, extraCount 0', () => {
  const { ev, extraCount } = extractEventObject(canonical)
  assertEquals(ev.resource_id, 87454)
  assertEquals(ev.endpoint, 'receive')
  assertEquals(ev.id, 12345)
  assertEquals(extraCount, 0)
})

// ─── Forma 2: ARRAY di eventi (ipotesi primaria del bug 22/7) ─────────────────

Deno.test('array: [Event] con un solo elemento → estrae il primo, extraCount 0', () => {
  const { ev, extraCount } = extractEventObject([canonical])
  assertEquals(ev.resource_id, 87454)
  assertEquals(ev.endpoint, 'receive')
  assertEquals(extraCount, 0)
})

Deno.test('array: [Event, Event] con più eventi → primo estratto, extraCount conta gli altri', () => {
  const second = { ...canonical, id: 12346, resource_id: 87455 }
  const { ev, extraCount } = extractEventObject([canonical, second])
  assertEquals(ev.resource_id, 87454)
  assertEquals(extraCount, 1)
})

// ─── Forma 3: wrapper annidato ────────────────────────────────────────────────

Deno.test('wrapper: { data: Event } → scava e estrae', () => {
  const { ev, extraCount } = extractEventObject({ data: canonical })
  assertEquals(ev.resource_id, 87454)
  assertEquals(ev.endpoint, 'receive')
  assertEquals(extraCount, 0)
})

Deno.test('wrapper: { event: Event } → scava e estrae', () => {
  const { ev } = extractEventObject({ event: canonical })
  assertEquals(ev.resource_id, 87454)
})

Deno.test('wrapper: { payload: Event } → scava e estrae', () => {
  const { ev } = extractEventObject({ payload: canonical })
  assertEquals(ev.resource_id, 87454)
})

Deno.test('wrapper: { events: [Event] } → array dentro wrapper, estrae il primo', () => {
  const { ev, extraCount } = extractEventObject({ events: [canonical] })
  assertEquals(ev.resource_id, 87454)
  assertEquals(extraCount, 0)
})

Deno.test('wrapper: { items: [Event, Event] } → estrae primo, conta extra', () => {
  const second = { ...canonical, resource_id: 87455 }
  const { ev, extraCount } = extractEventObject({ items: [canonical, second] })
  assertEquals(ev.resource_id, 87454)
  assertEquals(extraCount, 1)
})

Deno.test('wrapper annidato doppio: { result: { data: Event } } → scava in profondità', () => {
  const { ev } = extractEventObject({ result: { data: canonical } })
  assertEquals(ev.resource_id, 87454)
})

// ─── Non regressione: un Event che ha PER CASO una chiave "data" NON va scavato ─

Deno.test('non-regressione: Event con campo extra "data" resta l\'Event (ha campi noti)', () => {
  // Se l'oggetto ha già i campi noti dell'Event (id/resource_id/endpoint), è LUI
  // l'evento: non lo scaviamo dentro un eventuale campo "data" secondario.
  const withData = { ...canonical, data: { foo: 'bar' } }
  const { ev } = extractEventObject(withData)
  assertEquals(ev.resource_id, 87454)
  assertEquals(ev.endpoint, 'receive')
})

// ─── Casi degeneri: body vuoto/inatteso → oggetto vuoto, mai crash ────────────

Deno.test('degenere: null → oggetto vuoto (nessun campo), mai eccezione', () => {
  const { ev } = extractEventObject(null)
  assertEquals(ev.resource_id, undefined)
  assertEquals(ev.id, undefined)
})

Deno.test('degenere: array vuoto → oggetto vuoto', () => {
  const { ev } = extractEventObject([])
  assertEquals(ev.resource_id, undefined)
})

Deno.test('degenere: wrapper vuoto sconosciuto → oggetto vuoto (no chiavi note, no wrapper note)', () => {
  const { ev } = extractEventObject({ qualcosa: 'x' })
  assertEquals(ev.resource_id, undefined)
})

Deno.test('degenere: stringa/numero → oggetto vuoto', () => {
  assertEquals(extractEventObject('ciao').ev.resource_id, undefined)
  assertEquals(extractEventObject(42).ev.resource_id, undefined)
})

// ─── Alias camelCase: resourceId invece di resource_id ────────────────────────

Deno.test('alias: array con resourceId camelCase → estratto (normalize gestisce l\'alias)', () => {
  const camel = { id: 1, resourceId: 87454, endpoint: 'receive', success: true }
  const { ev } = extractEventObject([camel])
  assert(ev.resourceId === 87454 || ev.resource_id === undefined)
  assertEquals(ev.resourceId, 87454)
})
