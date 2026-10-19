# Monitor: Research (verified, with sources)

All checked 2026-10-19 against official docs. WebFetch returns summaries, so quotes are short excerpts. Re-verify anything marked "unverified".

## Gemini

### Model IDs (for T0.2)
| Env var | Recommended ID | Status | Source |
|---|---|---|---|
| `GEMINI_LIVE_MODEL` | `gemini-3.8-live` | GA 2026-09-15 | https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live , https://ai.google.dev/gemini-api/docs/changelog |
| `GEMINI_VISION_MODEL` | `gemini-3.8-flash` (or `gemini-3.5-flash-lite` for lower latency) | GA 2026-09-02 | https://ai.google.dev/gemini-api/docs/image-understanding , changelog 2026-09-18: "New projects should use 3.5 Flash-Lite or 3.8 Flash" |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-2` (recommended) or `gemini-embedding-001` (shutdown 2028-05-14) | GA 2026-04-22 | https://ai.google.dev/gemini-api/docs/embeddings |

Do NOT use from memory: `gemini-2.5-flash-native-audio-preview-12-2025` and `gemini-3.1-flash-live-preview` shut down 2026-11-17. `gemini-live-2.5-flash-preview` was shut down 2025-12-09. 2.5 models are restricted for new projects. Source: https://ai.google.dev/gemini-api/docs/deprecations

### Ephemeral tokens
- Endpoint is **`POST /v1beta/auth_tokens`** with header `x-goog-api-key`. Docs: tokens work "only with the v1beta version of the API". No mention of v1alpha. Source: https://ai.google.dev/gemini-api/docs/ephemeral-tokens
- Body `{uses, expireTime, newSessionExpireTime}`. Defaults: uses 1, expireTime 30 min, newSessionExpireTime 1 min.
- **Resumption with a `uses: 1` token works:** "Within the expireTime timeframe, you'll need sessionResumption to reconnect the call every 10 minutes (This can be done with the same token even if uses: 1)". So the builder's `uses=1` is fine; reconnects must happen within 30 minutes of minting or the browser must fetch a new token.
- Token can lock model and config with `liveConnectConstraints` ({model, config}). Locking keeps the system instruction and tools on the server, so the browser cannot repurpose the token.
- JS: `new GoogleGenAI({ apiKey: token.name })` then `ai.live.connect(...)`. SDK defaults to beta endpoints. js-genai README advises pinning `@google/genai` below 3.0.0 (3.0.0 will need Node 22+). Source: https://raw.githubusercontent.com/googleapis/js-genai/main/README.md

### Live session behavior
- Limits: audio-only 15 min, audio+video 2 min without compression; connection about 10 min; server sends `GoAway` with `timeLeft`. `contextWindowCompression: { slidingWindow: {} }` extends sessions. Resumption handles valid 2 h after termination; resuming when `resumable` is false can lose data. Source: https://ai.google.dev/gemini-api/docs/live-session
- Config can only be sent in the first setup message. Changing the system instruction (Guide vs Analyst) requires reconnecting. ADDENDUM-01 5.4 already says restart. Source: https://ai.google.dev/api/live
- Language: "models automatically choose the appropriate language and don't support explicitly setting the language code". Language mirroring (T2.6) comes free; do not set a language code. Source: https://ai.google.dev/gemini-api/docs/live-guide
- **Function calling on 3.8 Live defaults to async: "Async execution (behavior: NON_BLOCKING) is now the default".** The model can keep talking while `search_campus` runs, so it may answer before the grounded result arrives. Set `behavior: BLOCKING` on grounding tools. Source: gemini-3.8-live model page.
- 3.8 Live: affective dialog removed (setting it errors), proactive audio always on (setting false errors), `thinking_level` unsupported. Do not send these fields.
- Transcription: `inputAudioTranscription` and `outputAudioTranscription` in setup.
- Temperature: Live setup accepts `generationConfig.temperature`, but the changelog (2026-07-21) deprecates temperature/top_p/top_k, and the Gemini 3 guide recommends the default 1.0. Characters on Live must come from the system instruction only. Groq chat keeps real temperatures.

### Embeddings
- `gemini-embedding-2` has **no `taskType`**. Use text prefixes instead: query `task: search result | query: {text}`, document `title: {title} | text: {text}` (`title: none` if absent). Spaces of 001 and 2 are incompatible, so switching models means re-embedding everything.
- `gemini-embedding-001` accepts `taskType` RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY, input limit 2,048 tokens; embedding-2 limit 8,192.
- Default 3072 dims; 768 recommended for small corpora. 001 requires manual normalization for non-3072 dims; embedding-2 auto-normalizes.
- Multilingual: embedding-2 "over 100 languages"; Hindi and Kannada not named explicitly (unverified, test in T0.2).

