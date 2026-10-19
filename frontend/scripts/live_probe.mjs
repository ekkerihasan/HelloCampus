// T0.4/T2.1 probe: one short real Live session using the backend token and config, a question that needs a tool,
// tool calls forwarded to /api/tools exactly like the browser does. Prints timings and the caption only.
// Run from frontend/: node scripts/live_probe.mjs "Which cricket title did AITM win in 2025?"
import { GoogleGenAI } from '@google/genai'

const API = process.env.API || 'http://localhost:8000'
const question = process.argv[2] || 'Which cricket title did AITM win in 2025? Answer in one sentence.'
const post = (path, body) => fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  .then(async r => { if (!r.ok) throw new Error(`${path} ${r.status} ${await r.text()}`); return r.json() })

const t0 = Date.now(), ms = () => Date.now() - t0
const token = await post('/api/live/token', { character: 'analyst' })
console.log(`token ${ms()} ms, model ${token.model}, api ${token.api_version}, locked ${token.locked}`)
let sent = 0, firstAudio = 0, audioBytes = 0, caption = '', tools = [], done
const finished = new Promise(resolve => { done = resolve })
const ai = new GoogleGenAI({ apiKey: token.token, httpOptions: { apiVersion: token.api_version } })
const session = await ai.live.connect({ model: token.model, config: token.config, callbacks: {
  onopen: () => console.log(`open ${ms()} ms`),
  onmessage: async msg => {
    const c = msg.serverContent
    for (const part of c?.modelTurn?.parts || []) if (part.inlineData?.data) { audioBytes += part.inlineData.data.length * 3 / 4; firstAudio ||= ms() }
    caption += c?.outputTranscription?.text || ''
    if (msg.toolCall?.functionCalls?.length) {
      const responses = []
      for (const fc of msg.toolCall.functionCalls) {
        const result = await post(`/api/tools/${fc.name}`, { visitor_id: null, mode: 'voice', args: fc.args || {} })
        tools.push(`${fc.name}(${JSON.stringify(fc.args)}) at ${ms()} ms -> ${(result.sources || []).map(s => s.url).join(', ') || (result.refusal ? 'refusal' : 'no sources')}`)
        responses.push({ id: fc.id, name: fc.name, response: result })
      }
      session.sendToolResponse({ functionResponses: responses })
    }
    if (c?.turnComplete && sent && (firstAudio || caption)) done()
  },
  onerror: e => { console.log('error', e?.message || e); done() },
  onclose: e => { console.log(`close ${ms()} ms code ${e?.code} ${e?.reason || ''}`); done() },
} })
if (token.welcome_cue) session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: token.welcome_cue }] }], turnComplete: true })
const cueAt = ms()
// Wait for the welcome, then ask the question.
await new Promise(r => setTimeout(r, 6000))
console.log(`welcome audio: ${firstAudio ? `first chunk ${firstAudio - cueAt} ms after the cue` : 'none'}; caption: ${caption.trim().slice(0, 160)}`)
firstAudio = 0; caption = ''; audioBytes = 0; sent = ms()
session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: question }] }], turnComplete: true })
await Promise.race([finished, new Promise(r => setTimeout(r, 30000))])
session.close()
console.log(`tools: ${tools.length ? tools.join(' | ') : 'none'}`)
console.log(`answer first audio ${firstAudio ? firstAudio - sent : 'n/a'} ms after the question, ${Math.round(audioBytes / 1024)} KB audio`)
console.log(`caption: ${caption.trim()}`)
