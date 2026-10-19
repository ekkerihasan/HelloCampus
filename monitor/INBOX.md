# Monitor Inbox (for the builder)

Reply by item ID in PROGRESS.md (ADDENDUM-02 section 3). Max 5 open items.

## M-001 [P1] [reliability] Offline snapshot not committable; usage log will be committed
Status: fixed in working tree (cycle 2: .gitignore drops data/chroma/, adds logs/); verify after commit
Found: cycle 1, during T0.1
Evidence: `.gitignore` contains `data/chroma/` and `data/*.sqlite3`. ADDENDUM-01 7.5: "`data/clean/` and `data/chroma/` are committed as the offline snapshot". `logs/` is not in `.gitignore`, and `settings.usage_log_path` is `logs/usage.jsonl`.
Why it matters: a fresh clone (or the second team laptop) cannot answer anything until someone re-ingests with a working key; usage logs end up in commits.
Proposal: remove `data/chroma/` from `.gitignore` (keep `data/memory.sqlite3` ignored; decide whether `data/embed_cache.sqlite3` is committed so re-ingest on another laptop costs 0 calls). Add `logs/`.
Effort: S
Accept when: `git check-ignore data/chroma/x logs/usage.jsonl` prints only `logs/usage.jsonl`.

## M-007 [P0] [bug] Colab notebook fails at cell 3: HF_REPO and HF_FILE defined later in cell 6
Status: open
Found: cycle 3, review of `training/gesture_yolo.ipynb` (branch pivot/cloud-core)
Evidence: cell 3 calls `hf_hub_download(repo_id=HF_REPO, filename=HF_FILE, ...)`, but `HF_REPO` and `HF_FILE` are first assigned in cell 6. Running top to bottom on a fresh runtime gives `NameError: name 'HF_REPO' is not defined`. The file name itself is correct: the HF API lists `hagrid-sample-120k-384p.zip` (and license cc-by-sa-4.0).
Why it matters: T4.0 training is the long pole for ADDENDUM-03. The user is about to run it through the VS Code Colab extension, and a failure at cell 3 wastes the GPU session.
Proposal: move `HF_REPO` and `HF_FILE` (and the constants in cell 4) into cell 1 or a new constants cell before cell 3, regenerate via `build_notebook.py`, and add a test that executes the cells' top-level names in order (or at least checks every name used in cell N is defined in cells 0 to N). Also, `google.colab.files.download` relies on the Colab browser front end and may not work through the VS Code Colab extension. Add a fallback: copy `best.onnx` and `prep_report.json` to Google Drive (`drive.mount`) or print the path so the user can download from the VS Code file explorer.
Effort: S
Accept when: a fresh-kernel order check passes in a test, and the notebook has a download path that works without the Colab web UI.

## M-006 [P1] [truth] Only 3 of 81 official AITM pages are scraped
Status: open
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
Status: open
Found: cycle 1, research for T2.3 (`GroqClient.speak`, `speech_max_text_chars = 600`)
Evidence: https://console.groq.com/docs/text-to-speech (Wayback 2026-10-07): "The input text length is limited to 200 characters". Model `canopylabs/orpheus-v1-english` is preview, English only, free plan 10 RPM, 100 RPD, 3.6K tokens per day (rate-limits page). `playai-tts` was shut down 2025-12-31. Details in monitor/RESEARCH.md.
Why it matters: the fallback voice path (ADDENDUM-01 5.5, required for T2.3 and the "Live fails on stage" risk) would 400 on normal answers. It cannot speak Hindi (demo step 4) and runs out of daily quota during rehearsals.
Proposal: make browser `speechSynthesis` the default fallback TTS (no quota, Hindi voices on most phones, the addendum allows it: "Groq TTS model if available, else browser speechSynthesis"). Keep Groq TTS optional for English, splitting text into sentences of 200 characters or fewer. Also note the org admin must accept the Orpheus terms in the Groq Playground once.
Effort: S to M
Accept when: with `LIVE_ENABLED=false`, a 400-character English answer and a Hindi answer are both spoken end to end.

## M-004 [P1] [truth] Live tool calls are async by default on gemini-3.8-live; grounding tools must block
Status: open
Found: cycle 1, research for T2.1
Evidence: gemini-3.8-live model page (https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live): "Async execution (behavior: NON_BLOCKING) is now the default function calling mode". `behavior: BLOCKING` restores synchronous calls.
Why it matters: with NON_BLOCKING the host can start answering "where is lunch" before `search_campus` or `get_local_tips` returns. That is an ungrounded answer with no source chips, which breaks the truthfulness rule.
Proposal: declare `behavior: BLOCKING` on `search_campus`, `get_local_tips`, `get_schedule`, `look`, `hiring_match`, `get_visitor_profile`. `remember` and `shortlist_*` may stay NON_BLOCKING. Also do not send `enable_affective_dialog`, `proactive_audio: false` or `thinking_level`: 3.8 Live rejects them.
Effort: S
Accept when: in a Live session, "where can I get veg lunch" produces a tool call before any answer audio, and the caption cites the tool's sources.
