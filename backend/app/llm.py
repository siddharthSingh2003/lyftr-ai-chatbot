"""LiteLLM integration: cache setup, key pool walk with failover, cache labelling."""
import logging
import warnings
from dataclasses import dataclass

import litellm
from litellm.caching.caching import Cache

from .config import Settings

logger = logging.getLogger("app.llm")

CACHE_MAX_ITEMS = 1000


class AllProvidersUnavailable(Exception):
    """Every key in the pool failed for this request."""


class SimulatedFailure(Exception):
    """Raised in place of the provider call for keys named in X-Simulate-Failure."""

    def __init__(self, key_id: str, status_code: int) -> None:
        super().__init__(f"simulated {status_code} for {key_id}")
        self.status_code = status_code


class EmptyReply(Exception):
    """Provider answered 200 with no text. Treated as that key failing."""

    status_code = 502


@dataclass
class Resolution:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int
    cached: bool


def configure_litellm(settings: Settings) -> bool:
    """Set up LiteLLM once at startup. Returns whether the cache is active."""
    litellm.drop_params = True
    litellm.suppress_debug_info = True
    # LiteLLM's response objects trip harmless pydantic serializer warnings.
    warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
    # Provider errors can embed request URLs, and Gemini puts the key in the query
    # string. Silence LiteLLM's own loggers so key material can never reach logs.
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    if not settings.cache_enabled:
        litellm.cache = None
        return False
    try:
        litellm.cache = Cache(type="local", ttl=settings.cache_ttl_seconds)
        litellm.cache.cache.max_size_in_memory = CACHE_MAX_ITEMS
        return True
    except Exception as exc:  # never fail startup over the cache
        logger.warning("cache disabled: %s", type(exc).__name__)
        litellm.cache = None
        return False


def build_messages(system_prompt: str, history: list[dict], new_message: str) -> list[dict]:
    """Deterministic: identical inputs give a byte-identical list, which is what
    makes the LiteLLM cache key (model + messages) stable."""
    msgs = [{"role": "system", "content": system_prompt}]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})  # metadata dropped
    msgs.append({"role": "user", "content": new_message})
    return msgs


def _provider_call(**kwargs):
    # Single seam for tests: they wrap this to inject LiteLLM mock responses.
    return litellm.completion(**kwargs)


def _usage(resp, model: str, messages: list[dict], reply: str) -> tuple[int, int]:
    usage = getattr(resp, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    # Some providers omit usage; estimate instead of reporting 0.
    if prompt == 0:
        prompt = int(litellm.token_counter(model=model, messages=messages))
    if completion == 0 and reply:
        completion = int(litellm.token_counter(model=model, text=reply))
    return prompt, completion


def call_once(model: str, messages: list[dict], api_key: str, settings: Settings, skip_cache_read: bool):
    """One LiteLLM completion. Returns (reply, input_tokens, output_tokens, cache_hit)."""
    kwargs = {
        "model": model,
        "messages": messages,
        "api_key": api_key,
        "timeout": settings.request_timeout_seconds,
        "num_retries": 0,  # we own retries: the key pool walk below
    }
    if skip_cache_read:
        kwargs["cache"] = {"no-cache": True}
    resp = _provider_call(**kwargs)
    reply = (resp.choices[0].message.content or "") if resp.choices else ""
    hidden = getattr(resp, "_hidden_params", None) or {}
    in_tok, out_tok = _usage(resp, model, messages, reply)
    return reply, in_tok, out_tok, bool(hidden.get("cache_hit"))


def lookup_cache(settings: Settings, messages: list[dict]) -> Resolution | None:
    """Check LiteLLM's cache for every pool model before calling any provider.
    LiteLLM keys the cache on model + messages, so a reply cached under key_2's
    model would otherwise be found only after key_1's provider call fails."""
    if litellm.cache is None:
        return None
    for model in dict.fromkeys(settings.models):  # unique, pool order
        try:
            hit = litellm.cache.get_cache(model=model, messages=messages)
        except Exception as exc:
            logger.warning("cache lookup failed: %s", type(exc).__name__)
            return None
        if not hit:
            continue
        if not isinstance(hit, dict):
            hit = hit.model_dump() if hasattr(hit, "model_dump") else dict(hit)
        choices = hit.get("choices") or []
        reply = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
        if not reply.strip():
            continue
        usage = hit.get("usage") or {}
        return Resolution(
            reply=reply,
            model=model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            key_id=None,
            fallback_attempts=0,
            cached=True,
        )
    return None


def complete_with_failover(
    settings: Settings, messages: list[dict], simulated: dict[str, int]
) -> Resolution:
    """Walk the key pool in order. Any provider failure on a key (429, quota, 5xx,
    timeout, auth, empty reply) advances to the next key. Each request has its own
    attempt counter: no shared mutable state between concurrent requests."""
    attempts = 0
    # A failover demo must exercise the pool, so simulated requests skip the cache
    # read (otherwise a previously cached message would mask the failover).
    skip_cache_read = bool(simulated)
    if not skip_cache_read:
        cached = lookup_cache(settings, messages)
        if cached is not None:
            return cached

    for index, api_key in enumerate(settings.api_keys):
        key_id = f"key_{index + 1}"
        model = settings.models[index % len(settings.models)]
        try:
            if key_id in simulated:
                raise SimulatedFailure(key_id, simulated[key_id])  # before any HTTP call
            reply, in_tok, out_tok, cached = call_once(
                model, messages, api_key, settings, skip_cache_read
            )
            if not reply.strip():
                raise EmptyReply()
            return Resolution(
                reply=reply,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                key_id=None if cached else key_id,
                fallback_attempts=0 if cached else attempts,
                cached=cached,
            )
        except Exception as exc:
            # Type name and status only: provider messages may contain the key.
            logger.warning(
                "key %s failed: %s status=%s",
                key_id,
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            attempts += 1

    raise AllProvidersUnavailable()
