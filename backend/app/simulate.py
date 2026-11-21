"""X-Simulate-Failure header parsing. Lenient by design: a malformed header is
ignored, never a 500."""

ALLOWED_STATUSES = {429, 500, 502, 503}


def parse_simulate_header(raw: str | None, key_ids: list[str], enabled: bool) -> dict[str, int]:
    """'key_1=429,key_2=500' or '*=429' -> {'key_1': 429, ...}. Empty when disabled."""
    if not enabled or not raw:
        return {}
    out: dict[str, int] = {}
    for part in raw.split(","):
        target, sep, status_text = part.strip().partition("=")
        target = target.strip()
        if not sep or not target:
            continue
        try:
            status = int(status_text.strip())
        except ValueError:
            continue
        if status not in ALLOWED_STATUSES:
            continue
        if target == "*":
            out.update({k: status for k in key_ids})
        elif target in key_ids:
            out[target] = status
    return out
