import { useEffect, useRef, useState } from 'react'
import { request } from '../api/client'
import { advanceHold, emptyHold, type Detection, type GestureAction } from '../gesture/hold'
import './VideoMode.css'

export type { GestureAction } from '../gesture/hold'
type GestureConfig = {
  available: boolean; detail: string; classes: string[]; min_confidence: number; hold_ms: number
  cooldown_ms: number; fps: number; fps_generating: number; frame_width: number; max_frame_bytes: number
}
type Props = { generating: boolean; onGesture: (label: GestureAction) => void; onError?: (message: string) => void }
const keys: Record<string, GestureAction> = { ' ': 'palm', y: 'like', n: 'dislike', e: 'ok', c: 'peace' }
const labels: Record<GestureAction, string> = { palm: 'Talk or interrupt', like: 'Shortlist', dislike: 'Next candidate', ok: 'Open evidence', peace: 'Switch character' }

export function VideoMode({ generating, onGesture, onError }: Props) {
  const video = useRef<HTMLVideoElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const socket = useRef<WebSocket | null>(null)
  const callback = useRef(onGesture)
  const errorCallback = useRef(onError)
  const generatingRef = useRef(generating)
  const hold = useRef(emptyHold())
  const [config, setConfig] = useState<GestureConfig | null>(null)
  const [active, setActive] = useState(false)
  const [status, setStatus] = useState('Checking gesture model...')
  const [error, setError] = useState('')
  const [detection, setDetection] = useState<Detection | null>(null)
  const [lastAction, setLastAction] = useState('')
  const [progress, setProgress] = useState(0)
  const [cooldown, setCooldown] = useState(false)

  useEffect(() => { callback.current = onGesture; errorCallback.current = onError; generatingRef.current = generating }, [onGesture, onError, generating])
  useEffect(() => {
    let disposed = false
    request<GestureConfig>('/api/gesture/config').then(value => {
      if (disposed) return
      setConfig(value)
      setStatus(value.available ? 'Camera is off. Start it to use gestures.' : value.detail)
    }).catch(reason => { if (!disposed) setError(String(reason)) })
    return () => { disposed = true }
  }, [])

  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || target?.isContentEditable ||
        target?.closest('input,textarea,select,button,a,[role="button"]')) return
      const action = keys[event.key.toLowerCase()]
      if (!action) return
      event.preventDefault()
      callback.current(action)
      setLastAction(`${labels[action]} (keyboard)`)
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [])

  useEffect(() => {
    if (!active || !config) return
    const cfg = config
    const videoElement = video.current
    let disposed = false, timer = 0, tick = 0, waiting = false, encoding = false
    let lastSent = 0, lastReceived = 0
    function fail(message: string) { if (!disposed) { setError(message); errorCallback.current?.(message); setActive(false) } }
    async function start() {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        fail('Camera needs HTTPS or localhost. Keyboard controls are ready.'); return
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: cfg.frame_width } }, audio: false })
        if (disposed) { media.getTracks().forEach(track => track.stop()); return }
        stream.current = media
        if (!videoElement) return
        videoElement.srcObject = media
        await videoElement.play()
        if (disposed) return
        const url = new URL('/ws/gesture', window.location.href)
        url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(url)
        socket.current = ws
        ws.onopen = () => setStatus('Camera connected. Hold a gesture to act.')
        ws.onerror = () => fail('Camera connection failed. Keyboard controls are ready.')
        ws.onclose = () => { if (!disposed) fail('Camera connection closed. Keyboard controls are ready.') }
        ws.onmessage = event => {
          if (disposed) return
          let message: { type: string; message?: string; detections?: Detection[] }
          try { message = JSON.parse(event.data as string) } catch { fail('Invalid camera response. Restart the camera.'); return }
          if (message.type === 'error') { fail(message.message || 'Gesture model unavailable.'); return }
          if (message.type !== 'detections') return
          waiting = false
          const now = performance.now()
          lastReceived = now
          const best = (message.detections || []).filter(item => cfg.classes.includes(item.label) && item.confidence >= cfg.min_confidence)
            .sort((a, b) => b.confidence - a.confidence)[0]
          setDetection(best || null)
          const fps = generatingRef.current ? cfg.fps_generating : cfg.fps
          const next = advanceHold(hold.current, best, now, cfg.min_confidence, cfg.hold_ms, cfg.cooldown_ms, Math.max(cfg.hold_ms, 3000 / fps))
          hold.current = next.state
          if (next.action) { callback.current(next.action); setLastAction(labels[next.action]) }
        }
        function capture() {
          if (disposed) return
          const currentVideo = videoElement, currentCanvas = canvas.current
          const now = performance.now(), fps = generatingRef.current ? cfg.fps_generating : cfg.fps
          if (lastReceived && now - lastReceived > Math.max(cfg.hold_ms, 3000 / fps)) {
            hold.current = { ...hold.current, label: null, since: 0 }
            setDetection(null)
          }
          setProgress(hold.current.label ? Math.min(1, (now - hold.current.since) / cfg.hold_ms) : 0)
          setCooldown(now < hold.current.cooldownUntil)
          if (!waiting && !encoding && ws.readyState === WebSocket.OPEN && currentVideo && currentCanvas && currentVideo.videoWidth && now - lastSent >= 1000 / fps) {
            currentCanvas.width = cfg.frame_width
            currentCanvas.height = Math.max(1, Math.round(currentVideo.videoHeight * cfg.frame_width / currentVideo.videoWidth))
            currentCanvas.getContext('2d')?.drawImage(currentVideo, 0, 0, currentCanvas.width, currentCanvas.height)
            encoding = true
            currentCanvas.toBlob(blob => {
              encoding = false
              if (disposed || !blob || ws.readyState !== WebSocket.OPEN) return
              if (blob.size > cfg.max_frame_bytes) { fail('Camera frame exceeds the server limit.'); return }
              waiting = true
              lastSent = performance.now()
              ws.send(blob)
            }, 'image/jpeg', 0.7)
          }
          tick = window.setTimeout(capture, 40)
        }
        capture()
        // A dropped response must not leave the sender waiting indefinitely.
        timer = window.setInterval(() => { if (waiting && performance.now() - lastSent > 15000) fail('Gesture inference timed out. Restart the camera.') }, 1000)
      } catch (reason) { fail(reason instanceof Error ? reason.message : 'Camera could not start. Keyboard controls are ready.') }
    }
    void start()
    return () => {
      disposed = true
      window.clearTimeout(tick)
      window.clearInterval(timer)
      socket.current?.close()
      socket.current = null
      stream.current?.getTracks().forEach(track => track.stop())
      stream.current = null
      if (videoElement) videoElement.srcObject = null
      hold.current = emptyHold()
    }
  }, [active, config])

  return <section className="gesture-panel" aria-label="Video gestures">
    <div className="gesture-header"><strong>Camera gestures</strong><button type="button" disabled={!config?.available} onClick={() => {
      setError(''); setDetection(null); setProgress(0); setCooldown(false)
      if (active) setStatus('Camera is off. Keyboard controls are ready.')
      setActive(value => !value)
    }}>{active ? 'Stop camera' : 'Start camera'}</button></div>
    <p className="gesture-status" role="status">{error || status}</p>
    <div className={`gesture-camera ${active ? 'is-active' : ''}`}>
      <video ref={video} autoPlay muted playsInline aria-label="Your camera, used locally for hand gestures" />
      {!active && <p>Camera is off. Keyboard controls work below.</p>}
      {active && detection && <div className="gesture-box" style={{ left: `${detection.box[0] * 100}%`, top: `${detection.box[1] * 100}%`, width: `${(detection.box[2] - detection.box[0]) * 100}%`, height: `${(detection.box[3] - detection.box[1]) * 100}%` }}>
        <span>{detection.label} {Math.round(detection.confidence * 100)}%</span>
      </div>}
      {active && <div className="gesture-hold"><svg viewBox="0 0 40 40" aria-label={cooldown ? 'Gesture cooldown' : `Hold progress ${Math.round(progress * 100)}%`}><circle className="gesture-ring-bg" cx="20" cy="20" r="16" /><circle className="gesture-ring-fill" cx="20" cy="20" r="16" pathLength="100" strokeDasharray={`${progress * 100} 100`} /></svg><span>{cooldown ? 'Ready soon' : progress > 0 ? 'Hold...' : 'Show a gesture'}</span></div>}
    </div>
    <canvas ref={canvas} hidden />
    <div className="gesture-shortcuts">{Object.entries(labels).map(([action, text]) => <button type="button" key={action} onClick={() => { callback.current(action as GestureAction); setLastAction(`${text} (button)`) }}><kbd>{({ palm: 'Space', like: 'Y', dislike: 'N', ok: 'E', peace: 'C' } as const)[action as GestureAction]}</kbd> {text}</button>)}</div>
    <p className="gesture-status" aria-live="polite">{lastAction || 'Frames are processed on your local server and are not saved.'}</p>
  </section>
}
