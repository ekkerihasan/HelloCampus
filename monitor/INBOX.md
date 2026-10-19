# Monitor Inbox (for the builder)

Reply by item ID in PROGRESS.md (ADDENDUM-02 section 3). Max 5 open items.

## M-001 [P1] [reliability] Offline snapshot not committable; usage log will be committed
Status: verified cycle 4 (`git check-ignore` prints only logs/usage.jsonl and data/memory.sqlite3; data/chroma committable)
Found: cycle 1, during T0.1
Evidence: `.gitignore` contains `data/chroma/` and `data/*.sqlite3`. ADDENDUM-01 7.5: "`data/clean/` and `data/chroma/` are committed as the offline snapshot". `logs/` is not in `.gitignore`, and `settings.usage_log_path` is `logs/usage.jsonl`.
Why it matters: a fresh clone (or the second team laptop) cannot answer anything until someone re-ingests with a working key; usage logs end up in commits.
Proposal: remove `data/chroma/` from `.gitignore` (keep `data/memory.sqlite3` ignored; decide whether `data/embed_cache.sqlite3` is committed so re-ingest on another laptop costs 0 calls). Add `logs/`.
Effort: S
Accept when: `git check-ignore data/chroma/x logs/usage.jsonl` prints only `logs/usage.jsonl`.

## M-015 [P1] [truth] "Which departments does AITM have?" lists 3 of 11 as if complete
Status: verified cycle 7: departments question lists all 8 engineering departments with 11 chips (MBA, MCA, Basic Science correctly excluded as non-engineering); recruiters lists all 12 with 13 chips; every chip URL exists in data/clean. First request after restart 5.0 s first token, then 1.5 s (cold start, builder logged).
Found: cycle 6, after the M-014 prompt change
Evidence: /api/chat analyst "Which engineering departments does AITM have?" -> "AITM has the following engineering departments: CSE (with AIML and Data Science) [1], Civil [3], Mechanical [4]". data/clean/campus.jsonl has 11 /departments/ records (Basic Science, Civil, CSE AI-ML, CSE Data Science, CSE, EEE, ECE, MBA, MCA, Mechanical, Robotics and AI). No single page lists them all (home page mentions 6, academics page 1), and retrieval returns top 4 chunks, so list questions are incomplete by construction. The new "list every item the results contain" rule cannot fix it.
Why it matters: "which departments" is one of the most likely judge questions. Omitting EEE, ECE, Robotics and AI, MBA, MCA while saying "the following" reads as a factual error.
Proposal: at ingest, derive one record "AITM departments" from the titles and URLs of the 11 scraped department records (derived from stored data, nothing invented; each item carries its own source URL), or a small `list_departments` path in search_campus for list-style questions. Same pattern helps "which recruiters" (12 recruiter pages).
Effort: S to M
Accept when: the question lists all 11 departments with chips, and rag-eval still passes.

## M-014 [P1] [truth] RAG eval refusals are all off-topic; add in-domain unknowns, the risky kind
Status: verified cycle 6 via /api/chat: hostel fees, canteen hours, Murudeshwar bus, dress code refused; swimming pool and Wi-Fi password say not mentioned and cite only real facilities (facilities page); principal 'Dr. K. Fazlurahman' grounded on /about/. Builder eval 6/6 in-domain unknowns.
Found: cycle 6, reproduced `python -m scripts.rag_eval`: hit@4 1.0 (22/22), refusals 3/3
Evidence: the 3 refusal cases are "What is the GDP of the moon base?", "What is the capital of Mongolia?", "Who won the 2018 FIFA World Cup?". All are obviously off-domain. None test plausible campus questions the data cannot answer, which is where a model is most tempted to make things up, for example "What are the hostel fees?", "What time does the canteen close?", "Who is the principal?" (if not in data), "Is there a swimming pool?", "What is the Wi-Fi password?". Also ADDENDUM-01 7.6 asks for 3 refusal cases minimum; more in-domain ones make the 3/3 claim meaningful.
Why it matters: "refusals 3/3" will be quoted on stage; a judge's first adversarial question will be in-domain.
Proposal: add 5 in-domain unknowns to rag_eval.yaml (check each is truly absent from data/clean first), plus the same 5 through /api/chat to check the answer refuses rather than hedging with generic knowledge. Related wording nit seen in the browser: "While specific department lists can vary, AITM offers ... which commonly include" is generic hedging; the system prompt could forbid "commonly", "typically", "usually" phrasing for campus facts.
Effort: S
Accept when: rag-eval shows refusals at least 7/8 with the new cases, numbers logged in PROGRESS.md.

