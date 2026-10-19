import { useCallback, useEffect, useRef, useState } from 'react'
import { request, safeUrl } from '../api/client'
import { advanceHold, emptyHold, holdProgress, optionIndex, pickDetection } from '../gesture/hold'
import type { Detection, GestureAction, HoldState } from '../gesture/hold'

type QuizItem = { id: string; question: string; options: string[]; answer_index: number; source_url: string; source_title: string; evidence: string }
type QuizConfig = { enabled: boolean; questions: number; per_game: number; answer_s: number; points_correct: number; time_bonus_per_s: number; hold_ms: number }
type GestureConfig = { available: boolean; detail: string; min_confidence: number; hold_ms: number; cooldown_ms: number; fps: number; frame_width: number }
type ScoreRow = { name: string; mode: string; score: number; at: string }
type Phase = 'intro' | 'question' | 'reveal' | 'done'
const LETTERS = ['A', 'B', 'C', 'D'], REVEAL_MS = 3000, MAX_GAP_MS = 600

/** One symbol per sign, the same on cards, rings and hints (ADDENDUM-04): finger bars for 1 to 4, a palm for start/next. */
export function Sign({ fingers, label }: { fingers: number; label?: string }) {
  return <span className="sign" aria-label={label || (fingers ? `${fingers} finger${fingers > 1 ? 's' : ''}` : 'open palm')}>
    {fingers ? Array.from({ length: fingers }, (_, i) => <i key={i} />) : <b>✋</b>}
  </span>
}

function speak(text: string) {
  try { window.speechSynthesis?.cancel(); window.speechSynthesis?.speak(new SpeechSynthesisUtterance(text)) } catch { /* Voice is optional. */ }
}

