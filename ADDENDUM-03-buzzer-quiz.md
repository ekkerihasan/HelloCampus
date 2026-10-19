# PROPOSAL (draft ADDENDUM-03): Campus Buzzer Quiz, a realtime YOLO game

Status: **draft from the monitor for the humans.** It changes a non-goal in ADDENDUM-01 section 12 ("YOLO or any custom vision model"), so the builder must not act on it until a human saves it as `ADDENDUM-03-buzzer-quiz.md`. The monitor never edits addenda.

**Read order:** BUILD.md -> CLAUDE.md -> ADDENDUM-01 -> ADDENDUM-02 -> this file. Where this file conflicts with earlier files, this file wins.

---

## 1. What changes and why
- ADDENDUM-01 section 12 non-goal "YOLO or any custom vision model" is lifted for **exactly one** fine-tuned YOLO hand-gesture model, used **only** in a new Play tab. Every other non-goal stays.
- Reason: a memorable realtime moment for judges. Two people at the laptop webcam compete or cooperate on campus trivia using hand gestures. It shows true multi-object detection (two hands, two players at once), and every question is grounded in scraped campus data with a source.
- Priority: core first. The builder starts this only after T2.1 (Live voice) passes. The Play tab is isolated; nothing else may depend on it.

## 2. Model
- One YOLO detection model, classes (6): `palm` (buzz), `one`, `peace` (means 2), `three`, `four`, `no_gesture`.
- Data: public HaGRID only, about 800 images per class, 80/10/10 split, subject-separated by `user_id`. No team-captured frames.
  - **Use `cj-mills/hagrid-sample-120k-384p` on Hugging Face** (https://huggingface.co/datasets/cj-mills/hagrid-sample-120k-384p, checked 2026-10-19): 3.49 GB, 127,331 images at 384p, CC-BY-SA-4.0, built for free Colab. It contains all six classes (`palm`, `one`, `peace`, `three`, `four`, `no_gesture`). Annotations: `bboxes` normalized `[top-left x, top-left y, w, h]`, plus `labels` per hand and `user_id`. File layout is not documented, so inspect the Files tab first.
  - Do **not** use full HaGRIDv2 (https://github.com/hukenovs/hagrid): about 40 GB per class zip, 119 GB even at 512px. The old notebook expected HaGRIDv2's standalone `no_gesture` folder; in this sample `no_gesture` is a per-hand label instead, so `collect_hagrid` needs adapting.
  - License: CC-BY-SA-4.0 (the original HaGRID uses "a variant of" it). Record the attribution in README.
- Model: `yolo26n.pt` exists in Ultralytics (https://docs.ultralytics.com/models/yolo26/). **YOLO26 exports an end-to-end NMS-free head by default**, so the output shape differs from the `[1, 4 + classes, N]` format that the old `decode_output` parses. Export with `model.export(format="onnx", end2end=False)` to keep the old decoder, or adapt the decoder. Check the outcome with the metadata guard and a sample frame.
- Train on Colab GPU (the team has the Colab extension set up locally) at imgsz 416, about 40 epochs, early stopping. Download `best.onnx` and place it at `backend/vision/weights/gesture.onnx` (gitignored; keep a copy on a USB stick). Record mAP50 and per-class precision and recall in README.
- Runs on the demo laptop CPU in the backend, frames over `/ws/gesture` on localhost. No tunnel needed for the game.

## 3. Game: two modes, same gestures
Player sides: a detection box with its centre left of mid-frame belongs to P1, right of mid-frame to P2. The preview is mirrored. No faces, no identity, only hand boxes.

### 3.1 Versus: Buzzer Quiz
1. The question and 4 options are shown and read aloud (browser `speechSynthesis`).
2. The first `palm` held for `GESTURE_HOLD_MS` locks that player in (fill ring on their side).
3. They have `QUIZ_ANSWER_S` seconds to hold `one` / `peace` / `three` / `four`.
4. Correct scores +1. A wrong answer or timeout passes the question to the other player once.
5. Reveal: correct option, **source chip** (`source_url`), one short host reaction line. 5 questions per game.

### 3.2 Co-op: Mind Meld (team vs the clock)
1. Same questions, no buzzing. Both players must hold the **same** finger count at the same time for `GESTURE_HOLD_MS` to lock the team answer.
2. If they disagree, the host nudges ("You two need to talk!"), and the timer keeps running.
3. Team score plus a streak multiplier for consecutive correct answers, against a per-question timer `QUIZ_COOP_ANSWER_S`. The goal is to beat the day's best team score.
4. Good for two judges, or a judge and a team member during the pitch.

## 4. Questions: grounded, pre-generated, offline
- `make quiz` builds `data/clean/quiz.jsonl` from `data/clean/*.jsonl` with the Groq fast model (JSON mode, `temp_json`).
- Each item: `{id, question, options[4], answer_index, source_url, evidence}`.
- **Post-check (mandatory, like the hiring URL check):** drop the item unless all three hold: `evidence` is a verbatim substring of the cited record text; the correct option text appears in `evidence`; `source_url` exists in stored data (reuse the `allowed_urls` pattern in `backend/hiring/service.py`).
- A human skims and commits the bank. No LLM call happens during play, so the game works offline and costs no quota.
- If fewer than 5 items survive, the Play tab says "Quiz needs more campus data" rather than inventing questions.

## 5. UI and controls
- New **Play** tab: mode toggle (Versus / Co-op), name entry prefilled from the visitor record, camera preview with boxes and labels, per-side hold rings, scoreboard, source chip on reveal.
- Leaderboard: SQLite table `quiz_scores(name, mode, score, ts)`, top 10 for today. Names are typed by players, never derived from the camera.
- Keyboard mirror: `A` / `L` buzz for P1 / P2, `1` to `4` answer for the locked player. In co-op, P1 uses `1` to `4` and P2 uses `7` to `0`. The game is fully playable with no camera or no model.
- Kill switch `QUIZ_ENABLED`. If it is not stable by H6, set it false and the Play tab disappears.

## 6. Config (all in `backend/config.py` or `.env`)
`GESTURE_ONNX_PATH`, `GESTURE_CLASSES`, `GESTURE_MIN_CONF`, `GESTURE_HOLD_MS`, `GESTURE_COOLDOWN_MS`, `GESTURE_FPS`, `GESTURE_IMGSZ`, `QUIZ_ENABLED`, `QUIZ_QUESTIONS_PER_GAME`, `QUIZ_ANSWER_S`, `QUIZ_COOP_ANSWER_S`, `QUIZ_STREAK_BONUS`.

## 7. Reuse (deleted in the working tree, still in commit `4709f1c`)
- `training/build_notebook.py`, `training/gesture_yolo.ipynb`: change the `CLASSES` constant and drop `own_frames`.
- `backend/vision/gesture.py`: `GestureDetector`, `decode_output` with NMS (already returns multiple detections), and the ONNX class-metadata guard.
- `backend/routes/gesture.py`: bounded JPEG WebSocket with one in-flight inference.
- `frontend/src/gesture/hold.ts` `advanceHold`: one `HoldState` per side, labels widened to the new classes.
- `frontend/src/components/VideoMode.tsx`: camera capture and overlay as the base of `PlayMode.tsx`.
- `backend/tests/test_gesture.py`, `backend/tests/test_training.py`, `frontend/tests/gesture-hold.test.mjs`: adapt rather than rewrite.

## 8. Tasks
- **T4.0 (human, start now in parallel):** Colab run per section 2. **Accept:** ONNX file plus a mAP table.
- **T4.1** `make quiz` plus post-check. **Accept:** pytest drops an item whose evidence is not in the record, and one with an unknown URL; at least 5 items survive on real data.
- **T4.2** Restore the vision runtime and WebSocket with 6 classes. **Accept:** ONNX loads with the metadata guard; per-frame CPU latency logged, under 120 ms at 416.
- **T4.3** Play tab, both modes, keyboard only. **Accept:** a full versus game and a full co-op game playable by keyboard; leaderboard persists across a restart.
- **T4.4** Wire detections. **Accept:** with two people at the webcam, a buzz is attributed to the correct side 4 of 5 tries; each finger count is recognised 4 of 5 tries; a co-op lock happens only when both sides agree.
- **T4.5** Isolation. **Accept:** with the ONNX file removed, the Play tab says so and keyboard play works; chat, Live and fallback voice smoke still pass.

## 9. Non-goals (unchanged or added)
No face detection or recognition, no person identification, no second YOLO model, no gestures outside the Play tab, no LLM calls during play, no continuous video to Gemini.

## 10. Demo slot
Add to the end of the ADDENDUM-01 section 11 demo, about 20 seconds: "Two of you, step up." One co-op question, so both judges play together, then the source chip. Versus is shown only if time allows.
