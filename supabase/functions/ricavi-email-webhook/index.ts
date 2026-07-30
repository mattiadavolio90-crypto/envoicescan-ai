// ═══════════════════════════════════════════════════════════════════════════════
// Supabase Edge Function: ricavi-email-webhook
// ═══════════════════════════════════════════════════════════════════════════════
// Riceve il webhook con allegati XLS ricavi da due sorgenti:
//   A) Google Apps Script (Gmail) → allegato inline come base64Content
//   B) Brevo Inbound (futuro) → allegato via DownloadToken
//
// Flusso:
//   POST /functions/v1/ricavi-email-webhook?token=...
//     → verifica token
//     → parsing payload { items: [{ From, Subject, Attachments }] }
//     → filtra allegati .xls/.xlsx
//     → ottieni bytes (base64 inline o download Brevo)
//     → upload su Supabase Storage (bucket: ricavi-xls)
//     → lookup mittente in ricavi_email_sender_map
//     → INSERT idempotente in ricavi_email_queue
//     → risponde 200 SEMPRE
//
// Env secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
//              BREVO_WEBHOOK_TOKEN, BREVO_API_KEY
// ═══════════════════════════════════════════════════════════════════════════════

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.4'

const MAX_ATTACHMENT_BYTES  = 10 * 1024 * 1024
const MAX_BODY_BYTES        = 25 * 1024 * 1024   // cap globale sul payload inbound
const MAX_ITEMS             = 20                  // max email per richiesta
const MAX_ATTACHMENTS       = 20                  // max allegati per email
const STORAGE_BUCKET        = 'ricavi-xls'
const ALLOWED_EXTENSIONS    = ['.xls', '.xlsx']
const BREVO_ATTACHMENT_BASE = 'https://api.brevo.com/v3/inbound/attachments'
const BREVO_FETCH_TIMEOUT_MS = 15_000

interface BrevoAddress   { Address?: string; Name?: string }
interface BrevoAttachment {
  Name?:          string
  ContentType?:   string
  ContentLength?: number
  DownloadToken?: string
  base64Content?: string   // usato da Gmail Apps Script
}
interface BrevoEmailItem {
  From?:        BrevoAddress
  Subject?:     string
  Attachments?: BrevoAttachment[]
}
interface InboundPayload { items?: BrevoEmailItem[] }

export function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder()
  const aB  = enc.encode(a), bB = enc.encode(b)
  const len = Math.max(aB.length, bB.length)
  let diff = aB.length ^ bB.length
  for (let i = 0; i < len; i++) diff |= (aB[i] ?? 0) ^ (bB[i] ?? 0)
  return diff === 0
}

async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('')
}

async function sha256HexBytes(bytes: Uint8Array): Promise<string> {
  const view = new Uint8Array(bytes)  // copia con ArrayBuffer concreto (no SharedArrayBuffer)
  const buf = await crypto.subtle.digest('SHA-256', view.buffer as ArrayBuffer)
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('')
}

export function isXls(att: BrevoAttachment): boolean {
  return ALLOWED_EXTENSIONS.some(ext => (att.Name ?? '').toLowerCase().endsWith(ext))
}

export class BodyTooLargeError extends Error {
  constructor() { super('body oltre il cap') }
}

// Legge il body contando i byte REALI, non quelli dichiarati in content-length
// (assente con Transfer-Encoding: chunked). Interrompe appena supera il cap:
// il resto dello stream non viene mai accumulato in memoria.
export async function readBodyCapped(req: Request, maxBytes: number): Promise<string> {
  if (!req.body) return ''
  const reader = req.body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      total += value.byteLength
      if (total > maxBytes) throw new BodyTooLargeError()
      chunks.push(value)
    }
  } finally {
    reader.releaseLock()
  }
  const merged = new Uint8Array(total)
  let offset = 0
  for (const c of chunks) { merged.set(c, offset); offset += c.byteLength }
  return new TextDecoder().decode(merged)
}

