# ADDENDUM 01: Cloud Pivot to Hello Campus Live

**Read order:** `BUILD.md` -> `CLAUDE.md` -> this file.
**Precedence:** Where this file conflicts with `BUILD.md` or `CLAUDE.md`, this file wins. Anything not mentioned here still applies as written.
**Do not edit** `BUILD.md` or `CLAUDE.md`. Future changes arrive as new numbered addendum files (`ADDENDUM-02-...md`), read in number order, with the highest number winning on conflicts.

---

## 1. What changed and why

| Before | Now |
|---|---|
| Judged partly on using the training topics | Judged on innovation, quality of the idea, and quality of the build |
| Everything local (Ollama, local STT/TTS, YOLO) | Cloud APIs allowed: **Gemini** and **Groq** |
| Stitched STT -> LLM -> TTS pipeline | Realtime speech-to-speech conversation via the Gemini Live API |
| YOLO gesture control in video mode | Removed. Voice interruption handles barge-in; the camera is used for "Look" snapshots instead |
| Projector considered | Not used. Phone or laptop browser only |

Product name stays **Hello Campus**. Pitch line stays:

> You arrive at a new campus, and nobody's around to tell you what makes this place special, which students are doing great work, or where to grab lunch. Hello Campus is that friendly local you wish you had. Just chat, talk, or wave at your camera. And if you're hiring, it'll point you to the right people.

(If "wave at your camera" no longer matches the build, change it to "or show it what you're looking at" in the README and UI only.)

## 2. Superseded parts of BUILD.md

| BUILD.md section | Status |
|---|---|
| 1. Constraints: Cloud row, Memory budget row | **Replaced** by section 3 and 8 below |
| 2. Training topics table | **Removed.** No topic coverage requirement |
| 3. Stack decisions: LLM, Embeddings, STT, TTS, Vision | **Replaced** by section 3 below |
| 3. Repo layout: `vision/`, `training/` | **Removed.** Add `backend/live/` and `backend/tools/` |
| 4.2 Characters and temperature | **Kept**, implemented per section 5.4 |
| 4.3 RAG | **Replaced** by section 7 |
| 4.6 Speech | **Replaced** by section 5 |
| 4.7 Video mode and gestures, 4.8 YOLO training | **Removed** |
| 5. Task list | **Replaced** by section 10 |
| 6. Demo script | **Replaced** by section 11 |
| 7. Non-goals | **Extended** by section 12 |
| 8. Risks | **Extended** by section 13 |

Everything else in BUILD.md (visitor welcome and memory, locality data, hiring feature, scraping rules, privacy rules) still applies.

## 3. Stack and service split

| Job | Service | Notes |
|---|---|---|
| Live voice conversation | Gemini Live API | Audio in, audio out, interruption handled by the API, function calling to our tools |
| "Look" at a poster, notice board, menu | Gemini Flash (standard API, vision) | One snapshot per tap, called by the backend |
| Chat mode answers | Groq (larger text model) | Streamed over SSE |
| Routing, memory extraction, hiring ranking, role intake | Groq (small fast model) | Must return JSON. The Live API cannot produce structured output, so these never run on Live |
| Fallback STT | Groq Whisper (`whisper-large-v3-turbo`) | Used when Live is unavailable or out of quota |
| Fallback TTS | Groq TTS model if available, else browser `speechSynthesis` | Fallback only |
| Embeddings | Gemini embedding model | See section 7 |
| Vector store | Chroma, persistent, local folder | See section 7 |
| Memory, schedule, shortlist | SQLite | Structured data, not RAG |
| Backend | FastAPI, Python 3.11 | Unchanged |
| Frontend | Vite + React + TypeScript, `@google/genai` for Live | Unchanged plus Live client |

**Model IDs are never hardcoded.** Put them in `.env` (`GEMINI_LIVE_MODEL`, `GEMINI_VISION_MODEL`, `GEMINI_EMBED_MODEL`, `GROQ_CHAT_MODEL`, `GROQ_FAST_MODEL`, `GROQ_STT_MODEL`, `GROQ_TTS_MODEL`). In T0 verify each ID against the official docs or the provider's model list endpoint and record the verified IDs in PROGRESS.md. Do not trust model names from memory.

## 4. Architecture

