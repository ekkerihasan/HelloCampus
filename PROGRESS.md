# Hello Campus: Progress Log

## ADDENDUM-01 cloud pivot: replan (2026-10-19)
Status: in progress
ADDENDUM-01 supersedes the local stack. Everything logged below this block refers to the old Ollama/YOLO/local speech plan and is history only.
Plan (addendum section 10 order, keyless work first):
- T0.1: config for Gemini and Groq (keys and model IDs from .env only), provider clients with timeout, retry with backoff and jitter, Groq key rotation on 429, usage log in logs/usage.jsonl, /api/health per provider, /debug usage page. Remove YOLO, training, Ollama and local speech code (addendum section 12 non-goals).
- T0.2: model IDs verified against official docs by a research pass; one real call per model once keys exist.
- T1.2/T1.3/T1.4: locality and schedule mirrored into SQLite; ingest with content-hash embedding cache, Chroma, BM25; hybrid retrieval with RRF and refusal; rag_eval.yaml and `rag-eval` target.
- T1.5/T1.6/T1.7: tool registry from section 6 (one pydantic schema feeds Groq tools, Live declarations and /api/tools/*), Groq chat with tools over SSE, memory with language.
- Then: /api/live/token, Live client, Look, fallback voice, visit summary page.
Blocked on the team: GEMINI_API_KEY and GROQ_API_KEYS in .env. Without them, provider calls are tested with transport doubles only and no acceptance criterion that needs a real call is marked done.
Environment: Python 3.12.6 is the only interpreter on this laptop now (the 3.10 note below is outdated). Fresh .venv created from backend/requirements.txt.

## Lunch places and judging time (user-approved, 2026-10-19)
Status: done
- data/locality.json food-001 Layali Arabia Restaurant and food-002 Al Khaleej Arabian Restaurant from monitor/LOCALITY-DRAFT.md "USER-APPROVED" (address, cuisine, hours where shown, source_url to the listing pages). Price, distance and veg options were not shown, so they stay empty; veg_options is now yes/no/unknown and unknown is spoken as "not confirmed", never as "no veg". Other locality entries remain placeholders (not indexed).
- get_local_tips: a veg question with no confirmed veg place returns places with unknown veg options plus a note to say veg is not confirmed.
- data/schedule.json event-002: Hackathon judging, 2026-10-19 16:00, venue not announced (curated, from the user).
Evidence:
$ python -m backend.rag.locality -> VALID, 2 real entries; python -m backend.schedule.store -> 1 real event
$ python -m backend.rag.ingest -> 61 chunks (locality 2 embedded)
$ pytest backend/tests -q -> 96 passed, 2 skipped (new test_unknown_veg_is_offered_as_not_confirmed)
Real: "Where can I get good veg lunch nearby?" -> both places named, "Their vegetarian options are not confirmed, so I suggest asking the restaurant directly", chips to both listing pages (first token 7083 ms, first request after restart: too slow, follow-up).
Real: "When is the judging today?" -> "The Hackathon judging starts at 16:00 today. The venue has not been announced yet." (1531 ms)

## Team decisions applied (2026-10-19)
Status: done
- Placement numbers: the user chose /placements/statistics/ (46.50 LPA, 83.97%, 98 companies) as authoritative. backend/rag/ingest.py CORRECTIONS drops the conflicting "Highest Package 14.5 LPA" and the "90% Rate" title from /placements/ before indexing; data/clean keeps the page exactly as scraped. Real: "What is the highest placement package at AITM?" -> "46.50 Lakhs per annum (LPA) [1]", chip placements/statistics only.
- Named students in official news: the user confirmed they are public and the students agreed. Added the karate article. Real: "Did any AITM student win a karate championship?" -> "Yes, final-year MBA student Mr. Ihab Ruknuddin secured first place at the National Level Open Karate Championship 2024 [1]".
- Colab outputs: best.onnx and prep_report.json in the repo root are gitignored (/best.*, /prep_report.json); the model is at backend/vision/weights/gesture.onnx (ignored). Monitor results in monitor/TRAINING-RESULTS.md: test mAP50 0.988, mAP50-95 0.844 (1-epoch baseline mAP50 0.784), CPU p50 18.6 ms. T4.2 is unblocked.
$ python -m scraper.scrape_web -> campus 36, achievements 3; ingest -> 59 chunks, embedded 2, cached 57
$ pytest backend/tests -q -> 95 passed, 2 skipped; frontend tsc, lint, build pass
LinkedIn: unchanged, not scraped (CLAUDE.md rule, BUILD.md non-goal, login wall, LinkedIn terms). Official news pages now cover 8 articles.
Git: the monitor makes one commit of the whole tree on pivot/cloud-core, pushes and opens the PR (user decision); squash-merge to main needs the user.

## M-015 complete department and recruiter lists (2026-10-19)
Status: done
- No AITM page lists every department, and retrieval keeps the top 4, so answers named 3 of 11. Ingest now derives one list record per prefix (DERIVED_LISTS in backend/rag/ingest.py): "AITM departments and programmes" from the 11 scraped /departments/ pages and "Companies that recruit from AITM" from the 12 /placements/recruiters/ pages. Text is built only from the scraped page titles. source_url is "derived:<name>" and the chips expand to the real page URLs it was built from, so no invented URL ever reaches the UI.
- UI: more than 6 chips fold into "+N more sources".
- Router: removed "engineer" from the hiring keywords; it also matched "engineering", sending department questions to the student collection and the slower tool-choice path.
- Startup: VectorStore.warm_up runs one local query per collection with a stored vector (no API call). Measured 6 ms, so the index was not the cold-start cost.
Evidence (real):
"Which engineering departments does AITM have?" -> "AITM has these 11 departments, each with its own official page: ..." with 11 department chips.
"Which companies recruit from AITM?" -> all 12 recruiters listed, 12 recruiter chips plus /placements/.
$ python -m backend.rag.ingest -> 58 chunks, embedded 2 (the two derived lists), cached 56
$ pytest backend/tests -q -> 95 passed, 2 skipped (new test_derived_department_list_cites_each_real_page)
Latency note: the departments question still showed 5.4 s first token after a restart. Logged: query embedding 1866 ms (usually about 600 ms), stream first token 1237 ms; the remaining time is unexplained first-request overhead. Not fixed.
Inbox: M-015 done

## M-014 in-domain unknowns and no hedging (2026-10-19)
Status: done
- rag_eval.yaml: 6 in-domain unknowns, each confirmed absent from data/clean by grep (hostel fee amount, canteen timings, swimming pool, Wi-Fi password, Murudeshwar bus, dress code). They run through the real /api/chat and pass only if the answer is refused or admits not knowing.
- Prompt rules (chat and Live): related information is not an answer, so say "I don't have that yet" when the exact fact (amount, time, password, route) is missing; never hedge with commonly/typically/usually/generally/often for campus facts; list every item the results contain.
Evidence:
$ python -m scripts.rag_eval
in_domain_unknowns 6/6: hostel fee, canteen timings, bus, dress code -> canned refusal; swimming pool -> "there is no mention of a swimming pool at AITM. The campus facilities listed include ..." [1]; Wi-Fi password -> campus is Wi-Fi enabled [1], password not given.
hit_rate_at_4 1.0 (22/22) in the previous run; 0.955 in this run because STEM 2024 missed once. Re-checked three times in a fresh process: STEM page ranks first (0.836) every time. Likely cause: the eval opens data/chroma from a second process while the backend holds it, and Chroma's persistent index is not multi-process safe. The backend alone reads the index in the demo; it is restarted after every ingest.
refusals 3/3.

## M-013 markdown in chat bubbles (2026-10-19)
Status: done
- frontend/src/components/RichText.tsx renders **bold**, *italic*, bullet and numbered lists and paragraphs as React elements (no innerHTML, so model text cannot inject markup). Used for assistant and user bubbles.
- Fallback voice strips grouped citations ([1, 2], [1-3]) as well as [1], plus * # ` before speaking. Live speaks its own audio, so only captions show text there.
$ npx tsc -b, npm run lint, npm run build: pass.
Inbox: M-013 done

## T1.4 RAG eval (2026-10-19)
Status: done
Plan: backend/tests/rag_eval.yaml with 25 items (19 English, 2 Hindi, 1 Kannada answerable; 3 must refuse); every expected URL checked against data/clean (the page text contains the answer); scripts/rag_eval.py reports hit rate at 4 and refusal accuracy; `python tasks.py rag-eval`.
Evidence:
$ python -m scripts.rag_eval (run 1)
hit_rate_at_4 0.955 (21/22), refusals 3/3. Miss: "What was the STEM 2024 event for PUC students?" because stem-2024 was in achievements while the router sends event questions to campus.
Fix: stem-2024 moved to campus in sources.yaml (it is an outreach event). Re-scrape plus ingest: 56 chunks, embedded 1, removed 1.
$ python -m scripts.rag_eval (run 2)
{"hit_rate_at_4": 1.0, "answerable": 22, "hits": 22, "refusals": "3/3", "rag_min_score": 0.62, "rag_min_keyword_coverage": 0.6}
Latency: retrieval about 0.55 to 0.8 s per English question, 1.4 to 1.5 s for Hindi and Kannada (one translation call each).
Cross-language (ADDENDUM-01 7.2): Hindi and Kannada queries retrieve the English pages (e.g. Hindi placement rate -> placements/statistics, score 0.827).
Data issue for the team: the official site contradicts itself. /placements/ says highest package 14.5 LPA and 150+ recruiters; /placements/statistics/ says 46.50 LPA (2023-24) and 98 companies. The host cites whichever page it retrieves.
Threshold: RAG_MIN_SCORE stays 0.62 with gemini-embedding-2; refusals are 3/3 and no answerable question was refused.

## M-012 grouped citations and AITM news (2026-10-19)
Status: done
- M-012: citations are parsed in every form the model writes ([1], [1][2], [1, 2], [1,2], [1-3], [2–4]); test test_grouped_citations_are_parsed. Grouped-only answers keep their chips again.
- News: 5 public articles from https://aitm.edu.in/news/ added (Independence Day, human chain, MBA background, placements, STEM 2024). URLs taken from the official listing page, not from memory. Skipped: KEA seat notice (stale admissions notice), the karate article (names a student; consent decision pending with the team), and the stray /news/news/ link.
$ python -m scraper.scrape_web -> campus 35 records, achievements 3 (fees and scholarship pages still HTTP 500 from the server)
$ python -m backend.rag.ingest -> chunks 56, embedded 5, cached 51
$ pytest backend/tests -q -> 94 passed, 2 skipped
Needs the team: the already-indexed cricket article also names players (captain and wicket-keeper). Decide one consent rule for named students in official news; the karate article waits on the same decision.
LinkedIn: the monitor agrees the non-goal stays; flagged for the humans in monitor/REVIEW.md. Official news covers most of what LinkedIn would have added.
Inbox: M-012 done

## Monitor round 3: M-009 reopened, M-011, M-008c (2026-10-19)
Status: done
- M-009 reopened: a greeting whose grounding lookup found nothing ("hello, I'm here for the hackathon" -> get_schedule, 0 events) now greets and says the information is not available, instead of the bare refusal. Real: "Hello and welcome! I cannot answer your question from the campus data I have right now, so please check with the help desk or a student volunteer".
- M-011: blocked providers (401/403/404) are never retried while others are only busy (the old "try anyway" fallback put Groq back in); when every backend answered 429, wait TEXT_BUSY_RETRY_S=1.5 and retry the primary once.
- M-008c: plain campus questions (router picks only campus or achievements, no schedule, hiring, locality, memory or greeting words) skip the tool-choice call and search directly (CHAT_DIRECT_SEARCH). Real: "Tell me about the CSE department" first token 1559 ms with 3 department chips.
- Regression found and fixed: a synthesized tool call has no Gemini thought_signature, so Gemini returned 400 "Function call is missing a thought_signature" on every backend. Direct results now go in as a context message; a test asserts no fabricated tool calls in history.
- Chroma "Error creating hnsw segment reader: Nothing found on disk" reproduced in tests (the earlier intermittent failure): a vector query failure now falls back to BM25 results for that collection instead of failing the turn.
- One real placement answer came back without [n] markers, so it showed no chips; the direct-search context now asks for [n] after every fact.
$ pytest backend/tests -q -> 93 passed, 2 skipped (four consecutive runs)
LinkedIn (user question): not scraped. CLAUDE.md "Do not scrape LinkedIn, Instagram, login-walled pages", BUILD.md section 7 non-goal, LinkedIn terms forbid it, page is login-walled. Proposed to the monitor: a hand-curated news file with source URLs to public posts, preferring non-login sources; waiting for the user's approval before building it.

## Monitor P0s M-009, M-010, M-011 and latency M-008 (2026-10-19)
Status: done
Verified first from logs/usage.jsonl (last 400 calls): flash-lite tools ok 32 / 429 18; stream ok 21 vs first_token 17 (4 empty streams); 45 Groq 404s on real calls; 119 health model listings.
Fixes:
- M-009: a turn where no grounding tool ran (greeting answered with get_visitor_profile) is no longer a refusal; it streams with NO_FACTS_NOTE (no campus facts). Refusal now means: a grounding tool ran and returned nothing usable.
- M-010: an empty stream gets one non-streamed retry, then the canned refusal with refused true. search_campus chips appear only for [n] numbers the answer cites, so an answer citing nothing shows no chips.
- M-011: a 429 with a single key fails over at once (no retries against the same quota); backup backend gemini-backup on GEMINI_BACKUP_MODEL=gemini-3.1-flash-lite (own per-model quota; one real tool call worked but took 11.4 s, so it is a last resort); providers answering 401/403/404 cool down TEXT_BLOCKED_COOLDOWN_S=900 instead of 120; refusals skip memory extraction; health provider probes cached HEALTH_CACHE_S=120 (was 30).
- M-008: query embeddings are prefetched in parallel with the tool-choice call and kept in an LRU (QUERY_EMBED_CACHE=256). The vector search uses the visitor's own words, BM25 adds the model's query.
Evidence:
$ pytest backend/tests -q -> 88 passed, 2 skipped (new: greeting with profile tool not refused, empty stream retries then refuses, 429 single key fails over at once, blocked provider long cooldown, query embedding cached and prefetched). One unexplained intermittent failure in 10 full runs (truncated "Run..." error, likely a Windows temp file lock); 9 later runs clean.
$ python -m scripts.chat_probe (real):
"Hi! I just arrived on campus." -> get_visitor_profile, not refused, "Welcome! We are so glad you are here. How can I help you get settled in today?..." (first token 4083 ms, first request after restart)
"What is the GDP of the moon base?" -> search_campus, refused true, chips [] (863 ms)
"What is the placement rate at AITM?" -> chips [placements/statistics], "83.97%, 393 out of 468 ... 46.50 LPA [1]", first token 1634 ms (was 2.5 to 3.5 s)
Inbox: M-009 done | M-010 done | M-011 done | M-008 done (first token 1.6 s on a factual question; chat target 1 s still not met, the tool-choice call is the remaining cost)

## User testing round 2 (2026-10-19)
Status: done
1. Stats question still missed after the BM25 synonyms: the tool-selection model shortened the query to "Anjuman". Fix: search_campus searches the visitor's own words plus the model query (chat passes the typed message, Live passes the spoken transcript as user_message). Verified for real: "What are the recent stats about Anjuman?" -> answer "placement rate 83.97 percent, 393 of 468, highest package 46.50 LPA [2] ... VTU Inter Zone Championship 2025 [1]", sources placements/statistics and news/aitm-cricket.
2. Find talent returned HTTP 500: the model returned "mode": null and RoleSpec rejected it. Fix: RoleSpec validators turn null into "" and a single string into a one-item list. Test test_role_spec_accepts_model_nulls_and_strings. Verified for real: role intake returns {"title":"Frontend Intern","must_have":["built React applications"],...}. Match is [] because students_optin.csv is empty (expected, honest). Created one test visitor "Test Recruiter" while verifying.
3. Voice input on the hiring role box: frontend/src/hooks/useDictation.ts (MediaRecorder with echo cancellation and noise suppression -> /api/stt -> appended to the text), "Speak the role" button.
4. Noisy venue: Live voice activity detection is configurable and defaults to START_SENSITIVITY_LOW, END_SENSITIVITY_HIGH, prefix 300 ms, silence 700 ms (Live defaults to HIGH start sensitivity, from the installed SDK typings). Verified for real: locked token accepted, "What is the placement rate at AITM?" answered 83.97% from placements/statistics.
Decision (user): no Sarvam for now; test the current noise settings at the venue first. Wispr Flow is a desktop dictation app, not an embeddable API (not verified).
$ pytest backend/tests -q -> 83 passed, 2 skipped; tsc -b and lint pass.

## Bug fixes from user testing (2026-10-19)
Status: done
1. "What are the recent stats about Anjuman?" refused although https://aitm.edu.in/placements/statistics/ is indexed. Cause: BM25 never matched "stats" to "statistics", and gemini-embedding-2 scores every AITM page 0.66 to 0.69 for vague questions, so unrelated pages passed RAG_MIN_SCORE 0.62 and the model honestly said it had no stats. Fix: SYNONYMS map in backend/rag/bm25.py (stats->statistic, lpa/salary->package, cse->computer, ...). After: the statistics page enters the top 4 for the exact question. Follow-up: recalibrate RAG_MIN_SCORE for gemini-embedding-2 in T1.4 (rag_eval).
2. Live greeted visitor SKYN in Spanish. Cause: Live input transcription heard "el nombre"; extraction stored language "es" from that two-word fragment and every new session mirrored it. Fix: language only changes on turns of LANGUAGE_MIN_WORDS=4 or more and only to SUPPORTED_LANGUAGES (en, hi, kn, ur); prompts default to English and switch only on a full sentence. Test test_language_ignores_short_fragments_and_unsupported_languages.
DB: ran UPDATE visitors SET language='' WHERE code='SKYN' AND language='es' -> 0 rows; a later English turn (13:32) had already set it to 'en'. No rows changed.
$ pytest backend/tests -q -> 82 passed, 2 skipped

## T0.4 / T2.1 Live voice (2026-10-19)
Status: in progress (Live session, tools, welcome and grounding verified for real; mic, barge-in and phone still need a human test)
Plan:
- frontend/src/hooks/useLive.ts: token from /api/live/token, @google/genai loaded lazily, AudioWorklet mic at 16 kHz PCM, 24 kHz gapless playback flushed on serverContent.interrupted, captions from transcriptions, tool calls forwarded to /api/tools (look snapshots the camera to /api/look), chips from tool results only, goAway and close -> resume with handle, then a fresh session seeded with memory, at most 3 reconnects before the fallback voice.
- Transcripts feed memory: POST /api/visitor/{id}/turn (last ten turns plus extraction).
- Talk tab replaces Voice and Video; camera preview plus Look button; Fallback voice badge with push to talk when Live is off or unavailable.
- Fallback TTS order: Groq Orpheus, Gemini TTS, browser speechSynthesis (with the language from STT). Text chunks are at most 200 characters.
Verified from the installed SDK (@google/genai 2.30, node_modules typings and source), not memory: apiKey takes the ephemeral token, auth_tokens/ prefix switches to BidiGenerateContentConstrained, LiveServerContent.interrupted / inputTranscription / outputTranscription, toolCall.functionCalls, sessionResumptionUpdate.newHandle, goAway.timeLeft.
Finding: the REST token API rejects liveConnectConstraints (HTTP 400 "Unknown name"); the wire format is bidiGenerateContentSetup with generation settings under generationConfig, and every field in the setup must be listed in fieldMask. sessionResumption and contextWindowCompression are left to the browser.
Evidence (node frontend/scripts/live_probe.mjs, one short real session per run; final run):
token 680 ms, model gemini-3.8-live, api v1beta, locked true
open 861 ms; welcome audio 1418 ms after the cue: "Welcome to Hello Campus."
tools: search_campus(query "AITM cricket title 2025", collections achievements) -> https://aitm.edu.in/news/aitm-cricket/
answer first audio 2227 ms after the question (includes the tool round trip), caption: "AITM won the VTU Inter-Zone Championship in 2025, according to the AITM cricket achievement page."
Fixed on the way: citation markers were read aloud ("[1]"), now voice rules forbid them; Live never greeted because it waits for input, now a welcome cue is sent on fresh sessions.
$ pytest backend/tests -q -> 81 passed, 2 skipped; npm run lint, tsc -b, npm run build pass; main bundle 264 kB, Live SDK chunk loads on first Talk; no key material in dist/.
Latency: first answer audio 1.9 to 3.2 s across runs, over the 1.5 s budget; the tool round trip (embedding about 0.6 s plus search) is most of it. Follow-up: measure with real speech, consider caching query embeddings.
Not yet verified: real microphone capture, interruption mid-answer (acceptance), phone browser, Look with a real poster (T2.2).
Dependency added: @google/genai 2.30.0 (frontend), required by ADDENDUM-01 section 3.
Note: uvicorn --reload on this Windows laptop missed several file changes; restart the backend after editing backend/llm or backend/routes.

## M-006 / T1.1 AITM campus snapshot widened (2026-10-19)
Status: done
Plan:
- sources.yaml: every non-faculty URL from https://aitm.edu.in/sitemap.xml (robots.txt Allow: /, Crawl-delay 1). The 37 /faculty/* personal pages stay out (no opt-in).
- PoliteFetcher timeout is now SCRAPE_TIMEOUT_S=45 with one retry on timeout: the site often takes over 20 s.
Evidence:
$ python -m scraper.scrape_web   (run 1: 26 records, 10 timeouts; run 2 from cache plus refetch)
campus: 32 records, all https://aitm.edu.in/ source URLs; achievements: 1
Still failing on the server side: HTTP 500 for /admissions/fees/ and all 8 /admissions/scholarships/* pages. Kept in sources.yaml so a later scrape picks them up.
$ python -m backend.rag.ingest
chunks 51 (campus 50, achievements 1), embedded 45, cached 6, 3.9 s, one batch embed call
Inbox: M-006 done (32 aitm.edu.in records, ingest report logged)

## Groq as primary voice (user decision, 2026-10-19)
The user confirmed Groq STT and TTS are a main feature. This network returns HTTP 404 for every Groq endpoint, so Groq must be reached from another network (venue Wi-Fi, hotspot or VPN). Check: curl https://api.groq.com/openai/v1/models returns 401 without a key when reachable. Code keeps Groq first; failover order for TTS is Groq Orpheus, then Gemini TTS, then browser speechSynthesis. SERVER_TTS_ENABLED now defaults to true with text split into chunks of 200 characters or fewer (M-005 limit).

## M-008 Chat latency on Gemini (2026-10-19)
Status: done
Plan:
- GEMINI_REASONING_EFFORT config sent as reasoning_effort on the OpenAI-compatible endpoint when set.
- Text read timeout TEXT_TIMEOUT_S=12 (was 30), timeouts retried at most RETRY_TIMEOUTS=1 times, then the call fails over.
- Streams fail over when no first token arrives within TEXT_FIRST_TOKEN_TIMEOUT_S=6.
Evidence:
$ pytest backend/tests -q
80 passed, 2 skipped (new: reasoning_effort only when configured, timeout retried once then failover, stalled stream fails over)
Benchmark (one streamed call each, real):
gemini-3.8-flash  reasoning_effort=low   no first token within 12 s, twice (ReadTimeout)
gemini-3.5-flash-lite  default           first token 758 ms, total 905 ms
Decision: keep gemini-3.5-flash-lite for chat and Look. GEMINI_REASONING_EFFORT stays empty. Worst case for a stalled text backend is now about 24 s before failover instead of about 2 minutes.
Inbox: M-008 done (evidence above)

## T4.0 prep: gesture notebook restored for ADDENDUM-03 (2026-10-19)
Status: done (notebook ready for the team's Colab run; no training results claimed)
ADDENDUM-03 (Buzzer Quiz) adopted: confirmed by the user in this session.
Plan:
- Restore training/ from 5223ddf~1 (the deletion commit) instead of a full revert, so the old local vision runtime stays removed until T4.2.
- Classes palm, one, peace, three, four, no_gesture. Data cj-mills/hagrid-sample-120k-384p (CC BY-SA 4.0, checked via the HF API and README).
- Layout-agnostic loader: the zip layout is undocumented, so <class>.json and images are found by name. no_gesture comes from per-hand labels; images with any other gesture label are skipped whole and counted.
- yolo26n, imgsz 416, 40 epochs, patience 10, subject split by user_id, export end2end=False with an output-shape assert.
Evidence:
$ python training/build_notebook.py
wrote training/gesture_yolo.ipynb
$ pytest backend/tests/test_training.py -q
28 passed in 2.20s
Follow-ups: team runs training/gesture_yolo.ipynb on Colab GPU, downloads best.onnx to backend/vision/weights/gesture.onnx, pastes the mAP tables into README.

## T0.2 Model IDs verified (2026-10-19)
Status: done for Gemini; Groq blocked from this network
Sources: ai.google.dev/gemini-api/docs/models, /docs/embeddings, /docs/ephemeral-tokens, /docs/models/gemini-3.8-live (research pass plus monitor/RESEARCH.md); Gemini GET /v1beta/models with our key. Groq IDs from monitor/RESEARCH.md (console.groq.com docs, deprecations page), not callable from here.
Evidence (python -m scripts.verify_models, one real call each, user approved the lean run):
PASS gemini embed doc gemini-embedding-2      822 ms  dim=768
PASS gemini embed query gemini-embedding-2    619 ms  dim=768
PASS gemini vision gemini-3.8-flash         12671 ms  (after one 30 s ReadTimeout)
PASS gemini tts gemini-3.8-flash-tts         2724 ms  104078 bytes WAV
PASS gemini live token gemini-3.8-live        463 ms  token minted (v1beta, M-002)
PASS gemini chat gemini-3.8-flash          76486 ms  (two 30 s ReadTimeouts, then 15.2 s for 1 token)
PASS gemini json gemini-3.5-flash-lite        678 ms
PASS vision gemini-3.5-flash-lite            1381 ms
FAIL groq chat openai/gpt-oss-120b / json openai/gpt-oss-20b: HTTP 404 Not Found (same without a key)
Decision: gemini-3.8-flash is far over the latency budget (chat first token under 1 s, Look under 4 s), so GEMINI_CHAT_MODEL and GEMINI_VISION_MODEL are gemini-3.5-flash-lite. 3.8-flash stays available via .env.
Tokens used: about 1,180 prompt and 60 output tokens total (logs/usage.jsonl).
Needs the team: is Groq reachable from the venue network or a phone hotspot? If yes, Groq becomes primary again with no code change.

## T0.1 to T1.7 cloud core (in progress on branch pivot/cloud-core)
Status: in progress
Evidence so far:
$ pytest backend/tests -q   (real network blocked by conftest, zero quota spent)
48 passed, 2 skipped (public-network scraper checks, opt in with HC_NETWORK=1)
$ provider probe: Gemini /v1beta/models lists gemini-3.8-live, gemini-3.8-flash, gemini-embedding-2, gemini-3.8-flash-tts, gemini-3.5-flash-lite.
$ curl https://api.groq.com/openai/v1/models (no key) -> HTTP 404 {"error":{"message":"Not Found"}}; console.groq.com/docs also 404 from this network (Cloudflare MAA). Expected 401 without a key, so Groq looks blocked from this network, not a key problem.
Stack deviation (logged before use): text calls go through TextLLM, Groq first, failing over to Gemini's OpenAI-compatible endpoint (gemini-3.8-flash chat, gemini-3.5-flash-lite JSON) with a 120 s cooldown. Groq stays primary per ADDENDUM-01. Verified: one chat and one tool-call request to the Gemini OpenAI endpoint returned 200 (tool calls carry extra_content.thought_signature, echoed back).
Free-tier care (user request): tests never call providers; rules-only router (no LLM routing call); one tool-selection call per chat turn; embeddings cached by content hash; server TTS off by default (browser speechSynthesis).
Inbox: M-001 done (evidence: git check-ignore prints only logs/usage.jsonl and data/memory.sqlite3) | M-002 done in code (v1beta + liveConnectConstraints, unit test test_live_token_v1beta_with_constraints); real mint call pending T0.2 | M-003 done (gemini-embedding-2 with text templates, outputDimensionality 768, unit test) | M-004 done (BLOCKING on grounding tools, NON_BLOCKING on remember and shortlist, test_grounding_tools_block_on_live) | M-005 done (SERVER_TTS_ENABLED=false default) | M-006 deferred to the next task (scraping)
Git: deletions are commit 5223ddf on branch pivot/cloud-core; work lands on main via squashed PRs (user request).
T1.3 ingest (real, gemini-embedding-2, 768 dims): run 1 embedded 6 chunks in 3.1 s; run 2 embedded 0, cached 6, in 1.4 s. data/ingest_report.json written. No prior data/chroma existed, so nothing was reset.
T1.6 chat (real): curl /api/chat "Which cricket title did AITM win in 2025?" (analyst) -> meta, tool search_campus, token x2 "AITM won the VTU Inter-Zone Championship 2025 [1].", sources [aitm.edu.in/news/aitm-cricket/ ...], done 2791 ms via gemini failover.
T1.6 refusal (real): "Where can I get good veg lunch nearby?" -> tool get_local_tips(food, veg) -> canned refusal, sources [], refused true, 1153 ms. Locality placeholders stay unindexed until the team verifies monitor/LOCALITY-DRAFT.md.
Health: /api/health reports gemini reachable, text_groq unreachable (404), text_gemini reachable, ok true.
Follow-up: source chips currently list every confident tool source; filter to the [n] numbers the answer cites.
Inbox: M-007 done (download cell defines HF_REPO/HF_FILE before use; Drive copy plus browser download fallback plus printed paths; test_notebook_defines_every_name_before_use)

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