// Validazione magic bytes, come il resto della piattaforma fa per PDF/XML/P7M.
// L'estensione nel nome è scelta dal mittente: non prova nulla sul contenuto.
//   .xlsx = ZIP  → 50 4B 03 04 (anche 05 06 / 07 08 per archivi vuoti/spanned)
//   .xls  = OLE2 → D0 CF 11 E0 A1 B1 1A E1
export function hasXlsMagicBytes(bytes: Uint8Array): boolean {
  if (bytes.byteLength < 8) return false
  const zip = bytes[0] === 0x50 && bytes[1] === 0x4b &&
    ((bytes[2] === 0x03 && bytes[3] === 0x04) ||
     (bytes[2] === 0x05 && bytes[3] === 0x06) ||
     (bytes[2] === 0x07 && bytes[3] === 0x08))
  if (zip) return true
  const ole2 = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]
  return ole2.every((b, i) => bytes[i] === b)
}

// Alert Telegram non bloccante — stesso pattern di
// invoicetronic-webhook.notifyTelegramUnrecognizedEvent: silenzioso se i secret
// non sono configurati, mai propaga errori. Serve perché i due modi in cui i
// ricavi spariscono in silenzio (mittente sconosciuto, allegato non scaricabile)
// producono entrambi un 200 al producer: senza questo, l'unico segnale sarebbe
// una riga di console che nessuno legge.
export async function notifyTelegram(msg: string): Promise<void> {
  const token  = Deno.env.get('TELEGRAM_BOT_TOKEN')
  const chatId = Deno.env.get('TELEGRAM_CHAT_ID')
  if (!token || !chatId) return

  try {
    const ac = new AbortController()
    const timer = setTimeout(() => ac.abort(), 5000)
    try {
      await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ chat_id: chatId, text: msg }),
        signal:  ac.signal,
      })
    } finally {
      clearTimeout(timer)
    }
  } catch (err) {
    console.warn(`[email-wh] notifica Telegram fallita (non bloccante): ${err instanceof Error ? err.message : String(err)}`)
  }
}

// Registra un allegato non importabile come 'failed' invece di scartarlo in
// silenzio. La chiave include il motivo, così un allegato che prima falliva il
// download e poi i magic bytes produce due righe distinte e non si sovrascrivono.
// deno-lint-ignore no-explicit-any
async function registraFallimento(
  db: any, senderEmail: string, subject: string, filename: string,
  ristoranteId: string | null, userId: string | null,
  motivo: string, lastError: string,
): Promise<void> {
  const key = await sha256Hex(`${senderEmail}|${filename}|${motivo}|${subject}`)
  const { error } = await db
    .from('ricavi_email_queue')
    .upsert(
      { idempotency_key: key, email_sender: senderEmail,
        email_subject: subject || null, attachment_name: filename,
        storage_path: null, ristorante_id: ristoranteId,
        user_id: userId, status: 'failed', last_error: lastError },
      { onConflict: 'idempotency_key', ignoreDuplicates: true }
    )
  if (error) console.error(`[email-wh] DB error su riga failed (${motivo}): ${error.message}`)
}

export function buildPath(ristoranteId: string | null, filename: string, idempotencyKey: string): string {
  const yyyyMm   = new Date().toISOString().slice(0,7)
  const prefix   = ristoranteId ?? 'unknown'
  const safeName = filename.replace(/[^a-zA-Z0-9._\-]/g,'_').slice(0,128)
  return `${prefix}/${yyyyMm}/${idempotencyKey.slice(0,16)}_${safeName}`
}

