# Hello Campus: Build Plan

> You arrive at a new campus, and nobody's around to tell you what makes this place special, which students are doing great work, or where to grab lunch. Hello Campus is that friendly local you wish you had. Just chat, talk, or wave at your camera. And if you're hiring, it'll point you to the right people.

This file is the source of truth for scope, tasks, and acceptance criteria. `CLAUDE.md` defines how to work. `PROGRESS.md` is the running log.

---

## 1. Event constraints (non-negotiable)

| Constraint | Detail |
|---|---|
| Duration | 1 day (about 8 working hours). Demo freeze 1 hour before judging. |
| Team | 3 people. Tasks are tagged A (vision), B (voice, LLM, memory), C (data, RAG, UI). |
| Hardware | Laptops with 16 GB RAM, CPU only. Colab or Kaggle GPU allowed for training only. |
| Cloud | Assume NO cloud LLM or speech APIs. Everything must run locally on one laptop. |
| Client | Phone or laptop browser connecting to the laptop backend. No kiosk. |
| HTTPS | Phone camera and mic need HTTPS: expose the backend via a cloudflared or ngrok tunnel. |
| Network | Venue Wi-Fi may fail. The demo must work fully offline from a committed data snapshot. |
| Memory budget | LLM about 3 GB, embeddings under 1 GB, STT under 1 GB, TTS under 0.5 GB, YOLO under 0.1 GB. Leave at least 4 GB free for the OS and browser. |

## 2. Training topics: every one must be visibly used

| Topic | Where | Visible proof in demo |
|---|---|---|
| Web scraping | `scraper/` builds the knowledge base from college, club, hackathon pages and public GitHub | Source links on answers; `make scrape` output |
| GitHub README optimisation | Student side of hiring: generate an improved profile README | Before and after README view |
| RAG architecture | `backend/rag/` with four collections and citations | Every factual answer shows sources |
| Ollama local inference | All generation via local Ollama | Works with Wi-Fi off |
| Temperature | Guide (0.8) vs Analyst (0.2); interview kit (0.9) | Same question, two characters, toggle on screen |
| Memory | SQLite visitor memory shared across modes and devices | Resume on a second device with a short code |
| STT | Voice and video modes | Ask out loud |
| TTS | Voice and video modes | Host speaks back |
| Object detection + classification (fine-tuned YOLO) | Video mode gestures: ONE YOLO26n detection model whose classes are the gestures | Live box with gesture label triggering actions |

## 3. Architecture

```
Browser (phone or laptop)            Laptop backend (FastAPI, Python 3.11)
+---------------------------+        +------------------------------------------+
| React + TS (Vite)         |  HTTPS | /api/chat        SSE stream               |
|  Chat | Voice | Video     | <----> | /api/stt         audio -> text            |
|  Character toggle         | tunnel | /api/tts         text -> wav              |
|  Gesture overlay + ring   |        | /ws/gesture      JPEG frames -> detections|
|  Shortlist + cards        |        | /api/visitor     create, resume by code   |
+---------------------------+        | /api/hiring/*    role, shortlist, kit     |
                                     | /api/students/*  profile, README          |
                                     +------------------------------------------+
                                       | Ollama | Chroma | SQLite | YOLO26n ONNX |
                                       | faster-whisper | Kokoro TTS            |
```

### Stack decisions (do not change without logging why in PROGRESS.md)

- **Backend:** FastAPI, uvicorn, Python 3.11, pydantic v2.
- **Frontend:** Vite + React + TypeScript, plain CSS or Tailwind. Single page, three mode tabs.
- **LLM:** Ollama `gemma3:4b` (default) or `qwen3:4b` (fallback). Configurable in `.env`.
- **Embeddings:** Ollama `nomic-embed-text`.
- **Vector store:** Chroma (persistent, local folder).
- **Memory store:** SQLite via the standard library or SQLModel.
- **STT:** `faster-whisper` model `small` (int8, CPU). Optional Kannada via IndicConformer behind a feature flag.
- **TTS:** Kokoro 82M (English). Optional Kannada Kokoro voice behind a feature flag.
- **Vision:** Ultralytics YOLO26n, trained on Colab, exported to ONNX, run on CPU.
- **Scraping:** `httpx` + `selectolax` or BeautifulSoup, `trafilatura` for article text, GitHub REST API with a token from `.env`.

