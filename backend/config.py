"""All tunable values for Hello Campus. Override any field via .env (same name, upper case).
Keys and model IDs come from .env only (ADDENDUM-01 section 3). Empty model IDs fail loudly at call time."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing import Annotated

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # Keys (backend only)
    gemini_api_key: str = ""
    groq_api_keys: Annotated[list[str], NoDecode] = []
    github_token: str = ""

    # Model IDs (verified in T0.2, recorded in PROGRESS.md)
    gemini_live_model: str = ""
    gemini_vision_model: str = ""
    gemini_embed_model: str = ""
    groq_chat_model: str = ""
    groq_fast_model: str = ""
    groq_stt_model: str = ""
    groq_tts_model: str = ""
    groq_tts_voice: str = ""
    gemini_chat_model: str = ""  # text failover on Gemini's OpenAI-compatible endpoint
    gemini_fast_model: str = ""
    gemini_backup_model: str = ""  # second text model with its own free-tier quota
    gemini_tts_model: str = ""
    gemini_tts_voice: str = ""
    gemini_tts_sample_rate: int = 24000
    gemini_reasoning_effort: str = ""  # e.g. low for thinking models such as gemini-3.8-flash (M-008)

    # Endpoints
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    gemini_openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    text_providers: Annotated[list[str], NoDecode] = ["groq", "gemini", "gemini-backup"]  # failover order
    text_failover_cooldown_s: float = 120.0
    text_busy_retry_s: float = 1.5  # every backend answered 429: wait this long, then retry the primary once
    text_blocked_cooldown_s: float = 900.0  # a provider answering 401/403/404 is skipped for 15 minutes
    health_cache_s: float = 120.0  # provider probes list models; the UI polls health every 20 s

    # External call policy
    http_timeout_s: float = 30.0
    http_connect_timeout_s: float = 5.0
    retry_attempts: int = 4
    retry_base_delay_s: float = 0.5
    retry_max_delay_s: float = 8.0
    health_timeout_s: float = 6.0
    retry_timeouts: int = 1  # timeouts are retried at most once, then the call fails over
    text_timeout_s: float = 12.0  # read timeout for text backends
    text_first_token_timeout_s: float = 6.0  # stream fails over if no first token by then (M-008)
    usage_log_path: Path = ROOT / "logs" / "usage.jsonl"

    # Feature flags
    live_enabled: bool = True
    server_tts_enabled: bool = True  # Groq Orpheus, then Gemini TTS; the browser voice is the last resort
    rag_translate_queries: bool = True  # translate non-English queries before BM25 (ADDENDUM-01 section 13)

    # Generation
    llm_max_output_tokens: int = 400
    llm_json_output_tokens: int = 700
    chat_history_chars: int = 2400
    chat_max_message_chars: int = 4000
    chat_direct_search: bool = True  # plain campus questions skip the tool-choice call (M-008)
    chat_tool_rounds: int = 1  # one tool-selection call per turn keeps free-tier usage low
    memory_extract_timeout_s: float = 20.0
    memory_summary_chars: int = 600  # about 150 tokens (ADDENDUM-01 section 8)
    supported_languages: Annotated[list[str], NoDecode] = ["en", "hi", "kn", "ur"]  # visitor languages to mirror
    language_min_words: int = 4  # shorter turns never change the stored language (a misheard fragment did)

    # Character temperatures (BUILD.md 4.2)
    temp_guide: float = 0.8
    temp_analyst: float = 0.2
    temp_interview_kit: float = 0.9
    temp_json: float = 0.0

    # Live API
    live_token_uses: int = 1
    live_token_ttl_s: int = 1800
    live_new_session_window_s: int = 60
    live_voice: str = ""  # empty means the API default voice
    # Voice activity detection for noisy venues: Live defaults to HIGH start sensitivity, so chatter can barge in.
    live_vad_start_sensitivity: str = "START_SENSITIVITY_LOW"
    live_vad_end_sensitivity: str = "END_SENSITIVITY_HIGH"
    live_vad_prefix_padding_ms: int = 300
    live_vad_silence_ms: int = 700
    live_api_version: str = "v1beta"  # docs: ephemeral tokens are v1beta; SDK 2.30 warns v1alpha, so it is configurable

    # Look
    look_max_image_bytes: int = 4_000_000
    look_max_question_chars: int = 300

    # Data
    clean_dir: Path = ROOT / "data" / "clean"
    locality_path: Path = ROOT / "data" / "locality.json"
    schedule_path: Path = ROOT / "data" / "schedule.json"
    posts_path: Path = ROOT / "data" / "posts.json"  # hand-pasted posts with their public URLs
    students_optin_path: Path = ROOT / "data" / "students_optin.csv"
    ingest_report_path: Path = ROOT / "data" / "ingest_report.json"
    rag_eval_path: Path = ROOT / "backend" / "tests" / "rag_eval.yaml"

    # RAG (ADDENDUM-01 section 7)
    chroma_dir: Path = ROOT / "data" / "chroma"
    embed_cache_path: Path = ROOT / "data" / "embed_cache.sqlite3"
    embed_batch: int = 50
    embed_task_mode: str = "prefix"  # prefix for gemini-embedding-2, task_type for gemini-embedding-001
    embed_doc_template: str = "title: {title} | text: {text}"  # gemini-embedding-2 docs (M-003)
    embed_query_template: str = "task: search result | query: {text}"
    embed_dimensions: int = 768  # keeps the committed Chroma snapshot small; embedding-2 auto-normalizes
    embed_max_chars: int = 6000
    rag_vector_k: int = 10
    rag_bm25_k: int = 10
    rag_rrf_k: int = 60
    query_embed_cache: int = 256  # recent query embeddings kept in memory
    rag_top_k_chat: int = 4
    rag_top_k_voice: int = 3
    rag_min_score: float = 0.62  # cosine similarity; recalibrate for the Gemini embedder (PROGRESS.md)
    rag_min_keyword_coverage: float = 0.6  # share of query terms an exact-match chunk must contain
    chunk_tokens: int = 400
    chunk_overlap_tokens: int = 50
    chat_context_chars: int = 3600

    # Memory
    sqlite_path: Path = ROOT / "data" / "memory.sqlite3"
    memory_max_turns: int = 10
    resume_code_length: int = 4

    # Speech fallback
    speech_max_audio_bytes: int = 8_000_000
    speech_max_text_chars: int = 200  # Orpheus rejects longer input (M-005); the browser splits sentences to fit
    speech_recording_limit_s: float = 30.0

    # Scraping
    scrape_user_agent: str = "HelloCampusBot/0.1 (buildathon project; contact via team)"
    scrape_delay_s: float = 1.0
    scrape_timeout_s: float = 45.0  # aitm.edu.in often takes over 20 s to respond
    scrape_timeout_retries: int = 1

    # Server
    cors_origins: list[str] = ["*"]

    @field_validator("groq_api_keys", "text_providers", "supported_languages", mode="before")
    @classmethod
    def split_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [k.strip() for k in value.split(",") if k.strip()]
        return value


settings = Settings()
