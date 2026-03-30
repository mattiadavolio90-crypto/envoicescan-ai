// ═══════════════════════════════════════════════════════════════════════════════
// Supabase Edge Function: invoicetronic-webhook
// ═══════════════════════════════════════════════════════════════════════════════
// Riceve eventi webhook da Invoicetronic e li accoda in public.fatture_queue.
//
// Flusso:
//   Invoicetronic → POST /functions/v1/invoicetronic-webhook
//     → verifica HMAC-SHA256 + anti-replay (5 min)
//     → filtra: solo endpoint="receive" + success=true
//     → GET https://api.invoicetronic.com/receive/{resource_id}
//     → estrae XML, P.IVA, metadati
//     → lookup tenant in tabella ristoranti
//     → INSERT in fatture_queue (idempotente via ON CONFLICT DO NOTHING)
//     → risponde 200 SEMPRE dopo insert (evita retry aggressivi)
//
// Sicurezza:
//   - Body letto RAW prima di JSON.parse (obbligatorio per HMAC)
//   - Confronto firma timing-safe (nessun early-exit)
//   - SSRF whitelist: fetch solo da *.invoicetronic.com (HTTPS)
//   - redirect: 'error' su tutti i fetch (blocca redirect SSRF)
//   - XML max 10 MB
//   - Mai loggare XML, PII, API keys
//   - service_role key solo da env (Deno.env.get)
//
// Env secrets richiesti (supabase secrets set):
//   SUPABASE_URL                    → iniettato automaticamente da Supabase
//   SUPABASE_SERVICE_ROLE_KEY       → da Supabase dashboard → Settings → API
//   INVOICETRONIC_WEBHOOK_SECRET    → da dashboard Invoicetronic → Webhook
//   INVOICETRONIC_API_KEY           → da dashboard Invoicetronic → API Keys
//
// Runtime: Deno (Supabase Edge Functions)
// Tabella: public.fatture_queue (migration 045)
// ═══════════════════════════════════════════════════════════════════════════════

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

// ─── Costanti ─────────────────────────────────────────────────────────────────

const INVOICETRONIC_API_BASE = 'https://api.invoicetronic.com/v1'

// SSRF whitelist: unici host da cui questo servizio può fare fetch
const ALLOWED_HOST_EXACT  = 'invoicetronic.com'
const ALLOWED_HOST_SUFFIX = '.invoicetronic.com'

const MAX_XML_BYTES      = 10 * 1024 * 1024 // 10 MB — protezione DoS storage
const REPLAY_WINDOW_SECS = 300              // 5 min — finestra anti-replay
const API_TIMEOUT_MS     = 3_000           // timeout chiamata API Invoicetronic
const XML_TIMEOUT_MS     = 2_000           // timeout download XML da URL

// ─── Tipi ─────────────────────────────────────────────────────────────────────

/** Payload inviato via webhook da Invoicetronic per ogni evento.
 *  In produzione sono comparsi payload con naming diverso da quello usato
 *  nei test locali (`event=receive.add`, `resourceId`, `statusCode`).
 */
interface WebhookEvent {
  id?:          number | string
  user_id?:     number | string
  company_id?:  number | string
  resource_id?: number | string
  resourceId?:  number | string
  endpoint?:    string
  event?:       string
  method?:      string
  status_code?: number | string
  statusCode?:  number | string
  success?:     boolean | string
  date_time?:   string
  dateTime?:    string
  api_version?: number | string
}

interface NormalizedWebhookEvent {
  eventId: number | null
  userId: number | null
  companyId: number | null
  resourceId: number | null
  endpoint: string | null
  eventName: string | null
  method: string | null
  statusCode: number | null
  success: boolean
  dateTime: string | null
  apiVersion: number | null
}

/** Risposta da GET https://api.invoicetronic.com/receive/{resource_id} */
interface ReceiveApiRecord {
  id:         number
  payload?:   string
  encoding?:  'Xml' | 'Base64' | string
  xml_file?:  string   // XML FatturaPA in base64 (preferito)
  xml_url?:   string   // URL alternativo per download XML
  file_name?: string   // nome file originale (non-PII, utile per debug)
  [key: string]: unknown
}

// ─── Utility: comparazione timing-safe ────────────────────────────────────────
// Non ha early-exit sul contenuto → nessun timing oracle sul valore della firma.
// Dimensione uguale garantita (HMAC-SHA256 produce sempre 64 hex chars).

