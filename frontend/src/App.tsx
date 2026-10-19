import { useCallback, useEffect, useState } from 'react'
import { request } from './api/client'
import type { Character, Health, Visitor } from './api/client'
import { Icon } from './components/Icon'
import { Welcome } from './views/Welcome'
import { Ask } from './views/Ask'
import { Talent } from './views/Talent'
import PlayMode from './PlayMode'
import './App.css'

type Tab = 'ask' | 'talent' | 'quiz'
const tabs: { id: Tab; label: string }[] = [
  { id: 'ask', label: 'Ask' },
  { id: 'talent', label: 'Talent' },
  { id: 'quiz', label: 'Quiz' },
]
const VISITOR_KEY = 'hello-campus-visitor', TAB_KEY = 'hello-campus-tab'
const store = {
  get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* Storage blocked: the visit still works in this tab. */ } },
  remove: (k: string) => { try { localStorage.removeItem(k) } catch { /* Ignore. */ } },
}
const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Please try again.'
const isTab = (v: string | null): v is Tab => v === 'ask' || v === 'talent' || v === 'quiz'

function App() {
  const [visitor, setVisitor] = useState<Visitor | null>(null), [restoring, setRestoring] = useState(true)
  const [returning, setReturning] = useState(false)
  const [character, setCharacter] = useState<Character>('guide')
  const [health, setHealth] = useState<Health | null>(null), [healthChecked, setHealthChecked] = useState(false)
  const [tab, setTab] = useState<Tab>(() => { const t = store.get(TAB_KEY); return isTab(t) ? t : 'ask' })
  const [quizOpened, setQuizOpened] = useState(tab === 'quiz')
  const [error, setError] = useState(''), [sheet, setSheet] = useState(false), [copied, setCopied] = useState(false)

  useEffect(() => {
    let active = true
    const refresh = () => request<Health>('/api/health')
      .then(h => { if (active) setHealth(h) }).catch(() => { if (active) setHealth(null) })
      .finally(() => { if (active) setHealthChecked(true) })
    void refresh()
    const timer = window.setInterval(() => void refresh(), 20000)
    const id = store.get(VISITOR_KEY)
    if (id) request<Visitor>(`/api/visitor/${encodeURIComponent(id)}`)
      .then(v => { if (active) { setVisitor(v); setCharacter(v.character); setReturning(true) } })
      .catch(() => store.remove(VISITOR_KEY))
      .finally(() => { if (active) setRestoring(false) })
    else setRestoring(false)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  useEffect(() => {
    if (!sheet) return
    const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setSheet(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [sheet])

  const onError = useCallback((message: string) => setError(message), [])
  function enter(v: Visitor, resumed: boolean) { store.set(VISITOR_KEY, v.id); setVisitor(v); setCharacter(v.character); setReturning(resumed); setError('') }
  function go(next: Tab) { setTab(next); store.set(TAB_KEY, next); setError(''); if (next === 'quiz') setQuizOpened(true) }
  async function changeCharacter(next: Character) {
    if (!visitor || next === character) return
    setCharacter(next)
    try { setVisitor(await request<Visitor>(`/api/visitor/${visitor.id}/character`, 'PUT', { character: next })) }
    catch (e) { setCharacter(character); setError(errorMessage(e)) }
  }
  function copyCode() {
    if (!visitor) return
    void navigator.clipboard?.writeText(visitor.code).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1600) }).catch(() => undefined)
  }
  function newVisit() { store.remove(VISITOR_KEY); setSheet(false); setVisitor(null); setError(''); go('ask') }

  if (restoring) return <div className="splash" role="status">Loading your visit</div>
  if (!visitor) return <Welcome onEnter={enter} />

  const ready = Boolean(health?.components.llm?.ok && health?.components.rag?.ok)
  const status = !healthChecked ? 'checking' : !health ? 'offline' : ready ? 'ready' : 'starting'
  const statusText = { checking: 'Checking connection', offline: 'Assistant offline', ready: 'Assistant ready', starting: 'Assistant starting' }[status]

  return <div className="shell">
    <header className="masthead">
      <div className="masthead-inner">
        <div className="wordmark">
          <span className="wordmark-name">Hello Campus</span>
          <span className="wordmark-place">AITM Bhatkal</span>
        </div>
        <div className="masthead-meta">
          <span className={`status status-${status}`} title={statusText}><i aria-hidden="true" /><span className="status-text">{statusText}</span></span>
          <button className="visit-btn" onClick={() => setSheet(true)}>
            <span className="visit-btn-label">Visit</span><span className="mono">{visitor.code}</span>
          </button>
        </div>
      </div>
      <nav className="tabs" aria-label="Sections">
        <div className="tabs-inner">
          {tabs.map(t => <button key={t.id} className="tab" aria-current={tab === t.id ? 'page' : undefined} onClick={() => go(t.id)}>{t.label}</button>)}
        </div>
      </nav>
    </header>

    <main className="main">
      {error && <div className="banner" role="alert"><p>{error}</p><button className="icon-btn" aria-label="Dismiss" onClick={() => setError('')}><Icon name="close" size={18} /></button></div>}
      <section hidden={tab !== 'ask'}>
        <Ask visitor={visitor} returning={returning} character={character} onCharacter={c => void changeCharacter(c)} health={health} active={tab === 'ask'} onError={onError} />
      </section>
      <section hidden={tab !== 'talent'}><Talent visitor={visitor} onError={onError} /></section>
      {quizOpened && <section hidden={tab !== 'quiz'}><PlayMode initialPlayers={[visitor.name.slice(0, 40), 'Player 2']} /></section>}
    </main>

    {sheet && <div className="sheet-backdrop" onClick={() => setSheet(false)}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" onClick={e => e.stopPropagation()}>
        <div className="sheet-head"><h2 id="sheet-title">Your visit code</h2><button className="icon-btn" aria-label="Close" autoFocus onClick={() => setSheet(false)}><Icon name="close" size={18} /></button></div>
        <p className="sheet-code mono">{visitor.code}</p>
        <p className="sheet-text">Enter this code on another phone or laptop to continue with the same preferences and shortlist.</p>
        <div className="sheet-actions">
          <button className="btn btn-secondary" onClick={copyCode}><Icon name={copied ? 'check' : 'copy'} size={16} />{copied ? 'Copied' : 'Copy code'}</button>
          <button className="btn btn-plain btn-danger" onClick={newVisit}>Start a new visit</button>
        </div>
        <p className="sheet-meta">Visiting as {visitor.name}{visitor.purpose ? `, ${visitor.purpose.toLowerCase()}` : ''}.</p>
      </div>
    </div>}
  </div>
}

export default App
