// ═══════════════════════════════════════════════════════════════════════════════
// Unit test: autenticazione webhook (HMAC-SHA256 + anti-replay)
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test --allow-env hmac_test.ts
//
// È l'auth REALE del webhook (verify_jwt=false lato Supabase → tutta la sicurezza
// passa da qui). Schema firma Invoicetronic-Signature:
//   header = "t=<unix_ts>,v1=<hmac_hex>"
//   hmac   = HMAC-SHA256("{ts}.{rawBody}", secret)
//   anti-replay = |now - ts| <= 300s
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const { verifyHmac } = await import('./index.ts')

const SECRET = 'test-webhook-secret-123'

/** Costruisce un header di firma valido per (body, ts) con il secret dato. */
async function signature(body: string, ts: number, secret = SECRET): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  )
  const buf = await crypto.subtle.sign('HMAC', key, enc.encode(`${ts}.${body}`))
  const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
  return `t=${ts},v1=${hex}`
}

const nowSec = () => Math.floor(Date.now() / 1000)

Deno.test('verifyHmac: firma valida e fresca → true', async () => {
  const body = '{"event":"receive.add","id":42}'
  const header = await signature(body, nowSec())
  assertEquals(await verifyHmac(body, header, SECRET), true)
})

Deno.test('verifyHmac: header mancante → false', async () => {
  assertEquals(await verifyHmac('{}', null, SECRET), false)
})

Deno.test('verifyHmac: firma con secret SBAGLIATO → false', async () => {
  const body = '{"id":1}'
  const header = await signature(body, nowSec(), 'secret-diverso')
  assertEquals(await verifyHmac(body, header, SECRET), false)
})

Deno.test('verifyHmac: body manomesso dopo la firma → false', async () => {
  const header = await signature('{"importo":10}', nowSec())
  // L'attaccante cambia il body mantenendo la stessa firma
  assertEquals(await verifyHmac('{"importo":99999}', header, SECRET), false)
})

Deno.test('verifyHmac: anti-replay — timestamp troppo vecchio (>300s) → false', async () => {
  const body = '{"id":7}'
  const oldTs = nowSec() - 301
  const header = await signature(body, oldTs)
  assertEquals(await verifyHmac(body, header, SECRET), false)
})

Deno.test('verifyHmac: anti-replay — timestamp nel futuro (>300s) → false', async () => {
  const body = '{"id":8}'
  const futureTs = nowSec() + 301
  const header = await signature(body, futureTs)
  assertEquals(await verifyHmac(body, header, SECRET), false)
})

Deno.test('verifyHmac: timestamp dentro la finestra (299s) → true', async () => {
  const body = '{"id":9}'
  const header = await signature(body, nowSec() - 299)
  assertEquals(await verifyHmac(body, header, SECRET), true)
})

Deno.test('verifyHmac: header malformato (manca v1) → false', async () => {
  assertEquals(await verifyHmac('{}', `t=${nowSec()}`, SECRET), false)
})

Deno.test('verifyHmac: timestamp non numerico → false', async () => {
  const body = '{"id":10}'
  // firma calcolata ma ts non finito → respinto prima del confronto
  const header = `t=abc,v1=deadbeef`
  assertEquals(await verifyHmac(body, header, SECRET), false)
})
