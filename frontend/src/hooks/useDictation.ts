import { useEffect, useRef, useState } from 'react'
import { transcribeAudio } from '../api/client'

export type DictationState = 'idle' | 'recording' | 'transcribing'
const MAX_MS = 60000

/** Tap to dictate into a text field: record, then /api/stt (Groq Whisper, Gemini fallback), then onText. */
export function useDictation(onText: (text: string) => void) {
  const [state, setState] = useState<DictationState>('idle'), [error, setError] = useState('')
  const recorder = useRef<MediaRecorder | null>(null), stream = useRef<MediaStream | null>(null)
  const abort = useRef<AbortController | null>(null), timer = useRef<number | undefined>(undefined)
  const callback = useRef(onText); callback.current = onText
  function release() { window.clearTimeout(timer.current); stream.current?.getTracks().forEach(t => t.stop()); stream.current = null }
  async function start() {
    setError('')
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { setError('Voice input needs HTTPS or localhost and a current browser.'); return }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported(t))
      const rec = new MediaRecorder(stream.current, mimeType ? { mimeType } : undefined), chunks: BlobPart[] = []
      recorder.current = rec
      rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }
      rec.onstop = () => {
        release(); recorder.current = null; setState('transcribing')
        const ctrl = new AbortController(); abort.current = ctrl
        transcribeAudio(new Blob(chunks, { type: rec.mimeType }), ctrl.signal)
          .then(r => { if (r.text.trim()) callback.current(r.text.trim()); else setError('I did not catch that. Try again a little closer to the mic.') })
          .catch(e => { if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Could not transcribe that.') })
          .finally(() => { if (abort.current === ctrl) { abort.current = null; setState('idle') } })
      }
      rec.start(); setState('recording')
      timer.current = window.setTimeout(() => { if (rec.state === 'recording') rec.stop() }, MAX_MS)
    } catch (e) {
      release(); setState('idle')
      setError(e instanceof DOMException && e.name === 'NotAllowedError' ? 'Microphone access was blocked. Allow it in your browser site settings.' : 'Could not open the microphone.')
    }
  }
  function toggle() {
    if (state === 'recording') recorder.current?.stop()
    else if (state === 'transcribing') { abort.current?.abort(); abort.current = null; setState('idle') }
    else void start()
  }
  useEffect(() => () => { abort.current?.abort(); if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop() } release() }, [])
  return { state, error, toggle }
}
