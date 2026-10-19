"""Ask the running backend a few questions and print first-token latency, the answer and its chips.
Run: python -m scripts.chat_probe "question one" "question two" ... (each question costs one chat turn)."""
import json
import sys
import time

import httpx

API = "http://localhost:8000"


def ask(client: httpx.Client, question: str, character: str = "guide") -> None:
    start, first, answer, tools, sources, refused = time.perf_counter(), None, "", [], [], None
    with client.stream("POST", f"{API}/api/chat", json={"message": question, "character": character}) as r:
        event = ""
        for line in r.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
                if event == "token":
                    first = first or time.perf_counter()
                    answer += data.get("t", "")
                elif event == "tool":
                    tools.append(f"{data['name']}({json.dumps(data['args'], ensure_ascii=False)})")
                elif event == "sources":
                    sources, refused = [s["url"] for s in data["sources"]], data["refused"]
                elif event == "error":
                    answer = f"ERROR {data.get('message')}"
    ms = int(((first or time.perf_counter()) - start) * 1000)
    print(f"Q: {question}\n  first token {ms} ms | tools {tools or 'none'} | refused {refused}\n  chips {sources}\n"
          f"  A: {answer.strip()[:300]}")


if __name__ == "__main__":
    with httpx.Client(timeout=90) as c:
        for q in sys.argv[1:]:
            ask(c, q)
