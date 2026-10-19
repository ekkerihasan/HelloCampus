import { useEffect, useRef, useState } from 'react'
import { streamChat } from '../api/client'
import type { Character, Health, Source, Visitor } from '../api/client'
import { useVoice } from '../hooks/useVoice'
import { CitedText, Footnotes } from '../components/SourceChips'
import { Icon } from '../components/Icon'

type Entry = { id: string; question: string; answer: string; sources: Source[]; character: Character; refused?: boolean; done: boolean; interrupted?: boolean }

const characters: Record<Character, { label: string; temp: string; note: string }> = {
  guide: { label: 'Guide', temp: '0.8', note: 'Conversational, like a local showing you around.' },
  analyst: { label: 'Analyst', temp: '0.2', note: 'Short, factual answers with the key details first.' },
}
const suggestions = ['Tell me about AITM', 'How do I contact the college?', 'What does the CSE department offer?', 'What has AITM achieved recently?']
const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Please try again.'

type Props = {
  visitor: Visitor; returning: boolean; character: Character; onCharacter: (c: Character) => void
  health: Health | null; active: boolean; onError: (message: string) => void
}

export function Ask({ visitor, returning, character, onCharacter, health, active, onError }: Props) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [status, setStatus] = useState('')
  const [readAloud, setReadAloud] = useState(false), [notice, setNotice] = useState('')
  const controller = useRef<AbortController | null>(null), end = useRef<HTMLDivElement>(null)

  const ready = Boolean(health?.components.llm?.ok && health?.components.rag?.ok)
  const speechReady = Boolean(health?.components.stt?.ok && health?.components.tts?.ok)

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [entries, status])

  function stopResponse() { controller.current?.abort(); controller.current = null; setBusy(false); setStatus('') }

  async function send(text = draft, speak = readAloud) {
    const question = text.trim()
    if (busy || !question) return
    voice.stop(); setDraft(''); onError(''); setNotice(''); setBusy(true); setStatus('Searching campus sources')
    const id = crypto.randomUUID()
    setEntries(old => [...old.slice(-9), { id, question, answer: '', sources: [], character, done: false }])
    const update = (patch: (e: Entry) => Entry) => setEntries(old => old.map(e => e.id === id ? patch(e) : e))
    const abort = new AbortController(); controller.current = abort
    try {
      await streamChat(question, character, visitor.id, ({ event, data }) => {
        if (abort.signal.aborted) return
        if (event === 'token') { if (speak) voice.enqueue(data.t || ''); setStatus(''); update(e => ({ ...e, answer: e.answer + (data.t || '') })) }
        if (event === 'sources') { if (speak) voice.enqueue('', true); update(e => ({ ...e, sources: data.sources || [], refused: data.refused, done: true })) }
        if (event === 'memory') { setStatus(data.status === 'saving' ? 'Saving your preferences' : ''); if (data.status === 'failed') onError(data.message || 'Your preferences could not be saved.') }
      }, abort.signal)
      if (speak && !abort.signal.aborted) voice.enqueue('', true)
    } catch (e) {
      if (!abort.signal.aborted) onError(errorMessage(e))
      update(x => ({ ...x, interrupted: true, done: true }))
    } finally {
      if (controller.current === abort) { setBusy(false); setStatus(''); controller.current = null }
    }
  }

  const voice = useVoice(text => { void send(text, true) }, stopResponse)
  const stopAll = useRef(() => {}); stopAll.current = () => { stopResponse(); voice.stop() }
  useEffect(() => { if (!active) stopAll.current() }, [active])

  function micPressed() {
    if (!speechReady) { setNotice('Voice input is not available right now. You can type your question.'); return }
    setNotice(''); voice.toggle()
  }
  function toggleReadAloud() {
    if (!readAloud) {
      if (!speechReady) { setNotice('Read aloud is not available right now.'); return }
      void voice.warmAudio().catch(e => onError(errorMessage(e)))
    } else voice.stop()
    setReadAloud(on => !on)
  }

  const recording = voice.capture === 'recording', listening = voice.capture !== 'idle'
  const line = voice.playback !== 'idle' ? (voice.playback === 'playing' ? 'Reading the answer aloud' : 'Preparing audio')
    : voice.capture === 'requesting' ? 'Waiting for microphone permission'
    : recording ? 'Recording. Press Done when you finish speaking.'
    : voice.capture === 'transcribing' ? 'Transcribing your question'
    : voice.error || notice || status || (!ready ? 'Connecting to the campus assistant' : '')

  return <div className="page ask">
    <header className="page-head ask-head">
      <div>
        <h1>Ask</h1>
        <p className="lede">{returning ? `Welcome back, ${visitor.name}.` : `Hello, ${visitor.name}.`} Questions about AITM are answered from published campus sources.</p>
      </div>
      <div className="style-control">
        <span className="label" id="style-label">Answer style</span>
        <div className="segmented" role="radiogroup" aria-labelledby="style-label">
          {(['guide', 'analyst'] as Character[]).map(c => <button key={c} role="radio" aria-checked={character === c} disabled={busy}
            className="segment" onClick={() => onCharacter(c)}>
            <span>{characters[c].label}</span><span className="segment-meta mono">temp {characters[c].temp}</span>
          </button>)}
        </div>
        <p className="style-note">{characters[character].note}</p>
      </div>
    </header>

    <div className="transcript" role="log" aria-live="polite" aria-relevant="additions text">
      {entries.length === 0 && <section className="starters" aria-labelledby="starters-title">
        <h2 id="starters-title" className="label">Common questions</h2>
        <ul>{suggestions.map(q => <li key={q}><button disabled={busy || !ready} onClick={() => void send(q)}><span>{q}</span><Icon name="arrow" size={16} /></button></li>)}</ul>
      </section>}

      {entries.map(e => <article key={e.id} className="qa">
        <h2 className="qa-q">{e.question}</h2>
        <div className="qa-a">
          {e.answer ? <p><CitedText text={e.answer} /></p>
            : e.interrupted ? <p className="muted">Answer stopped.</p>
            : <p className="muted pending">Writing answer</p>}
          {e.refused && <p className="qa-note">No published source covers this yet, so no answer was given.</p>}
          <Footnotes sources={e.sources} />
          {e.done && !e.interrupted && <p className="qa-meta">{characters[e.character].label}, temperature {characters[e.character].temp}</p>}
        </div>
      </article>)}
      <div ref={end} className="transcript-end" />
    </div>

    <div className="dock">
      <div className="dock-inner">
        <p className="dock-line" role="status">
          {voice.playback !== 'idle' && <><span className="live" aria-hidden="true" />{line}<button className="btn-text" onClick={() => voice.stop()}>Stop</button></>}
          {voice.playback === 'idle' && line}
        </p>
        <form className={`composer ${recording ? 'is-recording' : ''}`} onSubmit={e => { e.preventDefault(); void send() }}>
          <label className="sr-only" htmlFor="message">Your question</label>
          {recording
            ? <div className="rec"><span className="live live-danger" aria-hidden="true" />Recording</div>
            : <textarea id="message" rows={1} placeholder="Type a question about the campus" maxLength={4000} value={draft}
                disabled={busy || listening} onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }} />}
          <div className="composer-actions">
            <button type="button" className={`tool ${readAloud ? 'is-on' : ''}`} aria-pressed={readAloud} onClick={toggleReadAloud} title="Read answers aloud">
              <Icon name={readAloud ? 'speaker' : 'mute'} size={18} /><span>Read aloud</span>
            </button>
            <button type="button" className={`tool ${recording ? 'is-rec' : ''}`} disabled={!ready} onClick={micPressed}>
              <Icon name={recording ? 'check' : listening ? 'close' : 'mic'} size={18} /><span>{recording ? 'Done' : listening ? 'Cancel' : 'Voice'}</span>
            </button>
            {busy
              ? <button type="button" className="btn btn-primary btn-send" onClick={() => stopAll.current()}>Stop</button>
              : <button className="btn btn-primary btn-send" disabled={!draft.trim() || !ready || listening}>Send</button>}
          </div>
        </form>
      </div>
    </div>
  </div>
}
