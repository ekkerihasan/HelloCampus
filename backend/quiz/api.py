"""Standalone quiz app and mountable router. Does not import the production app."""
import threading
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StrictInt

from .config import QuizSettings
from .engine import QuizEngine, QuizError

router = APIRouter(prefix="/api/quiz", tags=["quiz"])
_initialization = threading.Lock()


class StartGame(BaseModel):
    mode: Literal["versus", "coop"]
    players: list[str] = Field(min_length=2, max_length=2)


class GameAction(BaseModel):
    action: Literal["buzz", "answer", "next", "tick"]
    player: StrictInt | None = Field(default=None, ge=0, le=1)
    option: StrictInt | None = Field(default=None, ge=0, le=3)


def engine(request: Request) -> QuizEngine:
    with _initialization:
        if not hasattr(request.app.state, "quiz_engine"):
            settings = getattr(request.app.state, "quiz_settings", None) or QuizSettings()
            request.app.state.quiz_engine = QuizEngine(settings)
        return request.app.state.quiz_engine


def invoke(call):
    try:
        return call()
    except QuizError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/config")
def config(service: QuizEngine = Depends(engine)):
    result = invoke(service.config)
    return {**result, "question_count": result.get("questions_available", 0)}


@router.get("/leaderboard")
def leaderboard(mode: Literal["versus", "coop"] = "versus", service: QuizEngine = Depends(engine)):
    return {"entries": invoke(lambda: service.leaderboard(mode))}


@router.post("/start")
def start(body: StartGame, service: QuizEngine = Depends(engine)):
    return invoke(lambda: service.start(body.mode, body.players))


@router.get("/{game_id}")
def get_game(game_id: str, service: QuizEngine = Depends(engine)):
    return invoke(lambda: service.view(game_id))


@router.post("/{game_id}/action")
def action(game_id: str, body: GameAction, service: QuizEngine = Depends(engine)):
    return invoke(lambda: service.action(game_id, body.action, body.player, body.option))


def create_app(settings: QuizSettings | None = None, game_engine: QuizEngine | None = None) -> FastAPI:
    application = FastAPI(title="Hello Campus isolated Play preview")
    application.state.quiz_settings = settings or QuizSettings()
    if game_engine is not None:
        application.state.quiz_engine = game_engine
    application.add_middleware(CORSMiddleware,
        allow_origins=application.state.quiz_settings.cors_origins,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    application.include_router(router)
    return application


app = create_app()
