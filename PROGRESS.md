# Hello Campus: Progress Log

## Latest verified state after parallel work
Completed features: T0.1, T0.2, T1.2, T1.3, T1.4, T1.5, T2.1, T2.2, T2.4 and T2.5.
T1.7 is functional but its six-second speech target is unmet. T2.3 runtime/controls are implemented but need real trained weights and venue verification. T0.3/T1.6 real training remain blocked on HaGRID/venue inputs and GPU execution.
T1.1 real students/locality, T0.4 phone access and phase 3 full-demo/video/freeze acceptance are still pending. No code freeze is declared.
Final checks:
- `HC_OFFLINE=1 python -m pytest backend/tests -q`: 94 passed, two public-network scraper tests skipped, 26.99 s.
- `node --experimental-strip-types --test frontend/tests/gesture-hold.test.mjs`: four passed.
- `npm run build` and `npm run lint`: passed with 35 modules and no warnings.
- `python -m scripts.smoke --speech --offline`: PASS in 41.1 s with Python non-loopback connections blocked. Both characters, citations, refusal, fact extraction/resume, real STT/TTS endpoints and explicit unavailable gesture status passed. Speech roundtrip 10.87 s; six-second target remains unmet.
- Headless Chrome: 11 fixture checks passed, including actual MediaRecorder/AudioContext, early final sentence at sources before memory/done, SSE interruption, track cleanup, missing-model fallback, permission denial and source numbers [2]/[4]. No JavaScript runtime errors. Phone and actual trained-camera inference are not certified.
Review fixes: final spoken sentence flushes before memory extraction; speech limits come from backend config; camera throttles during hiring generation; one admitted CPU job per STT/TTS component prevents stale work queues after interruption; cancelled workers retain their slot until they finish; Chroma telemetry disabled; startup resources close even after errors.
Evidence remains scoped to the recorded runs. The complete physical offline demo still requires real student/locality inputs, trained gesture weights, venue repetitions and phone permissions.

## Parallel continuation results
Status: voice and camera-control implementation integrated; final combined checks in progress.
- Speech backend: 16 controlled tests passed. Real cached small-int8/Kokoro roundtrip succeeded with Python socket networking blocked: warm 13.153 s at two threads; four threads worsened to 14.614 s. Keep two threads. Six-second T1.7 acceptance remains unmet.
- Real app smoke including `/api/stt` and `/api/tts`: PASS in 67.0 s. Measured endpoint speech roundtrip 10.92 s, still above target. Gesture absence is reported honestly and does not stop chat or speech.
- Vision: 11 synthetic backend tests and four frontend hold/cooldown tests passed. CPU ONNX runtime, six-class metadata guard, bounded latest-frame WebSocket queue and camera controls are implemented. Real weights, model latency and venue 4/5 action success are unverified.
- Frontend: headless Chrome with mocked endpoints and test media exercised actual MediaRecorder, AudioContext, early sentence playback, barge-in/SSE abort, track cleanup, denied permissions, no-model fallback and keyboard character/shortlist controls. This is not a phone or real-trained-model acceptance run.
- Root reliability checks: citation numbering survives subsets and deduplication; original-passage extraction finds relevant late text; prompt history budgets and cleanup after exceptions are tested.
- Local chat comparison: 6,224 to 3,231 prompt characters; 33.109 s to 19.570 s first token (single measurements, different context budgets). Retrieval still uses top five; the CPU chat prompt uses up to three confident excerpts with 2,400 content characters.
- Combined suite before final notebook/admission changes: 59 passed, two external-network scraper tests skipped.
- Training repair: 27 synthetic tests passed. Embedded notebook prep executes independently with six-class fixture counts train48/val6/test6, subject-separated splits and duplicate-image rejection. Nonempty output folders are preserved. No real dataset, GPU training or accuracy claimed.
New team input: `training/own_frames/subjects.json` must map frame-relative paths to opaque subject/session IDs for leakage-safe splits. Use the same ID for the same person across captured frames.

## Parallel continuation plan
User explicitly requested multiple agents for faster completion.
- Speech agent: repair and verify offline STT/TTS adapters, validation tests, real roundtrip and latency.
- Voice frontend agent: microphone recording, sentence playback, interruption and cleanup, preserving chat/hiring.
- Vision agent: ONNX gesture runtime, bounded WebSocket frames, camera overlay, hold/cooldown and keyboard actions. Real training remains blocked on data.
- Root: integrate routers/startup, review citation correctness, startup cleanup and chat latency; run combined verification and update setup/status evidence.
No invented student/locality data, gesture accuracy or phone permission evidence will be introduced. Completed verified checkpoints may be committed and pushed without a co-author trailer, following the user's existing authorization.