export async function getAttachmentBytes(
  att: BrevoAttachment,
  brevoApiKey: string
): Promise<Uint8Array | null> {
  // Caso A: base64 inline — inviato da Gmail Apps Script
  if (att.base64Content && att.base64Content.length > 0) {
    try {
      const bin = atob(att.base64Content)
      if (bin.length > MAX_ATTACHMENT_BYTES) {
        console.warn(`[email-wh] Allegato troppo grande: ${bin.length}`)
        return null
      }
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      return bytes
    } catch (e) {
      console.error(`[email-wh] Decode base64:`, (e as Error).message)
      return null
    }
  }

  // Caso B: DownloadToken Brevo
  if (att.DownloadToken) {
    // Fail-closed esplicito: senza api-key la fetch tornerebbe 401 → null →
    // `continue` muto → nessuna riga in coda, 200 al producer, ricavi spariti
    // senza un solo segnale. Distinguiamo il "non configurato" dal "download
    // fallito" così il chiamante può scriverlo in coda invece di ignorarlo.
    if (!brevoApiKey) {
      console.error('[email-wh] BREVO_API_KEY assente: impossibile scaricare allegato via DownloadToken')
      return null
    }
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), BREVO_FETCH_TIMEOUT_MS)
    try {
      const resp = await fetch(
        `${BREVO_ATTACHMENT_BASE}/${encodeURIComponent(att.DownloadToken)}`,
        { headers: { 'api-key': brevoApiKey }, redirect: 'error', signal: ctrl.signal }
      )
      if (!resp.ok) {
        console.error(`[email-wh] Download Brevo HTTP ${resp.status}`)
        return null
      }
      const buf = await resp.arrayBuffer()
      if (buf.byteLength > MAX_ATTACHMENT_BYTES) {
        console.warn(`[email-wh] Allegato troppo grande: ${buf.byteLength}`)
        return null
      }
      return new Uint8Array(buf)
    } catch (e) {
      console.error(`[email-wh] Download Brevo:`, (e as Error).message)
      return null
    } finally {
      clearTimeout(timer)
    }
  }

  console.warn(`[email-wh] Allegato senza base64Content né DownloadToken`)
  return null
}

