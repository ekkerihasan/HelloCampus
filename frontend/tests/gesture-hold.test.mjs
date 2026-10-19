import { strict as assert } from 'node:assert'
import test from 'node:test'
import { advanceHold, emptyHold, holdProgress, optionIndex, pickDetection } from '../src/gesture/hold.ts'

const detection = (label = 'palm', confidence = .9) => ({ label, confidence, box: [0, 0, 1, 1] })
const advance = (state, frame, now) => advanceHold(state, frame, now, .5, 500, 1500, 1000)

test('requires 500ms of the same label and a fresh final detection', () => {
  let state = advance(emptyHold(), detection(), 100).state
  let next = advance(state, detection(), 599)
  assert.equal(next.action, undefined)
  next = advance(next.state, detection(), 600)
  assert.equal(next.action, 'palm')
  assert.equal(next.state.cooldownUntil, 2100)
})

test('cooldown blocks repeated gestures and requires another full hold', () => {
  let state = advance(emptyHold(), detection('peace'), 100).state
  state = advance(state, detection('peace'), 600).state
  let next = advance(state, detection('peace'), 2099)
  assert.equal(next.action, undefined)
  next = advance(next.state, detection('peace'), 2100)
  assert.equal(next.action, undefined)
  assert.equal(advance(next.state, detection('peace'), 2600).action, 'peace')
})

test('confidence loss, no gesture, and missing hand reset a hold', () => {
  for (const frame of [undefined, detection('palm', .49), detection('no_gesture')]) {
    const initial = advance(emptyHold(), detection(), 100).state
    const reset = advance(initial, frame, 400)
    assert.equal(reset.state.label, null)
    assert.equal(advance(reset.state, detection(), 600).action, undefined)
  }
})

test('label switches and stale frames restart the timer', () => {
  const initial = advance(emptyHold(), detection(), 100).state
  const switched = advance(initial, detection('one'), 600)
  assert.equal(switched.action, undefined)
  assert.equal(switched.state.since, 600)
  const stale = advance(initial, detection(), 1200)
  assert.equal(stale.action, undefined)
  assert.equal(stale.state.since, 1200)
})

test('each answer sign maps to its own option and palm is not an answer', () => {
  assert.deepEqual(['one', 'peace', 'three', 'four'].map(optionIndex), [0, 1, 2, 3])
  assert.equal(optionIndex('palm'), null)
})

test('pickDetection ignores no_gesture and picks the strongest sign', () => {
  const frames = [detection('no_gesture', .99), detection('one', .6), detection('three', .8)]
  assert.equal(pickDetection(frames).label, 'three')
  assert.equal(pickDetection([detection('no_gesture', .9)]), undefined)
})

test('pickDetection splits players by mirrored half of the frame', () => {
  const at = (label, x1, x2) => ({ label, confidence: .9, box: [x1, .2, x2, .6] })
  const frames = [at('one', .1, .3), at('four', .6, .9)]
  // Mirrored preview: the frame's right half is the player's left.
  assert.equal(pickDetection(frames, 'left').label, 'four')
  assert.equal(pickDetection(frames, 'right').label, 'one')
  assert.equal(pickDetection(frames, 'left', false).label, 'one')
})

test('holdProgress fills from 0 to 1 over the hold time', () => {
  const state = advance(emptyHold(), detection('peace'), 100).state
  assert.equal(holdProgress(state, 100, 500), 0)
  assert.equal(holdProgress(state, 350, 500), 0.5)
  assert.equal(holdProgress(state, 900, 500), 1)
  assert.equal(holdProgress(emptyHold(), 900, 500), 0)
})
