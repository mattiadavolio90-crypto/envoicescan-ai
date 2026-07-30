// ═══════════════════════════════════════════════════════════════════════════════
// Unit test: ricavi-email-webhook
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test --allow-all index_test.ts
//
// Copre auth (token timing-safe), filtro allegati, path building, alert Telegram
// e — punto centrale — i due modi in cui i ricavi potevano sparire in silenzio
// prima del fix del 30/7/2026:
//   1. BREVO_API_KEY assente/ruotata → fetch 401 → null → continue muto
//   2. mittente non mappato → status 'unknown_sender', mai claimato dal worker
// Entrambi rispondevano 200 al producer senza alcun segnale.
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const {
  timingSafeEqual, isXls, buildPath, notifyTelegram, getAttachmentBytes, handler,
  hasXlsMagicBytes, readBodyCapped, BodyTooLargeError,
} = await import('./index.ts')

// ─── Auth: confronto token ────────────────────────────────────────────────────

Deno.test('timingSafeEqual: token identici → true', () => {
  assert(timingSafeEqual('secret-abcdefghijklmnop', 'secret-abcdefghijklmnop'))
})

Deno.test('timingSafeEqual: token diversi → false', () => {
  assert(!timingSafeEqual('secret-abcdefghijklmnop', 'secret-abcdefghijklmnoq'))
})

Deno.test('timingSafeEqual: lunghezze diverse → false (no prefix match)', () => {
  assert(!timingSafeEqual('secret', 'secret-piu-lungo'))
  assert(!timingSafeEqual('', 'secret'))
})

// ─── Filtro allegati ──────────────────────────────────────────────────────────

Deno.test('isXls: accetta .xls e .xlsx, case-insensitive', () => {
  assert(isXls({ Name: 'ricavi.xls' }))
  assert(isXls({ Name: 'ricavi.xlsx' }))
  assert(isXls({ Name: 'RICAVI.XLSX' }))
})

Deno.test('isXls: scarta altre estensioni e nome assente', () => {
  assert(!isXls({ Name: 'fattura.pdf' }))
  assert(!isXls({ Name: 'ricavi.xls.exe' }))
  assert(!isXls({}))
})

// ─── Path Storage ─────────────────────────────────────────────────────────────

Deno.test('buildPath: sanitizza il nome file e prefissa il ristorante', () => {
  const p = buildPath('abc-123', 'ricavi giugno/2026.xlsx', 'deadbeefcafe0000ffff')
  assertStringIncludes(p, 'abc-123/')
  assertStringIncludes(p, 'deadbeefcafe0000_')
  assert(!p.includes(' '), 'gli spazi vanno sanitizzati')
  assertEquals(p.split('/').length, 3, 'nessun path traversal dal filename')
})

Deno.test('buildPath: ristorante null → prefisso unknown', () => {
  assertStringIncludes(buildPath(null, 'r.xlsx', 'k'.repeat(20)), 'unknown/')
})

// Il traversal è neutralizzato togliendo i SEPARATORI, non i punti: '../..' resta
// come '.._..' dentro il segmento finale, che è inerte. La proprietà che conta è
// che il filename non possa aggiungere livelli di path.
Deno.test('buildPath: filename ostile non evade la cartella', () => {
  const p = buildPath('rid', '../../etc/passwd.xlsx', 'k'.repeat(20))
  assertEquals(p.split('/').length, 3, `il filename ha aggiunto livelli di path: ${p}`)
  assertEquals(p.split('/')[0], 'rid', 'il prefisso ristorante deve restare il primo segmento')
  assert(!p.split('/')[2].includes('/'))
})

// ─── getAttachmentBytes: base64 inline (canale Gmail, quello vivo) ────────────

Deno.test('getAttachmentBytes: decodifica base64 inline', async () => {
  const bytes = await getAttachmentBytes({ base64Content: btoa('hello') }, 'api-key')
  assert(bytes !== null)
  assertEquals(new TextDecoder().decode(bytes!), 'hello')
})