### Vision structured output
- generateContent is labelled "Legacy" but "remains fully supported" with no shutdown date. JS SDK uses `responseMimeType` + `responseJsonSchema`. The REST example on the structured output page uses `generationConfig.responseFormat`. `responseSchema` does not appear on that page. Inconsistent docs: the builder must test with one real call. Source: https://ai.google.dev/gemini-api/docs/generate-content/structured-output

### Unverified
- Free-tier RPM/RPD and concurrent Live sessions: docs only say "viewed in Google AI Studio". Check in AI Studio once the key exists.

## Groq
Caveat: live console.groq.com/docs returned 404 from this machine, so these quotes come from Wayback snapshots of the official pages (dated per item, 2026-09-11 to 2026-10-18). Confirm with `GET https://api.groq.com/openai/v1/models` once a key exists (the builder's `GroqClient.ping` already reports missing IDs).

### Model IDs (for T0.2), models page snapshot 2026-10-18, https://console.groq.com/docs/models
| Env var | Recommended ID | Status |
|---|---|---|
| `GROQ_CHAT_MODEL` | `openai/gpt-oss-120b` | production, 131k context |
| `GROQ_FAST_MODEL` | `openai/gpt-oss-20b` | production, about 1000 tok/s |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` | production, 99+ languages, no translation |
| `GROQ_TTS_MODEL` | `canopylabs/orpheus-v1-english` | **preview**, English only |
| `GROQ_TTS_VOICE` | one of `autumn`, `diana`, `hannah`, `austin`, `daniel`, `troy` | |

**Already shut down for free and developer keys** (deprecations snapshot 2026-09-29, https://console.groq.com/docs/deprecations): `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` (2026-08-16), `qwen/qwen3.6-27b`, `qwen/qwen3-32b`, llama-4 scout and maverick, `groq/compound*`, `playai-tts` (2025-12-31), `gemma2-9b-it`, `mixtral-8x7b-32768`, `distil-whisper-large-v3-en`. "Requests to deprecated model IDs will return errors."

### Free plan rate limits (snapshot 2026-10-10, https://console.groq.com/docs/rate-limits)
| Model | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| gpt-oss-120b / gpt-oss-20b | 30 | 1K | 8K | 200K |
| whisper-large-v3-turbo | 20 | 2K | audio 7.2K s/h | 28.8K s/day |
| orpheus-v1-english | 10 | **100** | 1.2K | **3.6K** |

- **"Rate limits apply at the organization level, not individual users."** Several keys from the same Groq org add zero quota. Only keys from separate accounts (orgs) add capacity. `GROQ_API_KEYS` rotation is still correct code, but the team must create keys under different accounts.
- Headers: `retry-after` only on 429; `x-ratelimit-remaining-requests` (per day) and `x-ratelimit-remaining-tokens` (per minute) on every response. "Cached tokens do not count towards your rate limits."
- Budget implication: 8K TPM on the chat model. A chat turn with tool definitions, 4 RAG chunks (about 900 tokens), memory and history is likely 2K to 3K prompt tokens, often twice (tool round then answer). Expect about 2 chat turns per minute per org before 429. Measure in T3.2.

### STT (snapshot 2026-10-09, https://console.groq.com/docs/speech-to-text)
- Formats: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm (MediaRecorder webm is fine). 25 MB on free tier. Minimum billed length 10 s per request.
- `verbose_json` top-level `language` field is **not documented**. Do not rely on it for language memory; detect language with the fast model or from the transcript.

### TTS (snapshots 2026-10-06/07, https://console.groq.com/docs/text-to-speech)
- **Input limited to 200 characters per request.** wav only. English and Arabic only, no Hindi.
- Free: 10 RPM, 100 RPD, 3.6K tokens per day. One demo run could use a large share of that.
- Each Orpheus model needs one-time terms acceptance by the org admin in the Groq Playground (third-party report of error code `model_terms_required`: https://github.com/langflow-ai/langflow/issues/11120; not on official pages).

### Tool calling and structured output (snapshots 2026-09-11 to 2026-10-07)
- gpt-oss-20b/120b: tool use yes, **parallel tool calls no**, JSON mode yes. Streaming with tools is supported.
- `json_schema` strict mode is supported on gpt-oss but "Streaming and tool use are not currently supported with Structured Outputs." Keep JSON calls and tool calls as separate requests (the builder already does).
- `tool_choice`: auto, required, none, or a named function.
