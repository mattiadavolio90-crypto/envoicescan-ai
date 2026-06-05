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
const STORAGE_BUCKET        = 'ricavi-xls'
const ALLOWED_EXTENSIONS    = ['.xls', '.xlsx']
const BREVO_ATTACHMENT_BASE = 'https://api.brevo.com/v3/inbound/attachments'

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

function hourSlot(): string {
  const d = new Date(); d.setMinutes(0,0,0); return d.toISOString()
}

function isXls(att: BrevoAttachment): boolean {
  return ALLOWED_EXTENSIONS.some(ext => (att.Name ?? '').toLowerCase().endsWith(ext))
}

function buildPath(ristoranteId: string | null, filename: string): string {
  const yyyyMm   = new Date().toISOString().slice(0,7)
  const prefix   = ristoranteId ?? 'unknown'
  const safeName = filename.replace(/[^a-zA-Z0-9._\-]/g,'_').slice(0,128)
  return `${prefix}/${yyyyMm}/${safeName}`
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
    try {
      const resp = await fetch(
        `${BREVO_ATTACHMENT_BASE}/${encodeURIComponent(att.DownloadToken)}`,
        { headers: { 'api-key': brevoApiKey }, redirect: 'error' }
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

  // Verifica token
  const url           = new URL(req.url)
  const providedToken = url.searchParams.get('token') ?? req.headers.get('X-Oneflux-Webhook-Token') ?? ''
  if (!timingSafeEqual(providedToken, webhookToken)) {
    console.warn('[email-wh] Token non valido')
    return new Response('Unauthorized', { status: 401 })
  }

  let payload: InboundPayload
  try {
    payload = await req.json() as InboundPayload
  } catch (e) {
    console.error('[email-wh] JSON non valido:', (e as Error).message)
    return new Response('Bad Request', { status: 400 })
  }

  const items = payload.items ?? []
  if (items.length === 0) return new Response('OK', { status: 200 })

  const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } })

  for (const item of items) {
    const senderEmail = (item.From?.Address ?? '').trim().toLowerCase()
    const subject     = item.Subject ?? ''
    const xlsAtts     = (item.Attachments ?? []).filter(isXls)

    if (xlsAtts.length === 0) {
      console.info(`[email-wh] Nessun XLS da: ${senderEmail}`)
      continue
    }

    // Lookup mittente → ristorante
    const { data: senderMap } = await db
      .from('ricavi_email_sender_map')
      .select('ristorante_id, user_id:ristoranti(user_id)')
      .eq('email_sender', senderEmail)
      .eq('attivo', true)
      .limit(1)
      .maybeSingle()

    const ristoranteId = (senderMap?.ristorante_id as string | null) ?? null
    const userId       = (senderMap?.user_id as { user_id: string } | null)?.user_id ?? null
    const status       = ristoranteId ? 'pending' : 'unknown_sender'

    if (!ristoranteId) console.info(`[email-wh] Mittente sconosciuto: ${senderEmail}`)

    for (const att of xlsAtts) {
      const filename = att.Name ?? 'ricavi.xlsx'
      const idempotencyKey = await sha256Hex(`${senderEmail}|${subject}|${filename}|${hourSlot()}`)

      const attachmentBytes = await getAttachmentBytes(att, brevoApiKey)
      if (!attachmentBytes) continue

      // Upload Storage
      const path = buildPath(ristoranteId, filename)
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
