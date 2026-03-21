#!/usr/bin/env -S deno run --allow-net --allow-env
// ═══════════════════════════════════════════════════════════════════════════════
// Test: invoicetronic-webhook Edge Function
// ═══════════════════════════════════════════════════════════════════════════════
//
// Simula richieste webhook da Invoicetronic con firma HMAC-SHA256 valida.
// Copre tutti i percorsi principali della funzione.
//
// PREREQUISITI:
//   1. Deno installato: https://docs.deno.com/runtime/getting_started/installation/
//   2. "supabase functions serve" già avviato in un altro terminale:
//        supabase functions serve \
//          --project-ref vthikmfpywilukizputn \
//          --env-file ./supabase/functions/.env.local \
//          --no-verify-jwt
//
// USO:
//   # Testa su localhost (default)
//   $env:WEBHOOK_SECRET="wh_sec_IL_TUO_SECRET"
//   deno run --allow-net --allow-env test.ts
//
//   # Testa su produzione (ATTENZIONE: scrive nel DB reale)
//   $env:WEBHOOK_SECRET="wh_sec_IL_TUO_SECRET"
//   $env:SUPABASE_ANON_KEY="IL_TUO_ANON_KEY"
//   $env:TARGET="https://vthikmfpywilukizputn.supabase.co"
//   deno run --allow-net --allow-env test.ts --prod
//
// ─── Configurazione ─────────────────────────────────────────────────────────

const WEBHOOK_SECRET = Deno.env.get('WEBHOOK_SECRET') ?? ''
const isProd = Deno.args.includes('--prod')

// localhost: supabase functions serve (54321) oppure deno run standalone (8000 / PORT env var)
// prod:      Edge Function su Supabase Cloud
// Puoi sempre sovrascrivere con $env:TARGET="http://localhost:8000" (es. senza Docker)
const BASE_URL = isProd
  ? (Deno.env.get('TARGET') ?? 'https://vthikmfpywilukizputn.supabase.co')
  : (Deno.env.get('TARGET') ?? 'http://localhost:54321')

// Header Authorization richiesto da Supabase Cloud (non da serve locale con --no-verify-jwt)
const ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY') ?? ''

const FUNCTION_URL = `${BASE_URL}/functions/v1/invoicetronic-webhook`

// ─── Controllo prerequisiti ──────────────────────────────────────────────────

if (!WEBHOOK_SECRET) {
  console.error('\n❌ ERRORE: WEBHOOK_SECRET non impostato.')
  console.error('   PowerShell: $env:WEBHOOK_SECRET="wh_sec_il_tuo_secret"')
  console.error('   Bash:       export WEBHOOK_SECRET=wh_sec_il_tuo_secret\n')
  Deno.exit(1)
}

if (isProd && !ANON_KEY) {
  console.warn('⚠️  --prod attivo ma SUPABASE_ANON_KEY non impostato.')
  console.warn('   La funzione potrebbe rispondere 401 per JWT mancante.')
  console.warn('   Imposta: $env:SUPABASE_ANON_KEY="eyJhb..."\n')
}

// ─── Utility: genera firma HMAC-SHA256 ───────────────────────────────────────
// Replica esatta della formula Invoicetronic: HMAC-SHA256("{ts}.{body}", secret)

