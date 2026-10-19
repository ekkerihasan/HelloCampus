// Hand-sign hold logic for the Buzzer Quiz (ADDENDUM-04). Pure functions, no DOM, so they are unit tested.
export type GestureAction = 'palm' | 'one' | 'peace' | 'three' | 'four'
export type Detection = { label: string; confidence: number; box: [number, number, number, number] }
export type HoldState = { label: GestureAction | null; since: number; lastSeen: number; cooldownUntil: number }
export type Side = 'left' | 'right'

const ACTIONS: readonly GestureAction[] = ['palm', 'one', 'peace', 'three', 'four']
// Option A to D each have their own sign; palm is start or next in Solo and buzz in Versus.
export const OPTION_SIGNS: readonly GestureAction[] = ['one', 'peace', 'three', 'four']

export const emptyHold = (): HoldState => ({ label: null, since: 0, lastSeen: 0, cooldownUntil: 0 })
export const isAction = (label: string): label is GestureAction => (ACTIONS as readonly string[]).includes(label)

/** Option index 0 to 3 for an answer sign, or null for palm and anything else. */
export const optionIndex = (action: GestureAction): number | null => {
  const i = OPTION_SIGNS.indexOf(action)
  return i >= 0 ? i : null
}

/** Strongest actionable detection, optionally only on one half of the mirrored preview (Versus). */
export function pickDetection(detections: Detection[], side?: Side, mirrored = true): Detection | undefined {
  let best: Detection | undefined
  for (const d of detections) {
    if (!isAction(d.label)) continue
    if (side) {
      const centre = (d.box[0] + d.box[2]) / 2
      // The camera frame is unmirrored; the player sees a mirror, so their left is the frame's right.
      const onLeft = mirrored ? centre >= 0.5 : centre < 0.5
      if ((side === 'left') !== onLeft) continue
    }
    if (!best || d.confidence > best.confidence) best = d
  }
  return best
}

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

/** Fill fraction 0 to 1 for the hold ring. */
export const holdProgress = (state: HoldState, now: number, holdMs: number): number =>
  state.label ? Math.min(1, Math.max(0, (now - state.since) / holdMs)) : 0
