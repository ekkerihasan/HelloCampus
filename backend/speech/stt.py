"""Local, bounded CPU transcription. Browser audio is never saved to disk."""
import io
import logging
import threading
import time
from typing import TypedDict

from backend.config import settings

log = logging.getLogger("hello_campus.stt")


class _RecordingLimitError(ValueError):
    """Distinguish our duration guard from decoder errors that subclass ValueError."""


class Transcription(TypedDict):
    text: str
    language: str
    ms: int


class SpeechToText:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel
        path = settings.models_dir / f"whisper-{settings.stt_model}"
        if not (path / "model.bin").exists():
            raise FileNotFoundError("Speech recognition weights missing. Run python -m scripts.download_models")
        self.model = WhisperModel(str(path), device="cpu", compute_type=settings.stt_compute_type,
                                 cpu_threads=settings.speech_cpu_threads, local_files_only=True)
        self._lock = threading.Lock()
        self.status_detail = f"faster-whisper {settings.stt_model}, CPU {settings.stt_compute_type}"

    def transcribe(self, content: bytes) -> Transcription:
        import av
        import numpy as np
        start = time.perf_counter()
        chunks, total = [], 0
        try:
            with av.open(io.BytesIO(content)) as container:
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in container.decode(audio=0):
                    for converted in resampler.resample(frame):
                        pcm = converted.to_ndarray().flatten()
                        total += len(pcm)
                        if total / 16000 > settings.speech_max_duration_s:
                            raise _RecordingLimitError(f"Please keep recordings under {settings.speech_max_duration_s:g} seconds")
                        chunks.append(pcm)
                for converted in resampler.resample(None):
                    pcm = converted.to_ndarray().flatten()
                    total += len(pcm)
                    if total / 16000 > settings.speech_max_duration_s:
                        raise _RecordingLimitError(f"Please keep recordings under {settings.speech_max_duration_s:g} seconds")
                    chunks.append(pcm)
        except _RecordingLimitError as exc:
            raise ValueError(str(exc)) from exc
        except Exception as exc:
            raise ValueError("Could not read this audio. Please record again.") from exc
        if total / 16000 < settings.speech_min_duration_s:
            raise ValueError("The recording is too short. Hold the microphone button a little longer.")
        samples = np.concatenate(chunks).astype(np.float32) / 32768.0
        with self._lock:
            segments, info = self.model.transcribe(samples, language="en", beam_size=settings.stt_beam_size,
                                                    vad_filter=True, condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segments).strip()
        elapsed = round((time.perf_counter() - start) * 1000)
        log.info("stt %d ms for %.1f s audio", elapsed, total / 16000)
        if not text:
            raise ValueError("I didn't catch any speech. Please try again.")
        return {"text": text, "language": info.language, "ms": elapsed}