### Repo layout

```
hello-campus/
  BUILD.md  CLAUDE.md  PROGRESS.md  README.md  Makefile  .env.example
  backend/
    app.py                 FastAPI entry, routers, startup model loading
    config.py              all constants: temperatures, thresholds, model names
    llm/                   ollama client, characters, prompts, router
    rag/                   ingest, embed, retrieve, cite
    memory/                sqlite schema, fact extraction, resume codes
    hiring/                role intake, matching, interview kit, readme generator
    speech/                stt.py, tts.py
    vision/                gesture.py (onnx inference), weights/
    tests/                 pytest: unit + smoke
  scraper/
    sources.yaml           list of URLs to scrape (team fills in)
    scrape_web.py  scrape_github.py  normalize.py
  data/
    raw/                   cached HTML/JSON (gitignored if large)
    clean/                 normalized JSONL per collection (COMMITTED, offline snapshot)
    locality.json          hand-curated food, travel, places, practical
    students_optin.csv     opt-in form export
  training/
    gesture_yolo.ipynb     Colab notebook: dataset prep, train, eval, export
    own_frames/            team-captured frames per class
  frontend/
    src/  (modes/, components/, api/, hooks/)
  scripts/
    smoke.sh               end-to-end check used by the review loop
    tunnel.sh              starts cloudflared/ngrok
```

## 4. Functional spec

### 4.1 Visitor welcome and memory
- First open: ask name and "What brings you here today?" with quick chips: Session or talk, Judging or mentoring, Hiring, Event, Parent or alumni, Just visiting.
- Create visitor with a 4-character resume code (e.g. `K7QM`), shown on screen.
- Store: name, purpose, preferences, role requirements, shortlist, short rolling summary.
- After each turn, a low-temperature extraction call returns JSON facts to upsert. Never store raw transcripts beyond the last 10 turns.
- Facts are injected into the system prompt as a compact "What I know about this visitor" block.
- Resume on another device by entering the code.

### 4.2 Characters and temperature
| Character | Temp | Used for |
|---|---|---|
| Guide | 0.8 | Welcome briefing, food and travel tips, campus stories, small talk |
| Analyst | 0.2 | Facts, timings, contacts, hiring matches, comparisons |
| Interview kit generator | 0.9 | Fresh, varied questions per candidate |
| Fact extractor and router | 0.0 | JSON outputs |

- UI toggle and peace gesture switch Guide and Analyst. Hiring screens default to Analyst.
- Both characters use identical retrieved context. Only tone and temperature differ.

### 4.3 RAG
- Collections: `campus`, `achievements`, `students`, `locality`.
- Each chunk metadata: `collection`, `title`, `source_url` (or `curated`), `last_checked`, `entity_id` (for students).
- Chunking: about 400 to 600 tokens, 50 token overlap. Locality entries are one chunk each.
- Router (rules first, LLM at temp 0 as fallback) picks collections per question.
- Retrieve top 5. If best similarity is below `RAG_MIN_SCORE` (config), answer "I don't have that yet" and suggest who to ask. Never guess.
- Every factual answer ends with source chips the UI renders as links.

### 4.4 Locality data (`data/locality.json`)
Hand-curated, 20 to 30 entries, each with a `last_checked` date:
```json
{"id": "food-001", "type": "food", "name": "", "what_to_order": "", "price_range": "",
 "distance_from_campus": "", "veg_options": true, "notes": "", "last_checked": "2026-10-18"}
```
Types: `food`, `travel` (bus stand, railway station, airport, fares, durations), `place`, `practical` (ATM, pharmacy, stays). The team fills real values. Claude creates the schema, a validator, and clearly marked placeholder entries only.

