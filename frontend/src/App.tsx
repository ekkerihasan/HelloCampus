import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { request, safeUrl, streamChat } from './api/client'
import type { Candidate, Character, Health, Source, Visitor } from './api/client'
import './App.css'

type Message = { id: string; role: 'user' | 'assistant'; text: string; sources: Source[]; character: Character; refused?: boolean }
const purposes = ['Session or talk', 'Judging or mentoring', 'Hiring', 'Event', 'Parent or alumni', 'Just visiting']
const suggestions = ['Tell me about AITM', 'How can I contact the college?', 'What does the CSE department offer?', 'What has AITM achieved?']
const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Please try again.'

function App() {
  const [visitor, setVisitor] = useState<Visitor | null>(null), [restoring, setRestoring] = useState(true)
  const [name, setName] = useState(''), [purpose, setPurpose] = useState('Just visiting'), [code, setCode] = useState('')
  const [character, setCharacter] = useState<Character>('guide')
  const [messages, setMessages] = useState<Message[]>([]), [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false), [welcomeBusy, setWelcomeBusy] = useState(false)
  const [error, setError] = useState(''), [status, setStatus] = useState('')
  const [health, setHealth] = useState<Health | null>(null), [hiring, setHiring] = useState(false)
  const controller = useRef<AbortController | null>(null), scrollEnd = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let active = true
    const refresh = () => request<Health>('/api/health').then(h => { if (active) setHealth(h) }).catch(() => { if (active) setHealth(null) })
    void refresh()
    const timer = window.setInterval(() => void refresh(), 20000)
    const id = localStorage.getItem('hello-campus-visitor')
    if (id) request<Visitor>(`/api/visitor/${encodeURIComponent(id)}`).then(v => { if (active) { setVisitor(v); setCharacter(v.character) } }).catch(() => { localStorage.removeItem('hello-campus-visitor') }).finally(() => { if (active) setRestoring(false) })
    else setRestoring(false)
    return () => { active = false; window.clearInterval(timer); controller.current?.abort() }
  }, [])
  useEffect(() => { scrollEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, status])
  function enter(v: Visitor) { localStorage.setItem('hello-campus-visitor', v.id); setVisitor(v); setCharacter(v.character); setError('') }
  async function welcome(e: FormEvent, resume = false) {
    e.preventDefault(); setWelcomeBusy(true); setError('')
    try { enter(await request<Visitor>(resume ? `/api/visitor/resume/${encodeURIComponent(code.trim())}` : '/api/visitor', resume ? 'GET' : 'POST', resume ? undefined : { name: name.trim(), purpose })) }
    catch (e) { setError(errorMessage(e)) } finally { setWelcomeBusy(false) }
  }
  async function toggleCharacter(next: Character) {
    if (!visitor || busy) return
    try { const v = await request<Visitor>(`/api/visitor/${visitor.id}/character`, 'PUT', { character: next }); setVisitor(v); setCharacter(next) }
    catch (e) { setError(errorMessage(e)) }
  }
  async function send(text = draft) {
    if (!visitor || busy || !text.trim()) return
    setDraft(''); setError(''); setBusy(true); setStatus('Looking that up…')
    const answer: Message = { id: crypto.randomUUID(), role: 'assistant', text: '', sources: [], character }
    setMessages(old => [...old, { id: crypto.randomUUID(), role: 'user', text: text.trim(), sources: [], character }, answer])
    const abort = new AbortController(); controller.current = abort
    try {
      await streamChat(text.trim(), character, visitor.id, ({ event, data }) => {
        if (event === 'token') { setStatus('Replying…'); setMessages(old => old.map(m => m.id === answer.id ? { ...m, text: m.text + (data.t || '') } : m)) }
        if (event === 'sources') setMessages(old => old.map(m => m.id === answer.id ? { ...m, sources: data.sources || [], refused: data.refused } : m))
        if (event === 'memory') { setStatus(data.status === 'saving' ? 'Saving your preferences…' : ''); if (data.status === 'failed') setError(data.message || 'Preferences could not be updated.') }
      }, abort.signal)
    } catch (e) { if (!abort.signal.aborted) setError(errorMessage(e)) }
    finally { setBusy(false); setStatus(''); controller.current = null }
  }
  const ready = health?.components.llm?.ok && health?.components.rag?.ok
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Hello Campus home"><span className="brand-icon">h<span>c</span></span><span>Hello<br /><strong>Campus.</strong></span></a>
      <div className="campus-label">YOUR CAMPUS COMPANION</div><div className="campus-name">Anjuman Institute of<br />Technology & Management<span>Bhatkal, Karnataka</span></div>
      <nav aria-label="Explore"><button className={!hiring ? 'nav-item active' : 'nav-item'} onClick={() => setHiring(false)}><span>◌</span> Conversation <span className="nav-arrow">↗</span></button><button className={hiring ? 'nav-item active' : 'nav-item'} disabled={!visitor || busy} onClick={() => { setHiring(true); void toggleCharacter('analyst') }}><span>▤</span> Find talent <span className="nav-arrow">↗</span></button></nav>
      <div className="sidebar-note"><span className="dot" />A little local knowledge.<br /><strong>A warmer welcome.</strong><p>Ask about the campus, explore what’s happening, or find your next teammate.</p></div><a className="college-link" href="https://aitm.edu.in/" target="_blank" rel="noreferrer">Visit AITM website ↗</a>
    </aside>
    <main><header className="topbar"><span>WELCOME TO AITM <span className="topbar-divider">/</span> <strong>{hiring ? 'Find talent' : 'Your visit, made easier'}</strong></span><span className={`connection ${ready ? 'online' : ''}`}><i />{ready ? 'Local companion ready' : 'Companion connecting'}</span></header>
      {error && <div className="error-banner" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError('')}>×</button></div>}
      {restoring ? <div className="welcome"><p>Finding your visit…</p></div> : !visitor ? <section className="welcome"><div className="eyebrow">A FAMILIAR FACE IN A NEW PLACE</div><h1>New here?<br /><span>You’re in good company.</span></h1><p className="intro">A friendly guide to AITM, its people and the things that make it special. Let’s start with you.</p><div className="welcome-grid">
        <form className="welcome-card" onSubmit={e => void welcome(e)}><label htmlFor="visitor-name">What should I call you?</label><input id="visitor-name" autoComplete="given-name" placeholder="Your name" value={name} maxLength={60} required onChange={e => setName(e.target.value)} /><fieldset><legend>What brings you here today?</legend><div className="purpose-chips">{purposes.map(p => <button type="button" key={p} className={purpose === p ? 'chip selected' : 'chip'} onClick={() => setPurpose(p)}>{p}</button>)}</div></fieldset><button className="primary" disabled={welcomeBusy || !name.trim()}>{welcomeBusy ? 'Getting things ready…' : 'Let’s get acquainted'} <span>↗</span></button><small>Your visit is remembered on this laptop. A short code lets you continue on another device.</small></form>
        <form className="resume-card" onSubmit={e => void welcome(e, true)}><span className="resume-icon">↶</span><h2>Back for more?</h2><p>Pick up where you left off with your four-character visit code.</p><label htmlFor="resume-code">Visit code</label><input id="resume-code" className="code-input" placeholder="K7QM" value={code} maxLength={4} required onChange={e => setCode(e.target.value.toUpperCase())} /><button className="secondary" disabled={welcomeBusy || code.trim().length !== 4}>Resume my visit →</button></form>
      </div></section> : hiring ? <Hiring visitor={visitor} onError={setError} /> : <section className="conversation">
        <div className="conversation-heading"><div><div className="eyebrow">MAKE YOURSELF AT HOME</div><h1>Hello, {visitor.name}<span className="hello-spark">✳</span></h1><p>A campus question, a little curiosity. Where shall we start?</p></div><div className="visit-code"><span>YOUR VISIT CODE</span><strong>{visitor.code}</strong><small>Continue on any device</small></div></div>
        <div className="conversation-toolbar"><div className="mode-tabs" aria-label="Conversation mode"><button className="selected">◌ Chat</button><button disabled title="Voice will be available when local speech is ready">♫ Voice <small>Soon</small></button><button disabled title="Video will be available when gesture detection is ready">▣ Video <small>Soon</small></button></div><div className="character-toggle" aria-label="Character">{(['guide', 'analyst'] as Character[]).map(c => <button key={c} disabled={busy} aria-pressed={character === c} className={character === c ? 'selected' : ''} onClick={() => void toggleCharacter(c)}>{c === 'guide' ? 'Guide · 0.8' : 'Analyst · 0.2'}</button>)}</div></div>
        <div className="messages" role="log" aria-live="polite" aria-relevant="additions text">{messages.length === 0 && <div className="empty-chat"><span className="companion-mark">✳</span><h2>Your friendly local, right here.</h2><p>{character === 'guide' ? 'I’ll help you find your feet, one question at a time.' : 'Ask a specific question. I’ll bring the facts and their sources.'}</p><div className="suggestions">{suggestions.map((q, i) => <button disabled={busy || !ready} key={q} onClick={() => void send(q)}><span>0{i + 1}</span>{q}<b>↗</b></button>)}</div></div>}
          {messages.map(m => <article key={m.id} className={`message ${m.role}`}><div className="message-label">{m.role === 'user' ? visitor.name : m.character === 'guide' ? 'Your guide' : 'Analyst'}{m.role === 'assistant' && <span>✳</span>}</div><div className="message-text">{m.text || (busy ? 'Thinking…' : 'Response interrupted.')}</div>{m.sources.length > 0 && <div className="source-chips">{m.sources.map((s, i) => safeUrl(s.url) ? <a key={`${s.url}-${i}`} href={safeUrl(s.url)} target="_blank" rel="noreferrer" title={`Checked ${s.last_checked}`}>[{i + 1}] {s.title} ↗</a> : <span key={i}>{s.title} · Curated</span>)}</div>}{m.refused && <small className="refusal-label">No verified information found for this question.</small>}</article>)}<div ref={scrollEnd} />
        </div><div className="composer-area"><div className="response-status" role="status">{status || (!ready ? 'The companion is starting. You can resume chatting when it’s ready.' : '')}</div><form className="composer" onSubmit={e => { e.preventDefault(); void send() }}><label className="sr-only" htmlFor="message">Your question</label><input id="message" placeholder="Ask anything about your campus visit…" maxLength={4000} value={draft} disabled={busy} onChange={e => setDraft(e.target.value)} />{busy ? <button type="button" aria-label="Stop response" onClick={() => controller.current?.abort()}>■</button> : <button aria-label="Send message" disabled={!draft.trim() || !ready}>↑</button>}</form><div className="composer-footer"><span>Campus facts come with sources. If I don’t know, I’ll say so.</span><button disabled={busy} onClick={() => { localStorage.removeItem('hello-campus-visitor'); setVisitor(null); setMessages([]); setHiring(false) }}>Start a new visit</button></div></div>
      </section>}
    </main>
  </div>
}
function Hiring({ visitor, onError }: { visitor: Visitor; onError: (message: string) => void }) {
  const [description, setDescription] = useState(''), [busy, setBusy] = useState(false), [searched, setSearched] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([]), [shortlist, setShortlist] = useState<Candidate[]>([])
  const [selected, setSelected] = useState<string[]>([]), [comparison, setComparison] = useState<Candidate[]>([])
  const [readme, setReadme] = useState<{ before: string; after: string } | null>(null), [questions, setQuestions] = useState<{ text: string; url: string }[]>([])
  useEffect(() => { request<Candidate[]>(`/api/hiring/shortlist/${visitor.id}`).then(setShortlist).catch(e => onError(errorMessage(e))) }, [visitor.id, onError])
  async function perform(action: () => Promise<void>) { setBusy(true); onError(''); try { await action() } catch (e) { onError(errorMessage(e)) } finally { setBusy(false) } }
  async function find(e: FormEvent) { e.preventDefault(); await perform(async () => { await request('/api/hiring/role', 'POST', { visitor_id: visitor.id, description }); setCandidates(await request<Candidate[]>('/api/hiring/match', 'POST', { visitor_id: visitor.id })); setSearched(true) }) }
  async function toggle(c: Candidate) { await perform(async () => { if (shortlist.some(s => s.entity_id === c.entity_id)) await request(`/api/hiring/shortlist/${visitor.id}/${c.entity_id}`, 'DELETE'); else await request('/api/hiring/shortlist', 'POST', { visitor_id: visitor.id, entity_id: c.entity_id }); setShortlist(await request<Candidate[]>(`/api/hiring/shortlist/${visitor.id}`)) }) }
  const people = [...new Map([...candidates, ...shortlist].map(c => [c.entity_id, c])).values()]
  return <section className="hiring-panel"><div className="eyebrow">GOOD PEOPLE. REAL EVIDENCE.</div><h1>Meet your next teammate.</h1><p>Describe the role. Explore students who have opted in, with links to the work behind each match.</p><form className="role-form" onSubmit={e => void find(e)}><label htmlFor="role">What are you looking for?</label><textarea id="role" required minLength={3} maxLength={6000} value={description} onChange={e => setDescription(e.target.value)} placeholder="A frontend intern who has built React applications…" /><button className="primary" disabled={busy}>{busy ? 'Working…' : 'Find matches ↗'}</button></form>
    {searched && candidates.length === 0 && <div className="empty-result"><h2>No verified matches yet.</h2><p>Matches appear when opted-in student profiles and project evidence are available for this role.</p></div>}<div className="hiring-actions"><span>{shortlist.length} shortlisted</span><button className="secondary" disabled={busy || selected.length !== 2} onClick={() => void perform(async () => setComparison(await request<Candidate[]>('/api/hiring/compare', 'POST', { entity_ids: selected })))}>Compare selected</button>{shortlist.length > 0 && <a className="secondary" href={`/api/hiring/export/${visitor.id}`}>Export shortlist ↓</a>}</div>
    <div className="candidate-grid">{people.map(c => <article className="candidate-card" key={c.entity_id}><label className="compare-check"><input type="checkbox" checked={selected.includes(c.entity_id)} disabled={busy || (!selected.includes(c.entity_id) && selected.length >= 2)} onChange={e => setSelected(old => e.target.checked ? [...old, c.entity_id] : old.filter(id => id !== c.entity_id))} />Compare</label><h2>{c.name}</h2><p>@{c.entity_id} · {c.headline}</p><div className="language-chips">{c.languages.map(l => <span key={l}>{l}</span>)}</div>{c.claims.map((claim, i) => <p key={i}>{claim.text} <a href={safeUrl(claim.url)} target="_blank" rel="noreferrer">Evidence ↗</a></p>)}<details><summary>Project evidence</summary>{c.sources.map(url => <a className="evidence-link" key={url} href={safeUrl(url)} target="_blank" rel="noreferrer">{url} ↗</a>)}</details><div className="candidate-actions"><button disabled={busy} onClick={() => void toggle(c)}>{shortlist.some(s => s.entity_id === c.entity_id) ? 'Remove from shortlist' : '+ Shortlist'}</button><button disabled={busy} onClick={() => void perform(async () => { setQuestions(await request(`/api/hiring/interview/${c.entity_id}`, 'POST')); setReadme(null) })}>Interview kit</button><button disabled={busy} onClick={() => void perform(async () => { setReadme(await request(`/api/students/${c.entity_id}/readme`, 'POST')); setQuestions([]) })}>Improve README</button></div></article>)}</div>
    {comparison.length === 2 && <div className="comparison"><h2>Side by side</h2><table><thead><tr><th>Recorded evidence</th>{comparison.map(c => <th key={c.entity_id}>{c.name}</th>)}</tr></thead><tbody><tr><th>Languages</th>{comparison.map(c => <td key={c.entity_id}>{c.languages.join(', ') || 'Not recorded'}</td>)}</tr><tr><th>Sources</th>{comparison.map(c => <td key={c.entity_id}>{c.sources.map(url => <a key={url} className="evidence-link" href={safeUrl(url)} target="_blank" rel="noreferrer">{url}</a>)}</td>)}</tr></tbody></table></div>}
    {readme && <section><h2>Profile README</h2><div className="readme-grid"><div><h3>Before</h3><pre>{readme.before || 'No existing profile README.'}</pre></div><div><h3>Suggested version</h3><pre>{readme.after}</pre></div></div></section>}{questions.length > 0 && <section className="interview"><h2>Interview questions</h2><ol>{questions.map((q, i) => <li key={i}>{q.text} <a href={safeUrl(q.url)} target="_blank" rel="noreferrer">Repository ↗</a></li>)}</ol></section>}
  </section>
}
export default App
