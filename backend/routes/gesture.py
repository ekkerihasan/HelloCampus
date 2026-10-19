"""Bounded JPEG websocket protocol with one in-flight inference per connection."""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.config import settings
from backend.status import registry
from backend.vision.gesture import Detection

router = APIRouter()
log = logging.getLogger("hello_campus.gesture")
_connections = 0


class GestureConfig(BaseModel):
    available: bool
    detail: str
    classes: list[str]
    min_confidence: float
    hold_ms: int
    cooldown_ms: int
    fps: int
    fps_generating: int
    frame_width: int
    max_frame_bytes: int


class GestureFrame(BaseModel):
    type: str = "detections"
    detections: list[Detection]


@router.get("/api/gesture/config", response_model=GestureConfig)
async def gesture_config() -> GestureConfig:
    model = registry.get("gesture")
    status = registry.statuses.get("gesture")
    return GestureConfig(
        available=model is not None,
        detail=status.detail if status else "Gesture model has not been loaded. Keyboard controls are available.",
        classes=settings.gesture_classes, min_confidence=settings.gesture_min_conf,
        hold_ms=settings.gesture_hold_ms, cooldown_ms=settings.gesture_cooldown_ms,
        fps=settings.gesture_fps, fps_generating=settings.gesture_fps_generating,
        frame_width=settings.gesture_frame_width, max_frame_bytes=settings.gesture_max_frame_bytes,
    )


@router.websocket("/ws/gesture")
async def gesture_socket(websocket: WebSocket) -> None:
    global _connections
    await websocket.accept()
    detector = registry.get("gesture")
    if detector is None:
        config = await gesture_config()
        await websocket.send_json({"type": "error", "message": config.detail})
        await websocket.close(code=1013)
        return
    if _connections >= settings.gesture_max_connections:
        await websocket.send_json({"type": "error", "message": "Camera inference is busy. Try again shortly."})
        await websocket.close(code=1013)
        return
    _connections += 1
    inference: asyncio.Task | None = None
    try:
        await websocket.send_json({"type": "ready"})
        # Keep only the newest pending frame while inference runs. A fast sender
        # cannot build an unbounded application queue or replay stale gestures.
        pending: bytes | None = None
        receive = asyncio.create_task(websocket.receive())
        try:
            while True:
                waiting = {receive} | ({inference} if inference else set())
                done, _ = await asyncio.wait(waiting, timeout=settings.gesture_receive_timeout_s,
                                             return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    await websocket.close(code=1000, reason="Camera stream timed out")
                    break
                if receive in done:
                    message = receive.result()
                    if message["type"] == "websocket.disconnect":
                        break
                    frame = message.get("bytes")
                    if not frame or len(frame) > settings.gesture_max_frame_bytes:
                        await websocket.send_json({"type": "error", "message": "Send a binary JPEG within the frame limit."})
                        await websocket.close(code=1009)
                        break
                    pending = frame
                    receive = asyncio.create_task(websocket.receive())
                if inference is not None and inference in done:
                    try:
                        detections = inference.result()
                    except ValueError as exc:
                        await websocket.send_json({"type": "error", "message": str(exc)})
                        await websocket.close(code=1003)
                        break
                    except Exception:
                        log.exception("gesture inference failed")
                        await websocket.send_json({"type": "error", "message": "Gesture inference failed. Use keyboard controls."})
                        await websocket.close(code=1011)
                        break
                    inference = None
                    await websocket.send_json(GestureFrame(detections=detections).model_dump())
                if inference is None and pending is not None:
                    inference = asyncio.create_task(asyncio.to_thread(detector.predict, pending))
                    pending = None
        finally:
            receive.cancel()
            await asyncio.gather(receive, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    finally:
        # Do not release the connection slot until the worker finishes. Cancelling
        # to_thread does not stop its CPU work, and could bypass the worker bound.
        if inference is not None:
            await asyncio.gather(inference, return_exceptions=True)
        _connections -= 1
