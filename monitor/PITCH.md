# Hello Campus: Pitch

Owner: monitor. Written against the build as it runs on 2026-10-19 at about 15:30. Every number here was measured today; nothing is estimated. Re-check the marked items after the Buzzer Quiz and hiring land.

---

## 1. Hook and description

**Hook (say it first, 5 seconds):** "This morning you walked into AITM as outsiders. Hello Campus is the friendly local you wish had met you at the gate."

**57-word description (README, slides, submission form):**
You arrive at a new campus, and nobody's around to tell you what makes this place special, which students are doing great work, or where to grab lunch. Hello Campus is that friendly local you wish you had. Just chat, talk, or wave at your camera. And if you're hiring, it'll point you to the right people.

("wave at your camera" is true again: the **Get to Know AITM** quiz is played with hand signs.)

---

## 2. The 90-second story

| Time | Beat | What the presenter says (short) |
|---|---|---|
| 0:00 to 0:12 | **Problem, from the judges' own morning** | "You arrived here today as outsiders. Where is judging? Which departments are here? Where do you eat? You asked a volunteer, or you guessed. Let's ask Hello Campus instead." |
| 0:12 to 1:15 | **Live demo, 6 beats** | See section 3. |
| 1:15 to 1:30 | **What's new, then close** | "A host you can talk over, that only says what it can cite, that reads what you show it, and remembers you on any device. Built in one day on AITM's own pages." |

Rule for the presenter: **let the product talk**. Ask, then point at the source chip. Do not read answers aloud over the host's voice.

---

## 3. Demo narration (current build)

Setup before going on stage: laptop on `http://localhost:5173`, a visit already started with the judge-facing name (for example "AITM Judges"), Talk tab open, mic allowed, a printed or on-screen poster ready (STEM 2024 test poster works), Play tab ready if the quiz is merged. Second device (phone or second browser) with the page open for the resume beat.

### Beat 1: the host knows why you are here (10 s)
- **Do:** Talk tab, Start talking. The host greets by name. Ask: **"When is the judging today?"**
- **Expected:** "Judging starts at 16:00 today. The venue has not been announced yet."
- **Say:** "It knows today's schedule, and when it doesn't know something, like the venue, it says so."
- **Fallback:** type the same question in Chat. If Live shows the "Fallback voice" badge, carry on: push to talk works the same way.

### Beat 2: interrupt it (12 s)
- **Do:** ask **"Which engineering departments does AITM have?"** As it starts listing, interrupt: **"Just the AI ones."**
- **Expected:** it stops mid-sentence and answers the narrower question; chips link to the department pages on aitm.edu.in.
- **Say:** "You can talk over it like a person. And every fact has a chip that opens the college's own page."
- **Fallback:** Chat tab, same question; it lists all 8 engineering departments with chips.

### Beat 3: show it what you're looking at (12 s)
- **Do:** Camera on, point at the poster, tap **Look**: "What's this?"
- **Expected:** it reads the poster and links the matching AITM page (STEM 2024 news page in testing, about 3 s).
- **Say:** "It reads posters and notice boards, and connects them to what the college has published. It never identifies people."
- **Fallback:** ask "What was STEM 2024?" in Chat.

### Beat 4: same question, your language (8 s)
- **Do:** ask in Hindi: **"AITM में कौन से विभाग हैं?"**
- **Expected:** a Hindi answer with the same English source pages.
- **Say:** "It answers in the language you speak, from the same sources."
- **Fallback:** type it in Chat (tested: answers in Hindi with correct chips).

### Beat 5: lunch, and honesty (10 s)
- **Do:** ask **"Where can I get lunch nearby, something veg?"**
- **Expected:** Layali Arabia Restaurant and Al Khaleej Arabian Restaurant, with links, plus "vegetarian options are not confirmed".
- **Say:** "It would rather tell you it isn't sure than invent a menu. Every answer is cited, or it says it doesn't know."
- **Fallback:** none needed; the refusal itself is the point.

### Beat 6: Get to Know AITM (15 s), if the quiz is merged
- **Do:** Play tab, **Get to Know AITM**, Solo. Invite a judge: "How well do you know the campus you're judging at? Hold up the sign for your answer." One finger is A, two is B, three is C, four is D. 10-second timer.
- **Expected:** a ring fills as they hold the sign, the answer locks, the source chip appears, their name lands on the leaderboard.
- **Say:** "Every question comes from AITM's own pages, and the answer shows where it came from. You just learned something about this campus by playing. The hand signs come from a model we trained today and run on this laptop, about 50 milliseconds a frame. Hands only, no faces."
- **Fallback:** press 1 to 4 on the keyboard; the game is identical. If the quiz isn't merged, skip this beat and use beat 7 earlier.

### Beat 7: it remembers you (8 s)
- **Do:** on the second device, enter the 4-letter visit code shown top right. Open the visit summary page.
- **Expected:** "Welcome back", with what was asked about and the lunch places.
- **Say:** "No account. A four-letter code, and your visit follows you to any device."

### Optional beat (replace beat 5 or 6 once hiring is verified): hiring
- **Do:** Find talent, "I'm hiring a frontend intern."
- **Expected:** up to three opted-in students, each claim linked to a real repo URL.
- **Say:** "Every claim about a student links to their actual GitHub work, and only students who opted in are ever shown."
- **Status:** 11 consenting students added; not yet verified end to end. Do not use until the monitor or builder confirms.

### If everything fails
Switch to Chat mode (works without Live). If the backend is down, play the recorded fallback video (T3.3, still to record).

---