Deno.test('getAttachmentBytes: base64 corrotto → null (non lancia)', async () => {
  assertEquals(await getAttachmentBytes({ base64Content: '@@@non-base64@@@' }, 'api-key'), null)
})

Deno.test('getAttachmentBytes: né base64 né DownloadToken → null', async () => {
  assertEquals(await getAttachmentBytes({ Name: 'vuoto.xlsx' }, 'api-key'), null)
})

// ─── FIX 30/7: BREVO_API_KEY assente = fail-closed, non fetch cieca ──────────

Deno.test('getAttachmentBytes: DownloadToken senza BREVO_API_KEY → null SENZA chiamare Brevo', async () => {
  const originalFetch = globalThis.fetch
  let called = false
  globalThis.fetch = (() => {
    called = true
    return Promise.resolve(new Response('unauthorized', { status: 401 }))
  }) as typeof fetch
  try {
    const bytes = await getAttachmentBytes({ DownloadToken: 'tok-123' }, '')
    assertEquals(bytes, null)
    assertEquals(called, false, 'senza api-key non deve nemmeno tentare la fetch')
  } finally {
    globalThis.fetch = originalFetch
  }
})

Deno.test('getAttachmentBytes: DownloadToken con api-key → passa header api-key', async () => {
  const originalFetch = globalThis.fetch
  let capturedKey = ''
  globalThis.fetch = ((_url: string, init: RequestInit) => {
    capturedKey = (init.headers as Record<string, string>)['api-key']
    return Promise.resolve(new Response(new TextEncoder().encode('xlsdata'), { status: 200 }))
  }) as typeof fetch
  try {
    const bytes = await getAttachmentBytes({ DownloadToken: 'tok-123' }, 'la-mia-key')
    assertEquals(capturedKey, 'la-mia-key')
    assertEquals(new TextDecoder().decode(bytes!), 'xlsdata')
  } finally {
    globalThis.fetch = originalFetch
  }
})

Deno.test('getAttachmentBytes: Brevo risponde 401 → null (chiave ruotata)', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = (() => Promise.resolve(new Response('nope', { status: 401 }))) as typeof fetch
  try {
    assertEquals(await getAttachmentBytes({ DownloadToken: 'tok' }, 'key-vecchia'), null)
  } finally {
    globalThis.fetch = originalFetch
  }
})

// ─── FIX 30/7: alert Telegram (unico segnale attivo) ─────────────────────────

Deno.test('notifyTelegram: no-op senza secrets configurati', async () => {
  Deno.env.delete('TELEGRAM_BOT_TOKEN')
  Deno.env.delete('TELEGRAM_CHAT_ID')
  const originalFetch = globalThis.fetch
  let called = false
  globalThis.fetch = (() => { called = true; return Promise.reject(new Error('non doveva chiamare')) }) as typeof fetch
  try {
    await notifyTelegram('messaggio')
    assertEquals(called, false)
  } finally {
    globalThis.fetch = originalFetch
  }
})

Deno.test('notifyTelegram: invia a sendMessage con chat_id e testo', async () => {
  Deno.env.set('TELEGRAM_BOT_TOKEN', 'tok-abc')
  Deno.env.set('TELEGRAM_CHAT_ID', '4242')
  const originalFetch = globalThis.fetch
  let url = ''
  let body: Record<string, unknown> = {}
  globalThis.fetch = ((u: string, init: RequestInit) => {
    url = u
    body = JSON.parse(init.body as string)
    return Promise.resolve(new Response('{"ok":true}', { status: 200 }))
  }) as typeof fetch
  try {
    await notifyTelegram('⚠️ Ricavi email: mittente sconosciuto')
    assertStringIncludes(url, 'https://api.telegram.org/bottok-abc/sendMessage')
    assertEquals(body.chat_id, '4242')
    assertStringIncludes(body.text as string, 'mittente sconosciuto')
  } finally {
    globalThis.fetch = originalFetch
    Deno.env.delete('TELEGRAM_BOT_TOKEN')
    Deno.env.delete('TELEGRAM_CHAT_ID')
  }
})

