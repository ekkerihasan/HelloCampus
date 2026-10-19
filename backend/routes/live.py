"""POST /api/live/token: mints a v1beta ephemeral token locked to the Live model and this visitor's session config
(system instruction, tools, transcription, resumption). The API key never leaves the backend (ADDENDUM-01 4)."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.llm.characters import CharacterName, character
from backend.llm.prompts import TOOL_RULES
from backend.memory.store import visitor_block
from backend.providers.retry import ProviderError
from backend.routes.deps import optional, require
from backend.tools.registry import live_declarations

router = APIRouter()
log = logging.getLogger("hello_campus.live")

VOICE_RULES = (
    "You are speaking out loud. Keep answers to two or three short sentences unless asked for more. "
    "Call the right tool before stating any fact, and wait for its result. When the visitor says look at this, "
    "call look. After a tool result with sources, mention where the information is from in a few words.")
# Spoken answers never read citation markers; the screen shows source chips from tool results.
VOICE_TOOL_RULES = TOOL_RULES.replace("- Mark facts from search_campus with their [n] number.\n",
                                      "- Never say citation numbers such as [1] out loud. The screen shows the sources.\n")
WELCOME_CUE = "(The visitor just opened voice mode.)"


class TokenRequest(BaseModel):
    visitor_id: str | None = None
    character: CharacterName = CharacterName.guide
    resumed: bool = False  # true when reconnecting a dropped session without a resumption handle


class TokenResponse(BaseModel):
    welcome_cue: str  # sent by the client on a fresh session, because Live waits for input before speaking
    token: str
    model: str
    api_version: str
    expire_time: str
    config: dict
    locked: bool


def welcome_rule(name: str, upcoming: list[dict], resumed: bool) -> str:
    if resumed:
        return "The connection was restored. Continue the conversation naturally; do not greet again."
    items = "; ".join(f"{e['title']} on {e['date']} {e['start_time']} at {e['venue']}".strip() for e in upcoming)
    return (f"When you receive {WELCOME_CUE}, welcome {name or 'the visitor'} in one sentence. If they are returning, say welcome back and "
            "mention their stated purpose" + (f" or the next relevant event: {items}" if items else "") + ".")


def live_config(char_name: CharacterName, block: str, welcome: str) -> dict:
    char = character(char_name)
    instruction = "\n\n".join(p for p in (char.persona, VOICE_RULES, VOICE_TOOL_RULES, block, welcome) if p)
    config: dict = {
        "responseModalities": ["AUDIO"],
        "temperature": char.temperature,
        "systemInstruction": {"parts": [{"text": instruction}]},
        "tools": [{"functionDeclarations": live_declarations()}],
        "inputAudioTranscription": {},
        "outputAudioTranscription": {},
        "sessionResumption": {},
        "contextWindowCompression": {"slidingWindow": {}},
        "realtimeInputConfig": {"automaticActivityDetection": {
            "startOfSpeechSensitivity": settings.live_vad_start_sensitivity,
            "endOfSpeechSensitivity": settings.live_vad_end_sensitivity,
            "prefixPaddingMs": settings.live_vad_prefix_padding_ms,
            "silenceDurationMs": settings.live_vad_silence_ms}},
    }
    if settings.live_voice:
        config["speechConfig"] = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": settings.live_voice}}}
    return config


@router.post("/api/live/token", response_model=TokenResponse)
async def token(body: TokenRequest, gemini=Depends(require("gemini")), mem=Depends(optional("memory")),
                sched=Depends(optional("schedule"))) -> TokenResponse:
    if not settings.live_enabled:
        raise HTTPException(503, "Live voice is turned off. Using the fallback voice.")
    visitor = await asyncio.to_thread(mem.get, body.visitor_id) if (mem and body.visitor_id) else None
    upcoming = await asyncio.to_thread(sched.upcoming) if sched else []
    config = live_config(body.character, visitor_block(visitor),
                         welcome_rule(visitor.name if visitor else "", upcoming, body.resumed))
    locked = True
    try:
        minted = await gemini.mint_live_token(config)
    except ProviderError as exc:
        if exc.status != 400:
            raise HTTPException(503, f"{exc.user_message} Using the fallback voice.") from exc
        # The constraint schema was rejected: mint an unlocked token so voice still works, and log it.
        log.warning("live token constraints rejected, minting unlocked token: %s", exc)
        locked = False
        try:
            minted = await gemini.mint_live_token(None)
        except ProviderError as exc2:
            raise HTTPException(503, f"{exc2.user_message} Using the fallback voice.") from exc2
    if not minted.get("token"):
        raise HTTPException(503, "Live voice did not start. Using the fallback voice.")
    return TokenResponse(welcome_cue="" if body.resumed else WELCOME_CUE, token=minted["token"],
                         model=minted["model"], api_version=settings.live_api_version,
                         expire_time=minted["expire_time"], config=config, locked=locked)
