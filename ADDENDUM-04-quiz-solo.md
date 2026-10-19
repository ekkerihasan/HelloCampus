# ADDENDUM 04: Buzzer Quiz modes become Solo and Versus

Status: adopted by the user on 2026-10-19 (about 15:25). Saved as ADDENDUM-04 at the user's instruction.

**Read order:** after ADDENDUM-03. Where this conflicts with ADDENDUM-03, this file wins.

## 1. Changes to ADDENDUM-03
- **Co-op (Mind Meld, section 3.2) is removed.** Do not build it.
- **Solo mode is added and is the default and the demo mode.**
- **Versus (section 3.1) stays as the second mode**, built after Solo works.
- **Each answer option has its own hand-sign symbol**, shown next to the option text on screen. No retraining: the existing model classes are used.

| Option | Gesture class | On-screen symbol |
|---|---|---|
| A | `one` | one finger |
| B | `peace` | two fingers (V) |
| C | `three` | three fingers |
| D | `four` | four fingers |
| Start, next question (Solo); buzz in (Versus) | `palm` | open palm |

Use a clear icon or emoji per option, the same everywhere: question card, hold ring, help text and keyboard hints.

## 2. Solo mode
1. Player types a first name (prefilled from the visitor record) and shows a palm (or presses Space) to start.
2. Each question shows 4 options, each with its symbol, and a visible countdown of `QUIZ_SOLO_ANSWER_S` seconds (default 10).
3. Holding an option's sign for `GESTURE_HOLD_MS` locks the answer (fill ring around that option). One answer per question.
4. Correct: +100 points plus a time bonus of 10 points per remaining second; streak counter shown. Wrong or timeout: 0 points, streak resets.
5. Reveal for about 3 seconds: the correct option, the **source chip**, and one short host line (browser speechSynthesis). Palm (or Space) skips the reveal.
6. `QUIZ_QUESTIONS_PER_GAME` questions (default 5), then a final score and the day's leaderboard (top 10, `quiz_scores(name, mode, score, ts)`).

## 3. Versus mode (after Solo)
As ADDENDUM-03 3.1, with the per-option symbols above: palm buzzes in, then the option's sign answers. Left half of the frame is P1, right half P2. No identity, hands only.

## 4. Keyboard mirror
Solo: `1` to `4` answer A to D, `Space` start or next. Versus: `A` and `L` buzz for P1 and P2, `1` to `4` answer. Fully playable with no camera or no model.

## 5. Config (backend/config.py or .env)
`QUIZ_ENABLED`, `QUIZ_QUESTIONS_PER_GAME=5`, `QUIZ_SOLO_ANSWER_S=10`, `QUIZ_VERSUS_ANSWER_S`, `QUIZ_TIME_BONUS_PER_S=10`, `QUIZ_POINTS_CORRECT=100`, plus the gesture values from ADDENDUM-03 section 6. Remove `QUIZ_COOP_ANSWER_S` and `QUIZ_STREAK_BONUS` if unused.

## 6. Task order (replaces ADDENDUM-03 section 8 order; acceptance criteria otherwise unchanged)
1. T4.1 question bank with the evidence post-check (unchanged).
2. T4.2 vision runtime and WebSocket with the 6-class ONNX at `backend/vision/weights/gesture.onnx` (validated by the monitor: names match, output [1, 10, 3549], CPU p50 18.6 ms).
3. T4.3 **Solo** Play tab, keyboard only, with timer and symbols. Accept: a full 5-question game by keyboard; leaderboard persists across a restart.
4. T4.4 gestures in Solo. Accept: each option's sign locks the right option 4 of 5 tries at the demo laptop; palm starts and skips.
5. T4.5 isolation (unchanged): model file removed means the Play tab says so and keyboard play still works; chat, Live and fallback voice smoke still pass.
6. T4.6 Versus mode, only if time allows.

## 7. Demo slot (replaces ADDENDUM-03 section 10)
About 20 seconds: one judge plays 2 Solo questions with hand signs; the second answer shows its source chip; the leaderboard shows their name.