### 4.5 Hiring feature
1. **Role intake:** free text or pasted JD -> structured JSON `{title, must_have[], nice_to_have[], level, mode}` (temp 0). Saved to visitor memory.
2. **Match:** retrieve from `students`, Analyst ranks top 3 to 5. Every claim must cite a repo URL, project link, or achievement that exists in stored metadata. A post-check drops any URL not found in the data.
3. **Compare:** side-by-side table for two students.
4. **Shortlist:** add, remove, list. Persisted in memory.
5. **Interview kit:** 5 questions per candidate derived from their actual repos (temp 0.9).
6. **Export:** one-page markdown brief per shortlisted candidate.
7. **Student README:** from scraped GitHub data, generate an improved profile README. Show before and after.

Only students in `students_optin.csv` are ever indexed or shown.

### 4.6 Speech
- Voice mode: push-to-talk button (and palm gesture in video mode). Browser records with MediaRecorder, sends to `/api/stt`.
- TTS streams sentence by sentence so speech starts before the full answer is generated.
- Any new user speech or palm gesture stops current playback immediately (barge-in).

### 4.7 Video mode and gestures
- Browser captures the camera, downsizes to 320 px wide JPEG, sends about 10 fps over `/ws/gesture`. Drop to 3 fps while the LLM is generating.
- Backend returns `{label, confidence, box}`; frontend draws the box and label.
- Classes: `palm`, `like` (thumbs up), `dislike` (thumbs down), `ok`, `peace`, `no_gesture`.
- Actions: palm = talk or interrupt; like = shortlist current card; dislike = next card; ok = open evidence; peace = switch character.
- Trigger only after the same label holds for 500 ms above `GESTURE_MIN_CONF`, then 1.5 s cooldown. Show a fill-up ring while holding.
- Keyboard mirror for every gesture: `Space` palm, `Y` like, `N` dislike, `E` ok, `C` peace.

### 4.8 YOLO training (Colab, `training/gesture_yolo.ipynb`)
- Source: HaGRID subset for the 5 gesture classes plus `no_gesture`. Check and record the dataset license in README.
- Convert to YOLO format, sample about 800 images per class, 80/10/10 split.
- Add 50 to 100 team-captured frames per class from the venue lighting (`training/own_frames/`).
- Train YOLO26n, imgsz 416 to 480, about 40 to 60 epochs, early stopping.
- Record baseline (pretrained, no fine-tune) vs fine-tuned mAP50 and per-class precision and recall in README.
- Export ONNX to `backend/vision/weights/gesture.onnx`. Measure CPU latency per frame on the demo laptop.

### 4.9 Scraping
- `scraper/sources.yaml` lists URLs per collection. Team provides real URLs. Never invent URLs.
- Respect robots.txt, 1 request per second, custom User-Agent, cache raw responses.
- GitHub: only usernames from the opt-in CSV. Pull profile, pinned or top repos, languages, README, recent activity summary.
- Output normalized JSONL to `data/clean/<collection>.jsonl`. Ingest is idempotent.
- No LinkedIn or Instagram scraping. No login-walled pages.

## 5. Task list with acceptance criteria

Tick tasks in PROGRESS.md, not here. A task is done only when its acceptance check has actually been run and passed.

### Phase 0: Setup (H0 to H1)
- [ ] **T0.1 (all)** Repo skeleton, Makefile (`dev`, `scrape`, `ingest`, `test`, `smoke`, `tunnel`), `.env.example`, `config.py`. **Accept:** `make dev` starts backend and frontend; `/api/health` returns model status JSON.
- [ ] **T0.2 (B)** Ollama models pulled; `llm/client.py` with streaming and per-call temperature. **Accept:** unit test streams tokens at temp 0.2 and 0.8.
- [ ] **T0.3 (A)** Colab notebook runs dataset prep. **Accept:** class counts printed per split.
- [ ] **T0.4 (C)** Tunnel works; phone opens the app and grants mic and camera. **Accept:** screenshot or log line confirming HTTPS access from phone.

