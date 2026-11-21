"""Environment parsing. Read once at startup; fail loudly on bad config."""
import os
from dataclasses import dataclass, field

DEFAULT_MODEL = "gemini/gemini-2.5-flash"
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


@dataclass
class Settings:
    api_keys: list[str] = field(default_factory=list)  # index 0 -> key_1
    models: list[str] = field(default_factory=lambda: [DEFAULT_MODEL])
    database_url: str = "sqlite:////data/app.db"
    allowed_origins: list[str] = field(default_factory=list)
    enable_failure_simulation: bool = False
    cache_enabled: bool = True
    cache_ttl_seconds: int = 86400
    default_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_history_messages: int = 20
    request_timeout_seconds: float = 30.0

    @property
    def key_ids(self) -> list[str]:
        # Positional and stable: api_keys[i] -> key_{i+1}. Never derived from key material.
        return [f"key_{i + 1}" for i in range(len(self.api_keys))]


def _split(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    keys = _split(os.getenv("LLM_API_KEYS", ""))
    if len(keys) < 2:
        raise RuntimeError("LLM_API_KEYS must contain at least 2 comma-separated keys")
    return Settings(
        api_keys=keys,
        models=_split(os.getenv("LLM_MODELS", "")) or [DEFAULT_MODEL],
        database_url=os.getenv("DATABASE_URL", "sqlite:////data/app.db"),
        # Origins are compared literally by the browser: strip trailing slashes.
        allowed_origins=[
            o.rstrip("/") for o in _split(os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"))
        ],
        enable_failure_simulation=_bool("ENABLE_FAILURE_SIMULATION", "false"),
        cache_enabled=_bool("CACHE_ENABLED", "true"),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "86400")),
        default_system_prompt=os.getenv("DEFAULT_SYSTEM_PROMPT", "").strip()
        or DEFAULT_SYSTEM_PROMPT,
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "20")),
        request_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
    )