## Previous committed checkpoint
Completed: T0.1, T0.2, T1.2, T1.3, T1.4, T1.5, T2.1, T2.4 and T2.5.
Hiring and README flows passed synthetic endpoint acceptance tests; real demonstration still requires opted-in profiles.
T1.1 is partial: real campus and achievement snapshots exist; students and real locality data are not available.
T0.3/T1.6 need real training data and a Colab run. T0.4 needs a physical phone.
T1.7/T2.2 speech work remains local and is excluded from this feature checkpoint. T2.3 video and phase 3 demo verification remain pending.

Evidence from this continuation:
- `HC_OFFLINE=1 python -m pytest backend/tests -q`: 27 passed, 2 public-network scraper tests skipped, 22.70 s.
- `python -m scripts.smoke`: PASS in 84.6 s using real local Gemma 1B and nomic embeddings. Both characters generated with AITM citations, unrelated content was refused, vegetarian preference extraction and resume passed, empty shortlist stayed honest.
- `npm run build` and `npm run lint` in frontend: passed.
- `git diff --check`: passed.
- Core smoke does not certify speech, gestures, physical phone access or the complete offline demo. Chat first-token latency was about 30 s with the current retrieved context, so further performance work remains.

Changes reviewed: responsive welcome/chat/hiring UI, official AITM source snapshot, bounded memory and current-consent filtering, worker-thread database operations, evidence URL post-check, smaller local model fallback, setup documentation and core smoke utility.

## Needs the team
- Campus URL provided by user: https://aitm.edu.in/. Use verified official links for campus and achievements. Club and hackathon sources still welcome.
- `data/students_optin.csv` export from the opt-in form (GitHub usernames). No student is indexed without it.
- Real values for `data/locality.json` (every placeholder is marked `"placeholder": true`).
- Venue frames for YOLO in `training/own_frames/<class>/` and a Colab run of `training/gesture_yolo.ipynb`.
- Optional `GITHUB_TOKEN` in `.env`.
- Phone check of the tunnel (T0.4): open the tunnel URL on a phone, grant mic and camera.

## Stack deviations
- Python 3.10 instead of 3.11: the laptop has 3.10 and 3.13 only. Kokoro requires < 3.13, so 3.10 is the closest safe choice. Code avoids 3.11-only features.
- No GNU make on the Windows laptop: `Makefile` delegates to `tasks.py`, so `python tasks.py <target>` works everywhere with identical targets.
- Smoke test is `scripts/smoke.py` (Python, runs on Windows) instead of `smoke.sh`. `smoke.sh` is a thin wrapper.

## Dependencies added
- Backend: fastapi, uvicorn[standard], pydantic, pydantic-settings, httpx, pytest, pytest-asyncio, chromadb, pyyaml, selectolax, trafilatura.
- Frontend: Vite 6 react-ts template defaults only.

---

## T0.1 Repo skeleton, Makefile, config, health
Status: done
Plan:
- Layout from BUILD.md section 3, `backend/config.py` (pydantic-settings, all tunables), `.env.example`, `.gitignore`.
- `backend/status.py` registry: each model registers a loader, failures are recorded not fatal, `/api/health` reports per component.
- `tasks.py` runner plus Makefile targets; Vite proxies `/api` and `/ws` so one tunnel URL serves everything.
Evidence:
$ python tasks.py backend ; curl localhost:8000/api/health
{"ok":true,"components":{"llm":{"name":"llm","ok":true,"detail":"llm=gemma3:4b embed=nomic-embed-text","load_ms":753}}}
$ npm run dev (frontend) ; curl localhost:5173/api/health
same JSON through the Vite proxy
Review: config in config.py, no blocking calls in routes, no em dashes.
Follow-ups: none

## Continuation: setup blockers and core slice
T0.3 status: blocked. The notebook exists, but no HaGRID dataset or venue frames are available. No real class counts, training metrics or model export can be claimed.
T0.4 status: blocked. Tunnel script exists, but phone HTTPS and permission checks require a physical phone. Use localhost for development.
T1.1 status: in progress. Scraper code exists; real sources and opt-in CSV are still missing. The real-record acceptance check cannot pass yet.
Plan:
- Validate locality entries and create explicitly marked placeholders, never index them.
- Implement persistent Chroma ingestion, current opt-in filtering, retrieval and source metadata.
- Implement streamed Guide/Analyst chat with refusal and SQLite visitor resume memory.
- Add acceptance tests using isolated, explicitly synthetic fixtures; also run local Ollama integration checks.
- Add a smoke runner and record checks, failures and outstanding team inputs here.

