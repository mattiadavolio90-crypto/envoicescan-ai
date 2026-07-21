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

// Pinnato a versione esatta per stabilità supply-chain.
// Per upgrade: testare in staging prima di aggiornare in prod.
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.45.4'

// ─── Costanti ─────────────────────────────────────────────────────────────────

const INVOICETRONIC_API_BASE = 'https://api.invoicetronic.com/v1'

// SSRF whitelist: unici host da cui questo servizio può fare fetch
const ALLOWED_HOST_EXACT  = 'invoicetronic.com'
const ALLOWED_HOST_SUFFIX = '.invoicetronic.com'

const MAX_XML_BYTES      = 10 * 1024 * 1024 // 10 MB — protezione DoS storage
const REPLAY_WINDOW_SECS = 300              // 5 min — finestra anti-replay
const API_TIMEOUT_MS     = 10_000          // timeout chiamata API Invoicetronic (10s — coerente con XML, evita timeout spuri cross-cloud)
const XML_TIMEOUT_MS     = 15_000          // timeout download XML da URL (file fino a 10 MB su rete EU)

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

export interface NormalizedWebhookEvent {
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

export async function verifyHmac(
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

// ─── Utility: decodifica base64 → bytes grezzi ────────────────────────────────
// atob() produce latin-1 (1 char = 1 byte); ricostruiamo l'array di byte esatto.

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64)
  const buf = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
  return buf
}

// ─── Utility: decodifica base64 → stringa UTF-8 ───────────────────────────────
// serve TextDecoder per UTF-8 corretto (caratteri accentati in nomi/ragioni
// sociali nei file FatturaPA).

function base64ToUtf8(b64: string): string {
  return new TextDecoder('utf-8').decode(base64ToBytes(b64))
}

// ─── Utility: estrazione XML FatturaPA da busta P7M firmata (CAdES) ────────────
// Un file .xml.p7m è una struttura CMS/PKCS#7 (CAdES-BES) che INCAPSULA l'XML
// FatturaPA in chiaro (firma, non cifratura): l'XML è presente per intero, con
// attorno strati binari di firma/certificati che contengono byte nulli e sequenze
// non-UTF8. Decodificarlo direttamente come testo produce byte nulli che Postgres
// rifiuta nelle colonne text (causa dei 500 storici sulle fatture firmate).
//
// Strategia: individuiamo gli offset di BYTE di `<?xml … </…FatturaElettronica>`
// lavorando su una vista latin1 (1 byte = 1 char, nessuna perdita/rimappatura),
// poi ridecodifichiamo SOLO quella porzione come UTF-8. Robusto al prefisso di
// namespace variabile (ns0:, ns3:, p:, o assente) e a più occorrenze (prende
// l'ultima chiusura). Nessuna dipendenza da librerie ASN.1/CMS.
//
// Ritorna l'XML estratto, o null se la busta non contiene un XML FatturaPA
// riconoscibile (in tal caso il chiamante prosegue col fallback esistente).