```
Browser (phone or laptop, HTTPS)                 Backend (FastAPI on laptop, via tunnel)
+--------------------------------+               +-------------------------------------+
| Chat tab  -------------------- | -- SSE -----> | /api/chat        Groq + RAG          |
| Voice tab:                     |               |                                     |
|   @google/genai Live session --|-- WSS --> Gemini Live (ephemeral token)              |
|   tool calls from Live ------- | -- HTTP ----> | /api/tools/*     RAG, memory, hiring |
|   Look button (snapshot) ----- | -- HTTP ----> | /api/look        Gemini Flash vision |
| Captions from transcriptions   |               | /api/live/token  mints ephemeral tok |
| Source chips from tool results |               | /api/visitor     create, resume code |
| Visit summary page            <|-- HTTP ------ | /visit/{code}    shareable summary   |
+--------------------------------+               +-------------------------------------+
                                                   Chroma | SQLite | Groq | Gemini
```

- API keys live only on the backend. The browser gets a short-lived **ephemeral token** from `/api/live/token` to open the Live session.
- The browser receives tool calls from Live, forwards them to `/api/tools/<name>`, and returns the result to Live.

## 5. Live session design

### 5.1 Audio-only sessions with Look snapshots
- Live sessions with audio plus video are limited to about 2 minutes, audio-only to about 15 minutes, and connections to about 10 minutes. Video is processed at 1 frame per second.
- Therefore the Live session is **audio-only**. The camera preview is shown in the UI, and the **Look** button (or the visitor saying "look at this", which triggers the `look` tool) captures one JPEG and sends it to `/api/look`. The vision result returns to Live as a tool result.
- Handle connection end signals by reconnecting with session resumption. If resumption fails, start a new session seeded with the visitor's memory summary. The visitor should never have to repeat who they are.

### 5.2 Transcriptions
- Enable input and output audio transcription. Use them for on-screen captions and as the input to memory extraction (Groq, after each turn).

### 5.3 Language
- The host replies in the language the visitor speaks. Store the detected language in memory. Chat mode follows the same rule.

### 5.4 Guide and Analyst on Live
- Implement characters via the system instruction (tone, length, behavior). Set temperature in the Live generation config if the API supports it, otherwise rely on the instruction. Switching character restarts the Live session with the new instruction plus the memory summary.
- Chat mode keeps real temperature control on Groq (Guide 0.8, Analyst 0.2).

### 5.5 Fallback voice pipeline
- If Live fails to connect, hits quota, or `LIVE_ENABLED=false`: push-to-talk -> Groq Whisper -> Groq chat with the same tools (Groq tool calling) -> TTS fallback. Same UI, a small "fallback voice" badge.

## 6. Tool contract (used by both Live and Groq)

All tools are thin wrappers over backend services. Results are JSON with a `sources` array where relevant.

| Tool | Args | Returns |
|---|---|---|
| `search_campus` | `query`, optional `collections[]` | `{snippets[], sources[]}` or `{refusal: true}` |
| `get_local_tips` | `type` (food, travel, place, practical), optional `query`, optional `veg` | `{items[], sources[]}` |
| `get_schedule` | optional `date`, optional `venue` | `{events[]}` from SQLite |
| `get_visitor_profile` | none | `{name, purpose, language, facts[], shortlist[]}` |
| `remember` | `fact` | `{ok}` (explicit "remember that..." requests only) |
| `look` | optional `question` | `{description, text_found, related_sources[]}` |
| `hiring_set_role` | `description` | `{role}` structured via Groq |
| `hiring_match` | optional `limit` | `{candidates[]: {id, name, reasons[], evidence_urls[]}}` |
| `shortlist_add` / `shortlist_remove` | `student_id` | `{shortlist[]}` |
| `visit_summary` | none | `{url}` to `/visit/{code}` |

Rules:
- Source chips in the UI come from tool results, never from the model's own text.
- `hiring_match` runs the evidence post-check from BUILD.md 4.5 before returning.

## 7. RAG database

### 7.1 Not everything is RAG
| Data | Where | Why |
|---|---|---|
| Campus descriptions, departments, clubs, facilities | RAG `campus` | Prose, asked in many ways |
| Achievements, hackathon wins, papers | RAG `achievements` | Prose with names |
| Opt-in student profiles, repo summaries | RAG `students` | Prose, used by hiring |
| Food, travel, places, practical | RAG `locality` + the same rows in SQLite | Semantic questions via RAG, filters (veg, type) via SQL |
| Schedule, timings, venues, contacts | **SQLite only** | Exact answers. Never let similarity search guess a time |
| Visitor memory, shortlist | **SQLite only** | Per visitor state |