## T0.2 Ollama client with streaming and per-call temperature
Status: done
Plan:
- `backend/llm/client.py`: async httpx client, `stream_chat`, `chat_json` (format=json), `embed`, fallback model check.
- Test streams at temp 0.2 and 0.8, JSON mode, embeddings.
Evidence:
$ pytest backend/tests/test_llm_client.py -q
4 passed in 45.89s
Models pulled: gemma3:4b (3.4 GB), nomic-embed-text (274 MB)
Review: first-token latency logged per call.
Follow-ups: none

## T0.3 Colab notebook dataset prep
Status: in progress (needs team: run on Colab with HaGRID)
Plan:
- `training/build_notebook.py` generates `training/gesture_yolo.ipynb`: HaGRID to YOLO conversion, 80/10/10 split, class counts, baseline vs fine-tune, ONNX export, latency.
Evidence:
Dry run of the prep cell on a synthetic HaGRID-shaped folder printed class counts per split; box conversion checked (x 0.1, w 0.3 to cx 0.25).
Follow-ups: person A runs it on Colab with the real HaGRID subset.

## T0.4 Tunnel
Status: in progress (needs team: phone check)
- `scripts/tunnel.sh` prefers cloudflared, falls back to ngrok. The npm ngrok shim on this laptop does not run; install cloudflared (`winget install Cloudflare.cloudflared`).

## T1.1 Scrapers and normalizer
Status: blocked on team data (code done and tested)
Evidence:
$ pytest backend/tests/test_scraper.py -q
4 passed (real Wikipedia page and public octocat GitHub data, written to tmp dirs only)
Follow-ups: real URLs in sources.yaml and the opt-in CSV, then `python tasks.py scrape` and commit data/clean.

## T1.2 Locality schema, validator, placeholders
Status: done
Evidence:
$ python tasks.py validate-locality
8 entries, 0 real, 8 placeholders ... locality.json: VALID
$ pytest backend/tests/test_locality.py -q
3 passed
Placeholders are never ingested, so locality questions are refused until real entries exist.

## T1.3 RAG ingest and retrieve
Status: done
Evidence:
Calibration (nomic-embed-text, fixture data): relevant questions 0.73 to 0.80, off-topic 0.44 to 0.57. RAG_MIN_SCORE set to 0.62.
$ pytest backend/tests/test_rag.py -q
6 passed (sources returned, nonsense refused, idempotent re-ingest, chunk overlap, router rules, opt-in gate)

## T1.4 Chat endpoint (SSE, Guide and Analyst)
Status: in progress
Evidence:
$ curl -N -X POST /api/chat {"message":"Hi there!"}  -> meta, token x24, sources, done
$ curl -N -X POST /api/chat {"message":"When does the library open?"} -> refusal token, sources {"refused": true}
Blocker found: HARDWARE. This laptop has 7.3 GB RAM and a Ryzen 5 7520U (CPU only), not 16 GB.
gemma3:4b measured: prompt eval about 22 to 34 tok/s, generation about 6 tok/s, so a RAG prompt of about 2500 tokens means 1 to 2 minutes to first token.
Next steps when resuming:
- Re-run the model benchmark without prefix-cache reuse (gemma3:1b, qwen3.5:0.8b, gemma3:4b). gemma3:1b is pulled.
- Shrink RAG context (smaller chunks, top 3) and keep the persona prefix identical across calls for Ollama prefix caching.
- Decide with the team: is this the demo laptop? If yes, switch LLM_MODEL to a smaller model and log it here.
- Add a pytest for streamed tokens then a sources event with fixture data.

## T1.5 Visitor memory
Status: in progress (code written: backend/memory/store.py, extract.py, routes/visitor.py; tests not written yet)

## Continuation checks: AITM snapshot, chat and memory
User supplied https://aitm.edu.in/. Its robots.txt allows public pages with a one-second crawl delay.
Evidence:
$ python -m scraper.scrape_web
campus=3 real records; achievements=1 real record. Saved under data/clean with official source URLs and dates.
$ python -m backend.rag.ingest
campus=4 chunks, achievements=1, students=0, locality=0. No invented or placeholder records indexed.
$ pytest backend/tests/test_chat_memory.py backend/tests/test_locality.py -q
11 passed. Tests use synthetic data in temporary folders, real SQLite, and a controlled LLM double.
Checks cover both character temperatures, streamed tokens before sources, refusal without generation, visitor resume,
saved preferences in prompts, extraction failure recovery, restart persistence and the ten-message retention limit.
Fixes: blocking Chroma writes moved to worker threads; revoked consent checked at retrieval as well as ingestion;
blank requests rejected; greeting-plus-question cannot bypass grounding; extraction failure is visible and nonfatal.
Status: T1.1 remains partial until student and locality input arrive. T1.4/T1.5 await a live Ollama smoke check.

