import type { Action, Game } from './types'

export function keyboardAction(key: string, game: Game): Action | null {
  if (game.phase === 'finished') return null
  if (game.phase === 'reveal') return key === 'Enter' ? { action: 'next' } : null
  const lower = key.toLowerCase()
  if (game.mode === 'versus') {
    if (game.phase === 'buzz' && (lower === 'a' || lower === 'l')) return { action: 'buzz', player: lower === 'a' ? 0 : 1 }
    if (game.phase === 'answer' && game.active_player !== null && /^[1-4]$/.test(key)) return { action: 'answer', player: game.active_player, option: Number(key) - 1 }
  } else if (game.phase === 'coop') {
    if (/^[1-4]$/.test(key)) return { action: 'answer', player: 0, option: Number(key) - 1 }
    const option = ['7', '8', '9', '0'].indexOf(key)
    if (option >= 0) return { action: 'answer', player: 1, option }
  }
  return null
}

export function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || Boolean(target.closest('input, textarea, select')))
}
