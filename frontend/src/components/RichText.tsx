import type { ReactNode } from 'react'

// Minimal, safe markdown for chat answers: **bold**, *italic*, bullet and numbered lists, paragraphs.
// Built as React elements (never innerHTML), so model text can never inject markup.
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = []
  const pattern = /\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*/g
  let last = 0, match: RegExpExecArray | null, i = 0
  while ((match = pattern.exec(text))) {
    if (match.index > last) out.push(text.slice(last, match.index))
    out.push(match[1] !== undefined ? <strong key={`${key}-${i++}`}>{match[1]}</strong> : <em key={`${key}-${i++}`}>{match[2]}</em>)
    last = match.index + match[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let list: { ordered: boolean; items: string[] } | null = null
  let paragraph: string[] = []
  const flushParagraph = () => { if (paragraph.length) { blocks.push(<p key={`p${blocks.length}`}>{inline(paragraph.join(' '), `p${blocks.length}`)}</p>); paragraph = [] } }
  const flushList = () => {
    if (!list) return
    const items = list.items.map((item, i) => <li key={i}>{inline(item, `l${blocks.length}-${i}`)}</li>)
    blocks.push(list.ordered ? <ol key={`l${blocks.length}`}>{items}</ol> : <ul key={`l${blocks.length}`}>{items}</ul>)
    list = null
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const bullet = /^[*\-•]\s+(.*)$/.exec(line), numbered = /^\d+[.)]\s+(.*)$/.exec(line)
    if (bullet || numbered) {
      flushParagraph()
      const ordered = Boolean(numbered)
      if (list && list.ordered !== ordered) flushList()
      list ??= { ordered, items: [] }
      list.items.push((bullet || numbered)![1])
    } else if (!line) { flushParagraph(); flushList() }
    else { flushList(); paragraph.push(line.replace(/^#{1,6}\s+/, '')) }
  }
  flushParagraph(); flushList()
  return <>{blocks}</>
}
