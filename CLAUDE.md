# CLAUDE.md: How to Build Hello Campus

You are building Hello Campus, a 1-day buildathon project for a 3-person team. Read `BUILD.md` fully before writing any code. It defines scope, constraints, tasks and acceptance criteria. This file defines how you work.

The team has one day. A smaller thing that works beats a bigger thing that half works. Every training topic must be visibly demonstrated (BUILD.md section 2).

---

## 1. The build loop (follow for every task)

```
1. PICK      Take the next unticked task in BUILD.md order, respecting phase.
2. PLAN      Write 3 to 6 bullets in PROGRESS.md: files to touch, approach, how you will verify.
3. BUILD     Implement the smallest vertical slice that can be run end to end.
4. RUN       Execute it for real: tests, curl, script, or browser. Capture the output.
5. VERIFY    Compare output to the task's acceptance criteria. Pass or fail, no "probably".
6. REVIEW    Re-read your own diff against the Review Checklist (section 4).
7. IMPROVE   Fix every failed check. Return to step 4. Max 3 loops per task.
8. LOG       Record result, evidence (command + key output lines), and follow-ups in PROGRESS.md.
9. CHECKPOINT  After every 3 completed tasks, run `make smoke`. If it fails, fixing it is the next task.
```

If a task still fails after 3 loops: stop, write the blocker in PROGRESS.md, apply the fallback from BUILD.md section 8 or narrow the scope, and move on. Never sit on one problem.

## 2. Do

**Scope and priority**
- Build vertical slices first (one path working end to end), then widen.
- Get chat mode fully working before voice, and voice before video. Each mode builds on the previous one.
- Keep the demo script (BUILD.md section 6) runnable at all times after Phase 1.

**Local and offline**
- Run everything locally: Ollama, Chroma, SQLite, faster-whisper, Kokoro, ONNX YOLO.
- Commit the cleaned data snapshot in `data/clean/` so the demo works with Wi-Fi off.
- Load every model once at startup, keep it in memory, and report its status in `/api/health`.

**Performance on a 16 GB CPU laptop**
- Run blocking inference (STT, TTS, YOLO) in a thread pool, never on the event loop.
- Stream LLM output (SSE) and stream TTS sentence by sentence.
- Throttle gesture frames to about 3 fps while the LLM is generating.
- Measure and log latency for chat first token, STT, TTS first audio, and gesture inference.

**Truthfulness (most important)**
- Every factual answer cites sources from retrieved metadata.
- Below `RAG_MIN_SCORE`, say "I don't have that yet" instead of answering.
- In hiring, every claim about a student must link to a URL or record that exists in stored data. The post-check that removes unknown URLs must stay on.
- Use only students listed in `students_optin.csv`.

**Code quality**
- Python: type hints, pydantic models for every request and response, small modules.
- TypeScript: strict mode, typed API client in `frontend/src/api/`.
- Put every tunable value (temperatures, thresholds, fps, model names, hold time, cooldown) in `backend/config.py` or `.env`. No magic numbers in logic.
- Write a pytest test for each acceptance criterion that can be automated.
- Handle failures visibly: if a model is not loaded, the UI says so and the other modes keep working.
- Give every gesture a keyboard equivalent.

**Writing**
- No em dashes anywhere: UI copy, prompts, README, comments, commit messages, PROGRESS.md. Use commas, colons, or separate sentences.
- UI copy is warm, short and plain. The Guide sounds like a friendly local, the Analyst like a precise colleague.

## 3. Do not

- Do not invent data: no fake students, achievements, restaurants, URLs, fares or timings. Use clearly marked placeholders (`"placeholder": true`) and leave real values to the team.
- Do not scrape LinkedIn, Instagram, login-walled pages, or anything robots.txt disallows.
- Do not add face recognition or anything that identifies people from the camera.
- Do not build anything in BUILD.md section 7 (non-goals). That includes a second YOLO model.
- Do not call cloud LLM or speech APIs. Do not add API keys other than the optional GitHub token.
- Do not use models larger than about 4B parameters for the LLM.
- Do not commit secrets, `.env`, or large raw scrape caches.
- Do not mark a task done without running it and recording evidence.
- Do not silently change stack decisions in BUILD.md section 3. If you must, log the reason in PROGRESS.md first.
- Do not refactor working code for style during the day. Only refactor when it blocks a task.
- Do not add a dependency when the standard library or an existing one does the job. Log every new dependency.
- Do not store full conversation transcripts. Keep extracted facts and the last 10 turns only.
- Do not disable the RAG refusal or the evidence post-check to make a demo look better.
- Do not change anything after code freeze (T3.5) except bug fixes that a smoke test or demo run exposed.

## 4. Review checklist (run on every diff in step 6)

**Correctness**
- [ ] The acceptance criterion was actually executed and passed, with output logged.
- [ ] Error paths handled: model missing, empty retrieval, audio too short, no hand in frame, tunnel down.
- [ ] No blocking call inside an async route.

**Truthfulness and privacy**
- [ ] Answers include sources; refusal works below threshold.
- [ ] No invented facts, URLs or student data introduced.
- [ ] Only opt-in students reachable through any endpoint.

**Topics coverage**
- [ ] The training topic this task serves is visible in the UI or demo, not just in code.

**Performance**
- [ ] Models loaded once. Latency logged. Memory budget in BUILD.md section 1 respected.

**Quality**
- [ ] Config values live in `config.py` or `.env`.
- [ ] Types and pydantic models present. Tests added or updated.
- [ ] No em dashes in any text you added.
- [ ] `make test` passes. After every third task, `make smoke` passes.

## 5. PROGRESS.md format

Append one block per task:

```
## T1.3 RAG ingest and retrieve
Status: done | blocked | in progress
Plan:
- ...
Evidence:
$ pytest backend/tests/test_rag.py -q
4 passed in 3.2s
$ curl ... (key lines only)
Latency: retrieve p50 120 ms
Review: all checklist items pass
Follow-ups: placeholder locality entries still need real values (team)
```

Keep a short "Needs the team" section at the top of PROGRESS.md for anything only a human can provide: real URLs for `sources.yaml`, locality values, opt-in form export, venue frames for YOLO, GitHub token.

## 6. Improvement passes (only when all Phase 2 tasks are done)

Run these in order, one at a time, each through the full build loop:
1. Run the demo script end to end 3 times. Fix the single worst friction point each time.
2. Cut chat first-token latency and TTS first-audio latency, whichever is worse.
3. Tune gesture hold time and confidence with real venue frames.
4. Tighten Guide and Analyst prompts using real answers that felt off.
5. Polish README so a judge can see in 30 seconds how each training topic is used.

Stop improving at code freeze. A stable demo beats one more feature.

## 7. Commands

```
make dev               backend + frontend with reload
make scrape            run scrapers into data/raw and data/clean
make ingest            embed data/clean into Chroma
make validate-locality check locality.json schema and dates
make test              pytest
make smoke             scripts/smoke.sh end-to-end
make tunnel            start the HTTPS tunnel for phone access
```
