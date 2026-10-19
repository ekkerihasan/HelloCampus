"""Startup model registry. Each component registers a loader; failures are recorded, never fatal,
so one missing model never takes down the other modes."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

log = logging.getLogger("hello_campus.status")

Loader = Callable[[], Awaitable[Any]]


class ComponentStatus(BaseModel):
    name: str
    ok: bool = False
    detail: str = "not loaded"
    load_ms: int | None = None


@dataclass
class Registry:
    loaders: dict[str, Loader] = field(default_factory=dict)
    statuses: dict[str, ComponentStatus] = field(default_factory=dict)
    objects: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, loader: Loader) -> None:
        self.loaders[name] = loader
        self.statuses[name] = ComponentStatus(name=name)

    async def load_one(self, name: str) -> None:
        start = time.perf_counter()
        try:
            obj = await self.loaders[name]()
            self.objects[name] = obj
            detail = getattr(obj, "status_detail", "ready")
            self.statuses[name] = ComponentStatus(name=name, ok=True, detail=str(detail))
        except Exception as exc:  # noqa: BLE001, a failing model must not stop startup
            log.warning("component %s failed to load: %s", name, exc)
            self.statuses[name] = ComponentStatus(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}")
        self.statuses[name].load_ms = int((time.perf_counter() - start) * 1000)
        log.info("component %s ok=%s in %s ms", name, self.statuses[name].ok, self.statuses[name].load_ms)

    async def load_all(self) -> None:
        await asyncio.gather(*(self.load_one(n) for n in self.loaders))

    def get(self, name: str) -> Any | None:
        return self.objects.get(name) if self.statuses.get(name, ComponentStatus(name=name)).ok else None

    def health(self) -> dict:
        return {
            "ok": True,
            "components": {n: s.model_dump() for n, s in self.statuses.items()},
        }


registry = Registry()