Deno.test('notifyTelegram: fire-and-forget, mai propaga eccezioni', async () => {
  Deno.env.set('TELEGRAM_BOT_TOKEN', 'tok-abc')
  Deno.env.set('TELEGRAM_CHAT_ID', '4242')
  const originalFetch = globalThis.fetch
  globalThis.fetch = (() => Promise.reject(new Error('rete giù'))) as typeof fetch
  try {
    let threw = false
    try { await notifyTelegram('x') } catch { threw = true }
    assert(!threw, 'notifyTelegram non deve mai lanciare')
  } finally {
    globalThis.fetch = originalFetch
    Deno.env.delete('TELEGRAM_BOT_TOKEN')
    Deno.env.delete('TELEGRAM_CHAT_ID')
  }
})

// ─── FIX 30/7: magic bytes (l'estensione la sceglie il mittente) ─────────────

Deno.test('hasXlsMagicBytes: header ZIP (xlsx) → true', () => {
  const xlsx = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0, 0, 0, 0])
  assert(hasXlsMagicBytes(xlsx))
})

Deno.test('hasXlsMagicBytes: header OLE2 (xls legacy) → true', () => {
  const xls = new Uint8Array([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1])
  assert(hasXlsMagicBytes(xls))
})

Deno.test('hasXlsMagicBytes: PDF travestito da .xlsx → false', () => {
  const pdf = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37])
  assert(!hasXlsMagicBytes(pdf))
})

Deno.test('hasXlsMagicBytes: eseguibile e testo → false', () => {
  assert(!hasXlsMagicBytes(new Uint8Array([0x4d, 0x5a, 0x90, 0, 0, 0, 0, 0])))
  assert(!hasXlsMagicBytes(new TextEncoder().encode('ciao mondo')))
})

Deno.test('hasXlsMagicBytes: file troppo corto → false (no out-of-bounds)', () => {
  assert(!hasXlsMagicBytes(new Uint8Array([0x50, 0x4b])))
  assert(!hasXlsMagicBytes(new Uint8Array([])))
})

// ─── FIX 30/7: cap sui byte REALI, non su content-length dichiarato ──────────

Deno.test('readBodyCapped: body sotto il cap → letto per intero', async () => {
  const req = new Request('https://x/', { method: 'POST', body: 'ciao' })
  assertEquals(await readBodyCapped(req, 1024), 'ciao')
})

Deno.test('readBodyCapped: body oltre il cap → BodyTooLargeError', async () => {
  const req = new Request('https://x/', { method: 'POST', body: 'x'.repeat(5000) })
  let caught: unknown = null
  try { await readBodyCapped(req, 100) } catch (e) { caught = e }
  assert(caught instanceof BodyTooLargeError, 'deve lanciare BodyTooLargeError')
})

Deno.test('readBodyCapped: chunked senza content-length viene comunque capped', async () => {
  // Stream senza content-length: è esattamente il bypass che il check
  // sull'header non copriva.
  const stream = new ReadableStream({
    start(controller) {
      for (let i = 0; i < 50; i++) controller.enqueue(new TextEncoder().encode('y'.repeat(100)))
      controller.close()
    },
  })
  const req = new Request('https://x/', { method: 'POST', body: stream })
  assertEquals(req.headers.get('content-length'), null, 'lo scenario richiede content-length assente')
  let caught: unknown = null
  try { await readBodyCapped(req, 500) } catch (e) { caught = e }
  assert(caught instanceof BodyTooLargeError, 'il cap deve valere anche senza content-length')
})

// ─── Handler: metodi e auth ───────────────────────────────────────────────────

