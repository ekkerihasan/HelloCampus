import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './fonts'
import './index.css'
import PlayMode from './PlayMode'

const candidate = new URLSearchParams(window.location.search).get('api')
let apiBase = '/api/quiz'
if (candidate) {
  try {
    const url = new URL(candidate)
    if (['http:', 'https:'].includes(url.protocol)) apiBase = url.href.replace(/\/$/, '')
  } catch { /* Keep the same-origin default for an invalid preview URL. */ }
}
createRoot(document.getElementById('root')!).render(<StrictMode><PlayMode apiBase={apiBase} /></StrictMode>)
