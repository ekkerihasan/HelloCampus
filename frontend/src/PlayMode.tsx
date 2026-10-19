import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { quizClient } from './play/client'
import { isTyping, keyboardAction } from './play/keyboard'
import type { Action, Config, Game, Mode, Score } from './play/types'
import './PlayMode.css'

export default function PlayMode({ apiBase = '/api/quiz', initialPlayers = ['Player 1', 'Player 2'] }: { apiBase?: string; initialPlayers?: [string, string] }) {
  const api = useMemo(() => quizClient(apiBase), [apiBase])
  const [config, setConfig] = useState<Config | null>(null)
  const [mode, setMode] = useState<Mode>('versus')
  const [players, setPlayers] = useState<[string, string]>(initialPlayers)
  const [game, setGame] = useState<Game | null>(null)
  const [scores, setScores] = useState<Score[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const actionQueue = useRef<Promise<void>>(Promise.resolve())
  const polling = useRef(false)
  const active = game !== null && game.phase !== 'finished'
  const gameId = game?.id
  const gamePhase = game?.phase

  useEffect(() => {
    let ignore = false
    api.config().then(value => { if (!ignore) setConfig(value) }).catch(err => { if (!ignore) setError(String(err.message)) })
    return () => { ignore = true }
  }, [api])
  useEffect(() => {
    let ignore = false
    api.leaderboard(mode).then(value => { if (!ignore) setScores(value.entries) }).catch(err => { if (!ignore) setError(String(err.message)) })
    return () => { ignore = true }
  }, [api, mode, game?.phase])

  const act = useCallback(async (action: Action) => {
    if (!game) return
    const id = game.id
    actionQueue.current = actionQueue.current.then(async () => {
      try {
        const updated = await api.action(id, action)
        setGame(current => current?.id === id && updated.revision >= current.revision ? updated : current)
        setError('')
      } catch (err) { setError(err instanceof Error ? err.message : 'Could not update the game.') }
    })
    await actionQueue.current
  }, [api, game])

  useEffect(() => {
    if (!gameId || gamePhase === 'finished') return
    const id = gameId
    const timer = window.setInterval(() => {
      if (polling.current) return
      polling.current = true
      api.get(id).then(updated => {
        setGame(current => current?.id === id && updated.revision >= current.revision ? updated : current)
      }).catch(err => setError(err instanceof Error ? err.message : 'Could not refresh the game.')).finally(() => { polling.current = false })
    }, 200)
    return () => window.clearInterval(timer)
  }, [api, gameId, gamePhase])
  useEffect(() => {
    if (!game) return
    const keydown = (event: KeyboardEvent) => {
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) return
      const action = keyboardAction(event.key, game)
      if (action) { event.preventDefault(); void act(action) }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [act, game])
  useEffect(() => () => { window.speechSynthesis?.cancel() }, [game?.question?.id])

  async function start() {
    setBusy(true)
    try { setGame(await api.start(mode, players)); setError('') }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not start the game.') }
    finally { setBusy(false) }
  }
  function readQuestion() {
    if (!game?.question || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const { question, options } = game.question
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(`${question}. ${options.map((option, i) => `${i + 1}. ${option}`).join('. ')}`))
  }
  const question = game?.question
  const revealed = game?.phase === 'reveal' || game?.phase === 'finished'
  const safeSource = question?.source_url && /^https?:\/\//i.test(question.source_url) ? question.source_url : undefined

  return <section className="play-mode" aria-labelledby="play-title">
    <header className="play-header"><div><p className="play-eyebrow">Campus challenge</p><h1 id="play-title">Play together</h1><p>Two players. Five questions. Answers backed by campus sources.</p></div><span className="play-badge">Keyboard ready</span></header>
    <div className="play-layout"><main>
      <fieldset className="play-setup" disabled={active || busy}><legend>Set up your game</legend>
        <div className="play-modes"><button type="button" aria-pressed={mode === 'versus'} onClick={() => setMode('versus')}>Versus</button><button type="button" aria-pressed={mode === 'coop'} onClick={() => setMode('coop')}>Co-op</button></div>
        <div className="play-names">{players.map((name, index) => <label key={index}>Player {index + 1}<input value={name} maxLength={40} onChange={event => setPlayers(current => index === 0 ? [event.target.value, current[1]] : [current[0], event.target.value])} /></label>)}</div>
      </fieldset>
      <p className="play-instructions">{mode === 'versus' ? 'A buzzes Player 1. L buzzes Player 2. The locked player answers with 1 to 4. A miss passes the question once.' : 'Player 1 selects with 1 to 4. Player 2 selects with 7, 8, 9, 0. Agree for half a second to lock your answer. Keep a streak for bonus points.'} Press Enter after a reveal.</p>
      {error && <p role="alert" className="play-error">{error}</p>}
      {config && !config.enabled && <p role="status">Play is currently switched off.</p>}
      {config?.enabled && !config.ready && <p role="status">Quiz needs more campus data. {config.question_count} verified questions available; {config.questions_per_game} needed.</p>}
      {!active && <button className="play-primary" disabled={busy || !config?.enabled || !config.ready || players.some(name => !name.trim())} onClick={() => void start()}>{busy ? 'Starting...' : game ? 'Play again' : 'Start game'}</button>}
      {game && <div className="play-game">
        <div className="play-scoreboard" aria-label="Scoreboard">{game.mode === 'versus' ? game.players.map((name, i) => <div key={i} className={game.active_player === i ? 'play-player play-locked' : 'play-player'}><span>{name}</span><strong>{game.scores[i]}</strong>{game.active_player === i && <small>Answer locked to you</small>}</div>) : <div className="play-player"><span>{game.players.join(' + ')}</span><strong>{game.team_score}</strong><small>Streak: {game.streak}</small></div>}</div>
        <p className="play-progress">Question {game.question_number} of {game.total_questions} {game.remaining_ms !== null && <span role="timer">{Math.max(0, Math.ceil(game.remaining_ms / 1000))}s</span>}</p>
        <p role="status" className="play-status">{game.phase === 'finished' ? 'Game complete. Your score is saved to today’s leaderboard.' : game.message || (game.phase === 'buzz' ? 'Who knows this one? Buzz in!' : game.phase === 'coop' ? 'Choose together. Agree to lock.' : game.phase === 'answer' ? `${game.players[game.active_player ?? 0]}, choose your answer.` : 'Answer revealed.')}</p>
        {question && <article className="play-question"><h2>{question.question}</h2><button type="button" onClick={readQuestion} disabled={!('speechSynthesis' in window)}>Read question aloud</button><ol className="play-options">{question.options.map((option, i) => <li className={revealed && question.answer_index === i ? 'play-correct' : ''} key={i}><span>{i + 1}</span>{option}{revealed && question.answer_index === i && <strong>Correct</strong>}</li>)}</ol>
          {game.mode === 'versus' && game.phase === 'buzz' && <div className="play-modes">{game.players.map((name, i) => <button key={i} onClick={() => void act({ action: 'buzz', player: i === 0 ? 0 : 1 })}>Buzz: {name} ({i === 0 ? 'A' : 'L'})</button>)}</div>}
          {game.phase === 'answer' && <div className="play-answer-buttons">{question.options.map((_, i) => <button key={i} onClick={() => void act({ action: 'answer', player: game.active_player ?? 0, option: i })}>Answer {i + 1}</button>)}</div>}
          {game.phase === 'coop' && <div className="play-coop">{game.players.map((name, player) => <fieldset key={player}><legend>{name}</legend>{question.options.map((_, option) => <button key={option} aria-pressed={game.selections[player] === option} onClick={() => void act({ action: 'answer', player: player === 0 ? 0 : 1, option })}>{option + 1} <small>({player === 0 ? option + 1 : ['7', '8', '9', '0'][option]})</small></button>)}</fieldset>)}{game.hold_remaining_ms !== null && <p role="status">Agreed. Locking in {Math.max(0, game.hold_remaining_ms)}ms...</p>}</div>}
          {revealed && question.evidence && <blockquote>{question.evidence}{safeSource && <a href={safeSource} target="_blank" rel="noopener noreferrer">View campus source</a>}</blockquote>}
        </article>}
        {game.phase === 'reveal' && <button className="play-primary" onClick={() => void act({ action: 'next' })}>Continue (Enter)</button>}
      </div>}
    </main><aside className="play-leaderboard"><h2>Today’s leaderboard</h2><p>{mode === 'versus' ? 'Versus players' : 'Co-op teams'}</p>{scores.length ? <ol>{scores.map((score, i) => <li key={`${score.ts}-${i}`}><span>{score.name}</span><strong>{score.score}</strong></li>)}</ol> : <p>No scores yet. Start the first game.</p>}<small>Names and scores are stored on this server. Choose a nickname you are happy to display.</small></aside></div>
  </section>
}
