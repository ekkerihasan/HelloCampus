"""All tunable values for Hello Campus. Override any field via .env (same name, upper case)."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM (Ollama)
    ollama_url: str = "http://127.0.0.1:11434"
    llm_model: str = "gemma3:4b"
    llm_fallback_model: str = "qwen3:4b"
    embed_model: str = "nomic-embed-text"
    llm_timeout_s: float = 120.0
    llm_num_ctx: int = 4096
    llm_keep_alive: str = "60m"  # keep models resident between turns

    # Character temperatures (BUILD.md 4.2)
    temp_guide: float = 0.8
    temp_analyst: float = 0.2
    temp_interview_kit: float = 0.9
    temp_json: float = 0.0

    # RAG
    chroma_dir: Path = ROOT / "data" / "chroma"
    clean_dir: Path = ROOT / "data" / "clean"
    locality_path: Path = ROOT / "data" / "locality.json"
    students_optin_path: Path = ROOT / "data" / "students_optin.csv"
    rag_top_k: int = 5
    rag_min_score: float = 0.62  # calibrated: relevant 0.73-0.80, off-topic 0.44-0.57
    chunk_tokens: int = 500
    chunk_overlap_tokens: int = 50

    # Memory
    sqlite_path: Path = ROOT / "data" / "memory.sqlite3"
    memory_max_turns: int = 10
    resume_code_length: int = 4

    # Speech
    stt_model: str = "small"
    stt_compute_type: str = "int8"
    tts_voice: str = "af_heart"
    tts_lang_code: str = "a"
    tts_sample_rate: int = 24000
    enable_kannada: bool = False

    # Vision
    gesture_onnx_path: Path = ROOT / "backend" / "vision" / "weights" / "gesture.onnx"
    gesture_imgsz: int = 416
    gesture_min_conf: float = 0.5
    gesture_iou: float = 0.45
    gesture_hold_ms: int = 500
    gesture_cooldown_ms: int = 1500
    gesture_fps: int = 10
    gesture_fps_generating: int = 3
    gesture_frame_width: int = 320
    gesture_classes: list[str] = ["palm", "like", "dislike", "ok", "peace", "no_gesture"]

    # Scraping
    github_token: str = ""
    scrape_user_agent: str = "HelloCampusBot/0.1 (buildathon project; contact via team)"
    scrape_delay_s: float = 1.0

    # Server
    cors_origins: list[str] = ["*"]


settings = Settings()
