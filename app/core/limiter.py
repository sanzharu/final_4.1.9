"""
Centralised rate-limiter instance shared by main.py and route modules.

Uses Redis as storage backend so rate-limit counters are shared across all
Uvicorn workers (important for multi-worker production deployments).
Falls back to in-memory storage if Redis is unavailable.

Real client IP is extracted from X-Forwarded-For (set by Caddy / nginx)
so the limit applies to the actual user, not the reverse-proxy container.
"""
from slowapi import Limiter


def _get_real_ip(request) -> str:
    """
    Return the originating client IP.

    Priority:
      1. X-Forwarded-For header (set by Caddy / nginx)
      2. X-Real-IP header (alternative proxy header)
      3. Direct connection IP (fallback for local dev without proxy)
    """
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


def _make_limiter() -> Limiter:
    try:
        from app.core.config import settings
        redis_url = settings.REDIS_URL
    except Exception:
        redis_url = None

    if redis_url:
        try:
            return Limiter(key_func=_get_real_ip, storage_uri=redis_url)
        except Exception:
            pass  # Redis unreachable — fall back to in-memory

    return Limiter(key_func=_get_real_ip)


limiter = _make_limiter()
