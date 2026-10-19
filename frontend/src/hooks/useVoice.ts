import { useEffect, useRef, useState } from 'react'
import { request, synthesizeSpeech, transcribeAudio } from '../api/client'

type CaptureState = 'idle' | 'requesting' | 'recording' | 'transcribing'
type PlaybackState = 'idle' | 'preparing' | 'playing'
type SpeechConfig = { recording_max_ms: number; sentence_max_chars: number }

export function useVoice(onTranscript: (text: string) => void, onInterrupt: () => void) {
  const [capture, setCapture] = useState<CaptureState>('idle')
  const [playback, setPlayback] = useState<PlaybackState>('idle')
  const [error, setError] = useState('')
  const [config, setConfig] = useState<SpeechConfig | null>(null)
  const context = useRef<AudioContext | null>(null), source = useRef<AudioBufferSourceNode | null>(null)
  const microphone = useRef<MediaStream | null>(null), recorder = useRef<MediaRecorder | null>(null)
  const captureRef = useRef<CaptureState>('idle'), timer = useRef<number | undefined>(undefined)
  const session = useRef(0), abort = useRef(new AbortController())
  const queue = useRef<string[]>([]), pending = useRef(''), pumping = useRef(false)
  const callbacks = useRef({ onTranscript, onInterrupt }); callbacks.current = { onTranscript, onInterrupt }
  useEffect(() => {
    let active = true
    request<SpeechConfig>('/api/speech/config').then(value => { if (active) setConfig(value) }).catch(() => { if (active) setError('Speech settings could not load. Switch to Chat or reload to try again.') })
    return () => { active = false }
  }, [])

  function setCaptureState(next: CaptureState) { captureRef.current = next; setCapture(next) }
  function releaseMicrophone() {
    window.clearTimeout(timer.current)
    microphone.current?.getTracks().forEach(track => track.stop()); microphone.current = null
  }
  function stop() {
    session.current += 1
    abort.current.abort(); abort.current = new AbortController()
    queue.current = []; pending.current = ''; pumping.current = false
    if (source.current) { try { source.current.stop() } catch { /* Already ended. */ } source.current = null }
    const recording = recorder.current; recorder.current = null
    if (recording && recording.state !== 'inactive') { recording.onstop = null; recording.stop() }
    releaseMicrophone(); setCaptureState('idle'); setPlayback('idle')
  }
  function warmAudio() {
    context.current ??= new AudioContext()
    // Called directly from a tap so mobile browsers allow later sentence playback.
    return context.current.resume()
  }
  async function pump() {
    if (pumping.current) return
    const active = session.current, signal = abort.current.signal
    pumping.current = true
    try {
      while (queue.current.length && active === session.current) {
        const text = queue.current.shift()!
        setPlayback('preparing')
        const bytes = await synthesizeSpeech(text, signal)
        if (active !== session.current) return
        if (!context.current || context.current.state !== 'running') throw new Error('Tap the microphone to enable audio playback in this browser.')
        const buffer = await context.current.decodeAudioData(bytes)
        if (active !== session.current) return
        const node = context.current.createBufferSource(); node.buffer = buffer; node.connect(context.current.destination)
        source.current = node; setPlayback('playing')
        await new Promise<void>(resolve => { node.onended = () => { node.disconnect(); resolve() }; node.start() })
        if (source.current === node) source.current = null
      }
    } catch (e) {
      if (active === session.current && !signal.aborted) { queue.current = []; pending.current = ''; setError(e instanceof Error ? e.message : 'Could not play the reply. You can still read it below.') }
    } finally {
      if (active === session.current) { pumping.current = false; setPlayback('idle') }
    }
  }
  function enqueue(token: string, final = false) {
    if (!config) return
    pending.current += token
    while (pending.current.trim()) {
      const match = /[.!?](?=\s)/.exec(pending.current)
      let boundary = match ? match.index + 1 : 0
      if ((!boundary || boundary > config.sentence_max_chars) && pending.current.length > config.sentence_max_chars) {
        boundary = pending.current.lastIndexOf(' ', config.sentence_max_chars)
        if (boundary <= 0) boundary = config.sentence_max_chars
      }
      if (!boundary && final) boundary = pending.current.length
      if (!boundary) break
      const sentence = pending.current.slice(0, boundary).replace(/\[\d+\]/g, '').replace(/[*#`]/g, '').trim()
      pending.current = pending.current.slice(boundary)
      if (sentence) queue.current.push(sentence)
    }
    void pump()
  }
  async function start() {
    stop(); callbacks.current.onInterrupt(); setError('')
    if (!config) { setError('Speech settings are still loading. Try again in a moment.'); return }
    const active = session.current
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { setError('Microphone access needs HTTPS or localhost. Open this app through the secure tunnel on your phone.'); return }
    if (!window.MediaRecorder) { setError('This browser cannot record audio. Try a current Chrome, Edge, Firefox or Safari browser.'); return }
    setCaptureState('requesting')
    try {
      await warmAudio()
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false })
      if (active !== session.current) { stream.getTracks().forEach(track => track.stop()); return }
      microphone.current = stream
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type))
      const recording = new MediaRecorder(stream, mimeType ? { mimeType } : undefined), chunks: BlobPart[] = []
      recorder.current = recording
      recording.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      recording.onerror = () => { if (active === session.current) { stop(); setError('Recording stopped unexpectedly. Try the microphone again.') } }
      recording.onstop = () => {
        releaseMicrophone(); recorder.current = null
        if (active !== session.current) return
        setCaptureState('transcribing')
        const signal = abort.current.signal
        void transcribeAudio(new Blob(chunks, { type: recording.mimeType }), signal).then(result => {
          if (active !== session.current) return
          setCaptureState('idle')
          if (!result.text.trim()) setError('I did not catch any speech. Tap the microphone and try again.')
          else callbacks.current.onTranscript(result.text)
        }).catch(e => { if (active === session.current && !signal.aborted) { setCaptureState('idle'); setError(e instanceof Error ? e.message : 'Could not transcribe that recording.') } })
      }
      recording.start(); setCaptureState('recording')
      timer.current = window.setTimeout(() => finish(), config.recording_max_ms)
    } catch (e) {
      if (active !== session.current) return
      releaseMicrophone(); setCaptureState('idle')
      setError(e instanceof DOMException && e.name === 'NotAllowedError' ? 'Microphone access was blocked. Allow it in your browser site settings, then try again.' : e instanceof Error ? e.message : 'Could not open the microphone.')
    }
  }
  function finish() {
    window.clearTimeout(timer.current)
    if (recorder.current?.state === 'recording') { setCaptureState('transcribing'); recorder.current.stop() }
  }
  function toggle() { if (captureRef.current === 'recording') finish(); else if (captureRef.current === 'requesting' || captureRef.current === 'transcribing') stop(); else void start() }
  useEffect(() => () => {
    // Invalidate all pending async work before releasing browser resources.
    session.current += 1; abort.current.abort(); window.clearTimeout(timer.current)
    if (recorder.current && recorder.current.state !== 'inactive') { recorder.current.onstop = null; recorder.current.stop() }
    microphone.current?.getTracks().forEach(track => track.stop())
    try { source.current?.stop() } catch { /* Already ended. */ }
    void context.current?.close()
  }, [])
  return { capture, playback, error, toggle, stop, enqueue, warmAudio, config }
}
