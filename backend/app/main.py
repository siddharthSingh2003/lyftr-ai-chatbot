"""FastAPI app: routes, CORS, exception handlers."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .db import Database
from .llm import AllProvidersUnavailable, build_messages, complete_with_failover, configure_litellm
from .schemas import ChatRequest, ChatResponse, HealthResponse, HistoryResponse
from .simulate import parse_simulate_header

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.database_url)
    state = {"cache_enabled": False}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        db.init()
        state["cache_enabled"] = configure_litellm(settings)
        logger.info(
            "ready: keys=%d models=%s cache=%s simulation=%s",
            len(settings.api_keys),
            settings.models,
            state["cache_enabled"],
            settings.enable_failure_simulation,
        )
        yield

    app = FastAPI(title="LLM Chatbot", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Last line of defence: never a stack trace, never HTML.
        logger.error("unhandled error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    @app.get("/health", response_model=HealthResponse)
    def health():
        try:
            db.ping()
        except Exception:
            raise HTTPException(status_code=503, detail="database unavailable")
        return HealthResponse(
            status="ok",
            keys_configured=len(settings.api_keys),
            cache_enabled=state["cache_enabled"],
        )

    @app.post("/chat", response_model=ChatResponse)
    def chat(body: ChatRequest, x_simulate_failure: str | None = Header(default=None)):
        t0 = time.perf_counter()
        simulated = parse_simulate_header(
            x_simulate_failure, settings.key_ids, settings.enable_failure_simulation
        )

        # Prompt rule: this request's prompt > the session's saved prompt > default.
        system_prompt = (
            body.system_prompt
            or db.get_system_prompt(body.session_id)
            or settings.default_system_prompt
        )
        history = db.get_messages(body.session_id, limit=settings.max_history_messages)
        messages = build_messages(system_prompt, history, body.message)

        try:
            result = complete_with_failover(settings, messages, simulated)
        except AllProvidersUnavailable:
            # Nothing has been written: a failed request never enters history.
            raise HTTPException(status_code=503, detail="all providers unavailable")

        latency_ms = int((time.perf_counter() - t0) * 1000)
        metadata = {
            "resolution_source": "LLM_CACHE" if result.cached else "LIVE_INFERENCE",
            "model": result.model,
            "latency_ms": latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "key_id": result.key_id,
            "fallback_attempts": result.fallback_attempts,
        }
        db.append_turn(body.session_id, body.message, result.reply, metadata, body.system_prompt)
        return {"session_id": body.session_id, "reply": result.reply, "metadata": metadata}

    # exclude_none: user rows carry no metadata key at all, matching the brief's example.
    @app.get(
        "/sessions/{session_id}/messages",
        response_model=HistoryResponse,
        response_model_exclude_none=True,
    )
    def session_messages(session_id: str):
        messages = db.get_messages(session_id)
        if not messages:
            raise HTTPException(status_code=404, detail="session not found")
        return {"session_id": session_id, "messages": messages}

    return app


app = create_app()