// Sotto-caso CAdES: OCTET STRING "a chunk DER". In molte firme italiane l'XML NON
// è contiguo nella busta: è dentro un Constructed OCTET STRING (tag 0x24, lunghezza
// indefinita 0x80) spezzato in più chunk primitivi `0x04 <len> <dati>`. Lo slice
// grezzo `<?xml … </FatturaElettronica>` di sotto include allora gli header DER
// intermedi (tipicamente `0x04 <len>` ogni ~1004 byte) DENTRO i tag → XML non
// well-formed che il worker poi rifiuta (byte di controllo a metà elemento).
//
// Questa funzione riassembla i chunk droppando gli header DER — porta di Deno del
// metodo `_estrai_xml_con_der_scan` del worker Python (services/invoice_service.py),
// che gestiva già correttamente il caso. Ritorna i byte XML riassemblati, o null se
// la busta non è "a chunk DER" (allora vale lo slice contiguo).
function reassembleDerChunks(bytes: Uint8Array): Uint8Array | null {
  // Trova il primo <?xml (o BOM che lo precede).
  let xmlPos = indexOfBytes(bytes, [0x3c, 0x3f, 0x78, 0x6d, 0x6c]) // "<?xml"
  if (xmlPos < 0) {
    const bomPos = indexOfBytes(bytes, [0xef, 0xbb, 0xbf])
    if (bomPos < 0) return null
    xmlPos = bomPos
  }

  // Cerca il Constructed OCTET STRING (0x24 0x80) subito prima di <?xml.
  let pos = -1
  for (let i = xmlPos - 1; i >= Math.max(0, xmlPos - 20); i--) {
    if (bytes[i] === 0x80 && i > 0 && bytes[i - 1] === 0x24) {
      pos = i + 1
      break
    }
  }
  if (pos < 0) return null

  // Leggi chunk per chunk (0x04 <len> <dati>) fino a 0x00 0x00 (end-of-contents).
  const parts: Uint8Array[] = []
  let chunks = 0
  while (pos < bytes.length - 2) {
    if (bytes[pos] === 0x00 && bytes[pos + 1] === 0x00) break
    if (bytes[pos] !== 0x04) break

    const lb = bytes[pos + 1]
    let chunkLen: number
    let headerLen: number
    if (lb < 0x80) {
      chunkLen = lb
      headerLen = 2
    } else if (lb === 0x81) {
      chunkLen = bytes[pos + 2]
      headerLen = 3
    } else if (lb === 0x82) {
      chunkLen = (bytes[pos + 2] << 8) | bytes[pos + 3]
      headerLen = 4
    } else if (lb === 0x83) {
      chunkLen = (bytes[pos + 2] << 16) | (bytes[pos + 3] << 8) | bytes[pos + 4]
      headerLen = 5
    } else {
      break
    }

    if (pos + headerLen + chunkLen > bytes.length) break

    parts.push(bytes.subarray(pos + headerLen, pos + headerLen + chunkLen))
    pos += headerLen + chunkLen
    chunks++
  }

  if (chunks <= 1) return null

  // Concatena i chunk.
  let total = 0
  for (const p of parts) total += p.length
  const out = new Uint8Array(total)
  let off = 0
  for (const p of parts) {
    out.set(p, off)
    off += p.length
  }
  if (indexOfBytes(out, [0x46, 0x61, 0x74, 0x74, 0x75, 0x72, 0x61]) < 0) return null // "Fattura"
  return out
}

// Ricerca di una sottosequenza di byte (piccolo helper: niente dipendenze).
function indexOfBytes(hay: Uint8Array, needle: number[]): number {
  outer:
  for (let i = 0; i + needle.length <= hay.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (hay[i + j] !== needle[j]) continue outer
    }
    return i
  }
  return -1
}

// Ritaglia dai byte XML riassemblati l'intervallo `<?xml … </…FatturaElettronica>`
// e verifica che non restino byte di controllo invalidi per XML (0x00-0x08, 0x0B,
// 0x0C, 0x0E-0x1F): se ne restano, l'estrazione è sporca → si scarta e si prova
// lo slice contiguo. Speculare al controllo `bad_bytes` del worker Python.
function ritagliaXmlPulito(bytes: Uint8Array): string | null {
  let latin1 = ''
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) {
    latin1 += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  }
  const start = latin1.indexOf('<?xml')
  if (start < 0) return null

  const endRe = /<\/(?:[\w.-]+:)?FatturaElettronica\s*>/g
  let lastEnd = -1
  let m: RegExpExecArray | null
  while ((m = endRe.exec(latin1)) !== null) {
    lastEnd = m.index + m[0].length
  }
  if (lastEnd < 0) return null

  const slice = bytes.subarray(start, lastEnd)
  for (const b of slice) {
    if (b < 32 && b !== 9 && b !== 10 && b !== 13) return null // control char invalido
  }
  return new TextDecoder('utf-8').decode(slice)
}

export function extractXmlFromP7m(bytes: Uint8Array): string | null {
  // 1° tentativo: riassemblaggio chunk DER (p7m "a chunk OCTET STRING"). Se la
  // busta è di questo tipo, lo slice grezzo qui sotto produrrebbe XML corrotto.
  const reassembled = reassembleDerChunks(bytes)
  if (reassembled) {
    const xml = ritagliaXmlPulito(reassembled)
    if (xml) return xml
  }

  // 2° tentativo (busta contigua "classica"): l'XML è già intero nella busta, basta
  // ritagliare l'intervallo di byte. Vista latin1 a blocchi (evita "Maximum call
  // stack" su fromCharCode.apply con input grandi).
  let latin1 = ''
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) {
    latin1 += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  }

  const start = latin1.indexOf('<?xml')
  if (start < 0) return null

  const endRe = /<\/(?:[\w.-]+:)?FatturaElettronica\s*>/g
  let lastEnd = -1
  let m: RegExpExecArray | null
  while ((m = endRe.exec(latin1)) !== null) {
    lastEnd = m.index + m[0].length
  }
  if (lastEnd < 0) return null

  return new TextDecoder('utf-8').decode(bytes.subarray(start, lastEnd))
}

