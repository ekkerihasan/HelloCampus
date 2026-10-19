import { useState } from 'react'
import type { FormEvent } from 'react'
import { request } from '../api/client'
import type { Visitor } from '../api/client'

const purposes = ['Session or talk', 'Judging or mentoring', 'Hiring', 'Event', 'Parent or alumni', 'Just visiting']
const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Please try again.'

export function Welcome({ onEnter }: { onEnter: (v: Visitor, resumed: boolean) => void }) {
  const [name, setName] = useState(''), [purpose, setPurpose] = useState('Just visiting')
  const [code, setCode] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [resuming, setResuming] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      if (resuming) onEnter(await request<Visitor>(`/api/visitor/resume/${encodeURIComponent(code.trim())}`), true)
      else onEnter(await request<Visitor>('/api/visitor', 'POST', { name: name.trim(), purpose }), false)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  function switchTo(next: boolean) { setResuming(next); setError('') }

  return <div className="welcome">
    <header className="welcome-top">
      <div className="wordmark"><span className="wordmark-name">Hello Campus</span><span className="wordmark-place">AITM Bhatkal</span></div>
    </header>
    <div className="welcome-grid">
      <section className="welcome-intro">
        <p className="welcome-kicker">Anjuman Institute of Technology and Management</p>
        <h1>A guide to AITM, with the source behind every answer.</h1>
        <dl className="welcome-points">
          <div><dt>Ask</dt><dd>Departments, contacts, events and places to eat nearby.</dd></div>
          <div><dt>Talent</dt><dd>Students who opted in, matched to your role with links to their work.</dd></div>
          <div><dt>Quiz</dt><dd>A two-player campus quiz on one screen.</dd></div>
        </dl>
      </section>

      <section className="welcome-panel" aria-labelledby="welcome-form-title">
        <div className="panel-switch" role="tablist" aria-label="How to start">
          <button role="tab" aria-selected={!resuming} onClick={() => switchTo(false)}>New visit</button>
          <button role="tab" aria-selected={resuming} onClick={() => switchTo(true)}>I have a code</button>
        </div>
        <h2 id="welcome-form-title" className="sr-only">{resuming ? 'Continue a visit' : 'Start a visit'}</h2>

        {resuming
          ? <form onSubmit={e => void submit(e)}>
              <label className="label" htmlFor="resume-code">Visit code</label>
              <input id="resume-code" className="input input-code mono" placeholder="K7QM" autoComplete="off" autoCapitalize="characters" spellCheck={false}
                value={code} maxLength={4} required onChange={e => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} />
              <p className="hint">Four characters, shown on the device you started on.</p>
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="btn btn-primary btn-wide" disabled={busy || code.length !== 4}>{busy ? 'Opening visit' : 'Continue visit'}</button>
            </form>
          : <form onSubmit={e => void submit(e)}>
              <label className="label" htmlFor="visitor-name">Your name</label>
              <input id="visitor-name" className="input" autoComplete="given-name" value={name} maxLength={60} required onChange={e => setName(e.target.value)} />
              <fieldset className="radio-list">
                <legend className="label">Reason for visiting</legend>
                {purposes.map(p => <label key={p} className="radio">
                  <input type="radio" name="purpose" value={p} checked={purpose === p} onChange={() => setPurpose(p)} />
                  <span>{p}</span>
                </label>)}
              </fieldset>
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="btn btn-primary btn-wide" disabled={busy || !name.trim()}>{busy ? 'Starting' : 'Start visit'}</button>
              <p className="hint hint-center">You get a short code to continue on another device.</p>
            </form>}
      </section>
    </div>
  </div>
}
