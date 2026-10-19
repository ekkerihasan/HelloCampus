import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/play/keyboard.ts', import.meta.url), 'utf8')
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { keyboardAction } = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`)

test('versus: both buzz keys work, answers belong only to the locked player', () => {
  const game = { mode: 'versus', phase: 'buzz', active_player: null }
  assert.deepEqual(keyboardAction('A', game), { action: 'buzz', player: 0 })
  assert.deepEqual(keyboardAction('l', game), { action: 'buzz', player: 1 })
  assert.equal(keyboardAction('1', game), null)
  game.phase = 'answer'; game.active_player = 1
  assert.deepEqual(keyboardAction('4', game), { action: 'answer', player: 1, option: 3 })
  assert.equal(keyboardAction('a', game), null)
})
test('co-op: independent keyboard ranges address each player and every option', () => {
  const game = { mode: 'coop', phase: 'coop' }
  for (let option = 0; option < 4; option++) {
    assert.deepEqual(keyboardAction(String(option + 1), game), { action: 'answer', player: 0, option })
    assert.deepEqual(keyboardAction(['7', '8', '9', '0'][option], game), { action: 'answer', player: 1, option })
  }
  assert.equal(keyboardAction('a', game), null)
  assert.equal(keyboardAction('5', game), null)
})
test('only Enter advances reveals, no game key acts after completion', () => {
  assert.deepEqual(keyboardAction('Enter', { phase: 'reveal' }), { action: 'next' })
  assert.equal(keyboardAction('1', { phase: 'reveal' }), null)
  assert.equal(keyboardAction('Enter', { phase: 'finished' }), null)
})
