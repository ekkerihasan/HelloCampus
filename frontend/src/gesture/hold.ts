export type GestureAction = 'palm' | 'like' | 'dislike' | 'ok' | 'peace'
export type Detection = { label: string; confidence: number; box: [number, number, number, number] }
export type HoldState = { label: GestureAction | null; since: number; lastSeen: number; cooldownUntil: number }
export const emptyHold = (): HoldState => ({ label: null, since: 0, lastSeen: 0, cooldownUntil: 0 })
export const isAction = (label: string): label is GestureAction => ['palm', 'like', 'dislike', 'ok', 'peace'].includes(label)

// An action requires a fresh detection at the end of the hold period.
export function advanceHold(state: HoldState, detection: Detection | undefined, now: number,
  minConfidence: number, holdMs: number, cooldownMs: number, maxGapMs: number): { state: HoldState; action?: GestureAction } {
  if (now < state.cooldownUntil || !detection || !isAction(detection.label) || detection.confidence < minConfidence) {
    return { state: { ...state, label: null, since: 0, lastSeen: now } }
  }
  if (state.label !== detection.label || now - state.lastSeen > maxGapMs) {
    return { state: { ...state, label: detection.label, since: now, lastSeen: now } }
  }
  if (now - state.since >= holdMs) {
    return { state: { label: null, since: 0, lastSeen: now, cooldownUntil: now + cooldownMs }, action: detection.label }
  }
  return { state: { ...state, lastSeen: now } }
}