## M-013 [P1] [ux] Chat answers show raw markdown (** and * bullets) on screen
Status: verified cycle 6 in Chrome: 'Tell me about AITM's departments and placements' renders bold headings and bullet lists, no visible asterisks, chips intact.
Found: cycle 6, browser test of :5173 (Chrome, laptop width)
Evidence: clicking the suggestion "Tell me about AITM" rendered literal text: "**AITM (Anjuman Institute of Technology and Management)** is a premier..." and lines "* **Academic Offerings:** It is a VTU-affiliated...". `grep -r "markdown|dangerouslySetInnerHTML" frontend/src` finds no rendering. The Gemini models format with markdown by default.
Why it matters: it is the first answer a judge sees and it looks unfinished. On the fallback voice path, browser speechSynthesis may also read the asterisks aloud.
Proposal: (1) render a safe subset in the chat bubble without innerHTML: split lines, turn lines starting with "* " or "- " into list items and **x** into <strong>, leave [n] as is; and (2) strip markdown before speechSynthesis. Alternatively tell the model "plain sentences, no markdown, short bullets with a leading dash" in the system prompt, but (1) is more reliable.
Effort: S
Accept when: "Tell me about AITM" shows bold and bullets with no visible asterisks, and the fallback voice does not say "asterisk".

