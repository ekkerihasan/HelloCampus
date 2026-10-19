# Isolated quiz and Play handoff

Branch: `feat/quiz-play-isolated`, based on `origin/pivot/cloud-core`.

## Scope and build plan

- T4.1: build and revalidate a grounded quiz bank using only cleaned public campus records.
- T4.3: implement keyboard-only versus/co-op games, server-derived scoring and a persistent SQLite leaderboard.
- T3.4: describe the problem, architecture, RAG and privacy in README; measured numbers remain for the team.
- Add an independent FastAPI router/app under `backend/quiz/` and a standalone `play.html` preview. Leave the production app/router wiring and existing frontend files untouched.
- Test source validation, game transitions/timeouts, co-op agreement, score persistence and keyboard play. Use temporary databases and synthetic fixtures for unit tests; label real-data draft questions pending human review.

Protected areas: `backend/llm/`, `backend/rag/`, `backend/tools/`, `backend/routes/`, and all existing frontend files. The existing local `BUILD.md` change is preserved.

## Integration contract

The standalone API exposes `/api/quiz/config`, `/api/quiz/start`, `/api/quiz/{id}`, `/api/quiz/{id}/action` and `/api/quiz/leaderboard`.

Actions are `buzz`, `answer`, `next` and `tick`. Player and option indices start at zero. Correct answers, source URLs and evidence are disclosed only on reveal. The server owns scoring and timing; the browser never submits a score.

The production builder will mount `backend.quiz.api.router` and add the new `PlayMode` component once their core changes are ready. This isolated branch does not repair or replace the mid-change production entry points.
