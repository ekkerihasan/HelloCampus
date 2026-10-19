"""Every test runs with real network access blocked, so `make test` never spends free-tier quota.
Provider behaviour is tested through httpx.MockTransport doubles instead."""
import hashlib
import math
import os
import re

import httpx
import pytest

from backend.config import settings


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    async def blocked(self, request):  # noqa: ARG001
        raise RuntimeError(f"real network call blocked in tests: {request.url.host}")
    def blocked_sync(self, request):  # noqa: ARG001
        raise RuntimeError(f"real network call blocked in tests: {request.url.host}")

    if os.getenv("HC_NETWORK") != "1":  # opt in to the public-network scraper checks only
        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)
        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked_sync)
    monkeypatch.setattr(settings, "retry_base_delay_s", 0.0)
    monkeypatch.setattr(settings, "retry_max_delay_s", 0.0)
    monkeypatch.setattr(settings, "usage_log_path", tmp_path / "usage.jsonl")


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder: shared words give high cosine, unrelated text near zero."""
    embed_model = "fake-embed"
    dims = 256

    def __init__(self):
        self.calls = 0
        self.texts = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        for w in re.findall(r"\w+", text.lower()):
            if len(w) > 2:
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dims] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    async def embed(self, texts, task_type="RETRIEVAL_DOCUMENT", titles=None):
        self.calls += 1
        self.texts += len(texts)
        return [self._vec(t) for t in texts]

    async def embed_query(self, text):
        return self._vec(text)

    async def aclose(self):
        pass


@pytest.fixture
def embedder():
    return FakeEmbedder()