### Phase 1: Core slices (H1 to H4)
- [ ] **T1.1 (C)** Scrapers + normalizer + committed `data/clean/` snapshot. **Accept:** each collection JSONL has at least 1 real record with `source_url`.
- [ ] **T1.2 (C)** Locality schema, validator, placeholders. **Accept:** `make validate-locality` passes; placeholders flagged `"placeholder": true`.
- [ ] **T1.3 (C)** RAG ingest and retrieve with citations and min-score refusal. **Accept:** test question returns sources; nonsense question returns refusal.
- [ ] **T1.4 (B)** Chat endpoint with Guide and Analyst, SSE streaming, sources in final event. **Accept:** curl shows streamed tokens then a sources event.
- [ ] **T1.5 (B)** Visitor memory: create, extract facts, resume by code. **Accept:** test creates visitor, tells purpose, new session with code recalls it.
- [ ] **T1.6 (A)** YOLO26n trained and exported to ONNX; metrics recorded. **Accept:** mAP table in README; ONNX loads in `vision/gesture.py`.
- [ ] **T1.7 (B)** STT and sentence-streamed TTS endpoints. **Accept:** round trip test wav -> text -> wav under 6 s on the demo laptop.

### Phase 2: Modes and hiring (H4 to H6)
- [ ] **T2.1 (C)** Chat mode UI: welcome chips, character toggle, source chips, resume code display.
- [ ] **T2.2 (B)** Voice mode UI: push-to-talk, streamed playback, barge-in.
- [ ] **T2.3 (A)** Video mode: frames over WS, overlay, hold ring, cooldown, keyboard mirror, actions wired. **Accept:** each gesture triggers its action 4 of 5 tries at the venue.
- [ ] **T2.4 (B+C)** Hiring: role intake, match with evidence post-check, shortlist, compare, interview kit, export. **Accept:** a made-up URL injected into model output is removed by the post-check (unit test).
- [ ] **T2.5 (C)** Student README generator with before and after view.

### Phase 3: Polish and freeze (H6 to H8)
- [ ] **T3.1 (all)** `scripts/smoke.sh` covers health, chat both characters, RAG refusal, memory resume, STT/TTS round trip, gesture inference on sample frames, hiring match. **Accept:** passes twice in a row.
- [ ] **T3.2** Offline test: Wi-Fi off, full demo script works.
- [ ] **T3.3** Record fallback demo video.
- [ ] **T3.4** README: what it is, how every training topic is used (table from section 2), YOLO metrics, setup steps, licenses, privacy statement.
- [ ] **T3.5** Code freeze. Only bug fixes after this point.

## 6. Demo script (90 seconds)
1. Open on phone, enter name, pick "Session or talk". Guide gives a short campus briefing.
2. "Where can I get good lunch nearby?" Local tip with distance and price.
3. Toggle to Analyst, ask a timing question. Show the tone change and sources.
4. "I'm also hiring a frontend intern." Shortlist of 3 with evidence. Open one student's README before and after.
5. Switch to video mode. Thumbs up shortlists, OK opens evidence, peace switches character, palm interrupts speech.
6. Open the laptop browser, enter the resume code. Shortlist and lunch plan are already there.

## 7. Non-goals (do not build)
Kiosk mode, talking avatar or lip sync, face recognition or identifying people, LinkedIn or social scraping, user auth, cloud deployment, mobile native app, multi-college admin panel, a second YOLO model.

## 8. Risks and fallbacks
| Risk | Fallback |
|---|---|
| CPU overload with all models | Lower gesture fps during generation; switch LLM to a smaller tag; disable Kannada flags |
| Phone cannot reach backend | Run the demo on the laptop browser |
| Gesture misfires under venue light | More own frames, raise confidence threshold, keyboard mirror |
| Thin scraped data | Opt-in form and curated locality carry the demo |
| Tunnel blocked | Laptop hotspot to the phone over local HTTPS with a self-signed cert |
| Model invents facts | Min-score refusal and evidence URL post-check are mandatory, never disabled |