function timingSafeEqual(a: string, b: string): boolean {
  const enc    = new TextEncoder()
  const aBytes = enc.encode(a)
  const bBytes = enc.encode(b)
  const len    = Math.max(aBytes.length, bBytes.length)
  // XOR delle lunghezze: 0 se uguali → evita branch sulla lunghezza
  let diff = aBytes.length ^ bBytes.length
  for (let i = 0; i < len; i++) {
    diff |= (aBytes[i] ?? 0) ^ (bBytes[i] ?? 0)
  }
  return diff === 0
}

// ─── Utility: whitelist SSRF + validazione URL ────────────────────────────────

function validateSsrfUrl(rawUrl: string): URL {
  let u: URL
  try {
    u = new URL(rawUrl)
  } catch {
    throw new Error(`URL malformato: "${rawUrl}"`)
  }
  if (u.protocol !== 'https:') {
    throw new Error(`Protocollo non consentito (solo HTTPS): ${u.protocol}`)
  }
  if (u.hostname !== ALLOWED_HOST_EXACT && !u.hostname.endsWith(ALLOWED_HOST_SUFFIX)) {
    throw new Error(`Host non autorizzato (SSRF blocked): ${u.hostname}`)
  }
  return u
}

// ─── Utility: fetch sicuro (SSRF check + timeout + no-redirect) ───────────────

async function safeFetch(
  url:     string,
  init:    RequestInit,
  timeout: number,
): Promise<Response> {
  validateSsrfUrl(url) // SSRF check sincrono PRIMA di qualsiasi I/O

  const ac    = new AbortController()
  const timer = setTimeout(() => ac.abort(), timeout)
  try {
    return await fetch(url, {
      ...init,
      signal:   ac.signal,
      redirect: 'error', // blocca redirect → previene SSRF via 301/302
    })
  } finally {
    clearTimeout(timer)
  }
}

// ─── Utility: verifica firma HMAC-SHA256 Invoicetronic ────────────────────────
// Header formato: "Invoicetronic-Signature: t=1733395200,v1=a1b2c3..."
// Messaggio firmato: "{timestamp}.{rawBody}"

async function verifyHmac(
  rawBody: string,
  header:  string | null,
  secret:  string,
): Promise<boolean> {
  if (!header) return false

  // Parsing "t=...,v1=..."
  const parts: Record<string, string> = {}
  for (const seg of header.split(',')) {
    const i = seg.indexOf('=')
    if (i > 0) parts[seg.slice(0, i).trim()] = seg.slice(i + 1).trim()
  }

  const ts  = parts['t']
  const sig = parts['v1']
  if (!ts || !sig) return false

  // Anti-replay: rifiuta eventi con timestamp fuori dalla finestra
  const tsNum = Number(ts)
  if (!Number.isFinite(tsNum)) return false
  if (Math.abs(Date.now() / 1000 - tsNum) > REPLAY_WINDOW_SECS) return false

  // Calcolo HMAC-SHA256("{ts}.{rawBody}", secret)
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  const buf = await crypto.subtle.sign('HMAC', key, enc.encode(`${ts}.${rawBody}`))
  const hex = Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')

  return timingSafeEqual(hex, sig)
}

// ─── Utility: SHA-256 hex (per xml_hash) ──────────────────────────────────────

async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('')
}

// ─── Utility: decodifica base64 → stringa UTF-8 ───────────────────────────────
// atob() produce latin-1; serve TextDecoder per UTF-8 corretto (caratteri accentati
// in nomi/ragioni sociali nei file FatturaPA).

function base64ToUtf8(b64: string): string {
  const bin = atob(b64)
  const buf = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
  return new TextDecoder('utf-8').decode(buf)
}

function toNumberOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function toBool(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase()
    if (normalized === 'true') return true
    if (normalized === 'false') return false
  }
  return null
}

function normalizeWebhookEvent(ev: WebhookEvent): NormalizedWebhookEvent {
  const statusCode = toNumberOrNull(ev.status_code ?? ev.statusCode)
  const explicitSuccess = toBool(ev.success)

  return {
    eventId:   toNumberOrNull(ev.id),
    userId:    toNumberOrNull(ev.user_id),
    companyId: toNumberOrNull(ev.company_id),
    resourceId: toNumberOrNull(ev.resource_id ?? ev.resourceId),
    endpoint:  typeof ev.endpoint === 'string' ? ev.endpoint.trim().toLowerCase() : null,
    eventName: typeof ev.event === 'string' ? ev.event.trim().toLowerCase() : null,
    method:    typeof ev.method === 'string' ? ev.method.trim().toUpperCase() : null,
    statusCode,
    success: explicitSuccess ?? (statusCode != null && statusCode >= 200 && statusCode < 300),
    dateTime: typeof ev.date_time === 'string' ? ev.date_time : (typeof ev.dateTime === 'string' ? ev.dateTime : null),
    apiVersion: toNumberOrNull(ev.api_version),
  }
}

