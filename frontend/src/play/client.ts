import type { Action, Config, Game, Mode, Score } from './types'

async function request<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(typeof error?.detail === 'string' ? error.detail : `Quiz request failed (${response.status}).`)
  }
  return response.json() as Promise<T>
}
export function quizClient(base: string) {
  return {
    config: () => request<Config>(`${base}/config`),
    leaderboard: (mode: Mode) => request<{ entries: Score[] }>(`${base}/leaderboard?mode=${mode}`),
    start: (mode: Mode, players: [string, string]) => request<Game>(`${base}/start`, { mode, players }),
    get: (id: string) => request<Game>(`${base}/${encodeURIComponent(id)}`),
    action: (id: string, action: Action) => request<Game>(`${base}/${encodeURIComponent(id)}/action`, action),
  }
}
