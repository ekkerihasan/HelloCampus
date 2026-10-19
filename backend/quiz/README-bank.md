# Offline quiz bank

`python -m backend.quiz --candidates path/to/candidates.json` validates offline
candidates and writes `data/clean/quiz.jsonl`. The input accepts a JSON array,
`{"items": [...]}`, or JSONL. Use `--clean-dir` and `--output` for isolated runs.
An exit status of 1 means fewer than five questions survived; an existing bank
is preserved. Output must not overwrite source JSONL records or the candidates
file. Successful generation atomically replaces the bank using a temporary file
in the output directory, with cleanup on failure. The output is a
draft: a human must review question wording, ambiguity, distractors and freshness
before committing it. Evidence checks alone do not establish factual truth.

The included `review-candidates.json` is a **manual extractive draft pending human
review**, built from the checked-in AITM campus snapshots. It is not Groq-generated.
Reproduce its five validated items with
`python -m backend.quiz --candidates backend/quiz/review-candidates.json`.

Without `--candidates`, the CLI calls Groq's REST API using `GROQ_API_KEY` or the
first comma-separated key in `GROQ_API_KEYS`, and `GROQ_CHAT_MODEL`. No default
model ID is assumed. Environment variables must already be exported; this module
does not read `.env` or import the application or its LLM provider stack.

Only HTTPS AITM campus and achievement records from `data/clean/*.jsonl` are
eligible; student records, private/placeholder flags and `quiz.jsonl` are excluded.
Malformed source URLs are skipped rather than preventing the bank from loading.
Each quote must occur in one record matching the question's URL, and the exact
correct option must occur in the quote. IDs and normalized questions are unique.
Persisted banks undergo the same validation every time `load_bank` runs, so an
outdated bank cannot silently outlive deleted evidence.

Application integration: import `QuizItem, load_bank` from `backend.quiz`.
`load_bank(bank_path, clean_dir)` returns a list of frozen dataclass instances;
`item.to_dict()` returns the six-field persisted schema. Keep `answer_index` and
`evidence` private until the game reveal. No inference occurs while playing.

For custom providers, `await generate_bank(clean_dir, adapter)` invokes an async
`adapter(records)` and postchecks the returned list of candidate dictionaries.

Run focused checks with `python -m pytest backend/quiz/tests/test_bank.py -q`.