### 7.2 Store and embeddings
- **Chroma**, persistent in `data/chroma/`. The corpus is hundreds of chunks, so a hosted vector DB adds risk and no value.
- **Gemini embedding model** from `GEMINI_EMBED_MODEL`. Use the document task type at ingest and the query task type at search if the API offers task types. Verify in T0 that a Hindi or Kannada query retrieves an English chunk; record the result.
- Batch embed at ingest. Cache embeddings by content hash in SQLite so re-ingest never re-embeds unchanged chunks.

### 7.3 Chunking and metadata
- Prose: about 300 to 500 tokens, 50 overlap, split on headings first.
- One chunk per locality entry, per student profile section (summary, each top repo, achievements), and per achievement.
- Metadata: `collection`, `title`, `source_url` or `"curated"`, `last_checked`, `entity_id`, `content_hash`, optional `valid_until` for time-bound items.
- Prefix each chunk's text with its title before embedding so short chunks keep context.

### 7.4 Retrieval: hybrid
- Run vector search (top 10) and BM25 keyword search (top 10) in parallel, merge with reciprocal rank fusion, keep top 4.
- Reason: names of students, halls, events and restaurants are exact strings that embeddings often miss.
- Filter out chunks past `valid_until`.
- If the best fused result is below `RAG_MIN_SCORE`, return `{refusal: true}`. The host says it does not know yet and suggests who to ask.
- Voice answers use top 3 to keep latency and tokens low. Chat uses top 4.

### 7.5 Ingest pipeline
`make scrape` -> `data/clean/*.jsonl` -> `make ingest`: chunk -> hash -> embed new or changed only -> upsert to Chroma -> rebuild BM25 index -> write `data/ingest_report.json` (counts per collection, skipped, failed).
`data/clean/` and `data/chroma/` are committed as the offline snapshot so a fresh clone can demo without scraping.

### 7.6 Evaluation (part of the build loop)
- Maintain `backend/tests/rag_eval.yaml` with 20 or more question -> expected `entity_id` or `source_url` pairs, including 3 non-English questions and 3 questions that must be refused.
- `make rag-eval` reports hit rate at 4 and refusal accuracy. Target: hit rate at least 0.8, refusals 3 of 3. Log the numbers in PROGRESS.md every time retrieval changes.

## 8. Keys, quotas, cost

- Groq's free plan allows about 8,000 tokens per minute per model. Support `GROQ_API_KEYS` as a comma-separated list and rotate on HTTP 429, with exponential backoff and jitter.
- Keep prompts lean: memory summary under 150 tokens, RAG context top 3 to 4 chunks.
- Log every external call to `logs/usage.jsonl` with provider, model, tokens if reported, latency, and status. Show a tiny usage counter on a hidden `/debug` page.
- Never ship any key to the browser. Only ephemeral Live tokens leave the backend.

## 9. Feature additions

1. **Look:** snapshot -> Gemini vision -> combine with `search_campus` on any names found (event, venue, club) -> spoken answer with sources.
2. **Language mirroring:** section 5.3.
3. **Proactive welcome back:** on resume, the host greets by name and mentions the next relevant item from the schedule or their stated purpose.
4. **Visit summary page** at `/visit/{code}`: what they asked about, schedule items, places to eat, shortlist with evidence links. Mobile friendly, shareable.
5. **Hiring:** unchanged from BUILD.md 4.5, now exposed as tools.

## 10. Task list (replaces BUILD.md section 5)

### Phase 0: Setup (H0 to H1)
- [ ] **T0.1** Repo skeleton, Makefile (`dev`, `scrape`, `ingest`, `rag-eval`, `test`, `smoke`, `tunnel`), `.env.example` with every key and model variable. **Accept:** `/api/health` reports each provider reachable or not.
- [ ] **T0.2** Verify every model ID and record them in PROGRESS.md with the source. **Accept:** one successful call per model logged.
- [ ] **T0.3** Tunnel works; phone opens the app with mic and camera permission. **Accept:** logged from phone.
- [ ] **T0.4** Ephemeral token endpoint and a bare Live session that says hello. **Accept:** audio round trip on phone.

### Phase 1: Core (H1 to H4)
- [ ] **T1.1** Scrapers and committed clean snapshot (unchanged from BUILD.md T1.1).
- [ ] **T1.2** Locality schema, validator, placeholders, mirrored into SQLite.
- [ ] **T1.3** Ingest pipeline with hashing, Chroma, BM25. **Accept:** ingest report written; second run embeds 0 chunks.
- [ ] **T1.4** Hybrid retrieval, refusal, `rag_eval.yaml`. **Accept:** hit rate and refusal numbers logged.
- [ ] **T1.5** Tool endpoints from section 6 with pydantic schemas. **Accept:** pytest per tool.
- [ ] **T1.6** Chat mode on Groq with tools, SSE, Guide and Analyst. **Accept:** curl shows streamed answer then sources.
- [ ] **T1.7** Memory: visitor create, resume code, Groq JSON extraction after each turn. **Accept:** resume test recalls purpose and language.

