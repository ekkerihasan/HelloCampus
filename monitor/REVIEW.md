# Monitor: Review Log

## Cycle 1 (H1.5, 12:07, builder mid T0.1 of the ADDENDUM-01 pivot, uncommitted)

Scope reviewed: working tree diff of `backend/config.py`, `.env.example`, `backend/llm/client.py` (Groq), new `backend/llm/gemini.py`, `backend/providers/retry.py`, `backend/providers/usage.py`, staged deletions of the local speech, vision and training code, `backend/hiring/service.py`, `data/`.

### Good
- Keys and model IDs only come from `.env`; empty model IDs raise `MissingConfig` with a UI-safe message instead of guessing (`backend/providers/retry.py`).
- Every external call goes through `call_with_retry`: timeout, backoff with jitter, 429 key rotation, usage logged without keys or prompts.
- Groq JSON mode adds the word "json" when missing (Groq requires it). Invalid JSON returns `{}` rather than crashing.
- Hiring evidence post-check keeps only URLs that exactly match stored records and re-checks consent after inference (`backend/hiring/service.py:51`, `:114`).
- Local stack removal matches ADDENDUM-01 section 12.

### Concerns (filed or pending)
1. **Data is the biggest demo risk, and only the humans can fix it.** `data/clean/` has campus=3, achievements=1 records. `students_optin.csv` has a header only. All 8 locality entries are placeholders. No `data/schedule.json` exists. Even with perfect code, demo steps 2 (veg lunch), 3 (poster venue), 5 (three hiring candidates) and 6 (lunch plan on resume) cannot run, and `rag_eval.yaml` (20+ questions, hit rate 0.8) is not meaningful on 4 records. **Flagged for humans** (see top of this file and the chat summary).
2. `.gitignore` ignores `data/chroma/` and `data/*.sqlite3`, but ADDENDUM-01 7.5 requires `data/chroma/` to be committed as the offline snapshot. `logs/` is not ignored, so `logs/usage.jsonl` will be committed by accident. Filed as M-001.
3. `rag_min_score = 0.62` was calibrated for nomic-embed-text. Gemini embeddings have a different similarity distribution, and ADDENDUM-01 7.4 applies the threshold to the best fused result. An RRF score is about 1/61 and is not comparable to cosine. Builder's config comment already says "recalibrate"; will verify when retrieval lands.
4. `mint_live_token` uses `uses=1`, `newSessionExpireTime` 60 s. Whether a session-resumption reconnect consumes a use is being researched; if it does, reconnect after GoAway fails and the visitor loses the session mid-demo.
5. `app.py` already imports `routes.live`, `routes.tools`, `routes.visit`, which do not exist yet. Expected mid-task; will check the suite after the T0.1 commit.

### For the humans (do not route to builder)
- Fill `data/students_optin.csv` (at least 3 consenting students with public GitHub, ideally frontend work for demo step 5).
- ~~Replace locality placeholders~~ Cycle 3 update: user reinstated lunch for guests. Researched draft at `monitor/LOCALITY-DRAFT.md` (OSM plus articles, all with sources). User corrects it, then the builder copies it into `data/locality.json`. Team must still add at least 2 veg options.
- Provide a schedule (events, venues, times) and print or photograph one real event poster whose event and venue are in that schedule (demo step 3).
- ~~Keys~~ **Done (cycle 2):** both keys set in `.env` (1 Gemini, 1 Groq; checked presence only, values never printed). Model IDs match RESEARCH.md; `GEMINI_TTS_MODEL=gemini-3.8-flash-tts` unverified, builder asked to confirm with a real call.
- **Groq limits are per organization**, not per key (rate-limits docs). Extra keys only help if each comes from a different team member's own Groq account. Free plan: 8K tokens per minute on the chat model, roughly 2 chat turns per minute.
- If Groq TTS is kept, a Groq org admin must accept the Orpheus model terms once in the Groq Playground.
- Check the Gemini free-tier limits in AI Studio (not published in the docs).
- **Non-goal change requested by the user (cycle 1):** bring back one YOLO model for a realtime Play-tab game (Versus and Co-op Buzzer Quiz). Draft addendum at `monitor/PROPOSAL-buzzer-quiz.md`. A human must save it as `ADDENDUM-03-buzzer-quiz.md` before the builder acts. Start the HaGRID Colab training (T4.0) now if adopted; it is the long pole.

