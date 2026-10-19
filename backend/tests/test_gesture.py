"""Synthetic adapter/protocol checks plus a load check of the real trained ONNX when present.
Not a measurement of venue accuracy (ADDENDUM-04 T4.4)."""
import io
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import settings
from backend.routes import gesture
from backend.vision.gesture import Detection, GestureDetector, Letterbox, decode_output

CLASSES = ["palm", "one", "peace", "three", "four", "no_gesture"]
TRANSFORM = Letterbox(width=320, height=240, scale=1.3, left=0, top=52)


def test_end_to_end_boxes_unpad_and_normalize():
    output = np.array([[[0, 52, 416, 364, .9, 0], [10, 10, 20, 20, .2, 1],
                        [1, 2, 3, 4, .8, 99], [0, 52, 416, 364, .8, 5]]])
    detections = decode_output(output, TRANSFORM, CLASSES, .5, .45)
    assert [item.label for item in detections] == ["palm", "no_gesture"]
    assert detections[0].box == pytest.approx((0, 0, 1, 1))
    assert detections[0].confidence == pytest.approx(.9)


def test_raw_detection_head_scores_and_class_aware_nms():
    output = np.zeros((1, 10, 3), dtype=np.float32)
    output[0, :4, :] = np.array([[208, 208, 208], [208, 208, 208], [416, 416, 416], [312, 312, 312]])
    output[0, 4, :2] = [.9, .8]  # same palm box, suppress weaker
    output[0, 5, 2] = .7  # same box with a different class remains
    detections = decode_output(output, TRANSFORM, CLASSES, .5, .45)
    assert [item.label for item in detections] == ["palm", "one"]
    assert detections[0].box == pytest.approx((0, 0, 1, 1))


def test_empty_and_invalid_output_is_not_a_gesture():
    assert decode_output(np.empty((1, 0, 6)), TRANSFORM, CLASSES, .5, .45) == []
    invalid = np.array([[[0, 0, 5, 5, np.nan, 1], [5, 5, 0, 0, .9, 0],
                         [0, 0, 5, 5, 1.1, 0], [0, 0, 5, 5, .9, 1.5]]])
    assert decode_output(invalid, TRANSFORM, CLASSES, .5, .45) == []
    with pytest.raises(ValueError, match="shape"):
        decode_output(np.zeros((2, 3, 7)), TRANSFORM, CLASSES, .5, .45)


def test_model_missing_is_explicit(tmp_path):
    cfg = settings.model_copy(update={"gesture_onnx_path": tmp_path / "missing.onnx"})
    with pytest.raises(FileNotFoundError, match="Trained gesture weights are missing"):
        GestureDetector(cfg)


@pytest.mark.parametrize("names,expected", [(None, "class-name metadata"), ("{0: 'person'}", "classes must match")])
def test_pretrained_or_unlabelled_models_are_rejected(tmp_path, monkeypatch, names, expected):
    weights = tmp_path / "gesture.onnx"
    weights.write_bytes(b"synthetic export")
    session = SimpleNamespace(
        get_inputs=lambda: [SimpleNamespace(name="images", type="tensor(float)", shape=[1, 3, 416, 416])],
        get_modelmeta=lambda: SimpleNamespace(custom_metadata_map={"names": names} if names else {}),
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(
        SessionOptions=lambda: SimpleNamespace(), InferenceSession=lambda *args, **kwargs: session,
    ))
    with pytest.raises(ValueError, match=expected):
        GestureDetector(settings.model_copy(update={"gesture_onnx_path": weights}))


def test_jpeg_preprocessing_and_frame_limits():
    from PIL import Image

    seen = []
    detector = object.__new__(GestureDetector)
    detector.settings = settings.model_copy(update={"gesture_max_pixels": 100_000, "gesture_max_frame_bytes": 20_000})
    detector.width = detector.height = 416
    detector.classes = CLASSES
    detector.input = SimpleNamespace(name="images")
    detector.lock = threading.Lock()

    class Session:
        def run(self, _, inputs):
            seen.append(inputs["images"])
            return [np.array([[[0, 52, 416, 364, .9, 0]]])]

    detector.session = Session()
    frame = io.BytesIO()
    Image.new("RGB", (320, 240), (255, 0, 0)).save(frame, format="JPEG")
    detections = detector.predict(frame.getvalue())
    assert detections[0].box == pytest.approx((0, 0, 1, 1))
    assert seen[0].shape == (1, 3, 416, 416)
    assert seen[0].dtype == np.float32
    assert seen[0][0, 0, 208, 208] > .98
    assert seen[0][0, 1, 208, 208] < .02
    assert seen[0][0, 0, 0, 0] == pytest.approx(114 / 255)
    with pytest.raises(ValueError, match="valid JPEG"):
        detector.predict(b"invalid image")
    with pytest.raises(ValueError, match="byte limit"):
        detector.predict(b"x" * 20_001)
    huge = io.BytesIO()
    Image.new("RGB", (400, 400)).save(huge, format="JPEG")
    with pytest.raises(ValueError, match="pixel limit"):
        detector.predict(huge.getvalue())


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(gesture.router)
    monkeypatch.setattr(gesture, "_connections", 0)
    with TestClient(app) as test_client:
        yield test_client