### Phase 2: Live and features (H4 to H6)
- [ ] **T2.1** Live voice with tool calls, captions, session resumption, character switch. **Accept:** a question that needs `search_campus` is answered with source chips, and an interruption mid-answer works.
- [ ] **T2.2** Look: camera preview, snapshot, `/api/look`, combined answer. **Accept:** photo of a poster yields event name and venue from campus data.
- [ ] **T2.3** Fallback voice pipeline. **Accept:** with `LIVE_ENABLED=false` the same question works end to end.
- [ ] **T2.4** Hiring tools wired into chat and Live, evidence post-check test. **Accept:** injected fake URL removed.
- [ ] **T2.5** Visit summary page. **Accept:** opens on a second device from the code.
- [ ] **T2.6** Language mirroring. **Accept:** Hindi question gets a Hindi answer with correct sources.

### Phase 3: Polish and freeze (H6 to H8)
- [ ] **T3.1** `scripts/smoke.sh` covers health, chat, refusal, memory resume, every tool, look on a sample image, fallback voice, summary page. **Accept:** passes twice in a row.
- [ ] **T3.2** Quota rehearsal: run the full demo script 3 times back to back with no 429 failures visible to the user.
- [ ] **T3.3** Record fallback demo video.
- [ ] **T3.4** README: problem, what is new about it, architecture diagram, RAG design and eval numbers, privacy statement, setup.
- [ ] **T3.5** Code freeze.

## 11. Demo script (replaces BUILD.md section 6)

1. Phone, enter name, pick "Session or talk". Voice starts: the host welcomes them and gives a 20 second campus briefing.
2. Ask by voice: "Where can I get good lunch nearby, something veg?" Interrupt halfway with "actually, under 200 rupees". It adapts.
3. Tap Look on an event poster: "What's this and where is it?" It reads the poster and answers with the venue from campus data.
4. Ask the same kind of question in Hindi. It answers in Hindi.
5. "I'm also hiring a frontend intern." Three candidates with evidence, shortlist one by voice.
6. Open the laptop, enter the code. "Welcome back" with the shortlist and lunch plan. Open the visit summary page.

## 12. Non-goals (added)
YOLO or any custom vision model, Ollama or local LLMs, local STT or TTS models, projector features, continuous video streaming to Live, a hosted vector database, user accounts.

## 13. Risks (added)
| Risk | Fallback |
|---|---|
| Live API quota or connection failure on stage | Fallback voice pipeline (5.5), then chat mode |
| Groq 429 during demo | Key rotation, lean prompts, quota rehearsal T3.2 |
| Model ID changed or deprecated | IDs live in `.env`; T0.2 verification |
| Cross-language retrieval weak | Translate the query to English with the Groq fast model before retrieval, keep the answer in the visitor's language |
| Venue network slow | Demo on laptop browser, local backend; only model calls go out |

## 14. Additions to the CLAUDE.md build loop

Insert into the loop in CLAUDE.md section 1:

- **Step 0, before PICK:** read every `ADDENDUM-*.md` in number order. If a newer addendum has appeared since the last task, re-check the current plan against it before continuing.
- **Step 4, RUN, also run:** `make rag-eval` whenever retrieval, chunking or embeddings changed.
- **Step 5, VERIFY, also check:** latency budget (Live first audio under 1.5 s after the visitor stops speaking; chat first token under 1 s; Look answer under 4 s) and that no 429 reached the user.
- **Step 8, LOG, also record:** tokens and calls used by the task from `logs/usage.jsonl`.

Add to the CLAUDE.md review checklist (section 4):
- [ ] No API key reachable from the browser bundle or network tab.
- [ ] Model IDs read from `.env`, none hardcoded.
- [ ] Every external call has timeout, retry with backoff, and a user-visible fallback.
- [ ] Citations in the UI come from tool results only.
- [ ] Fallback voice path still passes after this change.
- [ ] RAG eval numbers did not drop (or the drop is explained in PROGRESS.md).

Add to the CLAUDE.md "Do not" list:
- Do not trust model names, limits or API shapes from memory. Check the official docs and record what you found.
- Do not stream continuous video to the Live API.
- Do not answer schedule, timing or contact questions from RAG. Use SQLite.
- Do not remove the fallback voice path, even if Live works perfectly in testing.
