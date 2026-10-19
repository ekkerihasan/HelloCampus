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
