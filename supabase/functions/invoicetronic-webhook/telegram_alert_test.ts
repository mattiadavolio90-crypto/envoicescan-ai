// ═══════════════════════════════════════════════════════════════════════════════
// Unit test: alert Telegram su evento webhook non riconosciuto (Voce 7, Strato 1)
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test telegram_alert_test.ts
//
// Verifica notifyTelegramUnrecognizedEvent: no-op senza secrets configurati,
// chiamata corretta all'API Telegram quando presenti, e mai un'eccezione
// propagata (deve restare fire-and-forget anche se fetch fallisce) — l'alert
// non deve MAI poter far fallire la risposta al webhook.
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const { notifyTelegramUnrecognizedEvent, normalizeWebhookEvent } = await import('./index.ts')

function baseEvent() {
  return normalizeWebhookEvent({
    id: 1, resource_id: 84532, endpoint: 'strano/xyz', event: undefined, success: true,
  })
}

Deno.test('telegram alert: no-op se TELEGRAM_BOT_TOKEN assente', async () => {
  Deno.env.delete('TELEGRAM_BOT_TOKEN')
  Deno.env.delete('TELEGRAM_CHAT_ID')
  const originalFetch = globalThis.fetch
  let called = false
  globalThis.fetch = (() => { called = true; return Promise.reject(new Error('non doveva chiamare fetch')) }) as typeof fetch
  try {
    await notifyTelegramUnrecognizedEvent('endpoint/event non riconosciuto come receive', baseEvent())
    assertEquals(called, false)
  } finally {
    globalThis.fetch = originalFetch
  }
})

Deno.test('telegram alert: no-op se solo TELEGRAM_CHAT_ID presente (manca token)', async () => {
  Deno.env.delete('TELEGRAM_BOT_TOKEN')
  Deno.env.set('TELEGRAM_CHAT_ID', '12345')
  const originalFetch = globalThis.fetch
  let called = false
  globalThis.fetch = (() => { called = true; return Promise.reject(new Error('non doveva chiamare fetch')) }) as typeof fetch
  try {
    await notifyTelegramUnrecognizedEvent('endpoint/event non riconosciuto come receive', baseEvent())
    assertEquals(called, false)
  } finally {
    globalThis.fetch = originalFetch
    Deno.env.delete('TELEGRAM_CHAT_ID')
  }
})

Deno.test('telegram alert: chiama sendMessage con token/chat_id/testo corretti', async () => {
  Deno.env.set('TELEGRAM_BOT_TOKEN', 'test-token-abc')
  Deno.env.set('TELEGRAM_CHAT_ID', '999888')
  const originalFetch = globalThis.fetch
  let capturedUrl = ''
  let capturedBody: Record<string, unknown> = {}
  globalThis.fetch = ((url: string, init: RequestInit) => {
    capturedUrl = url
    capturedBody = JSON.parse(init.body as string)
    return Promise.resolve(new Response('{"ok":true}', { status: 200 }))
  }) as typeof fetch
  try {
    await notifyTelegramUnrecognizedEvent('endpoint/event non riconosciuto come receive', baseEvent())
    assertStringIncludes(capturedUrl, 'https://api.telegram.org/bottest-token-abc/sendMessage')
    assertEquals(capturedBody.chat_id, '999888')
    assertStringIncludes(capturedBody.text as string, 'evento non riconosciuto')
    assertStringIncludes(capturedBody.text as string, 'endpoint/event non riconosciuto come receive')
    assertStringIncludes(capturedBody.text as string, 'resource_id=84532')
  } finally {
    globalThis.fetch = originalFetch
    Deno.env.delete('TELEGRAM_BOT_TOKEN')
    Deno.env.delete('TELEGRAM_CHAT_ID')
  }
})

Deno.test('telegram alert: non propaga eccezione se fetch fallisce (fire-and-forget)', async () => {
  Deno.env.set('TELEGRAM_BOT_TOKEN', 'test-token-abc')
  Deno.env.set('TELEGRAM_CHAT_ID', '999888')
  const originalFetch = globalThis.fetch
  globalThis.fetch = (() => Promise.reject(new Error('rete giù'))) as typeof fetch
  try {
    let threw = false
    try {
      await notifyTelegramUnrecognizedEvent('event_id o resource_id mancante', baseEvent())
    } catch {
      threw = true
    }
    assert(!threw, 'notifyTelegramUnrecognizedEvent non deve mai lanciare')
  } finally {
    globalThis.fetch = originalFetch
    Deno.env.delete('TELEGRAM_BOT_TOKEN')
    Deno.env.delete('TELEGRAM_CHAT_ID')
  }
})