function setEnvBase() {
  Deno.env.set('SUPABASE_URL', 'https://example.supabase.co')
  Deno.env.set('SUPABASE_SERVICE_ROLE_KEY', 'service-key-test')
  Deno.env.set('BREVO_WEBHOOK_TOKEN', 'token-abbastanza-lungo-123')
}

Deno.test('handler: GET → 200 (health check)', async () => {
  setEnvBase()
  assertEquals((await handler(new Request('https://x/', { method: 'GET' }))).status, 200)
})

Deno.test('handler: DELETE → 405', async () => {
  setEnvBase()
  assertEquals((await handler(new Request('https://x/', { method: 'DELETE' }))).status, 405)
})

Deno.test('handler: env vars mancanti → 500 senza dettagli', async () => {
  Deno.env.delete('SUPABASE_URL')
  Deno.env.set('SUPABASE_SERVICE_ROLE_KEY', 'k')
  Deno.env.set('BREVO_WEBHOOK_TOKEN', 'token-abbastanza-lungo-123')
  const resp = await handler(new Request('https://x/', { method: 'POST', body: '{}' }))
  assertEquals(resp.status, 500)
  const text = await resp.text()
  assert(!text.includes('SUPABASE'), 'la risposta non deve nominare le env var')
})

Deno.test('handler: token assente → 401', async () => {
  setEnvBase()
  const resp = await handler(new Request('https://x/', { method: 'POST', body: '{}' }))
  assertEquals(resp.status, 401)
})

Deno.test('handler: token errato → 401', async () => {
  setEnvBase()
  const resp = await handler(new Request('https://x/?token=sbagliato', { method: 'POST', body: '{}' }))
  assertEquals(resp.status, 401)
})

Deno.test('handler: token corto (<16) rifiutato anche se combacia', async () => {
  Deno.env.set('SUPABASE_URL', 'https://example.supabase.co')
  Deno.env.set('SUPABASE_SERVICE_ROLE_KEY', 'k')
  Deno.env.set('BREVO_WEBHOOK_TOKEN', 'corto')
  const resp = await handler(new Request('https://x/?token=corto', { method: 'POST', body: '{}' }))
  assertEquals(resp.status, 401, 'un secret debole non deve autenticare')
})

Deno.test('handler: token valido via header X-Oneflux-Webhook-Token', async () => {
  setEnvBase()
  const resp = await handler(new Request('https://x/', {
    method: 'POST',
    headers: { 'X-Oneflux-Webhook-Token': 'token-abbastanza-lungo-123' },
    body: JSON.stringify({ items: [] }),
  }))
  assertEquals(resp.status, 200, 'items vuoti → 200 senza toccare il DB')
})

Deno.test('handler: body oltre il cap dichiarato → 413', async () => {
  setEnvBase()
  const resp = await handler(new Request('https://x/?token=token-abbastanza-lungo-123', {
    method: 'POST',
    headers: { 'content-length': String(30 * 1024 * 1024) },
    body: '{}',
  }))
  assertEquals(resp.status, 413)
})

Deno.test('handler: body chunked oltre il cap → 413 (bypass header chiuso)', async () => {
  setEnvBase()
  const stream = new ReadableStream({
    start(controller) {
      // 30 MB > MAX_BODY_BYTES (25 MB), senza dichiarare content-length.
      for (let i = 0; i < 30; i++) controller.enqueue(new Uint8Array(1024 * 1024))
      controller.close()
    },
  })
  const req = new Request('https://x/?token=token-abbastanza-lungo-123', {
    method: 'POST', body: stream,
  })
  assertEquals(req.headers.get('content-length'), null)
  assertEquals((await handler(req)).status, 413)
})

Deno.test('handler: JSON non valido → 400', async () => {
  setEnvBase()
  const resp = await handler(new Request('https://x/?token=token-abbastanza-lungo-123', {
    method: 'POST',
    body: 'non-json{',
  }))
  assertEquals(resp.status, 400)
})
