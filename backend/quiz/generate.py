"""Generate candidates with an injected adapter or explicit Groq configuration."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

from .bank import read_records, validate_bank


async def generate_bank(clean_dir: Path, adapter):
    """Adapter is async callable(records) returning a list of candidate dictionaries."""
    records = read_records(clean_dir)
    return validate_bank(await adapter(records), records)


async def groq_candidates(records: list[dict]) -> list:
    keys = os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY", "")
    key = keys.split(",")[0].strip()
    model = os.environ.get("GROQ_CHAT_MODEL", "").strip()
    if not key or not model:
        raise ValueError("Set GROQ_API_KEY(S) and GROQ_CHAT_MODEL, or use --candidates.")
    prompt = (
        'Return JSON {"items": [...]} with at least 8 campus quiz candidates. '
        'Each item has id, question, options (4 unique strings), answer_index (0-3), '
        'source_url, evidence. Evidence MUST be an exact verbatim quote from ONE '
        'record.text, including original whitespace. Correct option must occur in '
        'that quote. Use only supplied records. Avoid ambiguous questions.\n'
        + json.dumps(records, ensure_ascii=False)
    )
    body = json.dumps({"model": model, "temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()

    def request():
        req = Request("https://api.groq.com/openai/v1/chat/completions", data=body,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            payload = json.load(response)
        return json.loads(payload["choices"][0]["message"]["content"])["items"]

    return await asyncio.to_thread(request)


def main():
    parser = argparse.ArgumentParser(description="Build evidence-checked quiz draft; human review required.")
    parser.add_argument("--clean-dir", type=Path, default=Path("data/clean"))
    parser.add_argument("--output", type=Path, default=Path("data/clean/quiz.jsonl"))
    parser.add_argument("--candidates", type=Path, help="Offline JSON array or JSONL candidate file")
    args = parser.parse_args()
    output = args.output.resolve()
    source_paths = {path.resolve() for path in args.clean_dir.glob("*.jsonl")
                    if path.name != "quiz.jsonl"}
    if args.candidates:
        source_paths.add(args.candidates.resolve())
    if output in source_paths:
        parser.error("Output must not overwrite source records or the candidates file.")
    if args.candidates:
        content = args.candidates.read_text(encoding="utf-8")
        try:
            candidates = json.loads(content)
        except ValueError:
            candidates = [json.loads(line) for line in content.splitlines() if line.strip()]
        if isinstance(candidates, dict):
            candidates = candidates.get("items", [])
        if not isinstance(candidates, list):
            parser.error("Candidates must be a JSON list or JSONL objects")
        items = validate_bank(candidates, read_records(args.clean_dir))
    else:
        try:
            items = asyncio.run(generate_bank(args.clean_dir, groq_candidates))
        except Exception:
            parser.exit(1, "Quiz generation failed; check provider configuration or use --candidates.\n")
    if len(items) < 5:
        parser.exit(1, "Quiz needs more campus data (fewer than 5 valid questions).\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=args.output.parent, prefix=".quiz-",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            for item in items:
                handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, args.output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Wrote {len(items)} evidence-checked DRAFT questions; human review pending.")


if __name__ == "__main__":
    main()
