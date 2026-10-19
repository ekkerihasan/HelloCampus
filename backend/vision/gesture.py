"""Local YOLO26 ONNX gesture inference. Camera frames never leave this process.

Supports Ultralytics end-to-end [1, N, 6] xyxy/confidence/class outputs and
traditional [1, 4 + classes, N] xywh/class-score outputs.
"""
from __future__ import annotations

import ast
import io
import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, Field

from backend.config import Settings, settings as default_settings

log = logging.getLogger("hello_campus.gesture")


class Detection(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    box: tuple[float, float, float, float]  # normalized x1, y1, x2, y2


@dataclass(frozen=True)
class Letterbox:
    width: int
    height: int
    scale: float
    left: int
    top: int


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    intersection = np.maximum(0, np.minimum(a[2:], b[2:]) - np.maximum(a[:2], b[:2])).prod()
    area_a = np.maximum(0, a[2:] - a[:2]).prod()
    area_b = np.maximum(0, b[2:] - b[:2]).prod()
    return float(intersection / max(float(area_a + area_b - intersection), 1e-9))


def decode_output(output: np.ndarray, transform: Letterbox, classes: list[str],
                  min_conf: float, iou_threshold: float) -> list[Detection]:
    """Validate an exported tensor and map model boxes back to camera coordinates."""
    rows = np.asarray(output)
    if rows.ndim == 3 and rows.shape[0] == 1:
        rows = rows[0]
    if rows.ndim != 2:
        raise ValueError(f"Unsupported gesture output shape: {rows.shape}")
    raw = rows.shape[-1] != 6
    if raw:
        if rows.shape[0] == len(classes) + 4:
            rows = rows.T
        if rows.shape[1] != len(classes) + 4:
            raise ValueError(f"Unsupported gesture output shape: {np.asarray(output).shape}")
    candidates: list[tuple[np.ndarray, float, int]] = []
    for row in rows:
        if not np.isfinite(row).all():
            continue
        if raw:
            class_id = int(np.argmax(row[4:]))
            score = float(row[4 + class_id])
            cx, cy, w, h = row[:4]
            box = np.asarray([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
        else:
            score, class_value = float(row[4]), float(row[5])
            if not class_value.is_integer():
                continue
            class_id = int(class_value)
            box = row[:4].copy()
        if not 0 <= class_id < len(classes) or not min_conf <= score <= 1:
            continue
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        candidates.append((box, score, class_id))
    candidates.sort(key=lambda item: item[1], reverse=True)
    kept: list[tuple[np.ndarray, float, int]] = []
    for box, score, class_id in candidates:
        if raw and any(c == class_id and _iou(box, other) > iou_threshold for other, _, c in kept):
            continue
        kept.append((box, score, class_id))
    result = []
    for box, score, class_id in kept:
        x1, y1, x2, y2 = box
        normalized = (
            (float(x1) - transform.left) / transform.scale / transform.width,
            (float(y1) - transform.top) / transform.scale / transform.height,
            (float(x2) - transform.left) / transform.scale / transform.width,
            (float(y2) - transform.top) / transform.scale / transform.height,
        )
        clipped = tuple(max(0.0, min(1.0, value)) for value in normalized)
        if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
            result.append(Detection(label=classes[class_id], confidence=score, box=clipped))
    return result


class GestureDetector:
    def __init__(self, settings: Settings = default_settings):
        self.settings = settings
        if not settings.gesture_onnx_path.is_file():
            raise FileNotFoundError(
                "Trained gesture weights are missing. Export the fine-tuned YOLO26 model to "
                f"{settings.gesture_onnx_path}. Keyboard gesture controls remain available."
            )
        import onnxruntime as ort
        from PIL import Image  # noqa: F401, report missing optional dependency at startup

        options = ort.SessionOptions()
        options.intra_op_num_threads = settings.gesture_cpu_threads
        self.session = ort.InferenceSession(str(settings.gesture_onnx_path), sess_options=options,
                                           providers=["CPUExecutionProvider"])
        inputs = self.session.get_inputs()
        if len(inputs) != 1 or inputs[0].type != "tensor(float)":
            raise ValueError("Gesture ONNX must accept one float32 NCHW image tensor.")
        self.input = inputs[0]
        shape = self.input.shape
        if len(shape) != 4 or (isinstance(shape[1], int) and shape[1] != 3):
            raise ValueError(f"Unsupported gesture input shape: {shape}")
        self.height = shape[2] if isinstance(shape[2], int) else settings.gesture_imgsz
        self.width = shape[3] if isinstance(shape[3], int) else settings.gesture_imgsz
        self.classes = list(settings.gesture_classes)
        names = self.session.get_modelmeta().custom_metadata_map.get("names")
        if not names:
            raise ValueError("Gesture ONNX must include Ultralytics class-name metadata. Re-export the trained model.")
        try:
            parsed = ast.literal_eval(names)
            exported = [parsed[i] for i in range(len(parsed))] if isinstance(parsed, dict) else list(parsed)
        except (ValueError, SyntaxError, KeyError, TypeError) as exc:
            raise ValueError("Invalid gesture class names in ONNX metadata.") from exc
        if set(exported) != set(self.classes) or len(exported) != len(self.classes):
            raise ValueError(f"Gesture ONNX classes must match {self.classes}; received {exported}")
        self.classes = exported
        self.lock = threading.Lock()
        self.status_detail = f"YOLO26 ONNX CPU ready, {self.width}x{self.height}; venue accuracy unverified"

    def predict(self, jpeg: bytes) -> list[Detection]:
        from PIL import Image, UnidentifiedImageError

        if not jpeg or len(jpeg) > self.settings.gesture_max_frame_bytes:
            raise ValueError("Camera frame is empty or exceeds the frame byte limit.")
        try:
            with Image.open(io.BytesIO(jpeg)) as image:
                if image.format != "JPEG":
                    raise ValueError("Only binary JPEG camera frames are accepted.")
                w, h = image.size
                if w * h > self.settings.gesture_max_pixels:
                    raise ValueError("Camera frame exceeds the pixel limit.")
                image = image.convert("RGB")
                scale = min(self.width / w, self.height / h)
                resized = image.resize((round(w * scale), round(h * scale)), Image.Resampling.BILINEAR)
                left = (self.width - resized.width) // 2
                top = (self.height - resized.height) // 2
                canvas = Image.new("RGB", (self.width, self.height), (114, 114, 114))
                canvas.paste(resized, (left, top))
                tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Camera frame is not a valid JPEG image.") from exc
        start = time.perf_counter()
        # One session run at a time limits CPU pressure across connected browsers.
        with self.lock:
            outputs = self.session.run(None, {self.input.name: tensor})
        if len(outputs) != 1:
            raise ValueError("Gesture ONNX must expose one detection output.")
        result = decode_output(outputs[0], Letterbox(w, h, scale, left, top), self.classes,
                               self.settings.gesture_min_conf, self.settings.gesture_iou)
        log.info("gesture inference_ms=%d detections=%d", round((time.perf_counter() - start) * 1000), len(result))
        return result
