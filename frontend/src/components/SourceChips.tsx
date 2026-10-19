import { safeUrl } from '../api/client'
import type { Source } from '../api/client'

const host = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return '' } }

/** Footnote list under an answer. Numbers match the [n] markers in the answer text. */
export function Footnotes({ sources }: { sources: Source[] }) {
  if (!sources.length) return null
  return <ol className="footnotes" aria-label="Sources">
    {sources.map((s, i) => {
      const href = safeUrl(s.url), nums = s.citations?.length ? s.citations : [i + 1]
      return <li key={`${s.url}-${i}`}>
        <span className="fn-num mono">{nums.join(', ')}</span>
        <span className="fn-body">
          {href ? <a href={href} target="_blank" rel="noreferrer">{s.title}</a> : <span>{s.title}</span>}
          <span className="fn-meta">{href ? host(href) : 'Curated by the team'}{s.last_checked ? `, checked ${s.last_checked}` : ''}</span>
        </span>
      </li>
    })}
  </ol>
}

/** Renders answer text with [n] citation markers as superscript references. */
export function CitedText({ text }: { text: string }) {
  return <>{text.replace(/\s+(\[\d+\])/g, '$1').split(/(\[\d+\])/g).map((part, i) => /^\[\d+\]$/.test(part)
    ? <sup key={i} className="ref">{part.slice(1, -1)}</sup>
    : part)}</>
}