## Cycle 2 (12:35, after commit 5223ddf, T0.1 provider work still uncommitted)
- `HC_OFFLINE=1 pytest backend/tests -q`: 48 passed, 2 skipped, 8.8 s. Count dropped from 94 because speech and vision suites were deleted (expected).
- New `test_providers.py` covers 429 key rotation, bounded retries, fail-fast on non-retryable, missing model IDs, v1beta token with constraints, embedding prefixes, Groq-to-Gemini text failover, and blocks real network in tests. Good.
- M-001, M-002, M-003 addressed in the working tree (see INBOX statuses). M-004, M-005, M-006 still open.
- Hybrid retrieval (`backend/rag/store.py`, `bm25.py`): the refusal gate passes on semantic score >= RAG_MIN_SCORE OR IDF-weighted keyword coverage >= 0.6. Edge case to watch in rag-eval: a one-word query matching one rare term gives coverage 1.0 and passes the gate even if the chunk only mentions it in passing. Also `\w+` tokenization fragments Devanagari words (vowel signs are not `\w`), so BM25 is weak for Hindi; the translate-before-retrieval flag covers it. Not filed; recheck with rag-eval numbers.
- Commit hash note: builder reported 04f2e1c for the deletion commit, but main has 5223ddf (same tree, 04f2e1c is on no branch). Builder told to restore from 5223ddf.
- ADDENDUM-03 (Buzzer Quiz) adopted by the user at about 12:30. Builder asked to restore and adapt the notebook first so Colab training can start.

## Cycle 4 (about 13:30, black-box test of the core chat flow against the builder's :8000)
Harness: scratchpad `chat_probe.py`, 25 chat turns plus validation and visitor flow; stage timings from SSE; cross-checked with `logs/usage.jsonl`.
Works:
- Grounded answers with correct chips: departments (CSE, Civil, Mechanical), cricket (VTU Inter-Zone Championship 2025), recruiters. Every recruiter name was checked against the scraped placement pages: all present.
- Refusals: lunch (no data yet), library closing time (schedule via SQLite only), prompt injection asking to invent restaurants, one-word "hostel". All refused with no chips.
- Validation: blank 422, 5000 chars 422, unknown character 422, unknown visitor gets a friendly error event.
- Memory: "remember I'm vegetarian and hiring a frontend intern" saved preferences, interests, summary and language; resume by code returns them. Visit page 200.
- Guide vs Analyst tone visibly differs on the same question with the same chips.
Broken (filed):
- M-009 P0: a greeting is refused (forced tool on round 0).
- M-010 P0: 4 of 19 streams empty but chips shown; chips shown on refusal text.
- M-011 P0: 32% of Flash-Lite calls 429; Hindi and concurrent turns fail with "Gemini is busy".
Latency (M-008 update): first token 2.5 to 3.5 s on factual questions; refusals 1.2 to 2.1 s. p50 per call: embed 644 ms, tool round 900 ms, stream first token 760 ms, memory JSON 1005 ms (after the answer). Live token mint 519 ms.
Not tested this cycle: Look, Live voice in a browser, hiring (no opt-in students).

## Cycle 5 (verification of builder's M-009 to M-011 fixes, 29 turns in 113 s)
- M-010 verified. M-009 reopened P1 (hackathon greeting refused because the schedule is empty). M-011 still open: 1 visible error in 29, 429 rate unchanged at 34%, now absorbed by a backup model.
- Hindi works end to end: both Hindi questions answered in Hindi with the same correct chips (T2.6 looks achievable in chat).
- Latency under sustained load: first token p50 3.35 s, p90 6.8 s; idle single-call measurements are faster (builder reports 1.6 s). The difference is 429 failover hops.