## 4. What's innovative (three points, each visible on stage)

1. **A voice host that cannot bluff.** Live, interruptible speech, but every factual answer comes from a tool result and shows a source chip; when the data has nothing, it says "I don't have that yet" (beats 1, 2, 5). Most campus chatbots answer anything confidently.
2. **A camera that understands, not identifies.** Look turns a poster into a cited campus answer, and the Get to Know AITM quiz reads hand signs with a model we trained ourselves and run locally. No face detection anywhere (beats 3, 6).
3. **It is about this campus, today, for you.** Built from AITM's own pages, knows today's judging time, remembers you across devices with a 4-letter code, and answers in Hindi or Kannada from the same sources (beats 1, 4, 7).

---

## 5. Judge Q&A prep

| # | Likely question | Short answer |
|---|---|---|
| 1 | How do you stop it making things up? | Answers come only from retrieved campus data; below a confidence threshold it refuses. We test this: 22 of 22 questions found the right page, all 3 off-topic and all 6 plausible-but-unknown questions (hostel fees, canteen hours, Wi-Fi password) were refused or answered "not mentioned". |
| 2 | Where does the data come from? | Official aitm.edu.in pages (scraped with robots.txt respected, 1 request per second), plus two lunch listings the team chose and a schedule the team entered. 61 indexed chunks. Nothing from LinkedIn or social media. |
| 3 | What about privacy? | Students appear only if they opted in (11 have). No face recognition; the camera reads posters and hand signs only, and snapshots aren't stored. We keep extracted facts and the last 10 turns, not full transcripts. |
| 4 | Why not just use a general assistant app? | A general assistant doesn't know AITM's departments, today's judging time or which students opted in, and it will guess. Ours cites the college's own page or says it doesn't know. |
| 5 | What does it cost to run? | Free tiers today (Gemini). Each chat turn is a few model calls; we measured and cut them (direct search, cached embeddings). A college deployment would be a small paid API budget. |
| 6 | What happens when the AI service is slow or down? | It fails over to a backup model on rate limits, and voice falls back to push-to-talk; chat works without Live. In a 17-turn burst with 3 concurrent users we saw 0 errors and 0 empty answers. |
| 7 | How fast is it? | First words of a chat answer in about 1.5 to 2.5 s; Look about 3 s; hand-sign recognition about 50 ms per frame on this laptop's CPU. |
| 8 | How would this scale to other colleges? | The college-specific parts are data: a list of URLs, a locality file and a schedule. Point the scraper at another college's site and re-ingest. |
| 13 | Why a quiz? | "Get to Know AITM" turns the same cited campus data into a 1-minute game, so a visitor actually remembers what makes the place special. Every question is generated from AITM's pages and fact-checked against them before it is used. |
| 9 | How good is the gesture model? | YOLO26n trained on a public HaGRID sample; on 400 test images of 210 people not seen in training, mAP50 0.988 (a 1-epoch baseline was 0.784). We have not yet measured it at this venue's lighting. |
| 10 | Can it handle languages? | The voice host replies in the visitor's language; retrieval translates the question first. Our test set includes Hindi and Kannada questions, all retrieved correctly. |
| 11 | What if the college's own pages disagree? | They do: two AITM pages give different placement figures. The team picked the statistics page as authoritative, and the chip always shows exactly which page an answer came from. |
| 12 | What would you build next? | Verified venue and event data straight from the organisers, more curated local tips (veg confirmed), a phone-first layout with QR resume, and a richer hiring flow with interview kits. |

---

## 6. Numbers to quote (all measured 2026-10-19)

| Claim | Number | Source |
|---|---|---|
| Retrieval accuracy | 22 of 22 correct page in top 4 (incl. 2 Hindi, 1 Kannada) | `scripts/rag_eval.py`, reproduced by the monitor |
| Refusals | 3 of 3 off-topic, 6 of 6 plausible unknowns | rag_eval.yaml, builder run, monitor spot-check |
| Knowledge base | 61 chunks from official AITM pages plus team-curated lunch and schedule | ingest report |
| Chat speed | first words about 1.5 to 2.5 s on single questions | monitor probes, cycles 5 to 7 |
| Robustness | 17-turn burst with 3 concurrent and Hindi: 0 errors, 0 empty answers | monitor probe, cycle 5 |
| Look | poster to cited answer in 3.0 s | monitor e2e, cycle 7 |
| Fallback voice | speech to text 1.9 s, then first word 1.6 s | monitor e2e, cycle 7 |
| Gesture model | mAP50 0.988 on 400 held-out images (baseline 0.784) | monitor/TRAINING-RESULTS.md |
| Gesture speed | about 50 ms per frame including decoding, laptop CPU | monitor, T4.2 runtime |
| AITM placements (if asked) | 83.97% placed, 393 of 468, highest 46.50 LPA | aitm.edu.in/placements/statistics/ (team chose this page as authoritative) |

Wording rules: say "22 of 22 on our test set", not "100 percent accurate". Say "on test images of new people", not "99 percent accurate here". Do not quote venue gesture accuracy until T4.4 is measured.

---

## 7. Before going on stage (checklist)
- [ ] Backend and frontend running; `/api/health` all green.
- [ ] Visit started with the presenter name; code visible; second device ready.
- [ ] Mic and camera allowed in the browser; poster in reach.
- [ ] Quiz merged and one Solo game played that morning, or beat 6 removed from the script.
- [ ] Fallback video recorded (T3.3).
- [ ] Ask the judging-time question once to warm the services (the first request after a restart is slower, about 5 s).