// ─── Utility: byte grezzi → XML FatturaPA (gestisce XML puro e P7M firmato) ────
// Rilevamento sul CONTENUTO (prologo "<?xml" + assenza di byte nulli), non sul
// nome file: così copre anche P7M annunciati con `encoding: Xml`. Se non è XML
// pulito, tenta l'estrazione dalla busta P7M; se anche quella fallisce, torna
// alla decodifica diretta (il chiamante applica i suoi guardrail).

export function bytesToXml(bytes: Uint8Array): string {
  const looksLikeCleanXml =
    bytes.length >= 5 &&
    bytes[0] === 0x3c && bytes[1] === 0x3f &&   // "<?"
    !bytes.includes(0x00)

  if (looksLikeCleanXml) return new TextDecoder('utf-8').decode(bytes)

  return extractXmlFromP7m(bytes) ?? new TextDecoder('utf-8').decode(bytes)
}

// ─── Utility: decodifica payload fattura (XML semplice o P7M firmato) ──────────
// Wrapper su bytesToXml che prima porta il payload a byte grezzi in base
// all'encoding dichiarato dall'API (Base64 vs testo).

function decodePayloadToXml(rawPayload: string, encoding: string): string {
  const bytes = encoding === 'Base64'
    ? base64ToBytes(rawPayload)
    : new TextEncoder().encode(rawPayload)
  return bytesToXml(bytes)
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

// ─── Riconoscimento tipo evento webhook ───────────────────────────────────────
// Un match troppo stretto (`endpoint === 'receive'`) ha causato lo scarto
// silenzioso di fatture reali con 200 senza salvarle (bug 21/7/2026): il payload
// live di Invoicetronic porta in `endpoint` l'API endpoint effettivo, che può
// essere "receive", "receive/86940", "/v1/receive", ecc. — non sempre il secco
// "receive" usato nei test. Riconosciamo quindi qualsiasi endpoint che contenga
// il segmento "receive", più l'alias storico `event` che inizia per "receive".

export function isReceiveWebhook(ev: NormalizedWebhookEvent): boolean {
  const endpointMatch = ev.endpoint != null && /(^|[^a-z])receive([^a-z]|$)/.test(ev.endpoint)
  const eventMatch    = ev.eventName != null && ev.eventName.startsWith('receive')
  return endpointMatch || eventMatch
}

// Evento sicuramente NON di ricezione (send/status/…): endpoint valorizzato che
// non menziona "receive" e nessun eventName di ricezione → ignorabile senza
// traccia. Distinto da "receive non riconosciuto per naming anomalo", che invece
// va registrato dalla rete di sicurezza (mai perso in silenzio).
export function isOtherWebhook(ev: NormalizedWebhookEvent): boolean {
  return ev.endpoint != null &&
    !/receive/.test(ev.endpoint) &&
    (ev.eventName == null || !ev.eventName.startsWith('receive'))
}

// ─── Utility: estrazione P.IVA del destinatario da XML FatturaPA ──────────────
// Cerca nel blocco <CessionarioCommittente> (destinatario della fattura):
//   1° tentativo: <IdCodice>  → P.IVA italiana (11 cifre) o estera
//   2° tentativo: <CodiceFiscale> → CF persona fisica

// Normalizza una P.IVA italiana per il match col DB (dove e' salvata come 11 cifre
// pure). Allineata a utils/piva_validator.normalizza_piva: rimuove prefisso IT e
// caratteri non numerici, MA solo se il risultato e' esattamente 11 cifre. Per
// P.IVA estere o codici diversi ritorna il valore originale invariato (no-op sui
// dati attuali, gia' 11 cifre pure).
function normalizePivaForMatch(raw: string): string {
  const stripped = raw.replace(/^IT/i, '').replace(/[^0-9A-Za-z]/g, '')
  const digitsOnly = stripped.replace(/[^0-9]/g, '')
  return digitsOnly.length === 11 ? digitsOnly : raw
}

function extractPivaDestinatario(xml: string): string | null {
  // Isola il blocco CessionarioCommittente per evitare falsi match
  const blockMatch = xml.match(
    /<CessionarioCommittente\b[^>]*>([\s\S]*?)<\/CessionarioCommittente>/,
  )
  if (!blockMatch) return null
  const block = blockMatch[1]

  // \s ammesso DENTRO la cattura: alcuni gestionali inseriscono spazi nella P.IVA.
  const idCodice = block.match(/<IdCodice>\s*([A-Z0-9\s]{1,28})\s*<\/IdCodice>/i)?.[1]?.trim()
  if (idCodice) return normalizePivaForMatch(idCodice)

  const cf = block.match(/<CodiceFiscale>\s*([A-Z0-9]{11,16})\s*<\/CodiceFiscale>/i)?.[1]?.trim()
  if (cf) return cf

  return null
}

// ─── Utility: estrazione indirizzo del destinatario da XML FatturaPA ──────────
// Serve SOLO per i clienti multi-sede (più ristoranti con la stessa P.IVA): l'indirizzo
// del CessionarioCommittente.Sede distingue a quale sede appartiene la fattura.
// Nei dati FatturaPA il blocco è <Sede> con <Indirizzo>/<NumeroCivico>/<CAP>/<Comune>.

export function extractIndirizzoDestinatario(xml: string): string | null {
  const blockMatch = xml.match(
    /<CessionarioCommittente\b[^>]*>([\s\S]*?)<\/CessionarioCommittente>/,
  )
  if (!blockMatch) return null
  const block = blockMatch[1]

  // Isola la <Sede> per non pescare per errore altri indirizzi (es. StabileOrganizzazione)
  const sede = block.match(/<Sede\b[^>]*>([\s\S]*?)<\/Sede>/)?.[1] ?? block

  const tag = (n: string): string =>
    sede.match(new RegExp(`<${n}>\\s*([^<]+?)\\s*<\\/${n}>`, 'i'))?.[1]?.trim() ?? ''

  const indirizzo = tag('Indirizzo')
  const civico    = tag('NumeroCivico')
  const cap       = tag('CAP')
  const comune    = tag('Comune')

  const joined = [indirizzo, civico, cap, comune].filter(Boolean).join(' ').trim()
  return joined.length > 0 ? joined : null
}

// ─── Utility: normalizzazione indirizzo (gemella della SQL normalizza_indirizzo_match) ─
// DEVE restare allineata a public.normalizza_indirizzo_match() (migration
// 20260611140000_multi_sede_routing): stesse abbreviazioni, stesso output, così
// l'indirizzo della fattura e quello salvato su ristoranti.indirizzo_match sono
// confrontabili sulla stessa base.

export function normalizeIndirizzo(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/\bv\.?le\b/g, 'viale')
    .replace(/\bc\.?so\b/g, 'corso')
    .replace(/\bp\.?(zza|za)\b/g, 'piazza')
    .replace(/\bv\.?\b/g, 'via')
    .replace(/\bstr\.?\b/g, 'strada')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

// ─── Utility: punteggio di similarità fra due indirizzi normalizzati ──────────
// Similarità di Dice sui token (parole): |intersezione*2| / (|A|+|B|).
// Robusta a parole in più/in meno e all'ordine; ritorna [0..1].
// Scelta su token (non bigrammi di caratteri) perché le sedi hanno indirizzi
// COMPLETAMENTE diversi (via/civico/comune distinti) → il segnale forte è quante
// parole-chiave coincidono, non la somiglianza ortografica.

export function indirizzoSimilarity(a: string, b: string): number {
  const ta = new Set(a.split(' ').filter(Boolean))
  const tb = new Set(b.split(' ').filter(Boolean))
  if (ta.size === 0 || tb.size === 0) return 0
  let inter = 0
  for (const t of ta) if (tb.has(t)) inter++
  return (2 * inter) / (ta.size + tb.size)
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

// ─── Utility: scarica il payload fattura da Invoicetronic ed estrai l'XML ─────
// Condivisa dal flusso webhook e dalla modalità reprocess. Ritorna l'XML estratto
// (con la logica p7m corretta, incluso chunked-DER) o lancia in caso di errore.
export async function fetchXmlForResource(
  resourceId: number | string,
  apiKey: string,
): Promise<{ xmlContent: string; xmlUrl: string | null }> {
  const apiUrl  = `${INVOICETRONIC_API_BASE}/receive/${resourceId}?include_payload=true`
  const authHdr = `Basic ${btoa(`${apiKey}:`)}`
  const apiResp = await safeFetch(
    apiUrl,
    { headers: { Authorization: authHdr, Accept: 'application/json' } },
    API_TIMEOUT_MS,
  )
  if (!apiResp.ok) throw new Error(`API Invoicetronic HTTP ${apiResp.status}`)

  const data = await apiResp.json() as ReceiveApiRecord
  let xmlContent: string | null = null
  let xmlUrl: string | null = null

  if (typeof data.payload === 'string' && data.payload.length > 0) {
    const encoding = typeof data.encoding === 'string' ? data.encoding : 'Xml'
    xmlContent = decodePayloadToXml(data.payload.trim(), encoding)
  } else if (typeof data.xml_file === 'string' && data.xml_file.length > 0) {
    xmlContent = decodePayloadToXml(data.xml_file, 'Base64')
    if (typeof data.xml_url === 'string') xmlUrl = data.xml_url
  } else if (typeof data.xml_url === 'string' && data.xml_url.length > 0) {
    xmlUrl = data.xml_url
    const xmlResp = await safeFetch(xmlUrl, {}, XML_TIMEOUT_MS)
    if (!xmlResp.ok) throw new Error(`Download XML fallito: HTTP ${xmlResp.status}`)
    const rawBytes = new Uint8Array(await xmlResp.arrayBuffer())
    if (rawBytes.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
    xmlContent = bytesToXml(rawBytes)
  }

  if (!xmlContent) throw new Error('API ok ma payload/xml_file/xml_url assenti')
  if (xmlContent.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
  if (xmlContent.includes('\x00')) xmlContent = xmlContent.replace(/\x00/g, '')
  return { xmlContent, xmlUrl }
}

// ─── Modalità reprocess (riparazione righe già in coda) ────────────────────────
// Uso: POST firmato HMAC con body { "reprocess_queue_ids": [id, …] }.
// Ri-scarica ogni riga dalla sua resource_id e RISCRIVE xml_content/xml_hash/
// indirizzo con l'estrazione p7m corretta — SENZA toccarne lo status (una riga
// 'da_assegnare' resta 'da_assegnare', solo con XML ora leggibile). Serve a
// recuperare le fatture salvate con XML corrotto PRIMA del fix chunked-DER.
// Non è un percorso Invoicetronic: è un canale di manutenzione protetto dallo
// stesso secret del webhook (nessun nuovo secret, nessun endpoint pubblico in più).
// deno-lint-ignore no-explicit-any
async function handleReprocess(ids: unknown, db: any, apiKey: string): Promise<Response> {
  if (!Array.isArray(ids) || ids.length === 0 || ids.length > 50) {
    return new Response(JSON.stringify({ error: 'reprocess_queue_ids: array 1..50 richiesto' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    })
  }

  const results: Array<Record<string, unknown>> = []
  for (const rawId of ids) {
    const id = typeof rawId === 'number' ? rawId : parseInt(String(rawId), 10)
    if (!Number.isFinite(id)) { results.push({ id: rawId, ok: false, error: 'id non valido' }); continue }

    const { data: row, error: selErr } = await db
      .from('fatture_queue')
      .select('id, status, payload_meta')
      .eq('id', id)
      .maybeSingle()

    if (selErr)  { results.push({ id, ok: false, error: `select: ${selErr.message}` }); continue }
    if (!row)    { results.push({ id, ok: false, error: 'riga non trovata' }); continue }

    const resourceId = (row.payload_meta ?? {}).resource_id
    if (resourceId == null) { results.push({ id, ok: false, error: 'resource_id assente in payload_meta' }); continue }

    try {
      const { xmlContent, xmlUrl } = await fetchXmlForResource(resourceId, apiKey)
      const xmlHash = await sha256Hex(xmlContent)
      const indirizzo = extractIndirizzoDestinatario(xmlContent)
      const meta = { ...(row.payload_meta ?? {}), reprocessed_at: new Date().toISOString() }
      if (indirizzo) meta.indirizzo_destinatario = indirizzo

      const { error: updErr } = await db
        .from('fatture_queue')
        .update({ xml_content: xmlContent, xml_url: xmlUrl, xml_hash: xmlHash, payload_meta: meta })
        .eq('id', id)

      if (updErr) { results.push({ id, ok: false, error: `update: ${updErr.message}` }); continue }
      results.push({ id, ok: true, xml_len: xmlContent.length, status: row.status })
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      results.push({ id, ok: false, error: msg })
    }
  }

  console.info(`[wh] reprocess completato: ${results.filter(r => r.ok).length}/${results.length} ok`)
  return new Response(JSON.stringify({ reprocessed: results }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })
}

// ─── Handler principale ───────────────────────────────────────────────────────

export const handler = async (req: Request): Promise<Response> => {
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

  // ── 2a. Modalità reprocess (manutenzione, NON è un evento Invoicetronic) ────
  // Canale di riparazione delle righe già in coda con xml_content corrotto (bug
  // p7m chunked-DER pre-fix). NON usa l'HMAC del webhook (secret detenuto da
  // Invoicetronic): si autentica con la service_role key via header X-Reprocess-Key,
  // confrontata timing-safe. Riconosciuto PRIMA della verifica HMAC così può
  // funzionare senza conoscere il segreto di firma dei webhook reali.
  const reprocessKey = req.headers.get('X-Reprocess-Key')
  if (reprocessKey) {
    if (!timingSafeEqual(reprocessKey, serviceKey)) {
      console.warn('[wh] reprocess: X-Reprocess-Key non valida')
      return new Response('Unauthorized', { status: 401 })
    }
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(rawBody) as Record<string, unknown>
    } catch {
      return new Response('Bad Request: JSON non valido', { status: 400 })
    }
    const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } })
    return await handleReprocess(parsed['reprocess_queue_ids'], db, apiKey)
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
  const isReceiveEvent   = isReceiveWebhook(ev)
  const looksLikeOther   = isOtherWebhook(ev)

  // Altri eventi legittimi (send/status/…), con firma valida ma NON di ricezione:
  // ignorabili senza traccia, non sono fatture in ingresso.
  if (looksLikeOther && ev.success === true) {
    return new Response('OK', { status: 200 })
  }

  // ── 4b. Rete di sicurezza: MAI perdere una fattura firmata in silenzio ─────
  // Se siamo qui l'HMAC è già valido → l'evento viene DAVVERO da Invoicetronic.
  // Se non lo riconosciamo come "receive" valido, o mancano i dati minimi per
  // scaricare l'XML, NON rispondiamo 200-e-via (che perderebbe la fattura per
  // sempre: Invoicetronic non ritenta sui 2xx). La registriamo invece in coda
  // con status 'failed' + il payload NON-PII completo in payload_meta, così
  // resta visibile negli avvisi Admin e recuperabile a mano. Il campo
  // `unrecognized_event` è la traccia per un fix mirato del parser.
  const missingCore = ev.eventId == null || ev.resourceId == null
  if (!isReceiveEvent || ev.success !== true || missingCore) {
    const reason = !isReceiveEvent
      ? 'endpoint/event non riconosciuto come receive'
      : ev.success !== true
        ? 'success != true'
        : 'event_id o resource_id mancante'
    console.error(
      `[wh] Evento firmato NON processabile (${reason}) — ` +
      `endpoint=${ev.endpoint} event=${ev.eventName} ` +
      `event_id=${ev.eventId} resource_id=${ev.resourceId} success=${ev.success}`,
    )

    const db = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } })
    // event_id univoco anche quando ev.eventId è null: fallback su resource_id o
    // hash del body, così due eventi diversi non collidono su ON CONFLICT.
    const fallbackKey =
      ev.eventId != null ? String(ev.eventId)
      : ev.resourceId != null ? `res:${ev.resourceId}`
      : `sig:${(await sha256Hex(rawBody)).slice(0, 32)}`
    const { error: insErr } = await db
      .from('fatture_queue')
      .upsert(
        {
          event_id:  fallbackKey,
          piva_raw:  'UNKNOWN',
          source:    'invoicetronic',
          status:    'failed',
          payload_meta: {
            unrecognized_event: reason,
            raw_endpoint: ev.endpoint,
            raw_event:    ev.eventName,
            resource_id:  ev.resourceId,
            invoicetronic_event_id: ev.eventId,
            invoicetronic_company_id: ev.companyId,
            date_time:    ev.dateTime,
            success:      ev.success,
          },
          correlation_id: req.headers.get('X-Request-ID') ?? req.headers.get('X-Correlation-ID') ?? null,
        },
        { onConflict: 'event_id', ignoreDuplicates: true },
      )
    if (insErr) {
      // Non riusciamo nemmeno a registrarla → 500, così Invoicetronic ritenta e
      // non perdiamo l'unica occasione di catturarla.
      console.error(`[wh] Errore INSERT evento non riconosciuto: ${insErr.message}`)
      return new Response('Internal Server Error', { status: 500 })
    }
    // Se manca proprio il resource_id non possiamo scaricare l'XML: la lasciamo
    // in coda come 'failed' registrata e chiudiamo 200 (l'abbiamo salvata).
    // Se invece è un vero receive con resource_id ma qualche altro campo non
    // tornava, proseguiamo comunque il flusso normale sotto quando possibile.
    if (missingCore) {
      return new Response('OK', { status: 200 })
    }
    // isReceiveEvent falso ma abbiamo comunque event_id+resource_id: l'abbiamo
    // registrata; non tentiamo il parse ottimistico per non mascherare il caso.
    if (!isReceiveEvent) {
      return new Response('OK', { status: 200 })
    }
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
  let indirizzoRaw: string | null = null         // indirizzo destinatario (routing multi-sede)
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
        // decodePayloadToXml gestisce sia XML puro sia buste P7M firmate.
        const normalizedPayload = data.payload.trim()
        const encoding = typeof data.encoding === 'string' ? data.encoding : 'Xml'
        const decoded = decodePayloadToXml(normalizedPayload, encoding)
        if (decoded.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
        xmlContent = decoded

      } else if (typeof data.xml_file === 'string' && data.xml_file.length > 0) {
        // Caso A: XML in base64 direttamente nel response JSON (anche P7M firmato)
        const decoded = decodePayloadToXml(data.xml_file, 'Base64')
        if (decoded.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
        xmlContent = decoded
        // Mantieni xml_url se presente (utile per recupero futuro post-purge GDPR)
        if (typeof data.xml_url === 'string') xmlUrl = data.xml_url

      } else if (typeof data.xml_url === 'string' && data.xml_url.length > 0) {
        // Caso B: solo URL → download con SSRF check
        xmlUrl = data.xml_url
        const xmlResp = await safeFetch(xmlUrl, {}, XML_TIMEOUT_MS)
        if (!xmlResp.ok) throw new Error(`Download XML fallito: HTTP ${xmlResp.status}`)
        // Leggiamo i byte grezzi: il file remoto può essere XML puro o P7M firmato.
        const rawBytes = new Uint8Array(await xmlResp.arrayBuffer())
        if (rawBytes.length > MAX_XML_BYTES) throw new Error('XML supera limite 10 MB')
        xmlContent = bytesToXml(rawBytes)

      } else {
        // API risponde OK ma senza XML (caso anomalo, loggare per debug)
        meta.api_warning = 'API ok ma payload/xml_file/xml_url assenti nel response'
      }

      // ── 7. Estrazione dati dall'XML ────────────────────────────────────────
      if (xmlContent) {
        // Difesa in profondità: se per un formato non riconosciuto fossero rimasti
        // byte nulli, l'INSERT in una colonna text di Postgres fallirebbe con 500
        // (storicamente il caso delle fatture P7M firmate). Li rimuoviamo e lo
        // segnaliamo in meta per tracciabilità.
        if (xmlContent.includes('\x00')) {
          xmlContent = xmlContent.replace(/\x00/g, '')
          meta.payload_sanitized = 'null_bytes_removed'
        }

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

        // Indirizzo destinatario: serve solo a smistare i clienti multi-sede.
        // Salvato in payload_meta per mostrarlo nella coda "da assegnare".
        indirizzoRaw = extractIndirizzoDestinatario(xmlContent)
        if (indirizzoRaw) meta.indirizzo_destinatario = indirizzoRaw

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
  //
  // Multi-sede: una P.IVA può avere PIÙ ristoranti (sedi). Si recuperano tutti e:
  //   • 1 sede           → assegna (caso normale, la stragrande maggioranza)
  //   • N sedi + match    → assegna alla sede col punteggio indirizzo più alto,
  //                         SE c'è distacco netto dalla seconda (decisione sicura)
  //   • N sedi + ambiguo  → 'da_assegnare': il cliente sceglie in UI (caso estremo)
  if (status === 'pending') {
    const { data: ristoranti, error: ristErr } = await db
      .from('ristoranti')
      .select('user_id, id, indirizzo_match, nome_ristorante')
      .eq('partita_iva', pivaRaw)
      .eq('attivo', true)
      .order('created_at', { ascending: false })

    if (ristErr) {
      console.error(`[wh] Errore lookup ristoranti: ${ristErr.message}`)
      // Continua con unknown_tenant per non perdere la fattura
    }

    const sedi = ristoranti ?? []

    if (sedi.length === 0) {
      // P.IVA sconosciuta: salva il record, risolvi quando arriva il ristorante
      // via funzione SQL resolve_unknown_tenant(piva)
      status   = 'unknown_tenant'
      userId   = null
      ristoranteId = null
      console.info(`[wh] Tenant sconosciuto per piva=${pivaRaw} event_id=${eventId}`)

    } else if (sedi.length === 1) {
      // Caso mono-sede: comportamento storico invariato.
      userId       = sedi[0].user_id as string
      ristoranteId = sedi[0].id as string

    } else {
      // Caso multi-sede: smista per indirizzo. Lo user_id è lo stesso per tutte
      // (stessa P.IVA = stesso cliente), quindi è noto fin da subito.
      userId = sedi[0].user_id as string

      // Soglie di sicurezza per l'assegnazione automatica:
      //   - il match migliore deve superare MIN_SCORE (somiglianza minima accettabile)
      //   - e distanziare il secondo di almeno MIN_GAP (nessuna ambiguità)
      // Se non sono soddisfatte → 'da_assegnare' (mai assegnare a caso).
      const MIN_SCORE = 0.40
      const MIN_GAP   = 0.20

      const target = indirizzoRaw ? normalizeIndirizzo(indirizzoRaw) : ''
      const scored = sedi
        .map(r => ({
          id:    r.id as string,
          score: target && r.indirizzo_match
            ? indirizzoSimilarity(target, r.indirizzo_match as string)
            : 0,
        }))
        .sort((a, b) => b.score - a.score)

      const best   = scored[0]
      const second = scored[1]
      const gap    = best.score - (second?.score ?? 0)

      if (best.score >= MIN_SCORE && gap >= MIN_GAP) {
        ristoranteId = best.id
        meta.routing = { mode: 'auto', score: best.score, gap }
        console.info(`[wh] Multi-sede risolto auto piva=${pivaRaw} score=${best.score.toFixed(2)} gap=${gap.toFixed(2)}`)
      } else {
        // Ambiguo o indirizzo assente/non distintivo → coda manuale.
        status       = 'da_assegnare'
        ristoranteId = null
        meta.routing = {
          mode:       'manual',
          best_score: best.score,
          gap,
          sedi_count: sedi.length,
        }
        console.info(`[wh] Multi-sede ambiguo → da_assegnare piva=${pivaRaw} best=${best.score.toFixed(2)} gap=${gap.toFixed(2)}`)
      }
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
}

// Avvia il server tranne quando importato da un test unitario.
// Fail-safe per produzione: in Supabase Edge il modulo è l'entry point e DEVE
// servire; ci tiriamo indietro SOLO se un test imposta esplicitamente
// WEBHOOK_TEST_MODE=1 (così non dipendiamo da import.meta.main, il cui valore
// può variare col bundler Supabase). Porta configurabile via PORT env var.
if (Deno.env.get('WEBHOOK_TEST_MODE') !== '1') {
  const _servePort = parseInt(Deno.env.get('PORT') ?? '8000', 10)
  Deno.serve({ port: _servePort }, handler)
}