## Next slice: frontend and hiring
Plan:
- Replace the frontend starter with a responsive welcome, resume and streamed chat interface.
- Add hiring role intake, matching, evidence filtering, shortlist, compare, interview questions and export.
- Add student README before/after generation using only currently consented records.
- Test evidence filtering and consent revocation with isolated fixtures; compile and lint the frontend.
- Keep unavailable speech/gesture modes visibly unavailable until their models are installed and tested.

## Speech and hardware continuation plan
- Use Kokoro 82M through kokoro-onnx for CPU inference, preserving the specified voice model while avoiding a second PyTorch runtime on this 7.3 GB laptop.
- Install faster-whisper, kokoro-onnx and soundfile; cache speech weights under data/models for offline startup.
- Implement bounded raw-audio STT and per-sentence WAV synthesis in worker threads; surface missing model status.
- Connect microphone recording and queued sentence playback with immediate interruption.
- Benchmark the already installed gemma3:1b against gemma3:4b and use the smaller model on this laptop if needed (BUILD.md section 8 allows a smaller tag).
Evidence so far: gemma3:1b cold request 9.12 s, 32 generated tokens in 2.01 s; full comparison pending.
Benchmark complete: gemma3:4b cold request 109.45 s, prompt 20.44 s and generation 8.32 s.
Stack deviation: default changed to gemma3:1b with gemma3:4b fallback for this 7.3 GB CPU laptop, as allowed by BUILD.md section 8.

## UI/UX redesign (branch feat/ui-redesign)
Status: done (frontend only)
Plan:
- One app shell with three sections: Ask (chat and voice), Talent (hiring), Play (quiz, previously only play.html). Left rail on laptop, bottom tab bar on phone.
- Clean minimal system: neutral surfaces, one accent, hairline borders, 4px spacing grid, fixed type scale, Inter bundled locally so it works offline.
- No decorative markers: no emoji, sparkle icons, gradients, all-caps eyebrows or badge clutter.
- Removed the dead Video mode (its component was deleted in 5223ddf but App.tsx still imported it). Voice moved into the composer: mic button, optional spoken replies.
Evidence:
$ npm run build   -> built, no type errors
$ npm run lint    -> no warnings
$ node --test tests/play-keyboard.test.mjs -> 3 pass
Headless Chrome against a scratch mock API, phone 390x844 and laptop 1440x900: welcome, resume, ask (answer with citations, refusal, character switch), talent (match, shortlist, interview questions), play (setup, revealed question), visit code sheet. No page errors.
Fixed during review: newest message hidden under the sticky composer, misaligned segment labels, cramped welcome brand, long purpose list on phone.
Dependency added: @fontsource-variable/inter (self-hosted font, offline safe).
Config: vite.config.ts accepts HC_API_TARGET to point the dev proxy at another backend (default unchanged, 127.0.0.1:8000).
Not covered: the real backend on this branch fails to import (app.py still imports routes.speech and routes.gesture, removed in 5223ddf) and does not mount the quiz API. The UI shows clear fallbacks when those are down.

## UI/UX redesign, pass 2 (professional, single-device quiz)
Status: done (frontend only, branch feat/ui-redesign, uncommitted)
Plan:
- Replace the generic template look (Inter, pills, chat bubbles, big greeting) with an institutional style: IBM Plex Serif headings, Plex Sans text, Plex Mono codes, one deep green, thin rules, square corners.
- Ask becomes a footnoted Q and A transcript: question as heading, answer as body text, numbered sources with host and checked date, style and temperature noted under each answer.
- Talent becomes a directory list with consistent actions. Masthead with text tabs (Ask, Talent, Quiz) replaces sidebar and bottom bar.
- Quiz gets one-screen two-player pads: Player 1 left, question centre, Player 2 right on laptops; stacked on phones with an optional face to face mode that rotates Player 1's pad. Keyboard play unchanged.
- Resumed visits now say "Welcome back".
Evidence:
$ npm run build ; npm run lint -> pass, no warnings
$ node --test tests/play-keyboard.test.mjs -> 3 pass
$ node tests/play-browser.mjs (real isolated quiz API on :8011 with a scratch SQLite file, new play.html UI)
PASS: full versus keyboard game, answer secrecy, pass once, source reveal, typing focus, scores 4/1
PASS: full co-op keyboard game, disagreement, 500ms agreement, streak 5, score 15, SQLite leaderboard survives page reload
Headless Chrome screenshots, phone and laptop, every screen including quiz buzz, answer and reveal with touch pads: no page errors.
Dependencies: removed @fontsource-variable/inter, added @fontsource/ibm-plex-sans, ibm-plex-serif, ibm-plex-mono (self-hosted, offline safe).
Follow-ups: backend app.py still imports removed speech and gesture routes and does not mount the quiz router (team).