export const handler = async (req: Request): Promise<Response> => {
  if (req.method === 'GET')  return new Response('OK', { status: 200 })
  if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 })

  const supabaseUrl  = Deno.env.get('SUPABASE_URL')              ?? ''
  const serviceKey   = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
  const webhookToken = Deno.env.get('BREVO_WEBHOOK_TOKEN')       ?? ''
  const brevoApiKey  = Deno.env.get('BREVO_API_KEY')             ?? ''

  if (!supabaseUrl || !serviceKey || !webhookToken) {
    console.error('[email-wh] Env vars mancanti')
    return new Response('Internal Server Error', { status: 500 })
  }

  // Verifica token. Preferire l'header X-Oneflux-Webhook-Token: gli URL (e quindi
  // la querystring) finiscono nei log di rete/proxy molto piu' dei body/header.
  // La querystring resta accettata per retrocompatibilita' col producer attuale.
  const url           = new URL(req.url)
  const providedToken = req.headers.get('X-Oneflux-Webhook-Token') ?? url.searchParams.get('token') ?? ''
  if (webhookToken.length < 16 || !timingSafeEqual(providedToken, webhookToken)) {
    console.warn('[email-wh] Token non valido')
    return new Response('Unauthorized', { status: 401 })
  }

  // Body cap in DUE fasi (anti-DoS).
  // Fase 1 — scorciatoia sull'header: se il producer dichiara già troppo, tagliamo
  // corto senza leggere niente.
  const contentLength = Number(req.headers.get('content-length') ?? '0')
  if (contentLength > MAX_BODY_BYTES) {
    console.warn(`[email-wh] Body troppo grande (dichiarato): ${contentLength}`)
    return new Response('Payload Too Large', { status: 413 })
  }

  // Fase 2 — cap REALE sui byte letti. L'header da solo non è una difesa:
  // con Transfer-Encoding: chunked `content-length` è assente (→ 0, passa il
  // check) e il body può essere arbitrariamente grande. Qui contiamo davvero e
  // interrompiamo appena si supera la soglia, così non si riempie la memoria.
  let rawBody: string
  try {
    rawBody = await readBodyCapped(req, MAX_BODY_BYTES)
  } catch (e) {
    if (e instanceof BodyTooLargeError) {
      console.warn('[email-wh] Body troppo grande (letto in streaming)')
      return new Response('Payload Too Large', { status: 413 })
    }
    console.error('[email-wh] Body non leggibile:', (e as Error).message)
    return new Response('Bad Request', { status: 400 })
  }

  let payload: InboundPayload
  try {
    payload = JSON.parse(rawBody) as InboundPayload
  } catch (e) {
    console.error('[email-wh] JSON non valido:', (e as Error).message)
    return new Response('Bad Request', { status: 400 })
  }

  const items = (payload.items ?? []).slice(0, MAX_ITEMS)
  if (items.length === 0) return new Response('OK', { status: 200 })

  const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } })

  // Errori DB accumulati: il ciclo non si interrompe, l'esito si decide alla fine.
  const erroriDb: string[] = []

  for (const item of items) {
    const senderEmail = (item.From?.Address ?? '').trim().toLowerCase()
    const subject     = item.Subject ?? ''
    const xlsAtts     = (item.Attachments ?? []).filter(isXls).slice(0, MAX_ATTACHMENTS)

    if (xlsAtts.length === 0) {
      console.info(`[email-wh] Nessun XLS da: ${senderEmail}`)
      continue
    }

    // Lookup mittente → ristorante
    const { data: senderMap } = await db
      .from('ricavi_email_sender_map')
      .select('ristorante_id')
      .eq('email_sender', senderEmail)
      .eq('attivo', true)
      .limit(1)
      .maybeSingle()

    const ristoranteId = (senderMap?.ristorante_id as string | null) ?? null

    // user_id derivato con lookup esplicito su ristoranti (il join PostgREST era
    // fragile: poteva tornare null silenziosamente e i tipi non combaciavano).
    let userId: string | null = null
    if (ristoranteId) {
      const { data: rist } = await db
        .from('ristoranti')
        .select('user_id')
        .eq('id', ristoranteId)
        .limit(1)
        .maybeSingle()
      userId = (rist?.user_id as string | null) ?? null
    }
    const status = ristoranteId ? 'pending' : 'unknown_sender'

    // 'unknown_sender' NON è claimabile da claim_ricavi_email_batch (claima solo
    // 'pending' e 'failed'): la riga finisce in una coda che nessuno guarda. È lo
    // scenario del cliente che cambia l'email del gestionale — i ricavi smettono
    // di arrivare e nessuno se ne accorge. L'alert è l'unico segnale attivo.
    if (!ristoranteId) {
      console.info(`[email-wh] Mittente sconosciuto: ${senderEmail}`)
      await notifyTelegram([
        '⚠️ Ricavi email: mittente sconosciuto',
        `Da: ${senderEmail}`,
        `Oggetto: ${subject || '—'}`,
        `Allegati XLS: ${xlsAtts.length}`,
        'La riga resta in ricavi_email_queue status=unknown_sender e NON viene',
        'lavorata finché il mittente non è mappato in ricavi_email_sender_map.',
      ].join('\n'))
    }

    for (const att of xlsAtts) {
      const filename = att.Name ?? 'ricavi.xlsx'

      const attachmentBytes = await getAttachmentBytes(att, brevoApiKey)
      // Allegato non recuperabile (base64 corrotto, 401 Brevo, timeout, api-key
      // assente). Prima qui c'era un `continue` muto: nessuna riga, nessun
      // errore, 200 al producer → ricavi persi in silenzio. Ora lo registriamo
      // come 'failed' così è visibile, ri-claimabile e conteggiabile.
      if (!attachmentBytes) {
        console.error(`[email-wh] Allegato non recuperabile: ${filename} da ${senderEmail}`)
        await registraFallimento(
          db, senderEmail, subject, filename, ristoranteId, userId,
          'fetch-failed',
          'allegato non recuperabile (base64 non valido, download Brevo fallito o BREVO_API_KEY assente)',
        )
        await notifyTelegram([
          '⚠️ Ricavi email: allegato non recuperabile',
          `Da: ${senderEmail}`,
          `File: ${filename}`,
          'Registrato in ricavi_email_queue status=failed.',
        ].join('\n'))
        continue
      }

      // Magic bytes: l'estensione la scrive il mittente, i primi byte no. Un file
      // che non è né ZIP (xlsx) né OLE2 (xls) non è un foglio: lo registriamo
      // 'failed' invece di caricarlo su Storage e farlo esplodere nel worker.
      if (!hasXlsMagicBytes(attachmentBytes)) {
        console.error(`[email-wh] Magic bytes non XLS/XLSX: ${filename} da ${senderEmail}`)
        await registraFallimento(
          db, senderEmail, subject, filename, ristoranteId, userId,
          'magic-bytes',
          'contenuto non riconosciuto come XLS/XLSX (magic bytes non ZIP né OLE2)',
        )
        await notifyTelegram([
          '⚠️ Ricavi email: allegato non è un foglio XLS/XLSX',
          `Da: ${senderEmail}`,
          `File: ${filename}`,
          'Registrato in ricavi_email_queue status=failed.',
        ].join('\n'))
        continue
      }

      // Idempotenza sul CONTENUTO dell'allegato (non sull'ora): lo stesso file
      // ri-consegnato a cavallo dell'ora non genera piu' un doppio import.
      const contentHash = await sha256HexBytes(attachmentBytes)
      const idempotencyKey = await sha256Hex(`${senderEmail}|${filename}|${contentHash}`)

      // Upload Storage: path univoco per idempotency key, cosi' due email diverse
      // con allegato omonimo nello stesso mese non si sovrascrivono.
      const path = buildPath(ristoranteId, filename, idempotencyKey)
      let savedPath: string | null = null
      try {
        const { error: uploadErr } = await db.storage
          .from(STORAGE_BUCKET)
          .upload(path, attachmentBytes, {
            contentType: att.ContentType ?? 'application/octet-stream',
            upsert: true,
          })
        if (uploadErr) console.error(`[email-wh] Upload Storage: ${uploadErr.message}`)
        else savedPath = path
      } catch (e) {
        console.error(`[email-wh] Eccezione upload:`, (e as Error).message)
      }

      // INSERT coda
      const { error: dbErr } = await db
        .from('ricavi_email_queue')
        .upsert(
          { idempotency_key: idempotencyKey, email_sender: senderEmail,
            email_subject: subject || null, attachment_name: filename,
            storage_path: savedPath, ristorante_id: ristoranteId,
            user_id: userId, status },
          { onConflict: 'idempotency_key', ignoreDuplicates: true }
        )

      // Un errore DB su UN allegato non deve far perdere gli altri: prima qui
      // c'era un `return 500` immediato, che abbandonava il ciclo lasciando non
      // accodati gli allegati successivi (già scaricati) e le email successive.
      // Ora annotiamo e continuiamo; l'esito 500 lo diamo a fine ciclo, così il
      // producer ritenta e l'idempotency_key rende innocuo il ri-accodamento di
      // ciò che era già passato.
      if (dbErr) {
        console.error(`[email-wh] DB error su ${filename}: ${dbErr.message}`)
        erroriDb.push(`${filename}: ${dbErr.message}`)
        continue
      }

      console.info(`[email-wh] Accodato ${filename} da ${senderEmail} status=${status}`)
    }
  }

  if (erroriDb.length > 0) {
    await notifyTelegram([
      '🔴 Ricavi email: errori DB in accodamento',
      `${erroriDb.length} allegato/i non accodati:`,
      ...erroriDb.slice(0, 5),
      'Il producer riceve 500 e ritenta.',
    ].join('\n'))
    return new Response('Internal Server Error', { status: 500 })
  }

  return new Response('OK', { status: 200 })
}

// Avvia il server tranne quando importato da un test unitario — stesso fail-safe
// di invoicetronic-webhook: in produzione il modulo è l'entry point e DEVE
// servire, ci tiriamo indietro SOLO se un test imposta WEBHOOK_TEST_MODE=1.
if (Deno.env.get('WEBHOOK_TEST_MODE') !== '1') {
  Deno.serve(handler)
}
