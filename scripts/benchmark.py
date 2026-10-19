"""Measure the installed local models without reusing a prompt prefix between models."""
import time
import uuid

import httpx

from backend.config import settings


def main():
    for model in ("gemma3:1b", "gemma3:4b"):
        start = time.perf_counter()
        r = httpx.post(settings.ollama_url + "/api/chat", timeout=180, json={
            "model": model, "stream": False, "keep_alive": "0s",
            "messages": [{"role": "system", "content": "Request " + uuid.uuid4().hex + ". Give brief factual answers."},
                         {"role": "user", "content": "Describe how a college library helps visitors in two sentences."}],
            "options": {"temperature": 0.2, "num_predict": 32, "num_ctx": settings.llm_num_ctx}})
        r.raise_for_status()
        data = r.json()
        print(model, {"elapsed_s": round(time.perf_counter() - start, 2),
                      "prompt_tokens": data.get("prompt_eval_count"),
                      "prompt_s": round(data.get("prompt_eval_duration", 0) / 1e9, 2),
                      "generation_tokens": data.get("eval_count"),
                      "generation_s": round(data.get("eval_duration", 0) / 1e9, 2)}, flush=True)


if __name__ == "__main__":
    main()