## For the humans (cycle 5): LinkedIn request
- The user asked about scraping https://www.linkedin.com/school/anjumanitm/. Builder and monitor agree: **no automated LinkedIn scraping** (CLAUDE.md "Do not" list, BUILD.md section 7 non-goal, LinkedIn terms, login wall). The monitor does not recommend changing the non-goal.
- Allowed path: hand-curated facts with source URLs, preferring public aitm.edu.in pages. Draft and template at `monitor/CURATED-NEWS-DRAFT.md`.
- Quick win needing no human work: 7 more official news articles at aitm.edu.in/news/ can be scraped (only 1 of 9 is). Listed in the draft.
- Decision needed: the karate news article names a student. Mention it or not (consent)?
- Watch out: "AITM" search results are often Angadi Institute of Technology and Management, Belagavi, a different college.

## Cycle 6 (browser test of :5173 in Chrome, about 14:10)
- UI loads, polished: visit code shown (SKYN), Guide 0.8 / Analyst 0.2 toggle visible, suggestion chips, "Campus facts come with sources. If I don't know, I'll say so."
- Chat via UI: "Tell me about AITM" streamed with 4 numbered source chips. Raw markdown visible: filed M-013.
- **Live voice works**: Start talking connected, and the host proactively said "Welcome back, Wasih. Let me know how I can help with your session or talk today." (ADDENDUM-01 section 9.3). End conversation closed cleanly. Screenshot: C:\Users\Home\AppData\Local\Temp\claude-chrome-screenshots-m4aJLM\screenshot-1792399263024-0.png
- Console: the @google/genai SDK warns "ephemeral token support is in v1alpha only". The session connected anyway using the v1beta token, consistent with the official docs (RESEARCH.md). Stale SDK warning, not a bug; recheck if Live ever fails to connect.
- Not testable by the monitor: speaking into the mic, interruption, Look with a real poster (needs a human at the mic and camera). T2.1 and T2.2 acceptance need a human run.

## Cycle 7 (full end-to-end probe of every non-human part, about 15:00)
All passed against :8000 (scratchpad e2e.py):
- Health: llm, gemini, rag, memory, schedule all ok; text provider gemini; Live enabled.
- Tools via /api/tools/*: search_campus (robotics, 2 real chips, 1.1 s), get_local_tips veg refuses honestly (no locality data yet), get_schedule says no confirmed entry, remember ok, profile shows the fact, hiring_set_role structures "Frontend intern, React and TypeScript, remote" (3.5 s), hiring_match returns an honest empty list (no opt-in students), visit_summary returns /visit/<code>, unknown tool 404.
- **Look** on a test poster (STEM 2024, rendered by the monitor, clearly marked TEST): 200 in **3.0 s** (target under 4 s), read all text, related source https://aitm.edu.in/news/stem-2024/ first. Wrong content type 415, empty 422.
- **Fallback voice** (ADDENDUM-01 5.5): server TTS produced a 154 KB WAV; /api/stt transcribed it exactly ("Which engineering departments does AITM have?", en) in **1.9 s**; chat on the transcript gave first token in **1.6 s** with 11 chips. Speech-in to first-word about 3.5 s.
- Live token: 200 in 1.0 s, token is auth_tokens/..., config locked, welcome cue included.
- Resume returns name, remembered fact, interests and role title; visit page 200 with the name; unknown code 404; /debug 200.
- Security: no API key value or key pattern in /debug, /api/health or /api/speech/config; frontend only receives the ephemeral Live token; no VITE_ variables in .env.
Still needs a human: speaking to Live, interruption, Hindi by voice, Look with the phone camera on a real poster, and the Buzzer Quiz once T4.x is built.