export function PlayMode({ playerName, onError }: { playerName: string; onError: (message: string) => void }) {
  const [config, setConfig] = useState<QuizConfig | null>(null), [gestures, setGestures] = useState<GestureConfig | null>(null)
  const [name, setName] = useState(playerName), [phase, setPhase] = useState<Phase>('intro')
  const [items, setItems] = useState<QuizItem[]>([]), [index, setIndex] = useState(0)
  const [picked, setPicked] = useState<number | null>(null), [score, setScore] = useState(0), [streak, setStreak] = useState(0)
  const [left, setLeft] = useState(0), [board, setBoard] = useState<ScoreRow[]>([]), [lastGain, setLastGain] = useState(0)
  const [cameraOn, setCameraOn] = useState(false), [detections, setDetections] = useState<Detection[]>([])
  const [hold, setHold] = useState<HoldState>(emptyHold()), [now, setNow] = useState(0)
  const video = useRef<HTMLVideoElement | null>(null), socket = useRef<WebSocket | null>(null), timer = useRef<number | undefined>(undefined)
  const deadline = useRef(0), holdRef = useRef<HoldState>(emptyHold())
  const state = useRef({ phase, index, picked, items, score }); state.current = { phase, index, picked, items, score }

  useEffect(() => {
    request<QuizConfig>('/api/quiz/config').then(setConfig).catch(e => onError(e instanceof Error ? e.message : 'The quiz could not load.'))
    request<GestureConfig>('/api/gesture/config').then(setGestures).catch(() => setGestures(null))
    request<ScoreRow[]>('/api/quiz/leaderboard').then(setBoard).catch(() => undefined)
  }, [onError])

  const start = useCallback(async () => {
    if (!name.trim()) { onError('Type your name first, then start.'); return }
    try {
      const game = await request<QuizItem[]>('/api/quiz/game')
      setItems(game); setIndex(0); setScore(0); setStreak(0); setPicked(null); setLastGain(0); setPhase('question')
      deadline.current = Date.now() + (config?.answer_s || 10) * 1000
      speak(game[0].question)
    } catch (e) { onError(e instanceof Error ? e.message : 'The quiz could not start.') }
  }, [name, config, onError])

  const answer = useCallback((choice: number | null) => {
    const s = state.current
    if (s.phase !== 'question' || s.picked !== null || !config) return
    const item = s.items[s.index], remaining = Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000))
    const correct = choice === item.answer_index
    const gain = correct ? config.points_correct + config.time_bonus_per_s * remaining : 0
    setPicked(choice ?? -1); setLastGain(gain); setScore(old => old + gain); setStreak(old => correct ? old + 1 : 0); setPhase('reveal')
    speak(correct ? `Correct! ${item.options[item.answer_index]}.` : choice === null ? `Time is up. It was ${item.options[item.answer_index]}.` : `Not quite. It was ${item.options[item.answer_index]}.`)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => next(), REVEAL_MS)
  }, [config]) // eslint-disable-line react-hooks/exhaustive-deps

  const next = useCallback(() => {
    const s = state.current
    window.clearTimeout(timer.current)
    if (s.phase !== 'reveal') return
    if (s.index + 1 >= s.items.length) {
      setPhase('done')
      // Side effects run once here, not inside a state updater (StrictMode calls updaters twice, which saved every game twice).
      const final = s.score
      request<ScoreRow[]>('/api/quiz/score', 'POST', { name: name.trim(), mode: 'solo', score: final }).then(setBoard).catch(() => undefined)
      speak(`Well played, ${name.trim()}. You scored ${final} points.`)
      return
    }
    setIndex(s.index + 1); setPicked(null); setPhase('question')
    deadline.current = Date.now() + (config?.answer_s || 10) * 1000
    speak(s.items[s.index + 1].question)
  }, [config, name])

  // Countdown: a missed answer is a timeout with no points.
  useEffect(() => {
    if (phase !== 'question') return
    const tick = window.setInterval(() => {
      const ms = deadline.current - Date.now()
      setLeft(Math.max(0, ms / 1000))
      if (ms <= 0) answer(null)
    }, 100)
    return () => window.clearInterval(tick)
  }, [phase, index, answer])

  const act = useCallback((action: GestureAction | 'start') => {
    const s = state.current
    if (action === 'palm' || action === 'start') { if (s.phase === 'intro' || s.phase === 'done') void start(); else if (s.phase === 'reveal') next(); return }
    const option = optionIndex(action)
    if (option !== null && s.phase === 'question') answer(option)
  }, [start, next, answer])

  // Keyboard mirror (ADDENDUM-04): 1 to 4 answer A to D, Space starts or skips. Fully playable with no camera.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement | null)?.tagName === 'INPUT') return
      if (e.code === 'Space') { e.preventDefault(); act('start') }
      const n = ['1', '2', '3', '4'].indexOf(e.key)
      if (n >= 0) act((['one', 'peace', 'three', 'four'] as GestureAction[])[n])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [act])

  // Camera: about fps JPEG frames over /ws/gesture, one in flight, hands only, nothing stored.
  useEffect(() => {
    if (!cameraOn || !gestures?.available) return
    let stopped = false, stream: MediaStream | null = null, busy = false, loop: number | undefined
    const canvas = document.createElement('canvas')
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/gesture`)
    ws.binaryType = 'arraybuffer'; socket.current = ws
    ws.onmessage = e => {
      busy = false
      const msg = JSON.parse(e.data as string)
      if (msg.type === 'error') { onError(msg.message); return }
      if (msg.type !== 'detections') return
      const found: Detection[] = msg.detections || [], t = Date.now()
      setDetections(found)
      const step = advanceHold(holdRef.current, pickDetection(found), t, gestures.min_confidence, gestures.hold_ms, gestures.cooldown_ms, MAX_GAP_MS)
      holdRef.current = step.state; setHold(step.state); setNow(t)
      if (step.action) act(step.action)
    }
    navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 } }, audio: false }).then(s => {
      if (stopped) { s.getTracks().forEach(tr => tr.stop()); return }
      stream = s
      if (video.current) { video.current.srcObject = s; void video.current.play() }
      loop = window.setInterval(() => {
        const v = video.current
        if (busy || ws.readyState !== WebSocket.OPEN || !v || !v.videoWidth) return
        canvas.width = gestures.frame_width; canvas.height = Math.round(v.videoHeight * gestures.frame_width / v.videoWidth)
        canvas.getContext('2d')?.drawImage(v, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(b => { if (b && ws.readyState === WebSocket.OPEN) { busy = true; void b.arrayBuffer().then(buf => ws.send(buf)) } }, 'image/jpeg', 0.7)
      }, 1000 / gestures.fps)
    }).catch(() => { onError('Camera access was blocked. You can still play with the keyboard.'); setCameraOn(false) })
    return () => { stopped = true; window.clearInterval(loop); ws.close(); socket.current = null; stream?.getTracks().forEach(tr => tr.stop()); setDetections([]) }
  }, [cameraOn, gestures, act, onError])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!config) return <section className="play-panel"><p>Loading the quiz…</p></section>
  if (!config.enabled) return <section className="play-panel"><h1>Get to Know AITM</h1><p>This needs more campus data first.</p></section>
  const item = items[index], holding = hold.label ? optionIndex(hold.label) : null, ring = holdProgress(hold, now, gestures?.hold_ms || config.hold_ms)
  return <section className="play-panel">
    <div className="eyebrow">GET TO KNOW AITM</div>
    <div className="play-layout">
      <div className="play-main">
        {phase === 'intro' && <div className="play-card"><h1>Get to Know AITM: how well do you know this campus?</h1><p>{config.per_game} questions, {config.answer_s} seconds each. Every answer comes from AITM's own pages.</p>
          <label htmlFor="player">Your name</label><input id="player" value={name} maxLength={30} onChange={e => setName(e.target.value)} />
          <p className="play-hint">Show <Sign fingers={0} /> or press <kbd>Space</kbd> to start. Answer with <Sign fingers={1} /> <Sign fingers={2} /> <Sign fingers={3} /> <Sign fingers={4} /> or keys <kbd>1</kbd> to <kbd>4</kbd>.</p>
          <button className="primary" onClick={() => void start()}>Start ↗</button></div>}
        {(phase === 'question' || phase === 'reveal') && item && <div className="play-card">
          <div className="play-status"><span>Question {index + 1} of {items.length}</span><span>Score {score}{streak > 1 ? ` · streak ${streak}` : ''}</span>{phase === 'question' && <span className={left <= 3 ? 'timer low' : 'timer'}>{Math.ceil(left)} s</span>}</div>
          {phase === 'question' && <div className="timer-bar"><i style={{ width: `${(left / config.answer_s) * 100}%` }} /></div>}
          <h2>{item.question}</h2>
          <ol className="options">{item.options.map((o, i) => {
            const state = phase === 'reveal' ? (i === item.answer_index ? 'correct' : i === picked ? 'wrong' : '') : ''
            return <li key={i} className={`option ${state}`}><button disabled={phase !== 'question'} onClick={() => answer(i)}>
              <Sign fingers={i + 1} /><b>{LETTERS[i]}</b><span>{o}</span><kbd>{i + 1}</kbd>
              {holding === i && phase === 'question' && <span className="hold-ring" style={{ ['--p' as string]: ring }} />}
            </button></li>
          })}</ol>
          {phase === 'reveal' && <div className="reveal"><strong>{picked === item.answer_index ? `Correct! +${lastGain}` : picked === -1 ? 'Time is up.' : 'Not quite.'}</strong>
            <span>From the college site: “{item.evidence}”</span>
            {safeUrl(item.source_url) && <div className="source-chips"><a href={safeUrl(item.source_url)} target="_blank" rel="noreferrer">[1] {item.source_title || 'AITM'} ↗</a></div>}
            <small>Show <Sign fingers={0} /> or press <kbd>Space</kbd> for the next question.</small></div>}
        </div>}
        {phase === 'done' && <div className="play-card"><h1>{score} points</h1><p>Well played, {name}. You just got to know AITM a little better, and every answer came from its own pages.</p>
          <button className="primary" onClick={() => void start()}>Play again ↗</button><p className="play-hint">Or show <Sign fingers={0} /> / press <kbd>Space</kbd>.</p></div>}
      </div>
      <aside className="play-side">
        <div className="play-camera">
          {gestures?.available ? <><div className="camera-frame"><video ref={video} className={cameraOn ? 'camera-preview on mirrored' : 'camera-preview'} playsInline muted />
            {cameraOn && detections.map((d, i) => <div key={i} className="hand-box" style={{ left: `${(1 - d.box[2]) * 100}%`, top: `${d.box[1] * 100}%`, width: `${(d.box[2] - d.box[0]) * 100}%`, height: `${(d.box[3] - d.box[1]) * 100}%` }}><span>{d.label} {Math.round(d.confidence * 100)}%</span></div>)}</div>
            <button className="secondary" onClick={() => setCameraOn(on => !on)}>{cameraOn ? 'Camera off' : '▣ Play with hand signs'}</button>
            <small>Only hand shapes are detected. Nobody is identified and no frame is stored.</small></>
            : <small>{gestures ? `Hand signs unavailable: ${gestures.detail}` : 'Hand signs unavailable.'} Keyboard play works.</small>}
        </div>
        <div className="leaderboard"><h3>Get to Know AITM: today's top scores</h3>{board.length ? <ol>{board.map((r, i) => <li key={i}><span>{r.name}</span><b>{r.score}</b></li>)}</ol> : <p>No scores yet. Be the first.</p>}</div>
      </aside>
    </div>
  </section>
}
