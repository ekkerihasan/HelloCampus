"""One-time speech model download. Runtime never downloads models."""
from pathlib import Path

import httpx

from backend.config import settings

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"


def download(url: str, dest: Path):
    if dest.exists():
        print(f"Already present: {dest.name}", flush=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    print(f"Downloading {dest.name}", flush=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=180) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_bytes(1024 * 1024):
                file.write(chunk)
    partial.replace(dest)
    print(f"Saved {dest.name}: {dest.stat().st_size // 1024 // 1024} MB", flush=True)


def main():
    download(RELEASE + "kokoro-v1.0.onnx", settings.tts_model_path)
    download(RELEASE + "voices-v1.0.bin", settings.tts_voices_path)
    from huggingface_hub import snapshot_download
    print(f"Downloading faster-whisper {settings.stt_model}", flush=True)
    snapshot_download(f"Systran/faster-whisper-{settings.stt_model}",
        local_dir=str(settings.models_dir / f"whisper-{settings.stt_model}"),
        allow_patterns=["*.json", "model.bin", "vocabulary.*"])
    print("Speech models cached for offline startup.", flush=True)


if __name__ == "__main__":
    main()
