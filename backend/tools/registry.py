"""Tool contract (ADDENDUM-01 section 6). One pydantic args model per tool feeds three consumers:
Groq/OpenAI tool definitions for chat, Gemini Live function declarations for voice, and /api/tools/<name>.
Grounding tools are declared BLOCKING on Live so the host cannot answer before the data arrives (M-004)."""
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError


@dataclass
class ToolContext:
    visitor_id: str | None
    mode: str  # chat | voice
    components: dict[str, Any] = field(default_factory=dict)
    user_message: str = ""  # the visitor's own words, so a model-shortened tool query cannot drop key terms

    def get(self, name: str) -> Any:
        return self.components.get(name)


class ToolError(Exception):
    """Raised by a tool for a user-visible problem (missing visitor, nothing configured)."""


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[ToolContext, Any], Awaitable[dict]]
    blocking: bool = True
    chat: bool = True  # exposed to the chat model
    live: bool = True  # exposed to Gemini Live
    client_side: bool = False  # executed by the browser (look needs the camera)


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, args: type[BaseModel], blocking: bool = True, chat: bool = True,
         live: bool = True, client_side: bool = False):
    def register(fn: Callable[[ToolContext, Any], Awaitable[dict]]):
        TOOLS[name] = Tool(name, description, args, fn, blocking, chat, live, client_side)
        return fn
    return register


def clean_schema(schema: dict) -> dict:
    """Pydantic JSON schema -> the OpenAPI subset both providers accept: no titles or defaults,
    Optional[X] collapsed to X, nested $defs inlined."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            if "anyOf" in node:
                options = [o for o in node["anyOf"] if o.get("type") != "null"]
                merged = {**walk(options[0]), **{k: v for k, v in node.items() if k in ("description",)}}
                return merged
            return {k: walk(v) for k, v in node.items() if k not in ("title", "default", "$defs")}
        if isinstance(node, list):
            return [walk(n) for n in node]
        return node

    out = walk(schema)
    out.setdefault("type", "object")
    out.setdefault("properties", {})
    if not out.get("required"):
        out.pop("required", None)
    return out


def chat_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": clean_schema(t.args.model_json_schema())}}
            for t in TOOLS.values() if t.chat]


def live_declarations() -> list[dict]:
    return [{"name": t.name, "description": t.description,
             "parameters": clean_schema(t.args.model_json_schema()),
             "behavior": "BLOCKING" if t.blocking else "NON_BLOCKING"}
            for t in TOOLS.values() if t.live]


async def run_tool(name: str, raw_args: dict | None, ctx: ToolContext) -> dict:
    """Validate args and run. Errors come back as data so the model can say what went wrong."""
    t = TOOLS.get(name)
    if t is None:
        return {"error": f"unknown tool {name}"}
    if t.client_side:
        return {"error": f"{name} runs in the browser"}
    try:
        args = t.args.model_validate(raw_args or {})
    except ValidationError as exc:
        return {"error": "invalid arguments", "detail": exc.errors(include_url=False, include_context=False)}
    try:
        return await t.run(ctx, args)
    except ToolError as exc:
        return {"error": str(exc)}
