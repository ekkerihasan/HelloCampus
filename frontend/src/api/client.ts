export type Character = 'guide' | 'analyst'
export type Source = { title: string; url: string; collection: string; last_checked: string; citations?: number[] }
export type Visitor = { id: string; code: string; name: string; purpose: string; character: Character; language: string; facts: Record<string, string[]>; shortlist: string[] }
export type Health = { ok: boolean; components: Record<string, { ok: boolean; detail: string }>; providers?: Record<string, { reachable: boolean; detail: string }>; live_enabled?: boolean; text_active?: string }
export type LiveToken = { welcome_cue: string; token: string; model: string; api_version: string; expire_time: string; config: Record<string, unknown>; locked: boolean }
export type ToolResult = Record<string, unknown> & { sources?: Source[]; related_sources?: Source[]; refusal?: boolean; error?: string }
export type SpeechConfig = { live_enabled: boolean; server_tts: boolean; sentence_max_chars: number; recording_max_ms: number }
export type Candidate = { entity_id: string; name: string; headline: string; languages: string[]; claims: { text: string; url: string }[]; sources: string[]; linkedin_url?: string }
export type StreamEvent = { event: string; data: { t?: string; message?: string; sources?: Source[]; refused?: boolean; status?: string } }
export async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(path, { method, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Request failed (${res.status}). Please try again.`)
  }
  return res.json() as Promise<T>
}
export async function streamChat(message: string, character: Character, visitorId: string, onEvent: (event: StreamEvent) => void, signal: AbortSignal): Promise<void> {
  const res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, character, visitor_id: visitorId }), signal })
  if (!res.ok) {
    const error = await res.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : 'Could not start the conversation.')
  }
  if (!res.body) throw new Error('This browser cannot stream responses.')
  const reader = res.body.getReader(), decoder = new TextDecoder()
  let buffer = '', completed = false
  const consume = (frame: string) => {
    const lines = frame.split('\n'), event = lines.find(l => l.startsWith('event:'))?.slice(6).trim()
    const data = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n')
    if (!event || !data) return
    const parsed = { event, data: JSON.parse(data) } as StreamEvent
    if (event === 'error') throw new Error(parsed.data.message || 'The response could not be completed.')
    if (event === 'done') completed = true
    onEvent(parsed)
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) >= 0) { consume(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2) }
      if (done) break
    }
    if (buffer.trim()) consume(buffer)
    if (!completed) throw new Error('The connection ended before the response finished. Please try again.')
  } finally { await reader.cancel().catch(() => undefined); reader.releaseLock() }
}
export function safeUrl(url: string): string | undefined {
  try { const u = new URL(url); return ['http:', 'https:'].includes(u.protocol) ? u.href : undefined } catch { return undefined }
}

async function speechResponse(response: Response): Promise<Response> {
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Speech is unavailable (${response.status}).`)
  }
  return response
}
export async function transcribeAudio(audio: Blob, signal: AbortSignal): Promise<{ text: string; language: string }> {
  return (await speechResponse(await fetch('/api/stt', { method: 'POST', headers: { 'Content-Type': audio.type || 'application/octet-stream' }, body: audio, signal }))).json()
}
export async function synthesizeSpeech(text: string, signal: AbortSignal): Promise<ArrayBuffer> {
  return (await speechResponse(await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal }))).arrayBuffer()
}
export function callTool(name: string, args: Record<string, unknown>, visitorId: string | null, userMessage = '', signal?: AbortSignal): Promise<ToolResult> {
  return fetch(`/api/tools/${encodeURIComponent(name)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ visitor_id: visitorId, mode: 'voice', args, user_message: userMessage }), signal })
    .then(async res => res.ok ? res.json() as Promise<ToolResult> : { error: `Tool ${name} failed (${res.status}).` })
}
export async function lookAt(image: Blob, question: string, signal?: AbortSignal): Promise<ToolResult> {
  const res = await fetch(`/api/look?question=${encodeURIComponent(question)}`, { method: 'POST', headers: { 'Content-Type': image.type || 'image/jpeg' }, body: image, signal })
  if (!res.ok) { const error = await res.json().catch(() => null); return { error: typeof error?.detail === 'string' ? error.detail : `Look failed (${res.status}).` } }
  return res.json() as Promise<ToolResult>
}