## M-012 [P1] [truth] Grouped citations "[1, 2]" are not parsed: cited sources dropped, some factual answers show zero chips
Status: verified cycle 6: 5 of 5 library questions show the library chip, including grouped citations like [1, 2] and [1, 3]; builder test covers [1], [1][2], [1, 2], [1,2], [1-3].
Found: cycle 5 round 3
Evidence: "Is there a library on campus?" (analyst) answered 874 characters of facts with **0 chips** in the burst run. A rerun answered "there is a central library on campus [1, 2] ... [1] ... [1, 2]" and showed only source 1; source 2 was cited but dropped. `merge_sources` uses `re.findall(r"\[(\d+)\]", answer)`; on "library [1, 2]. facilities [1, 2]." it returns []. After the M-010 rule (no search chips without a parsed citation), an answer that cites only in grouped form loses all chips. The facts themselves were grounded (30,000+ books and IEEE are on https://aitm.edu.in/library/).
Why it matters: a grounded answer with no visible sources looks like a hallucination to a judge, and breaks "every factual answer cites sources".
Proposal: parse all numbers inside brackets: `re.findall(r"\[([\d,\s]+)\]")`, then split on commas; also accept "[1][2]" and "[1-2]". Optionally instruct the model to cite as "[1][2]". Unit test with "[1, 2]", "[1,2]", "[1][2]", "[1-3]".
Effort: S
Accept when: those formats all map to the right chips in a test, and 5 library questions all show the library chip.

## M-009 [P0] [bug] Greeting is refused: "Hi! I just arrived on campus." returns "I don't have that yet"
Status: verified cycle 5 round 3: "hello, I'm here for the hackathon" and "Hi, I'm a judge today, what's happening?" both get a warm welcome plus an honest note that the schedule is not available; no refusal, no invented facts. The judge greeting took 8.9 s to first token (outlier).
Found: cycle 4, black-box chat probe against :8000
Evidence: POST /api/chat {"message":"Hi! I just arrived on campus.","character":"guide"} -> meta smalltalk=false, tool get_visitor_profile, token "I don't have that yet. The help desk or a student volunteer will know...", sources [], refused true (1.35 s). Cause: `backend/llm/chat.py:90-91` forces `tool_choice="required"` on round 0, so a greeting must call a tool; `is_smalltalk` did not match this greeting; the model picks get_visitor_profile, which errors without a visitor, and `grounded()` turns that into a refusal.
Why it matters: demo step 1 is the welcome briefing. A judge's first message gets a refusal.
Proposal: use `tool_choice="auto"` on round 0 and let a no-tool answer go to the Guide only for greetings or small talk (the system prompt already forbids facts without tools). Or widen `is_smalltalk` and treat a non-grounding tool error as small talk, not a refusal. Add tests for "Hi! I just arrived on campus.", "hello, I'm here for the hackathon", "thanks!".
Effort: S
Accept when: those 3 messages get a warm reply with no refusal and no fabricated facts; refusal tests still pass.

## M-010 [P0] [truth] Empty answers with source chips, and chips shown on refusal text
Status: verified cycle 5: 29 turns, 0 empty answers (3 empty streams in usage.jsonl were retried invisibly); moon-base shows no chips; Nobel refused true with no chips. Minor: moon-base text is a refusal but refused=false; chips empty so not misleading.
Found: cycle 4, chat probe plus logs/usage.jsonl
Evidence: (a) "Tell me about AITM's Nobel prize winner." -> tool search_campus, ZERO token events, then sources [aitm-cricket, home, about], refused false. Repeating "Which engineering departments does AITM have?" 3 times gave no tokens on 2 of 3. usage.jsonl last 15 min: gemini-3.5-flash-lite stream ok=19 but stream_first_token=15, so 4 streams finished with no content. (b) "What is the GDP of the AITM moon base?" -> text "I do not have that yet..." but sources [wipro, placements/statistics, placements], refused false. Cause: `chat.py:106-112` emits sources even when the stream yielded nothing, and `merge_sources` (`chat.py:47-51`) keeps every search_campus chip when the answer cites no [n].
Why it matters: an empty bubble with citation chips, or citations attached to "I don't know", makes the host look broken or misleading. This breaks the truthfulness rule that chips come from evidence the answer used.
Proposal: (1) if the stream yields no text, retry once non-streamed (`complete`), and if still empty send REFUSAL with refused true and no chips; log it. (2) If the answer cites no [n], send no search_campus chips (keep chips for tools whose items are the answer); if the answer matches the refusal wording, set refused true. Tests for both.
Effort: S
Accept when: 10 repeats of the departments question all produce text; the moon-base and Nobel questions produce refusal with sources [] and refused true.

## M-011 [P0] [reliability] 32% of Gemini calls hit 429 at light load; Hindi and concurrent chats fail with "Gemini is busy"
Status: verified cycle 5 round 3: 17 turns in 44 s (12 sequential, 3 concurrent, 1 Hindi, 2 greetings): 0 errors, 0 empty. Groq no longer called. Most turns served by gemini-backup (3.1-flash-lite) while primary cools down; 1 backup 429 absorbed invisibly. Re-test at demo pace during T3.2.
Found: cycle 4, chat probe (about 25 chat turns over 3 minutes, 3 concurrent)
Evidence: usage.jsonl last 15 min: gemini-3.5-flash-lite tools ok 30 / 429 18, json ok 12 / 429 4, stream ok 19 / 429 4. The Hindi question and the code question returned event error "Gemini is busy right now" after 6.5 s and 8.2 s; 2 of 3 concurrent chats on one visitor failed the same way. Each turn costs 3 Flash-Lite calls (tool round, stream, memory JSON) plus 1 embedding, and Groq is unreachable, so there is no second provider. Groq is also still retried every cooldown (24 tools 404 and 13 stream 404 in 15 min).
Why it matters: rehearsals plus judges asking quickly will see "Gemini is busy". T3.2 requires no visible 429.
Proposal: (1) on Gemini 429, fail over to a second model with its own per-model quota (for example `gemini-3.8-flash` with reasoning_effort low, or `gemini-3.5-flash`) before giving up, config-driven list; (2) cut calls per turn: skip memory extraction on refusals and small talk, and run it only when the message has a first-person statement (I am, I'm, my, remember); (3) `TEXT_PROVIDER_ORDER` config so Groq is not tried at all on networks where it is blocked; (4) team action: a second Gemini key from a different Google Cloud project, rotated on 429 like Groq.
Effort: M
Accept when: 30 chat turns in 5 minutes (including 3 concurrent and 2 Hindi) show zero user-visible "busy" errors; 429 counts logged.

## M-008 [P1] [perf] Chat on gemini-3.8-flash took 76 s; thinking is never limited
Status: open
Found: cycle 3, PROGRESS.md T0.2 log
Evidence: PROGRESS.md: "PASS gemini chat gemini-3.8-flash 76486 ms (two 30 s ReadTimeouts, then 15.2 s for 1 token)" and "gemini vision gemini-3.8-flash 12671 ms (after one 30 s ReadTimeout)". Same log: gemini-3.5-flash-lite json 678 ms, vision 1381 ms. `grep thinking|reasoning_effort backend/` finds nothing, so 3.8 Flash runs at its default thinking level. https://ai.google.dev/gemini-api/docs/openai: `reasoning_effort` maps to `thinking_level`; "Reasoning cannot be turned off for ... 3 models"; `minimal` returns an error on 3.8 Flash (monitor/RESEARCH.md), so `low` is the floor. Groq is blocked here, so this failover path is the real chat path on demo day.
Why it matters: ADDENDUM-01 budget is chat first token under 1 s and Look under 4 s. A 15 to 76 s wait kills demo steps and makes the 30 s timeout plus retries the visitor's experience.
Proposal: (1) send `reasoning_effort: "low"` (config value, e.g. `GEMINI_REASONING_EFFORT=low`) on every OpenAI-compat chat and tool call to 3.8 Flash; (2) measure 5 chat calls each on 3.8-flash(low) and 3.5-flash-lite, and pick the faster acceptable one for `GEMINI_CHAT_MODEL`. Consider flash-lite for `GEMINI_VISION_MODEL` too (Look measured 1.4 s); (3) a separate shorter first-byte timeout for streaming (e.g. 8 s) that fails over to the fast model instead of waiting 30 s twice.
Effort: S to M
Accept when: chat first token p50 under 3 s over 5 real calls, Look under 4 s, numbers logged in PROGRESS.md.
Cycle 4 update: builder switched chat and vision to gemini-3.5-flash-lite. Measured first token now 2.5 to 3.5 s on factual questions (13 runs). Breakdown from usage.jsonl p50: query embedding 644 ms, then tool round 900 ms, then stream first token 760 ms, all sequential. Next latency wins, in order: (a) start retrieval on the raw user message in parallel with the tool-choice call and reuse it when the model calls search_campus with a similar query (saves about 650 ms); (b) LRU cache query embeddings (repeat questions in rehearsal and demo); (c) for questions the rules router classifies confidently, skip the tool-choice LLM call and call the tool directly (saves about 900 ms and one quota unit, also helps M-011). Target first token under 1.5 s.

## M-007 [P0] [bug] Colab notebook fails at cell 3: HF_REPO and HF_FILE defined later in cell 6
Status: verified cycle 3 (cell 3 defines HF_REPO/HF_FILE; cell 13 copies outputs to Drive, tries files.download, prints paths; test_training.py 29 passed incl. use-before-define check). Colab run itself not yet done.
Found: cycle 3, review of `training/gesture_yolo.ipynb` (branch pivot/cloud-core)
Evidence: cell 3 calls `hf_hub_download(repo_id=HF_REPO, filename=HF_FILE, ...)`, but `HF_REPO` and `HF_FILE` are first assigned in cell 6. Running top to bottom on a fresh runtime gives `NameError: name 'HF_REPO' is not defined`. The file name itself is correct: the HF API lists `hagrid-sample-120k-384p.zip` (and license cc-by-sa-4.0).
Why it matters: T4.0 training is the long pole for ADDENDUM-03. The user is about to run it through the VS Code Colab extension, and a failure at cell 3 wastes the GPU session.
Proposal: move `HF_REPO` and `HF_FILE` (and the constants in cell 4) into cell 1 or a new constants cell before cell 3, regenerate via `build_notebook.py`, and add a test that executes the cells' top-level names in order (or at least checks every name used in cell N is defined in cells 0 to N). Also, `google.colab.files.download` relies on the Colab browser front end and may not work through the VS Code Colab extension. Add a fallback: copy `best.onnx` and `prep_report.json` to Google Drive (`drive.mount`) or print the path so the user can download from the VS Code file explorer.
Effort: S
Accept when: a fresh-kernel order check passes in a test, and the notebook has a download path that works without the Colab web UI.

## M-006 [P1] [truth] Only 3 of 81 official AITM pages are scraped
Status: verified cycle 4 (data/clean/campus.jsonl 32 records with aitm.edu.in URLs; ingest report campus 50 chunks, 45 embedded, 5 cached)
Found: cycle 1 (`scraper/sources.yaml`, `data/clean/`)
Evidence: `curl https://aitm.edu.in/sitemap.xml` lists 81 URLs. robots.txt says `Allow: /` and disallows only admin, accounts and private media. `sources.yaml` has 3 campus URLs and 1 achievement. The data holds 3 campus records and 1 achievement.
Why it matters: a thin corpus means most visitor questions get refused, `rag_eval.yaml` cannot reach 20 meaningful questions, and Look cannot match posters to campus data. These are real official URLs from the sitemap, not invented ones.
Proposal: add to `campus` in `sources.yaml`: `/`, `/academics/`, `/admissions/`, `/admissions/fees/`, `/placements/`, `/placements/statistics/`, `/library/`, `/facilities/`, and all 11 `/departments/*/` pages from the sitemap. Recruiter pages (`/placements/recruiters/*`) can go into `achievements` or `campus` as "who hires here". Skip the 37 `/faculty/*` pages: they are individual people who did not opt in, so leave them out unless the team decides otherwise. Re-scrape at 1 request per second, then ingest and commit `data/clean/`.
Effort: S
Accept when: `data/clean/campus.jsonl` has at least 15 records with `https://aitm.edu.in/` source URLs, and the ingest report is logged.

## M-002 [P0] [bug] Ephemeral token endpoint is v1alpha; docs say v1beta only
Status: code verified cycle 2 (`gemini.py:129-131` posts to /v1beta/auth_tokens with liveConnectConstraints; `test_live_token_v1beta_with_constraints` passes, key absent from output). Acceptance (real mint + bare Live session) pending API keys.
Found: cycle 1, during T0.1 (`backend/llm/gemini.py`, `mint_live_token`)
Evidence: code posts to `/v1alpha/auth_tokens`. https://ai.google.dev/gemini-api/docs/ephemeral-tokens: tokens work "only with the v1beta version of the API", endpoint `POST /v1beta/auth_tokens`. Details in monitor/RESEARCH.md.
Why it matters: if the token call fails, Live never starts. That breaks demo steps 1 to 5, which would all run on the fallback voice path.
Proposal: use `/v1beta/auth_tokens`. Also add `liveConnectConstraints: {model, config}` to the body, locking model, system instruction, tools, transcription and session resumption on the server, so the browser cannot reuse the token for anything else. `uses=1` is fine: docs confirm resumption reconnects work with the same token within `expireTime`. The browser must fetch a fresh token if a reconnect happens more than 30 minutes after minting.
Effort: S
Accept when: one real mint call returns 200 with a token `name`, and a bare Live session opens with it (T0.4).

## M-003 [P1] [research] Pick the embedding model knowingly: taskType vs prefixes
Status: code addressed in working tree (cycle 2: prefix templates for embedding-2, taskType for 001, test passes). Hindi cross-language check pending keys.
Found: cycle 1, during T0.1 (`GeminiClient.embed` sends `taskType`)
Evidence: https://ai.google.dev/gemini-api/docs/embeddings. `gemini-embedding-2` (recommended, GA) has no `taskType` and uses text prefixes instead: query `task: search result | query: {text}`, document `title: {title} | text: {text}`. `gemini-embedding-001` supports `taskType` and works until 2028-05-14. Default 3072 dims; 001 needs manual normalization below 3072.
Why it matters: with embedding-2, `taskType` is either rejected (ingest fails) or ignored (worse retrieval, weaker cross-language hits for T2.6).
Proposal: either set `GEMINI_EMBED_MODEL=gemini-embedding-001` and keep `taskType` (smallest change), or support embedding-2 by switching to prefixes when the model is not 001. Consider `outputDimensionality: 768` to keep `data/chroma/` small for committing (M-001); normalize if on 001. Recalibrate `RAG_MIN_SCORE` afterwards.
Effort: S
Accept when: ingest of `data/clean/` succeeds with the chosen model and one Hindi query retrieves an English chunk (ADDENDUM-01 7.2), result logged.

## M-005 [P1] [reliability] Groq TTS fallback rejects anything over 200 characters and has 100 requests a day
Status: verified cycle 4 (frontend/src/hooks/useVoice.ts uses window.speechSynthesis; server TTS off by default)
Found: cycle 1, research for T2.3 (`GroqClient.speak`, `speech_max_text_chars = 600`)
Evidence: https://console.groq.com/docs/text-to-speech (Wayback 2026-10-07): "The input text length is limited to 200 characters". Model `canopylabs/orpheus-v1-english` is preview, English only, free plan 10 RPM, 100 RPD, 3.6K tokens per day (rate-limits page). `playai-tts` was shut down 2025-12-31. Details in monitor/RESEARCH.md.
Why it matters: the fallback voice path (ADDENDUM-01 5.5, required for T2.3 and the "Live fails on stage" risk) would 400 on normal answers. It cannot speak Hindi (demo step 4) and runs out of daily quota during rehearsals.
Proposal: make browser `speechSynthesis` the default fallback TTS (no quota, Hindi voices on most phones, the addendum allows it: "Groq TTS model if available, else browser speechSynthesis"). Keep Groq TTS optional for English, splitting text into sentences of 200 characters or fewer. Also note the org admin must accept the Orpheus terms in the Groq Playground once.
Effort: S to M
Accept when: with `LIVE_ENABLED=false`, a 400-character English answer and a Hindi answer are both spoken end to end.

## M-004 [P1] [truth] Live tool calls are async by default on gemini-3.8-live; grounding tools must block
Status: verified cycle 4 at code level (registry declares BLOCKING on grounding tools; test_grounding_tools_block_on_live). Live behavior check pending T2.1
Found: cycle 1, research for T2.1
Evidence: gemini-3.8-live model page (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live): "Async execution (behavior: NON_BLOCKING) is now the default function calling mode". `behavior: BLOCKING` restores synchronous calls.
Why it matters: with NON_BLOCKING the host can start answering "where is lunch" before `search_campus` or `get_local_tips` returns. That is an ungrounded answer with no source chips, which breaks the truthfulness rule.
Proposal: declare `behavior: BLOCKING` on `search_campus`, `get_local_tips`, `get_schedule`, `look`, `hiring_match`, `get_visitor_profile`. `remember` and `shortlist_*` may stay NON_BLOCKING. Also do not send `enable_affective_dialog`, `proactive_audio: false` or `thinking_level`: 3.8 Live rejects them.
Effort: S
Accept when: in a Live session, "where can I get veg lunch" produces a tool call before any answer audio, and the caption cites the tool's sources.