// ─── Utility: estrazione P.IVA del destinatario da XML FatturaPA ──────────────
// Cerca nel blocco <CessionarioCommittente> (destinatario della fattura):
//   1° tentativo: <IdCodice>  → P.IVA italiana (11 cifre) o estera
//   2° tentativo: <CodiceFiscale> → CF persona fisica

function extractPivaDestinatario(xml: string): string | null {
  // Isola il blocco CessionarioCommittente per evitare falsi match
  const blockMatch = xml.match(
    /<CessionarioCommittente\b[^>]*>([\s\S]*?)<\/CessionarioCommittente>/,
  )
  if (!blockMatch) return null
  const block = blockMatch[1]

  const idCodice = block.match(/<IdCodice>\s*([A-Z0-9]{1,28})\s*<\/IdCodice>/)?.[1]?.trim()
  if (idCodice) return idCodice

  const cf = block.match(/<CodiceFiscale>\s*([A-Z0-9]{11,16})\s*<\/CodiceFiscale>/)?.[1]?.trim()
  if (cf) return cf

  return null
}

// ─── Utility: estrazione metadati documento da XML (no PII) ───────────────────
// Estrae solo dati strutturati non personali per payload_meta.
// Non vengono estratti nomi, indirizzi, IBAN o altri dati personali.

function extractDocMeta(xml: string): Record<string, unknown> {
  // Helper: primo tag match nel documento generico
  const tag = (n: string): string | undefined =>
    xml.match(new RegExp(`<${n}>\\s*([^<]+?)\\s*<\\/${n}>`))?.[1]

  // P.IVA cedente (emittente) — da CedentePrestatore
  const cpBlock = xml.match(
    /<CedentePrestatore\b[^>]*>([\s\S]*?)<\/CedentePrestatore>/,
  )?.[1] ?? ''
  const pivaCedente = cpBlock
    .match(/<IdCodice>\s*([A-Z0-9]{1,28})\s*<\/IdCodice>/)?.[1]
    ?.trim()

  const importoStr = tag('ImportoTotaleDocumento')

  return {
    tipo_documento:  tag('TipoDocumento'),
    data_fattura:    tag('Data'),
    numero_fattura:  tag('Numero'),
    importo_totale:  importoStr != null ? parseFloat(importoStr) : undefined,
    piva_cedente:    pivaCedente,
  }
}

// ─── Handler principale ───────────────────────────────────────────────────────

