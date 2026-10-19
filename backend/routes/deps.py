"""FastAPI dependencies that fetch loaded components, or fail with a clear 503."""
from fastapi import HTTPException

from backend.status import registry


def require(name: str):
    def dep():
        obj = registry.get(name)
        if obj is None:
            status = registry.statuses.get(name)
            raise HTTPException(503, f"{name} is not available: {status.detail if status else 'not registered'}")
        return obj
    return dep


def optional(name: str):
    def dep():
        return registry.get(name)
    return dep


def components() -> dict:
    """Every loaded component by name, for tool execution."""
    return {name: registry.get(name) for name in registry.loaders if registry.get(name) is not None}
