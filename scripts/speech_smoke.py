"""Offline real-model WAV -> text -> WAV check, with separate cold and warm timings.

Run: .venv/Scripts/python -m scripts.speech_smoke
The input is synthesized test speech, never a recording of a visitor.
"""
import argparse
import io
import json
import time
import wave
from unittest.mock import patch

from backend.config import settings
from backend.speech.stt import SpeechToText
from backend.speech.tts import TextToSpeech


def timed(call):
    start = time.perf_counter()
    value = call()
    return value, round((time.perf_counter() - start) * 1000)


def check_wav(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio)) as wav:
        assert wav.getnchannels() == 1 and wav.getnframes() > 0
        return round(wav.getnframes() / wav.getframerate(), 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-under-six", action="store_true",
                        help="Return failure if the warm round trip exceeds the BUILD.md target")
    parser.add_argument("--threads", type=int, default=settings.speech_cpu_threads,
                        help="CPU threads for this run only, for laptop latency tuning")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    settings.speech_cpu_threads = args.threads
    # Model constructors and inference must succeed with Python networking disabled.
    with patch("socket.socket.connect", side_effect=RuntimeError("Offline speech check: network disabled")), \
            patch("socket.create_connection", side_effect=RuntimeError("Offline speech check: network disabled")):
        return run(args.require_under_six)


def run(require_under_six: bool) -> int:
    tts, tts_load_ms = timed(TextToSpeech)
    stt, stt_load_ms = timed(SpeechToText)
    prompt = "Hello campus. Where is the library?"
    seed, seed_ms = timed(lambda: tts.synthesize(prompt))
    print(json.dumps({"python_network": "blocked", "cpu_threads": settings.speech_cpu_threads,
                      "tts_load_ms": tts_load_ms, "stt_load_ms": stt_load_ms,
                      "fixture_tts_ms": seed_ms, "input_audio_s": check_wav(seed)}), flush=True)
    warm_ms = 0
    for run in ("cold", "warm"):
        start = time.perf_counter()
        transcript = stt.transcribe(seed)
        assert "library" in transcript["text"].lower(), transcript
        answer, synth_ms = timed(lambda: tts.synthesize(transcript["text"]))
        warm_ms = round((time.perf_counter() - start) * 1000)
        print(json.dumps({"run": run, "transcript": transcript, "tts_ms": synth_ms,
                          "roundtrip_ms": warm_ms, "output_audio_s": check_wav(answer),
                          "under_six_seconds": warm_ms < 6000}), flush=True)
    return int(require_under_six and warm_ms >= 6000)


if __name__ == "__main__":
    raise SystemExit(main())