// Porta configurabile via PORT env var (utile per test locali senza Docker)
const _servePort = parseInt(Deno.env.get('PORT') ?? '8000', 10)
Deno.serve({ port: _servePort }, async (req: Request): Promise<Response> => {
  // Health check (utile per Supabase dashboard e test rapidi)
  if (req.method === 'GET') return new Response('OK', { status: 200 })
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  // ── Env vars ──────────────────────────────────────────────────────────────
  const supabaseUrl   = Deno.env.get('SUPABASE_URL')                ?? ''
  const serviceKey    = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')   ?? ''
  const webhookSecret = Deno.env.get('INVOICETRONIC_WEBHOOK_SECRET') ?? ''
  const apiKey        = Deno.env.get('INVOICETRONIC_API_KEY')        ?? ''

  if (!supabaseUrl || !serviceKey || !webhookSecret || !apiKey) {
    // Non dettagliare quali variabili mancano (info-leak)
    console.error('[wh] Env vars obbligatorie mancanti — verificare secrets Supabase')
    return new Response('Internal Server Error', { status: 500 })
  }

  // ── 1. Leggi body RAW ─────────────────────────────────────────────────────
  // CRITICO: deve precedere qualsiasi .json() o .formData().
  // Se si legge prima come JSON, req.text() restituisce stringa vuota
  // e la firma HMAC non combacia mai.
  let rawBody: string
  try {
    rawBody = await req.text()
  } catch {
    return new Response('Bad Request: body non leggibile', { status: 400 })
  }

  // ── 2. Verifica firma HMAC-SHA256 + anti-replay ────────────────────────────
  const sigHeader = req.headers.get('Invoicetronic-Signature')
  if (!await verifyHmac(rawBody, sigHeader, webhookSecret)) {
    // 401 → Invoicetronic non ritenta per errori 4xx (config error lato loro)
    console.warn('[wh] Firma non valida o replay attack rilevato')
    return new Response('Unauthorized', { status: 401 })
  }

  // ── 3. Deserializza JSON ───────────────────────────────────────────────────
  let parsedEvent: WebhookEvent
  try {
    parsedEvent = JSON.parse(rawBody) as WebhookEvent
  } catch {
    return new Response('Bad Request: JSON non valido', { status: 400 })
  }

  const ev = normalizeWebhookEvent(parsedEvent)

  // ── 4. Filtra: processa solo "receive" con successo ────────────────────────
  // Altri eventi (send, status, ecc.) → ignora silenziosamente → 200.
  // Alcuni webhook usano `event=receive.add` invece di `endpoint=receive`.
  const isReceiveEvent = ev.endpoint === 'receive' || ev.eventName === 'receive.add'
  if (!isReceiveEvent || ev.success !== true) {
    return new Response('OK', { status: 200 })
  }

  if (ev.eventId == null || ev.resourceId == null) {
    console.warn('[wh] Webhook firmato ma senza event_id/resource_id validi')
    return new Response('OK', { status: 200 })
  }

  const eventId       = String(ev.eventId)
  const resourceId    = ev.resourceId
  const correlationId = (
    req.headers.get('X-Request-ID') ??
    req.headers.get('X-Correlation-ID') ??
    null
  )

  // Client Supabase con service_role (bypassa RLS — mai usare anon key qui)
  const db = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false },
  })

  // ── Stato accumulato durante l'elaborazione ────────────────────────────────
  let xmlContent:   string | null = null
  let xmlUrl:       string | null = null
  let xmlHash:      string | null = null
  let pivaRaw                     = 'UNKNOWN'     // sentinel: P.IVA non estratta
  let status                      = 'failed'      // default pessimistic
  let userId:       string | null = null
  let ristoranteId: string | null = null

  // Metadati non-PII da salvare in payload_meta (per query/debug senza XML)
  const meta: Record<string, unknown> = {
    resource_id:              resourceId,
    invoicetronic_event_id:   ev.eventId,
    invoicetronic_company_id: ev.companyId,
    date_time:                ev.dateTime,
    webhook_event:            ev.eventName,
    webhook_endpoint:         ev.endpoint,
  }

  // ── 5. Recupera dettaglio fattura da API Invoicetronic ─────────────────────
  try {
    const apiUrl  = `${INVOICETRONIC_API_BASE}/receive/${resourceId}?include_payload=true`
    // Basic auth: username=apiKey, password='' → base64("apiKey:")
    const authHdr = `Basic ${btoa(`${apiKey}:`)}`

    const apiResp = await safeFetch(
      apiUrl,
      { headers: { Authorization: authHdr, Accept: 'application/json' } },
      API_TIMEOUT_MS,
    )

    if (!apiResp.ok) {
      // API non disponibile o resource_id non trovato → failed per retry
      meta.api_error = `HTTP ${apiResp.status}`
      console.warn(`[wh] API Invoicetronic HTTP ${apiResp.status} per resource_id=${resourceId}`)
      // status rimane 'failed', pivaRaw rimane 'UNKNOWN'
    } else {
      const data = await apiResp.json() as ReceiveApiRecord

      // Nome file (non-PII, utile per identificare il documento nei log)
      if (typeof data.file_name === 'string') meta.nome_file = data.file_name

      // ── 6. Ottieni XML (base64 inline o URL remoto) ──────────────────────
      if (typeof data.payload === 'string' && data.payload.length > 0) {
        // API v1 corrente: l'XML arriva in `payload`, plain text o base64.
        const normalizedPayload = data.payload.trim()
        const encoding = typeof data.encoding === 'string' ? data.encoding : 'Xml'
        const decoded = encoding === 'Base64'
          ? base64ToUtf8(normalizedPayload)
          : normalizedPayload
        if (decoded.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
        xmlContent = decoded

      } else if (typeof data.xml_file === 'string' && data.xml_file.length > 0) {
        // Caso A: XML in base64 direttamente nel response JSON
        const decoded = base64ToUtf8(data.xml_file)
        if (decoded.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
        xmlContent = decoded
        // Mantieni xml_url se presente (utile per recupero futuro post-purge GDPR)
        if (typeof data.xml_url === 'string') xmlUrl = data.xml_url

      } else if (typeof data.xml_url === 'string' && data.xml_url.length > 0) {
        // Caso B: solo URL → download con SSRF check
        xmlUrl = data.xml_url
        const xmlResp = await safeFetch(xmlUrl, {}, XML_TIMEOUT_MS)
        if (!xmlResp.ok) throw new Error(`Download XML fallito: HTTP ${xmlResp.status}`)
        const text = await xmlResp.text()
        if (text.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
        xmlContent = text

      } else {
        // API risponde OK ma senza XML (caso anomalo, loggare per debug)
        meta.api_warning = 'API ok ma payload/xml_file/xml_url assenti nel response'
      }

      // ── 7. Estrazione dati dall'XML ────────────────────────────────────────
      if (xmlContent) {
        xmlHash = await sha256Hex(xmlContent)

        // P.IVA destinatario (necessaria per tenant lookup)
        const extracted = extractPivaDestinatario(xmlContent)
        if (extracted) {
          pivaRaw = extracted
          status  = 'pending' // ottimistico: se abbiamo P.IVA, proviamo a risolverla
        } else {
          meta.piva_warn = 'IdCodice/CodiceFiscale non trovato in CessionarioCommittente'
          // status rimane 'failed' — il worker non può fare nulla senza P.IVA
        }

        // Metadati documento (no PII: solo tipo, numero, data, importo, p.iva emittente)
        Object.assign(meta, extractDocMeta(xmlContent))
      }
    }
  } catch (err) {
    // Errori di rete, timeout, SSRF, dimensione XML, ecc.
    // Non loggare mai l'XML o dati PII — solo il tipo di errore
    const msg = err instanceof Error ? err.message : String(err)
    console.error(`[wh] Errore durante recupero fattura resource_id=${resourceId}: ${msg}`)
    meta.fetch_error = msg
    status = 'failed'
  }

  // ── 8. Lookup tenant: cerca P.IVA in tabella ristoranti ───────────────────
  // Solo se abbiamo una P.IVA valida e non siamo già in stato failed.
  // Se P.IVA non trovata → 'unknown_tenant' (mai scartare la fattura SDI).
  if (status === 'pending') {
    const { data: rist, error: ristErr } = await db
      .from('ristoranti')
      .select('user_id, id')
      .eq('partita_iva', pivaRaw)
      .eq('attivo', true)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle()

    if (ristErr) {
      console.error(`[wh] Errore lookup ristoranti: ${ristErr.message}`)
      // Continua con unknown_tenant per non perdere la fattura
    }

    if (rist) {
      userId       = rist.user_id as string
      ristoranteId = rist.id as string
      // status rimane 'pending' — il worker elaborerà normalmente
    } else {
      // P.IVA sconosciuta: salva il record, risolvi quando arriva il ristorante
      // via funzione SQL resolve_unknown_tenant(piva)
      status   = 'unknown_tenant'
      userId   = null
      ristoranteId = null
      console.info(`[wh] Tenant sconosciuto per piva=${pivaRaw} event_id=${eventId}`)
    }
  }

  // ── 9. INSERT idempotente in fatture_queue ─────────────────────────────────
  // upsert con ignoreDuplicates=true → ON CONFLICT (event_id) DO NOTHING
  // Re-invii dello stesso webhook da Invoicetronic vengono ignorati senza errore.
  const { error: dbErr } = await db
    .from('fatture_queue')
    .upsert(
      {
        event_id:       eventId,
        user_id:        userId,
        ristorante_id:  ristoranteId,
        piva_raw:       pivaRaw,
        xml_content:    xmlContent,
        xml_url:        xmlUrl,
        xml_hash:       xmlHash,
        payload_meta:   meta,
        source:         'invoicetronic',
        status,
        correlation_id: correlationId,
      },
      {
        onConflict:       'event_id',
        ignoreDuplicates: true, // ON CONFLICT (event_id) DO NOTHING
      },
    )

  if (dbErr) {
    // Errore DB reale (non duplicato — gestito da ignoreDuplicates).
    // Ritorno 500: Invoicetronic ritenterà e il record verrà salvato.
    console.error(`[wh] Errore INSERT fatture_queue event_id=${eventId}: ${dbErr.message}`)
    return new Response('Internal Server Error', { status: 500 })
  }

  console.info(`[wh] Accodato event_id=${eventId} status=${status} piva=${pivaRaw}`)

  // ── 10. Risponde SEMPRE 200 dopo insert ────────────────────────────────────
  // Status 2xx → Invoicetronic non ritenta.
  // I retry interni sono gestiti dal worker tramite fatture_queue.status.
  return new Response('OK', { status: 200 })
})
