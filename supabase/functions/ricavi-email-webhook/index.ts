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

function timingSafeEqual(a: string, b: string): boolean {
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

function isXls(att: BrevoAttachment): boolean {
  return ALLOWED_EXTENSIONS.some(ext => (att.Name ?? '').toLowerCase().endsWith(ext))
}

function buildPath(ristoranteId: string | null, filename: string, idempotencyKey: string): string {
  const yyyyMm   = new Date().toISOString().slice(0,7)
  const prefix   = ristoranteId ?? 'unknown'
  const safeName = filename.replace(/[^a-zA-Z0-9._\-]/g,'_').slice(0,128)
  return `${prefix}/${yyyyMm}/${idempotencyKey.slice(0,16)}_${safeName}`
}

async function getAttachmentBytes(
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

Deno.serve(async (req: Request): Promise<Response> => {
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

  // Body cap: rifiuta payload enormi PRIMA di leggerli in memoria (anti-DoS).
  const contentLength = Number(req.headers.get('content-length') ?? '0')
  if (contentLength > MAX_BODY_BYTES) {
    console.warn(`[email-wh] Body troppo grande: ${contentLength}`)
    return new Response('Payload Too Large', { status: 413 })
  }

  let payload: InboundPayload
  try {
    payload = await req.json() as InboundPayload
  } catch (e) {
    console.error('[email-wh] JSON non valido:', (e as Error).message)
    return new Response('Bad Request', { status: 400 })
  }

  const items = (payload.items ?? []).slice(0, MAX_ITEMS)
  if (items.length === 0) return new Response('OK', { status: 200 })

  const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } })

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

    if (!ristoranteId) console.info(`[email-wh] Mittente sconosciuto: ${senderEmail}`)

    for (const att of xlsAtts) {
      const filename = att.Name ?? 'ricavi.xlsx'

      const attachmentBytes = await getAttachmentBytes(att, brevoApiKey)
      if (!attachmentBytes) continue

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

      if (dbErr) {
        console.error(`[email-wh] DB error: ${dbErr.message}`)
        return new Response('Internal Server Error', { status: 500 })
      }

      console.info(`[email-wh] Accodato ${filename} da ${senderEmail} status=${status}`)
    }
  }

  return new Response('OK', { status: 200 })
})
