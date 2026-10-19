# Hello Campus

A local campus companion for Anjuman Institute of Technology and Management (AITM), Bhatkal. Chat with a friendly Guide or a factual Analyst, follow source links, and continue your visit on another device with a four-character code.

## Current capabilities

- Responsive welcome, chat and hiring interface.
- Local Ollama streaming with Guide (0.8) and Analyst (0.2).
- Persistent Chroma retrieval with citations and minimum-score refusal.
- Real offline snapshot of three official AITM campus pages and one achievement page.
- SQLite visitor profiles, extracted preferences, character selection and resume codes. Only the last ten messages are retained.
- Hiring role intake, evidence-filtered matches, shortlist, comparison, interview questions, Markdown export and README before/after generation.
- Hiring currently has no real candidates. The opt-in CSV is empty. Locality entries are marked placeholders and never indexed.

Speech and video are not enabled in this version. Voice implementation and model downloads are in progress locally. YOLO training, phone HTTPS checks and a full offline demo still need completion.

## Setup

Use Python 3.10 or 3.11, Node.js 20+, and a locally running Ollama. All commands below run from the repository root.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.txt
npm.cmd install --prefix frontend
Copy-Item .env.example .env
ollama pull gemma3:1b
ollama pull nomic-embed-text
.venv\Scripts\python -m backend.rag.ingest
.venv\Scripts\python tasks.py dev
```

Open http://localhost:5173. Vite proxies `/api` and `/ws` to FastAPI on port 8000. On Linux/macOS, use `.venv/bin/python` and `npm`.

The default model is Gemma 3 1B because the development laptop has 7.3 GB RAM. A cold 32-token benchmark took 9.12 seconds with 1B and 109.45 seconds with 4B on this laptop. Override `LLM_MODEL` and `LLM_FALLBACK_MODEL` in `.env` for a larger demo machine. See `BUILD.md` for the full intended scope and `PROGRESS.md` for evidence and incomplete acceptance checks.

## Data

`scraper/sources.yaml` contains verified official AITM links. Scraping checks robots.txt, uses a custom User-Agent, waits between requests and caches raw responses. Scraping is a refresh step, not required for offline runtime.

```powershell
.venv\Scripts\python tasks.py scrape
.venv\Scripts\python tasks.py validate-locality
.venv\Scripts\python tasks.py ingest
```

Add consenting students to `data/students_optin.csv` with columns `name,github_username,headline,consent`; only explicit affirmative consent is accepted. Scraping, ingestion, retrieval and student endpoints check consent. Removing consent hides stale indexed records from subsequent retrieval and API requests. Previously viewed information cannot be recalled from a visitor's browser.

Fill `data/locality.json` with verified values and set `placeholder` to false for real entries. Include `last_checked`. No fictional student or locality data is shipped. Test fixtures use example.org and temporary directories.

## Verification

```powershell
.venv\Scripts\python tasks.py test
.venv\Scripts\python tasks.py smoke
npm.cmd run build --prefix frontend
npm.cmd run lint --prefix frontend
```

LLM and RAG tests require local Ollama and its models. Two scraper integration tests access public websites; set `HC_OFFLINE=1` to skip those. Core smoke uses real local inference and checks health, both characters, AITM citations, refusal, memory extraction and resume. It does not certify speech, gestures, phone access or the full demo freeze criteria.

For phone access, use `scripts/tunnel.sh` with cloudflared or ngrok installed. The phone must open the HTTPS tunnel URL and explicitly grant microphone/camera permissions. This check has not yet been performed.

## Training topics

| Topic | Implementation and current proof |
|---|---|
| Web scraping | Official AITM snapshot, source links, `scraper/` |
| GitHub README improvement | Generator and before/after interface; needs real opted-in profiles |
| RAG | Four Chroma collections, citations, threshold refusal |
| Ollama | All generation and embeddings run locally |
| Temperature | Guide 0.8, Analyst 0.2, interview 0.9, extraction 0.0 |
| Memory | SQLite profiles, bounded history, extracted preferences, resume code |
| STT/TTS | In progress, not enabled in this version |
| YOLO detection/classification | Notebook exists; real training, ONNX weights and metrics pending |

## Privacy and licenses

No face recognition, cloud inference or login-walled scraping. Audio/camera features are not active. Visitor data stays in local SQLite; the resume code grants access to that visitor's profile and should be shared carefully. Raw conversations are limited to the last ten messages, with compact extracted facts retained for continuity.

AITM source content remains owned by its respective rights holders; snapshots retain source URLs and check dates. Model and dependency terms apply separately: consult [Gemma terms](https://ai.google.dev/gemma/terms), [Ollama](https://github.com/ollama/ollama), [nomic-embed-text](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5), and dependency distributions. No YOLO model or HaGRID images are shipped, so no training metrics or dataset license clearance is claimed yet.
