// Integration smoke for a running isolated preview and a headless Chrome CDP port.
// Run from frontend: node tests/play-browser.mjs
// Browser: --headless=new --remote-debugging-port=9223 (use a temporary profile).
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const preview = process.env.PLAY_PREVIEW_URL || 'http://localhost:5174/play.html?api=http://127.0.0.1:8001/api/quiz'
const debug = process.env.PLAY_CDP_URL || 'http://127.0.0.1:9223'
const bank = (await readFile(new URL('../../data/clean/quiz.jsonl', import.meta.url), 'utf8')).trim().split('\n').map(JSON.parse)
const targets = await (await fetch(`${debug}/json`)).json()
const target = targets.find(value => value.type === 'page')
assert.ok(target, 'Chrome needs an open page')
const socket = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
let nextId = 0
const calls = new Map()
const errors = []
socket.onmessage = event => {
  const message = JSON.parse(event.data)
  if (message.id) {
    const pending = calls.get(message.id)
    if (pending) { calls.delete(message.id); message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result) }
  } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
}
function cdp(method, params = {}) {
  const id = ++nextId
  return new Promise((resolve, reject) => { calls.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })) })
}
async function evaluate(expression) {
  const result = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function waitFor(expression, label) {
  for (let tries = 0; tries < 100; tries++) {
    const value = await evaluate(expression)
    if (value) return value
    await sleep(60)
  }
  throw new Error(`Timed out: ${label}. ${await evaluate('document.body.innerText')}`)
}
async function key(value) {
  await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: value, windowsVirtualKeyCode: value === 'Enter' ? 13 : value.toUpperCase().charCodeAt(0), text: value === 'Enter' ? '\r' : value, code: value === 'Enter' ? 'Enter' : /^\d$/.test(value) ? `Digit${value}` : `Key${value.toUpperCase()}` })
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: value })
}
async function state() { return evaluate('window.__quizState') }
async function start(mode) {
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent===${JSON.stringify(mode === 'coop' ? 'Co-op' : 'Versus')}).click()`)
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>/^(Start game|Play again)$/.test(b.textContent)).focus()")
  await key('Enter')
  return waitFor(`window.__quizState?.mode===${JSON.stringify(mode)} && window.__quizState?.phase===${JSON.stringify(mode === 'coop' ? 'coop' : 'buzz')} && window.__quizState`, `${mode} started`)
}
async function reveal(number) {
  await waitFor(`window.__quizState?.phase==='reveal' && window.__quizState.question_number===${number}`, 'answer reveal')
  await waitFor("document.querySelector('.play-question blockquote a')?.href", 'source evidence visible')
}
try {
  await cdp('Page.enable')
  await cdp('Runtime.enable')
  await cdp('Page.addScriptToEvaluateOnNewDocument', { source: `
    const originalFetch = window.fetch;
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      if (String(args[0]).includes('/api/quiz/')) {
        response.clone().json().then(data => { if (data.id && data.phase) window.__quizState = data }).catch(()=>{});
      }
      return response;
    };
  ` })
  await cdp('Page.navigate', { url: preview })
  await waitFor("document.querySelector('.play-primary') && !document.querySelector('.play-primary').disabled", 'ready bank')
  for (let player = 0; player < 2; player++) {
    await evaluate(`document.querySelectorAll('.play-names input')[${player}].focus()`)
    await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers: 2 })
    await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', modifiers: 2 })
    await cdp('Input.insertText', { text: `Keyboard smoke P${player + 1}` })
  }
  let game = await start('versus')
  // A focused text field must not capture gameplay shortcuts.
  await evaluate("const typing=document.createElement('input'); typing.id='typing-check'; document.body.append(typing); typing.focus()")
  await key('a')
  await sleep(300)
  assert.equal((await state()).phase, 'buzz')
  await evaluate("document.querySelector('#typing-check').remove()")
  for (let number = 1; number <= 5; number++) {
    game = await state()
    const item = bank.find(item => item.id === game.question.id)
    assert.ok(item, 'browser questions come from the stored bank')
    assert.equal(game.question.answer_index, undefined, 'answers stay hidden before reveal')
    await key('a')
    await waitFor("window.__quizState?.phase==='answer' && window.__quizState.active_player===0", 'P1 buzz')
    if (number === 1) {
      await key(String((item.answer_index + 1) % 4 + 1))
      await waitFor("window.__quizState?.phase==='answer' && window.__quizState.active_player===1", 'wrong answer passed to P2')
    }
    await key(String(item.answer_index + 1))
    await reveal(number)
    await key('Enter')
    await waitFor(`window.__quizState?.phase===${JSON.stringify(number === 5 ? 'finished' : 'buzz')}`, 'next versus question')
  }
  game = await state()
  assert.deepEqual(game.scores, [4, 1])
  console.log('PASS: full versus keyboard game, answer secrecy, pass once, source reveal, typing focus, scores 4/1')
  game = await start('coop')
  for (let number = 1; number <= 5; number++) {
    game = await state()
    const item = bank.find(item => item.id === game.question.id)
    await key(String(item.answer_index + 1))
    if (number === 1) {
      await key(['7', '8', '9', '0'][(item.answer_index + 1) % 4])
      await sleep(700)
      assert.equal((await state()).phase, 'coop', 'disagreement does not lock')
    }
    await key(['7', '8', '9', '0'][item.answer_index])
    await waitFor('window.__quizState?.hold_remaining_ms > 0', 'agreement hold')
    await reveal(number)
    await key('Enter')
    await waitFor(`window.__quizState?.phase===${JSON.stringify(number === 5 ? 'finished' : 'coop')}`, 'next co-op question')
  }
  game = await state()
  assert.equal(game.team_score, 15)
  assert.equal(game.streak, 5)
  await waitFor("document.querySelector('.play-leaderboard ol')?.innerText.includes('15')", 'persisted score displayed')
  await cdp('Page.reload')
  await waitFor("document.querySelector('.play-primary') && !document.querySelector('.play-primary').disabled", 'reload ready')
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Co-op').click()")
  await waitFor("document.querySelector('.play-leaderboard ol')?.innerText.includes('Keyboard smoke P1')", 'SQLite leaderboard survives page reload')
  assert.deepEqual(errors, [], 'no uncaught browser errors')
  console.log('PASS: full co-op keyboard game, disagreement, 500ms agreement, streak 5, score 15, SQLite leaderboard survives page reload')
} finally { socket.close() }
