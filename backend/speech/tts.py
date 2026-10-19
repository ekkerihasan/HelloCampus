"""Kokoro 82M ONNX speech. Each request is a sentence, allowing early playback."""
import io
import logging
import threading
import time

from backend.config import settings

log = logging.getLogger("hello_campus.tts")


class TextToSpeech:
    def __init__(self) -> None:
        from kokoro_onnx import Kokoro
        import onnxruntime as ort
        if not settings.tts_model_path.exists() or not settings.tts_voices_path.exists():
            raise FileNotFoundError("Speech synthesis weights missing. Run python -m scripts.download_models")
        options = ort.SessionOptions()
        options.intra_op_num_threads = settings.speech_cpu_threads
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(settings.tts_model_path), options, providers=["CPUExecutionProvider"])
        self.model = Kokoro.from_session(session, str(settings.tts_voices_path))
        if settings.tts_voice not in self.model.voices:
            raise ValueError(f"Kokoro voice {settings.tts_voice!r} is not in the cached voice file")
        self._lock = threading.Lock()
        self.status_detail = f"Kokoro 82M ONNX, voice {settings.tts_voice}"

    def synthesize(self, text: str) -> bytes:
        import soundfile as sf
        start = time.perf_counter()
        with self._lock:
            samples, sample_rate = self.model.create(text, voice=settings.tts_voice,
                                                     speed=settings.tts_speed, lang="en-us")
        output = io.BytesIO()
        sf.write(output, samples, sample_rate, format="WAV", subtype="PCM_16")
        log.info("tts first audio %d ms", (time.perf_counter() - start) * 1000)
        return output.getvalue()
