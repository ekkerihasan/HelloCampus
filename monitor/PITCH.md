# Monitor: Pitch

## 1. Hook and description

**Hook:** The friendly local you wish you had on day one at a new campus.

**57-word description (current, matches ADDENDUM-01):**
You arrive at a new campus, and nobody's around to tell you what makes this place special, which students are doing great work, or where to grab lunch. Hello Campus is that friendly local you wish you had. Just chat, talk, or wave at your camera. And if you're hiring, it'll point you to the right people.

Note: gestures were removed in ADDENDUM-01. If the UI has no wave action, use "or show it what you're looking at" (that makes it 59 words; drop "Just" and "at a new campus" becomes "on a new campus" if 57 matters).

## 2. The 90-second story (draft)
- **Problem (15 s), told from the judges' morning:** "This morning you walked into AITM as outsiders. Where is the hall? Who here is actually building things? Where do you eat? You asked a volunteer, or you guessed."
- **Demo (60 s):** follow ADDENDUM-01 section 11, narration in section 3 below.
- **What's new (15 s):** a voice host you can interrupt, that reads what you point your phone at, only says what it can cite, and remembers you across devices.

## 3. Demo narration
Cycle 3: lunch reinstated (locality draft being verified by the team). Keep this refusal beat as a backup for anything not in the data, for example a place the team did not list. Replacement beat, about 10 s: ask "Where can I get lunch around here?" and let the host say it does not have that yet and suggest who to ask. Presenter line: "It would rather say 'I don't know' than make up a restaurant. Every answer you hear is cited, or it's refused."

To be written against the real build once T2.1 runs. Each step will get: what the presenter says, what the audience should notice, and the fallback if it fails (fallback voice badge, then chat mode, then recorded video).

## 4. What's innovative
Pending real build. Candidates: interruptible live voice grounded in campus data with source chips; Look on a real poster resolved against the schedule; hiring claims that can only cite URLs present in stored data.

## 5. Judge Q&A prep
Pending. Will cover privacy (opt-in only, no face recognition, no transcripts kept beyond 10 turns), hallucinations (refusal threshold, evidence URL post-check), cost and free-tier quotas, scaling to other colleges, why not a general assistant app, next steps.

## 6. Numbers to quote
- Look: photo of a poster to answer with the matching campus page in 3.0 s (cycle 7, one test poster). Fallback voice: speech to text 1.9 s, then first word of the answer 1.6 s.
- Gesture model (Buzzer Quiz): YOLO26n fine-tuned on a public HaGRID sample, held-out test split of 400 images from 210 people never seen in training: **mAP50 0.988** (1-epoch baseline 0.784), every class 0.973 or higher. Runs on this laptop's CPU in **18.6 ms per frame** (p50). Source: monitor/TRAINING-RESULTS.md. Say "on a held-out test set of new people", not "99 percent accurate at the venue"; venue accuracy is not measured yet.
Only real, measured numbers. Re-measure before the pitch; these are from cycle 6 (2026-10-19, about 14:30).
- Knowledge base: 38 records from official aitm.edu.in pages (35 campus, 3 achievements), 56 chunks, every chip links to the page it came from. Source: ingest report.
- Chat first token: about 1.7 to 2.4 s on single questions (7 runs, cycle 6); p50 2.5 s under a 17-turn burst (cycle 5). Source: monitor probes.
- Robustness: 17-turn burst including 3 concurrent and Hindi, 0 errors, 0 empty answers (cycle 5 round 3).
- Grounding spot checks: every recruiter name and the placement figures (83.97%, 393 of 468, highest 46.50 LPA) matched the cited page text exactly.
- RAG eval (reproduced by the monitor, cycle 6): hit@4 1.0 on 22 questions including 2 Hindi and 1 Kannada, refusals 3/3. English retrieval about 0.6 s, Hindi and Kannada 1.2 to 1.8 s. Caveat: refusal cases are off-topic only until M-014 adds in-domain unknowns; say "22 of 22 on our eval set", not "100 percent accurate".
**Placement numbers conflict on AITM's own site** (found by the builder): /placements/ says highest 14.5 LPA and 150+ recruiters; /placements/statistics/ says 46.50 LPA and 98 companies. The host cites whichever page it retrieves. Do NOT use placement figures as a pitch line until the team decides which page is right. If asked on stage: "It cites the exact page it read; where the college's pages disagree, the chip shows you which one." 
