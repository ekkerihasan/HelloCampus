import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { request, safeUrl } from '../api/client'
import type { Candidate, Visitor } from '../api/client'
import { Icon } from '../components/Icon'

type Panel =
  | { kind: 'interview'; who: Candidate; questions: { text: string; url: string }[] }
  | { kind: 'readme'; who: Candidate; before: string; after: string }

const examples = ['Frontend intern with React projects', 'Backend developer, Python and APIs', 'ML engineer with computer vision work']
const errorMessage = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Please try again.'
const repoName = (url: string) => { try { return new URL(url).pathname.replace(/^\/|\/$/g, '') || url } catch { return url } }
const scrollTo = (id: string) => requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))

export function Talent({ visitor, onError }: { visitor: Visitor; onError: (message: string) => void }) {
  const [description, setDescription] = useState(''), [busy, setBusy] = useState(''), [searched, setSearched] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([]), [shortlist, setShortlist] = useState<Candidate[]>([])
  const [selected, setSelected] = useState<string[]>([]), [comparison, setComparison] = useState<Candidate[]>([])
  const [panel, setPanel] = useState<Panel | null>(null)

  useEffect(() => {
    request<Candidate[]>(`/api/hiring/shortlist/${visitor.id}`).then(setShortlist).catch(e => onError(errorMessage(e)))
  }, [visitor.id, onError])

  async function perform(label: string, action: () => Promise<void>) {
    setBusy(label); onError('')
    try { await action() } catch (e) { onError(errorMessage(e)) } finally { setBusy('') }
  }
  async function find(e: FormEvent) {
    e.preventDefault()
    await perform('match', async () => {
      await request('/api/hiring/role', 'POST', { visitor_id: visitor.id, description })
      setCandidates(await request<Candidate[]>('/api/hiring/match', 'POST', { visitor_id: visitor.id }))
      setSearched(true); setComparison([]); setPanel(null)
    })
  }
  const isShortlisted = (c: Candidate) => shortlist.some(s => s.entity_id === c.entity_id)
  async function toggleShortlist(c: Candidate) {
    await perform(`shortlist-${c.entity_id}`, async () => {
      if (isShortlisted(c)) await request(`/api/hiring/shortlist/${visitor.id}/${c.entity_id}`, 'DELETE')
      else await request('/api/hiring/shortlist', 'POST', { visitor_id: visitor.id, entity_id: c.entity_id })
      setShortlist(await request<Candidate[]>(`/api/hiring/shortlist/${visitor.id}`))
    })
  }

  // Matches first, then anything shortlisted earlier that is not in the current matches.
  const people = [...new Map([...candidates, ...shortlist].map(c => [c.entity_id, c])).values()]

  return <div className="page talent">
    <header className="page-head">
      <h1>Talent</h1>
      <p className="lede">Describe a role. Matches come only from students who opted in, and each claim links to their published work.</p>
    </header>

    <form className="role" onSubmit={e => void find(e)}>
      <label className="label" htmlFor="role">Role description</label>
      <textarea id="role" className="input" rows={3} required minLength={3} maxLength={6000} value={description}
        placeholder="Skills, level and whether the role is remote or on site" onChange={e => setDescription(e.target.value)} />
      <div className="role-foot">
        <p className="examples">Examples: {examples.map((x, i) => <span key={x}>{i > 0 && ', '}<button type="button" className="btn-text" onClick={() => setDescription(x)}>{x.toLowerCase()}</button></span>)}</p>
        <button className="btn btn-primary" disabled={!!busy || description.trim().length < 3}>{busy === 'match' ? 'Matching' : 'Find matches'}</button>
      </div>
    </form>

    {(people.length > 0 || searched) && <div className="results-bar">
      <p className="num">{candidates.length} {candidates.length === 1 ? 'match' : 'matches'}, {shortlist.length} shortlisted</p>
      <div className="results-actions">
        <button className="btn btn-secondary" disabled={!!busy || selected.length !== 2}
          onClick={() => void perform('compare', async () => {
            setComparison(await request<Candidate[]>('/api/hiring/compare', 'POST', { entity_ids: selected })); scrollTo('talent-compare')
          })}>
          Compare selected{selected.length ? <span className="num"> ({selected.length} of 2)</span> : null}
        </button>
        {shortlist.length > 0 && <a className="btn btn-secondary" href={`/api/hiring/export/${visitor.id}`}><Icon name="download" size={16} />Export shortlist</a>}
      </div>
    </div>}

    {searched && candidates.length === 0 && <div className="empty-note">
      <h2>No verified matches</h2>
      <p>Matches appear once students have opted in and their public projects are indexed. A broader description may help.</p>
    </div>}

    {people.length > 0 && <ul className="directory">
      {people.map(c => <li key={c.entity_id} id={`candidate-${c.entity_id}`} className="person">
        <div className="person-main">
          <div className="person-head">
            <h2>{c.name}</h2>
            {isShortlisted(c) && <span className="flag">Shortlisted</span>}
          </div>
          <p className="person-meta"><span className="mono">@{c.entity_id}</span>{c.headline && <>, {c.headline}</>}{c.languages.length > 0 && <>. {c.languages.join(', ')}</>}</p>
          {c.claims.length > 0 && <ul className="claims">
            {c.claims.map((claim, i) => <li key={i}>{claim.text}{safeUrl(claim.url) && <> <a href={safeUrl(claim.url)} target="_blank" rel="noreferrer">Evidence</a></>}</li>)}
          </ul>}
          {c.sources.length > 0 && <p className="repos">Projects: {c.sources.map((url, i) => <span key={url}>{i > 0 && ', '}<a href={safeUrl(url)} target="_blank" rel="noreferrer">{repoName(url)}</a></span>)}</p>}
        </div>
        <div className="person-actions">
          <button className={`btn ${isShortlisted(c) ? 'btn-secondary is-active' : 'btn-secondary'}`} disabled={!!busy} aria-pressed={isShortlisted(c)} onClick={() => void toggleShortlist(c)}>
            {isShortlisted(c) ? 'Remove from shortlist' : 'Add to shortlist'}
          </button>
          <button className="btn btn-secondary" disabled={!!busy} onClick={() => void perform(`kit-${c.entity_id}`, async () => {
            setPanel({ kind: 'interview', who: c, questions: await request(`/api/hiring/interview/${c.entity_id}`, 'POST') }); scrollTo('talent-panel')
          })}>{busy === `kit-${c.entity_id}` ? 'Writing questions' : 'Interview questions'}</button>
          <button className="btn btn-secondary" disabled={!!busy} onClick={() => void perform(`readme-${c.entity_id}`, async () => {
            setPanel({ kind: 'readme', who: c, ...await request<{ before: string; after: string }>(`/api/students/${c.entity_id}/readme`, 'POST') }); scrollTo('talent-panel')
          })}>{busy === `readme-${c.entity_id}` ? 'Drafting README' : 'Improve README'}</button>
          <label className="check">
            <input type="checkbox" checked={selected.includes(c.entity_id)} disabled={!!busy || (!selected.includes(c.entity_id) && selected.length >= 2)}
              onChange={e => setSelected(old => e.target.checked ? [...old, c.entity_id] : old.filter(id => id !== c.entity_id))} />
            Compare
          </label>
        </div>
      </li>)}
    </ul>}

    {comparison.length === 2 && <section id="talent-compare" className="block">
      <div className="block-head"><h2>Side by side</h2><button className="btn-text" onClick={() => setComparison([])}>Close</button></div>
      <div className="table-wrap"><table className="table">
        <thead><tr><th scope="col"><span className="sr-only">Field</span></th>{comparison.map(c => <th key={c.entity_id} scope="col">{c.name}</th>)}</tr></thead>
        <tbody>
          <tr><th scope="row">Languages</th>{comparison.map(c => <td key={c.entity_id}>{c.languages.join(', ') || 'Not recorded'}</td>)}</tr>
          <tr><th scope="row">Evidence</th>{comparison.map(c => <td key={c.entity_id}>{c.claims.length ? <ul className="plain">{c.claims.map((x, i) => <li key={i}>{x.text}</li>)}</ul> : 'Not recorded'}</td>)}</tr>
          <tr><th scope="row">Projects</th>{comparison.map(c => <td key={c.entity_id}><ul className="plain">{c.sources.map(url => <li key={url}><a href={safeUrl(url)} target="_blank" rel="noreferrer">{repoName(url)}</a></li>)}</ul></td>)}</tr>
        </tbody>
      </table></div>
    </section>}

    {panel && <section id="talent-panel" className="block">
      <div className="block-head">
        <h2>{panel.kind === 'interview' ? `Interview questions: ${panel.who.name}` : `Profile README: ${panel.who.name}`}</h2>
        <button className="btn-text" onClick={() => setPanel(null)}>Close</button>
      </div>
      {panel.kind === 'interview'
        ? <ol className="questions">{panel.questions.map((q, i) => <li key={i}><p>{q.text}</p>{safeUrl(q.url) && <a className="source-link" href={safeUrl(q.url)} target="_blank" rel="noreferrer">Based on {repoName(q.url)}</a>}</li>)}</ol>
        : <div className="docs">
            <div><h3>Current</h3><pre>{panel.before || 'No profile README yet.'}</pre></div>
            <div><h3>Suggested</h3><pre>{panel.after}</pre></div>
          </div>}
    </section>}
  </div>
}
