import { strict as assert } from 'node:assert'
import test from 'node:test'
import { advanceHold, emptyHold } from '../src/gesture/hold.ts'

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
  const switched = advance(initial, detection('like'), 600)
  assert.equal(switched.action, undefined)
  assert.equal(switched.state.since, 600)
  const stale = advance(initial, detection(), 1200)
  assert.equal(stale.action, undefined)
  assert.equal(stale.state.since, 1200)
})
