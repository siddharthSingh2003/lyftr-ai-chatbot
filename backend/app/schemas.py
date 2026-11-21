from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_CHARS = 4000
MAX_SESSION_ID_CHARS = 128
MAX_SYSTEM_PROMPT_CHARS = 4000


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=MAX_SESSION_ID_CHARS)
    message: str
    system_prompt: str | None = None

    @field_validator("message")
    @classmethod
    def check_message(cls, v: str) -> str:
        v = v.strip()  # length rules apply AFTER trimming
        if not (1 <= len(v) <= MAX_MESSAGE_CHARS):
            raise ValueError(f"message must be 1-{MAX_MESSAGE_CHARS} chars after trimming")
        return v

    @field_validator("session_id")
    @classmethod
    def check_session(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("session_id must not be empty")
        return v

    @field_validator("system_prompt")
    @classmethod
    def check_system_prompt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > MAX_SYSTEM_PROMPT_CHARS:
            raise ValueError(f"system_prompt must be at most {MAX_SYSTEM_PROMPT_CHARS} chars")
        return v or None  # empty string falls back to the session/default prompt


class ChatMetadata(BaseModel):
    resolution_source: Literal["LIVE_INFERENCE", "LLM_CACHE"]
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    metadata: dict | None = None


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]


class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool
