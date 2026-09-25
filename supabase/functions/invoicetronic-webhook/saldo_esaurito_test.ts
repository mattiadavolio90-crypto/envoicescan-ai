// ═══════════════════════════════════════════════════════════════════════════════
// Saldo crediti Invoicetronic esaurito (passo 0, 25/9/2026)
// ═══════════════════════════════════════════════════════════════════════════════
//   deno test --allow-env --allow-net saldo_esaurito_test.ts
//
// A saldo zero Invoicetronic risponde 403 `usage_limit_exceeded` a ogni GET su
// /receive: la fattura resta 'failed' e diventa 'dead' in circa 2 ore, senza
// avviso. Qui si esegue il flusso VERO di un evento (processaEvento) con la
// risposta API simulata, un DB finto e Telegram intercettato: si verifica che la
// riga venga marcata e che l'avviso parta una volta sola, e solo per quel 403.
// ═══════════════════════════════════════════════════════════════════════════════

import { assert, assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'

Deno.env.set('WEBHOOK_TEST_MODE', '1')

const {
  processaEvento, normalizeWebhookEvent, _usaClientDbDiTest,
  isSaldoEsaurito, leggiCodiceProblema, saldoEsauritoGiaSegnalato, CODICE_SALDO_ESAURITO,
} = await import('./index.ts')

type Riga = Record<string, unknown> & { payload_meta: Record<string, unknown> }

function dbFinto(opzioni: { righeRecenti?: unknown[]; erroreLettura?: boolean; eccezioneLettura?: boolean } = {}) {
  const registro = { upserts: [] as Riga[], filtri: [] as unknown[][], tabelleLette: [] as string[] }
  const client = {
    from(tabella: string) {
      // deno-lint-ignore no-explicit-any
      const q: any = {
        select(_colonne: string) { registro.tabelleLette.push(tabella); return q },
        eq(colonna: string, valore: unknown) { registro.filtri.push(['eq', colonna, valore]); return q },
        gte(colonna: string, valore: unknown) { registro.filtri.push(['gte', colonna, valore]); return q },
        limit(_n: number) {
          if (opzioni.eccezioneLettura) return Promise.reject(new Error('rete giù'))
          if (opzioni.erroreLettura) return Promise.resolve({ data: null, error: { message: 'permesso negato' } })
          return Promise.resolve({ data: opzioni.righeRecenti ?? [], error: null })
        },
        upsert(riga: Riga, _opts: unknown) { registro.upserts.push(riga); return Promise.resolve({ error: null }) },
        update(_riga: unknown) { return q },
      }
      return q
    },
  }
  return { client, registro }
}

function rispostaApi(status: number, corpo: unknown): Response {
  const testo = typeof corpo === 'string' ? corpo : JSON.stringify(corpo)
  return new Response(testo, { status, headers: { 'Content-Type': 'application/problem+json' } })
}

async function eseguiEvento(
  risposta: () => Response,
  db: ReturnType<typeof dbFinto>,
): Promise<{ esito: string; telegram: string[] }> {
  const telegram: string[] = []
  const originale = globalThis.fetch
  Deno.env.set('TELEGRAM_BOT_TOKEN', 'token-di-test')
  Deno.env.set('TELEGRAM_CHAT_ID', '42')
  globalThis.fetch = ((url: string | URL | Request, init?: RequestInit) => {
    const u = String(url)
    if (u.startsWith('https://api.telegram.org/')) {
      telegram.push(String(JSON.parse(String(init?.body)).text))
      return Promise.resolve(new Response('{"ok":true}', { status: 200 }))
    }
    if (u.startsWith('https://api.invoicetronic.com/v1/receive/')) return Promise.resolve(risposta())
    return Promise.reject(new Error(`fetch inatteso: ${u}`))
  }) as typeof fetch
  // deno-lint-ignore no-explicit-any
  _usaClientDbDiTest((() => db.client) as any)
  try {
    const ev = normalizeWebhookEvent({
      id: 501, resource_id: 98765, company_id: 1756, endpoint: 'receive', event: 'receive.add', success: true,
    })
    const esito = await processaEvento(
      ev, '{}', new Request('https://esempio.test/', { method: 'POST' }),
      'https://progetto.supabase.co', 'chiave-servizio', 'chiave-api',
    )
    return { esito, telegram }
  } finally {
    globalThis.fetch = originale
    _usaClientDbDiTest(null)
    Deno.env.delete('TELEGRAM_BOT_TOKEN')
    Deno.env.delete('TELEGRAM_CHAT_ID')
  }
}

const SALDO_ESAURITO = { type: 'about:blank', status: 403, code: 'usage_limit_exceeded', detail: 'Operazioni esaurite' }

// ─── Flusso vero: processaEvento ──────────────────────────────────────────────

Deno.test('403 saldo esaurito: riga marcata e un avviso Telegram', async () => {
  const db = dbFinto()
  const { esito, telegram } = await eseguiEvento(() => rispostaApi(403, SALDO_ESAURITO), db)

  assertEquals(esito, 'ok')
  assertEquals(db.registro.upserts.length, 1)
  const riga = db.registro.upserts[0]
  assertEquals(riga.status, 'failed')
  assertEquals(riga.payload_meta.api_error, 'HTTP 403')
  assertEquals(riga.payload_meta.api_error_code, 'usage_limit_exceeded')
  assertEquals(telegram.length, 1)
  assertStringIncludes(telegram[0], 'usage_limit_exceeded')
  assertStringIncludes(telegram[0], '§4bis')
  assertStringIncludes(telegram[0], 'Riprova')
  assertStringIncludes(telegram[0], 'Flusso dati')
})

Deno.test('403 saldo esaurito: l\'anti-ripetizione cerca le righe marcate nell\'ultima ora', async () => {
  const db = dbFinto()
  const prima = Date.now()
  await eseguiEvento(() => rispostaApi(403, SALDO_ESAURITO), db)

  assertEquals(db.registro.tabelleLette, ['fatture_queue'])
  const eq = db.registro.filtri.find((f) => f[0] === 'eq')
  assertEquals(eq, ['eq', 'payload_meta->>api_error_code', 'usage_limit_exceeded'])
  const gte = db.registro.filtri.find((f) => f[0] === 'gte')!
  assertEquals(gte[1], 'created_at')
  const daMs = Date.parse(String(gte[2]))
  assert(Math.abs(prima - 3_600_000 - daMs) < 5_000, `finestra attesa di 1 ora, trovata ${new Date(daMs).toISOString()}`)
})

Deno.test('403 saldo esaurito gia\' segnalato nell\'ultima ora: riga marcata, nessun avviso', async () => {
  const db = dbFinto({ righeRecenti: [{ id: 7 }] })
  const { telegram } = await eseguiEvento(() => rispostaApi(403, SALDO_ESAURITO), db)

  assertEquals(db.registro.upserts[0].payload_meta.api_error_code, 'usage_limit_exceeded')
  assertEquals(telegram.length, 0)
})

Deno.test('403 saldo esaurito con coda illeggibile: avvisa comunque (errore o eccezione)', async () => {
  for (const opzioni of [{ erroreLettura: true }, { eccezioneLettura: true }]) {
    const { telegram } = await eseguiEvento(() => rispostaApi(403, SALDO_ESAURITO), dbFinto(opzioni))
    assertEquals(telegram.length, 1, JSON.stringify(opzioni))
  }
})

Deno.test('403 per altre ragioni (firme, sotto-chiave, corpo non JSON): nessun avviso, nessuna marcatura', async () => {
  const casi: Array<[string, unknown]> = [
    ['firme esaurite', { status: 403, code: 'signature_limit_exceeded' }],
    ['sotto-chiave', { status: 403, code: 'subkey_not_allowed' }],
    ['code non stringa', { status: 403, code: 42 }],
    ['corpo non JSON', 'Forbidden'],
    ['corpo vuoto', ''],
  ]
  for (const [nome, corpo] of casi) {
    const db = dbFinto()
    const { telegram } = await eseguiEvento(() => rispostaApi(403, corpo), db)
    assertEquals(telegram.length, 0, nome)
    assertEquals(db.registro.upserts[0].payload_meta.api_error, 'HTTP 403', nome)
    assertEquals(db.registro.upserts[0].payload_meta.api_error_code, undefined, nome)
  }
})

Deno.test('usage_limit_exceeded con status diverso da 403: nessun avviso', async () => {
  for (const status of [402, 404, 429, 500]) {
    const db = dbFinto()
    const { telegram } = await eseguiEvento(() => rispostaApi(status, { status, code: 'usage_limit_exceeded' }), db)
    assertEquals(telegram.length, 0, `HTTP ${status}`)
    assertEquals(db.registro.upserts[0].payload_meta.api_error_code, undefined, `HTTP ${status}`)
  }
})

// ─── Le funzioni, una per una ────────────────────────────────────────────────

Deno.test('isSaldoEsaurito: solo 403 con il codice del saldo', () => {
  assertEquals(CODICE_SALDO_ESAURITO, 'usage_limit_exceeded')
  assert(isSaldoEsaurito(403, 'usage_limit_exceeded'))
  assert(!isSaldoEsaurito(403, 'signature_limit_exceeded'))
  assert(!isSaldoEsaurito(403, null))
  assert(!isSaldoEsaurito(429, 'usage_limit_exceeded'))
})

Deno.test('leggiCodiceProblema: legge code, non solleva mai', async () => {
  assertEquals(await leggiCodiceProblema(rispostaApi(403, SALDO_ESAURITO)), 'usage_limit_exceeded')
  assertEquals(await leggiCodiceProblema(rispostaApi(403, { detail: 'senza codice' })), null)
  assertEquals(await leggiCodiceProblema(rispostaApi(403, 'non json')), null)
  assertEquals(await leggiCodiceProblema(rispostaApi(403, 'null')), null)
  const giaLetta = rispostaApi(403, SALDO_ESAURITO)
  await giaLetta.text()
  assertEquals(await leggiCodiceProblema(giaLetta), null)
})

Deno.test('saldoEsauritoGiaSegnalato: vero solo se la coda ha una riga marcata', async () => {
  // deno-lint-ignore no-explicit-any
  const come = (d: ReturnType<typeof dbFinto>) => d.client as any
  assertEquals(await saldoEsauritoGiaSegnalato(come(dbFinto({ righeRecenti: [{ id: 1 }] }))), true)
  assertEquals(await saldoEsauritoGiaSegnalato(come(dbFinto({ righeRecenti: [] }))), false)
  assertEquals(await saldoEsauritoGiaSegnalato(come(dbFinto({ erroreLettura: true }))), false)
  assertEquals(await saldoEsauritoGiaSegnalato(come(dbFinto({ eccezioneLettura: true }))), false)
})