async function sign(timestamp: number, body: string): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(WEBHOOK_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  const buf = await crypto.subtle.sign('HMAC', key, enc.encode(`${timestamp}.${body}`))
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

// ─── Utility: costruisce header firma Invoicetronic ──────────────────────────

async function makeSignatureHeader(body: string, offsetSecs = 0): Promise<string> {
  const ts  = Math.floor(Date.now() / 1000) + offsetSecs
  const sig = await sign(ts, body)
  return `t=${ts},v1=${sig}`
}

// ─── Utility: invia richiesta e stampa risultato ─────────────────────────────

async function post(
  label:   string,
  body:    string,
  headers: Record<string, string>,
): Promise<{ status: number; text: string }> {
  const reqHeaders: Record<string, string> = {
    'Content-Type':  'application/json',
    'X-Request-ID':  `test-${Date.now()}`,
    ...headers,
  }
  if (isProd && ANON_KEY) reqHeaders['Authorization'] = `Bearer ${ANON_KEY}`

  let res: Response
  try {
    res = await fetch(FUNCTION_URL, { method: 'POST', headers: reqHeaders, body })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.log(`\n▶  ${label}`)
    console.log(`   ❌ Connessione fallita: ${msg}`)
    console.log('      La funzione è in esecuzione? "supabase functions serve ..."')
    return { status: 0, text: '' }
  }

  const text = await res.text()
  const icon = res.ok ? '✅' : (res.status === 401 ? '🔒' : '⚠️')
  console.log(`\n▶  ${label}`)
  console.log(`   ${icon} HTTP ${res.status}: ${text.slice(0, 120)}`)
  return { status: res.status, text }
}

// ─── Utility: GET health check ───────────────────────────────────────────────

async function getHealthCheck(): Promise<void> {
  console.log('\n▶  Health check (GET)')
  try {
    const res = await fetch(FUNCTION_URL, { method: 'GET' })
    const t   = await res.text()
    console.log(`   ${res.ok ? '✅' : '❌'} HTTP ${res.status}: ${t}`)
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.log(`   ❌ Connessione fallita: ${msg}`)
    console.log('      Avvia la funzione con: supabase functions serve \\')
    console.log('        --project-ref vthikmfpywilukizputn \\')
    console.log('        --env-file ./supabase/functions/.env.local \\')
    console.log('        --no-verify-jwt')
  }
}

// ─── Payload di test: evento receive.add ─────────────────────────────────────
// resource_id fittizio: l'API Invoicetronic risponderà 404/error
// → il record finisce in fatture_queue con status='failed' (comportamento atteso)
// Per testare status='pending'/'unknown_tenant' servono credenziali API reali.

const testPayloadBase = {
  id:          Math.floor(Math.random() * 900_000) + 100_000, // event_id univoco
  user_id:     100,
  company_id:  42,
  resource_id: 999999, // ID non esistente su Invoicetronic → API error → failed
  endpoint:    'receive',
  method:      'POST',
  status_code: 201,
  success:     true,
  date_time:   new Date().toISOString(),
  api_version: 1,
}

// ─── Suite di test ───────────────────────────────────────────────────────────

async function runTests(): Promise<void> {
  const target = isProd ? `PRODUZIONE (${BASE_URL})` : `LOCALE (${BASE_URL})`
  console.log('═'.repeat(60))
  console.log(`🧪  Test invoicetronic-webhook — ${target}`)
  console.log('═'.repeat(60))
  console.log(`   Funzione: ${FUNCTION_URL}`)
  console.log(`   Secret:   ${WEBHOOK_SECRET.slice(0, 8)}${'*'.repeat(8)}`)
  console.log(`   Payload event_id: ${testPayloadBase.id}`)

  let passed = 0
  let failed = 0

  // ── Test 0: Health check GET ──────────────────────────────────────────────
  await getHealthCheck()

  // ── Test 1: Firma valida → deve inserire in fatture_queue ─────────────────
  {
    const body = JSON.stringify(testPayloadBase)
    const sig  = await makeSignatureHeader(body)
    const r    = await post('T1: Firma valida (atteso 200)', body, {
      'Invoicetronic-Signature': sig,
    })
    if (r.status === 200) passed++; else failed++
  }

  // ── Test 2: Idempotenza — stesso event_id → ancora 200, no duplicato ───────
  {
    const body = JSON.stringify(testPayloadBase) // stesso event_id del test 1
    const sig  = await makeSignatureHeader(body)
    const r    = await post('T2: Idempotenza — stesso event_id (atteso 200)', body, {
      'Invoicetronic-Signature': sig,
    })
    if (r.status === 200) passed++; else failed++
    console.log('      (Nessun duplicato in DB: ON CONFLICT DO NOTHING)')
  }

  // ── Test 3: Firma mancante → 401 ──────────────────────────────────────────
  {
    const body = JSON.stringify({ ...testPayloadBase, id: testPayloadBase.id + 1 })
    const r    = await post('T3: Firma assente (atteso 401)', body, {})
    if (r.status === 401) passed++; else failed++
  }

  // ── Test 4: Firma errata → 401 ────────────────────────────────────────────
  {
    const body = JSON.stringify({ ...testPayloadBase, id: testPayloadBase.id + 2 })
    const ts   = Math.floor(Date.now() / 1000)
    const r    = await post('T4: Firma errata (atteso 401)', body, {
      'Invoicetronic-Signature': `t=${ts},v1=aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899`,
    })
    if (r.status === 401) passed++; else failed++
  }

  // ── Test 5: Anti-replay — timestamp vecchio di 10 minuti → 401 ────────────
  {
    const body    = JSON.stringify({ ...testPayloadBase, id: testPayloadBase.id + 3 })
    const oldSig  = await makeSignatureHeader(body, -601) // -601s = fuori finestra 300s
    const r       = await post('T5: Anti-replay (timestamp -10 min, atteso 401)', body, {
      'Invoicetronic-Signature': oldSig,
    })
    if (r.status === 401) passed++; else failed++
  }

  // ── Test 6: Evento non-receive (send) → 200 silenzioso ───────────────────
  {
    const payload = { ...testPayloadBase, id: testPayloadBase.id + 4, endpoint: 'send' }
    const body    = JSON.stringify(payload)
    const sig     = await makeSignatureHeader(body)
    const r       = await post('T6: Evento "send" ignorato (atteso 200)', body, {
      'Invoicetronic-Signature': sig,
    })
    if (r.status === 200) passed++; else failed++
    console.log('      (Nessun record inserito: endpoint != "receive")')
  }

  // ── Test 7: success=false → 200 silenzioso ────────────────────────────────
  {
    const payload = { ...testPayloadBase, id: testPayloadBase.id + 5, success: false }
    const body    = JSON.stringify(payload)
    const sig     = await makeSignatureHeader(body)
    const r       = await post('T7: success=false ignorato (atteso 200)', body, {
      'Invoicetronic-Signature': sig,
    })
    if (r.status === 200) passed++; else failed++
  }

  // ── Test 8: JSON malformato → 400 ─────────────────────────────────────────
  {
    const body = '{ INVALID JSON !!!'
    const sig  = await makeSignatureHeader(body) // firma valida del body rotto
    const r    = await post('T8: JSON malformato (atteso 400)', body, {
      'Invoicetronic-Signature': sig,
    })
    if (r.status === 400) passed++; else failed++
  }

  // ── Test 9: Health check via GET → 200 ───────────────────────────────────
  {
    let res: Response
    try {
      res = await fetch(FUNCTION_URL, { method: 'PUT' })
      const t = await res.text()
      const ok = res.status === 405
      console.log(`\n▶  T9: Metodo non consentito PUT (atteso 405)`)
      console.log(`   ${ok ? '✅' : '❌'} HTTP ${res.status}: ${t}`)
      if (ok) passed++; else failed++
    } catch { /* già loggato dal getHealthCheck */ }
  }

  // ── Riepilogo ─────────────────────────────────────────────────────────────
  console.log('\n' + '═'.repeat(60))
  const allOk = failed === 0
  console.log(`${allOk ? '🎉' : '💥'}  Risultati: ${passed} passati, ${failed} falliti`)
  if (!allOk) {
    console.log('   Controlla i log della funzione con:')
    console.log('   supabase functions logs invoicetronic-webhook --project-ref vthikmfpywilukizputn')
  }

  // ── Verifica DB (solo se test 1 è passato) ────────────────────────────────
  console.log('\n📋  Verifica DB (esegui su Supabase Dashboard → SQL Editor):')
  console.log(`\n   SELECT id, event_id, piva_raw, status, attempt_count,`)
  console.log(`          payload_meta->>'resource_id' AS resource_id,`)
  console.log(`          created_at`)
  console.log(`   FROM public.fatture_queue`)
  console.log(`   WHERE event_id = '${testPayloadBase.id}'`)
  console.log(`   ORDER BY created_at DESC;`)
  console.log('\n   Atteso: 1 riga con status="failed" (resource_id 999999 non esiste su Invoicetronic)')
  console.log('   Per testare status="pending"/"unknown_tenant" serve una API key reale + resource_id esistente.\n')

  Deno.exit(allOk ? 0 : 1)
}

await runTests()
