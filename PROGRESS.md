# Hello Campus: Progress Log

## Needs the team
- Real URLs for `scraper/sources.yaml` (college, clubs, hackathons). Nothing is scraped until these exist.
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
