export type Mode = 'versus' | 'coop'
export type Player = 0 | 1
export type Game = {
  id: string; mode: Mode; players: [string, string]; scores: [number, number]
  team_score: number; streak: number; phase: 'buzz' | 'answer' | 'coop' | 'reveal' | 'finished'
  active_player: Player | null; question_number: number; total_questions: number
  revision: number; server_now_ms: number; remaining_ms: number | null; hold_remaining_ms: number | null
  question: { id: string; question: string; options: string[]; answer_index?: number; evidence?: string; source_url?: string } | null
  selections: [number | null, number | null]; message?: string
}
export type Config = { enabled: boolean; ready: boolean; question_count: number; questions_per_game: number; hold_ms?: number }
export type Score = { name: string; mode: Mode; score: number; ts: number | string }
export type Action = { action: 'buzz' | 'answer' | 'next' | 'tick'; player?: Player; option?: number }
