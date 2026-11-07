"""Request-level protection that runs before any route code: client IP resolution, per-IP rate limits,
request-body size limits and security headers.

This is a pure ASGI middleware on purpose. FastAPI parses (and spools to disk) a multipart body *before* it
solves dependencies, so limits implemented as dependencies cannot stop an oversized upload.

The in-memory limiter is per process. With several backend instances, put a shared limiter (Redis) or the
platform's edge rate limiting in front; the cost quotas in ``costguard`` live in the database and are shared.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable

from .config import Settings


class SlidingWindowLimiter:
    """Thread-safe sliding-window counter keyed by (bucket, key). Memory is bounded by ``max_keys``."""

    def __init__(self, *, max_keys: int = 50_000, clock: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys
        self._clock = clock

    @staticmethod
    def key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _trim(self, q: deque[float], now: float, window: float) -> None:
        while q and q[0] <= now - window:
            q.popleft()

    def _evict(self, now: float) -> None:
        if len(self._hits) <= self._max_keys:
            return
        for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - 3600]:
            del self._hits[k]
        if len(self._hits) > self._max_keys:  # still full of live keys: drop the oldest half rather than grow
            for k in sorted(self._hits, key=lambda k: self._hits[k][-1] if self._hits[k] else 0)[: len(self._hits) // 2]:
                del self._hits[k]

    def hit(self, bucket: str, key: str, limit: int, window: float) -> float:
        """Record one event. Returns 0.0 if allowed, otherwise the seconds until it would be allowed."""
        now = self._clock()
        with self._lock:
            q = self._hits.setdefault((bucket, key), deque())
            self._trim(q, now, window)
            if limit <= 0 or len(q) >= limit:
                return max(1.0, (q[0] + window - now) if q else window)
            q.append(now)
            self._evict(now)
            return 0.0

    def blocked_for(self, bucket: str, key: str, limit: int, window: float) -> float:
        """Seconds until ``limit`` events in ``window`` would no longer be exceeded, without recording anything."""
        now = self._clock()
        with self._lock:
            q = self._hits.get((bucket, key))
            if not q:
                return 0.0 if limit > 0 else window
            self._trim(q, now, window)
            if limit > 0 and len(q) < limit:
                return 0.0
            return max(1.0, q[0] + window - now) if q else window

    def record(self, bucket: str, key: str, window: float) -> None:
        now = self._clock()
        with self._lock:
            q = self._hits.setdefault((bucket, key), deque())
            self._trim(q, now, window)
            q.append(now)
            self._evict(now)

    def reset(self, bucket: str, key: str) -> None:
        with self._lock:
            self._hits.pop((bucket, key), None)


def client_ip(scope: dict[str, Any], trusted_proxies: int) -> str:
    """Best-effort client address. X-Forwarded-For is honoured only for the configured number of trusted proxies,
    and only the entry those proxies appended (counted from the right) is used, so a client cannot choose its own."""
    peer = (scope.get("client") or ("unknown", 0))[0]
    chosen = peer
    if trusted_proxies > 0:
        raw = b",".join(v for k, v in scope.get("headers", []) if k == b"x-forwarded-for").decode("latin-1")
        hops = [h.strip() for h in raw.split(",") if h.strip()]
        if len(hops) >= trusted_proxies:
            chosen = hops[-trusted_proxies]
    try:
        addr = ipaddress.ip_address(chosen)
    except ValueError:
        return peer if peer != chosen else "unknown"
    if isinstance(addr, ipaddress.IPv6Address):  # one /64 is one subscriber; do not let a single host rotate addresses
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address) + "/64"
    return str(addr)


SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
    (b"permissions-policy", b"geolocation=(), camera=(), payment=()"),
]


class RequestTooLarge(Exception):
    pass


class GuardMiddleware:
    def __init__(self, app, settings: Settings, limiter: SlidingWindowLimiter) -> None:
        self.app, self.settings, self.limiter = app, settings, limiter

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _request_id(scope: dict[str, Any]) -> str:
        return (scope.get("state") or {}).get("request_id") or uuid.uuid4().hex

    async def _reject(self, scope, send, status: int, code: str, message: str, retry_after: float | None = None) -> None:
        rid = self._request_id(scope)
        body = json.dumps({"error": {"code": code, "message": message, "details": None}, "requestId": rid}).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                   (b"x-request-id", rid.encode())] + SECURITY_HEADERS
        if retry_after is not None:
            headers.append((b"retry-after", str(max(1, int(retry_after + 0.999))).encode()))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def _body_limit(self, path: str, content_type: str) -> int:
        s = self.settings
        audio_route = path in {"/v1/captures", "/v1/products/draft"} or path.endswith("/corrections/audio")
        if audio_route and content_type.startswith("multipart/form-data"):
            return s.max_audio_bytes + s.multipart_overhead_bytes
        return s.max_json_body_bytes

    def _ip_limits(self, method: str, path: str, ip: str) -> float:
        s, lim = self.settings, self.limiter
        if method == "OPTIONS":
            return 0.0
        wait = lim.hit("ip", ip, s.rl_ip_per_minute, 60)
        if wait:
            return wait
        if method == "POST" and path == "/v1/auth/login":
            return lim.hit("login_ip", ip, s.rl_login_ip_per_minute, 60)
        if method == "POST" and path == "/v1/auth/register":
            return lim.hit("register_ip", ip, s.rl_register_ip_per_hour, 3600)
        return 0.0

    # ------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path, method = scope["path"], scope["method"]
        headers = {k: v for k, v in scope.get("headers", [])}
        ip = client_ip(scope, self.settings.trusted_proxy_count)
        scope.setdefault("state", {})["client_ip"] = ip

        wait = self._ip_limits(method, path, ip)
        if wait:
            await self._reject(scope, send, 429, "RATE_LIMITED", "Too many requests. Slow down and retry shortly.", wait)
            return

        content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
        limit = self._body_limit(path, content_type)
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await self._reject(scope, send, 413, "REQUEST_TOO_LARGE", "The request body is too large")
                    return
            except ValueError:
                await self._reject(scope, send, 400, "BAD_REQUEST", "Invalid Content-Length")
                return

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge()
            return message

        async def secured_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                present = {k.lower() for k, _ in message.get("headers", [])}
                extra = [h for h in SECURITY_HEADERS if h[0] not in present]
                if not path.startswith(("/docs", "/redoc")):
                    if b"cache-control" not in present:
                        extra.append((b"cache-control", b"no-store"))
                    extra.append((b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"))
                if self.settings.app_env != "development":
                    extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        try:
            await self.app(scope, limited_receive, secured_send)
        except RequestTooLarge:
            if not started:
                await self._reject(scope, send, 413, "REQUEST_TOO_LARGE", "The request body is too large")
