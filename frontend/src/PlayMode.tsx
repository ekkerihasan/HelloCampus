import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { quizClient } from './play/client'
import { isTyping, keyboardAction } from './play/keyboard'
import type { Action, Config, Game, Mode, Player, Score } from './play/types'
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
  const [faceToFace, setFaceToFace] = useState(false)
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
  const statusText = !game ? '' : game.phase === 'finished' ? 'Game complete. The score is saved to today’s leaderboard.'
    : game.message || (game.phase === 'buzz' ? 'First to buzz answers.' : game.phase === 'coop' ? 'Both players pick an answer. Agree to lock it in.'
      : game.phase === 'answer' ? `${game.players[game.active_player ?? 0]} is answering.` : 'Answer revealed.')

  function pad(player: Player) {
    if (!game || !question) return null
    const name = game.players[player], keys = player === 0 ? ['1', '2', '3', '4'] : ['7', '8', '9', '0']
    const answering = game.mode === 'versus' && game.phase === 'answer' && game.active_player === player
    const waiting = game.mode === 'versus' && game.phase === 'answer' && game.active_player !== player
    return <section className={`pad pad-${player + 1} ${answering ? 'is-turn' : ''}`} aria-label={`${name} controls`}>
      <header className="pad-head">
        <span className="pad-name">{name}</span>
        <span className="pad-score num">{game.mode === 'versus' ? game.scores[player] : ''}</span>
      </header>
      {game.mode === 'versus' && game.phase === 'buzz' && <button type="button" className="pad-buzz" onClick={() => void act({ action: 'buzz', player })}>
        Buzz<span className="pad-key mono">{player === 0 ? 'A' : 'L'}</span>
      </button>}
      {answering && <div className="pad-options">{question.options.map((option, i) => <button type="button" key={i} onClick={() => void act({ action: 'answer', player, option: i })}>
        <span className="pad-opt-num mono">{i + 1}</span><span className="pad-opt-text">{option}</span>
      </button>)}</div>}
      {waiting && <p className="pad-wait">Waiting for {game.players[game.active_player ?? 0]}</p>}
      {game.phase === 'coop' && <div className="pad-options">{question.options.map((option, i) => <button type="button" key={i} aria-pressed={game.selections[player] === i}
        onClick={() => void act({ action: 'answer', player, option: i })}>
        <span className="pad-opt-num mono">{keys[i]}</span><span className="pad-opt-text">{option}</span>
      </button>)}</div>}
      {revealed && <p className="pad-wait">{game.phase === 'finished' ? 'Game over' : 'Next question when ready'}</p>}
    </section>
  }

  return <section className={`play-mode ${faceToFace ? 'is-face-to-face' : ''}`} aria-labelledby="play-title">
    <header className="play-header">
      <h1 id="play-title">Quiz</h1>
      <p>Two players on one screen, five questions. Every answer is checked against a campus source.</p>
    </header>
    <div className="play-layout"><main>
      {!active && <div className="play-setup-wrap">
        <fieldset className="play-setup" disabled={busy}><legend>New game</legend>
          <div className="play-modes" role="group" aria-label="Mode">
            <button type="button" aria-pressed={mode === 'versus'} onClick={() => setMode('versus')}>Versus</button>
            <button type="button" aria-pressed={mode === 'coop'} onClick={() => setMode('coop')}>Co-op</button>
          </div>
          <p className="play-instructions">{mode === 'versus'
            ? 'Race to buzz. The first player to buzz answers; a wrong answer passes the question to the other player once.'
            : 'Play as a team. Both players choose an answer and it locks when you agree. Correct answers in a row build a streak bonus.'}</p>
          <div className="play-names">{players.map((name, index) => <label key={index}>Player {index + 1}<input value={name} maxLength={40} onChange={event => setPlayers(current => index === 0 ? [event.target.value, current[1]] : [current[0], event.target.value])} /></label>)}</div>
          <label className="play-toggle"><input type="checkbox" checked={faceToFace} onChange={e => setFaceToFace(e.target.checked)} />Face to face: turn Player 1’s controls upside down for a phone or tablet laid flat between you</label>
          <details className="play-keys"><summary>Keyboard controls</summary>
            <p>{mode === 'versus' ? 'Player 1 buzzes with A, Player 2 with L. The buzzing player answers with 1 to 4.' : 'Player 1 picks with 1 to 4, Player 2 with 7, 8, 9 and 0.'} Enter moves to the next question.</p>
          </details>
        </fieldset>
        {error && <p role="alert" className="play-error">{error}</p>}
        {config && !config.enabled && <p role="status">The quiz is switched off.</p>}
        {config?.enabled && !config.ready && <p role="status">The quiz needs more campus data: {config.question_count} verified questions, {config.questions_per_game} needed.</p>}
        <button className="play-primary" disabled={busy || !config?.enabled || !config.ready || players.some(name => !name.trim())} onClick={() => void start()}>{busy ? 'Starting' : game ? 'Play again' : 'Start game'}</button>
      </div>}

      {game && <div className="play-game">
        <div className="play-bar">
          <span className="num">Question {game.question_number} of {game.total_questions}</span>
          {game.mode === 'coop' && <span className="num">Team {game.team_score}, streak {game.streak}</span>}
          {game.remaining_ms !== null && <span role="timer" className="play-timer num">{Math.max(0, Math.ceil(game.remaining_ms / 1000))}s</span>}
        </div>
        <p role="status" className="play-status">{statusText}</p>
        {active && error && <p role="alert" className="play-error">{error}</p>}
        <div className="play-stage">
          {pad(0)}
          {question && <article className="play-question">
            <h2>{question.question}</h2>
            <ol className="play-options">{question.options.map((option, i) => <li className={revealed && question.answer_index === i ? 'play-correct' : ''} key={i}>
              <span className="mono">{i + 1}</span>{option}{revealed && question.answer_index === i && <strong>Correct</strong>}
            </li>)}</ol>
            {game.hold_remaining_ms !== null && <p role="status" className="play-hold">Agreed. Locking in.</p>}
            {revealed && question.evidence && <blockquote>{question.evidence}{safeSource && <a href={safeSource} target="_blank" rel="noopener noreferrer">View campus source</a>}</blockquote>}
            <div className="play-question-foot">
              <button type="button" className="play-read" onClick={readQuestion} disabled={!('speechSynthesis' in window)}>Read aloud</button>
              {game.phase === 'reveal' && <button className="play-primary" onClick={() => void act({ action: 'next' })}>Next question</button>}
            </div>
          </article>}
          {pad(1)}
        </div>
      </div>}
    </main>
    <aside className="play-leaderboard"><h2>Today’s leaderboard</h2><p>{mode === 'versus' ? 'Versus players' : 'Co-op teams'}</p>
      {scores.length ? <ol>{scores.map((score, i) => <li key={`${score.ts}-${i}`}><span>{score.name}</span><strong>{score.score}</strong></li>)}</ol> : <p>No scores yet today.</p>}
      <small>Names and scores are stored on this server. Use a name you are happy to display.</small>
    </aside></div>
  </section>
}
