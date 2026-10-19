"""Timeout, retry with exponential backoff and jitter, and key rotation on HTTP 429 (ADDENDUM-01 section 8)."""
import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

import httpx

from backend.config import settings
from backend.providers import usage

log = logging.getLogger("hello_campus.providers")
T = TypeVar("T")
RETRYABLE = {408, 409, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """A provider call failed after retries. `user_message` is safe to show in the UI."""

    def __init__(self, provider: str, detail: str, status: int | None = None) -> None:
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.status = status
        self.user_message = (f"{provider.capitalize()} is busy right now, please try again in a moment."
                             if status == 429 else f"{provider.capitalize()} is not reachable right now.")


class MissingConfig(ProviderError):
    def __init__(self, provider: str, what: str) -> None:
        super().__init__(provider, f"{what} is not set in .env")
        self.user_message = f"{provider.capitalize()} is not configured yet ({what})."


@dataclass
class KeyRing:
    """Round-robin keys. A 429 moves to the next key so one exhausted key does not stall the demo."""
    provider: str
    keys: list[str]
    index: int = 0

    def current(self) -> tuple[int, str]:
        if not self.keys:
            raise MissingConfig(self.provider, f"{self.provider.upper()} API key")
        return self.index, self.keys[self.index % len(self.keys)]

    def rotate(self) -> None:
        if self.keys:
            self.index = (self.index + 1) % len(self.keys)


def backoff_delay(attempt: int, retry_after: str | None = None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), settings.retry_max_delay_s)
        except ValueError:
            pass
    base = min(settings.retry_base_delay_s * (2 ** attempt), settings.retry_max_delay_s)
    return base / 2 + random.uniform(0, base / 2)


async def call_with_retry(provider: str, model: str, op: str, ring: KeyRing,
                          send: Callable[[str], Awaitable[httpx.Response]],
                          tokens: Callable[[httpx.Response], tuple[int | None, int | None]] | None = None,
                          fail_fast_429: bool = False) -> httpx.Response:
    """`send(key)` performs one request. Returns the successful response or raises ProviderError.
    fail_fast_429: the caller has another backend to fail over to, so a 429 on the only key stops at once.
    Without it (embeddings, vision, Live tokens) a 429 waits with backoff and retries."""
    if not model:
        raise MissingConfig(provider, f"model ID for {op}")
    last_status: int | None = None
    last_detail = "no attempt made"
    timeouts = 0
    for attempt in range(settings.retry_attempts):
        key_index, key = ring.current()
        start = time.perf_counter()
        try:
            response = await send(key)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            ms = int((time.perf_counter() - start) * 1000)
            usage.record(provider, model, op, f"error:{type(exc).__name__}", ms, key_index)
            last_status, last_detail = None, type(exc).__name__
            timeouts += isinstance(exc, httpx.TimeoutException)
            if timeouts > settings.retry_timeouts:  # a slow model is failed over, not waited on again and again
                break
            await asyncio.sleep(backoff_delay(attempt))
            continue
        ms = int((time.perf_counter() - start) * 1000)
        if response.status_code < 400:
            p, c = tokens(response) if tokens else (None, None)
            usage.record(provider, model, op, "ok", ms, key_index, p, c)
            return response
        usage.record(provider, model, op, f"http_{response.status_code}", ms, key_index)
        last_status = response.status_code
        last_detail = await _error_text(response)
        if response.status_code not in RETRYABLE:
            break
        if response.status_code == 429:
            if fail_fast_429 and len(ring.keys) <= 1:  # nothing to rotate to: fail over to the next backend (M-011)
                break
            ring.rotate()
            log.warning("%s 429 on key %d, rotating", provider, key_index)
        await asyncio.sleep(backoff_delay(attempt, response.headers.get("retry-after")))
    raise ProviderError(provider, f"{op} failed ({last_status}): {last_detail}", last_status)


async def _error_text(response: httpx.Response) -> str:
    try:
        body = (await response.aread()).decode("utf-8", errors="replace")
    except httpx.HTTPError:
        body = ""
    return body[:300]


def timeout(read_s: float | None = None) -> httpx.Timeout:
    return httpx.Timeout(read_s or settings.http_timeout_s, connect=settings.http_connect_timeout_s)