def test_config_and_missing_model_websocket(client, monkeypatch):
    monkeypatch.setattr(gesture.registry, "get", lambda _: None)
    config = client.get("/api/gesture/config").json()
    assert config["available"] is False
    assert config["hold_ms"] == settings.gesture_hold_ms
    assert config["cooldown_ms"] == settings.gesture_cooldown_ms
    assert config["frame_width"] == 320
    assert config["fps"] == 10 and config["fps_generating"] == 3
    with client.websocket_connect("/ws/gesture") as ws:
        assert ws.receive_json()["type"] == "error"


def test_websocket_normalized_results_and_rejects_large_frames(client, monkeypatch):
    detector = SimpleNamespace(predict=lambda _: [Detection(label="peace", confidence=.9, box=(0, 0, 1, 1))])
    monkeypatch.setattr(gesture.registry, "get", lambda _: detector)
    with client.websocket_connect("/ws/gesture") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_bytes(b"synthetic")
        reply = ws.receive_json()
        assert reply["detections"][0] == {"label": "peace", "confidence": .9, "box": [0, 0, 1, 1]}
        ws.send_bytes(b"x" * (settings.gesture_max_frame_bytes + 1))
        assert ws.receive_json()["type"] == "error"


def test_backpressure_keeps_latest_frame_only(client, monkeypatch):
    started, release = threading.Event(), threading.Event()
    frames = []

    def predict(frame):
        frames.append(frame)
        if len(frames) == 1:
            started.set()
            assert release.wait(3)
        return []

    monkeypatch.setattr(gesture.registry, "get", lambda _: SimpleNamespace(predict=predict))
    with client.websocket_connect("/ws/gesture") as ws:
        ws.receive_json()
        ws.send_bytes(b"first")
        assert started.wait(2)
        for index in range(20):
            ws.send_bytes(f"frame-{index}".encode())
        # Allow the receiver to drain the burst while its CPU worker is blocked.
        time.sleep(.15)
        release.set()
        assert ws.receive_json()["type"] == "detections"
        assert ws.receive_json()["type"] == "detections"
    assert frames == [b"first", b"frame-19"]


def test_connection_limit_and_invalid_input(client, monkeypatch):
    monkeypatch.setattr(gesture.registry, "get", lambda _: SimpleNamespace(predict=lambda _: []))
    monkeypatch.setattr(gesture, "_connections", settings.gesture_max_connections)
    with client.websocket_connect("/ws/gesture") as ws:
        assert "busy" in ws.receive_json()["message"]
    monkeypatch.setattr(gesture, "_connections", 0)
    with client.websocket_connect("/ws/gesture") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_text("not jpeg")
        assert ws.receive_json()["type"] == "error"


REAL_MODEL = settings.gesture_onnx_path


@pytest.mark.skipif(not REAL_MODEL.is_file(), reason="trained gesture.onnx not installed")
def test_real_model_loads_with_quiz_classes():
    detector = GestureDetector(settings)
    assert detector.classes == ["palm", "one", "peace", "three", "four", "no_gesture"]
    assert (detector.width, detector.height) == (settings.gesture_imgsz, settings.gesture_imgsz)
    assert detector.session.get_outputs()[0].shape[1] == 4 + len(detector.classes)


@pytest.mark.skipif(not REAL_MODEL.is_file(), reason="trained gesture.onnx not installed")
def test_real_model_blank_frame_has_no_hand_and_is_fast():
    from PIL import Image

    detector = GestureDetector(settings)
    frame = io.BytesIO()
    Image.new("RGB", (settings.gesture_frame_width, 240), (128, 128, 128)).save(frame, format="JPEG")
    detector.predict(frame.getvalue())  # warm-up
    times = []
    for _ in range(10):
        start = time.perf_counter()
        detections = detector.predict(frame.getvalue())
        times.append(time.perf_counter() - start)
    hands = [d for d in detections if d.label != "no_gesture"]
    assert hands == []
    assert sorted(times)[len(times) // 2] < 0.12  # ADDENDUM-03 T4.2 budget, including JPEG decode and letterbox
