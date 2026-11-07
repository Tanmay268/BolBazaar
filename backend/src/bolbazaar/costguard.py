"""Protection of paid provider credits (Gnani speech, Azure OpenAI).

Every paid call goes through ``CostGuard``:

    user_slot -> reserve (atomic, all-or-nothing) -> provider slot + circuit breaker -> call -> reconcile

* Quotas are rows in ``usage_counters`` changed only by one conditional upsert per counter
  (``INSERT .. ON CONFLICT DO UPDATE .. WHERE used + n <= limit RETURNING used``). Fifty simultaneous requests with
  one unit left therefore produce exactly one winner, on SQLite and PostgreSQL, across processes and restarts.
  All counters of one reservation share a transaction, so a refusal by any of them rolls back the others.
* Reservations are never refunded after a provider call was attempted: the provider may have billed it, and a refund
  path would be a way to get unlimited calls out of a limited quota.
* If the ledger cannot be reached the guard fails closed (503). It never falls back to "allow".
* Kill switches (env flags and a live database switch), a per-provider circuit breaker, per-provider concurrency
  limits with a bounded wait, and per-user in-flight limits stop retry storms and queue build-up.

Estimated units (``est_tokens``) are heuristics and are labelled as such. Provider-reported usage (``actual_tokens``)
is recorded separately for monitoring and is never used to refund a reservation.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .errors import ApiError, too_many
from .models import ProviderSwitch, UsageCounter, utcnow
from .providers.base import USAGE_SINK, ProviderError

LOGGER = logging.getLogger("bolbazaar.costguard")
T = TypeVar("T")

PROVIDER_OF = {"stt": "gnani", "tts": "gnani", "llm": "azure"}
UNIT_OF = {"stt": "audio_seconds", "tts": "chars", "llm": "est_tokens"}
WINDOW_SECONDS = {"m": 60, "h": 3600, "d": 86400}
PROVIDERS = ("gnani", "azure")
# Failures that say the provider is unhealthy or unusable (as opposed to a bad request or an empty transcript).
HEALTH_FAILURES = {"network", "http", "rate_limit", "auth", "credits", "configuration"}
FATAL_FAILURES = {"auth", "credits"}


def estimate_tokens(*texts: str, output: int = 600) -> int:
    """Rough token estimate: ~3 characters per token (conservative for Hinglish) plus a typical output size."""
    return sum(len(t) for t in texts) // 3 + 1 + output


def window_key(kind: str, now: float) -> str:
    if kind == "m":
        return f"m:{int(now // 60)}"
    if kind == "h":
        return f"h:{int(now // 3600)}"
    if kind == "d":
        return "d:" + datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d")
    return "life"


def seconds_left(kind: str, now: float) -> float:
    size = WINDOW_SECONDS.get(kind)
    return float(size - (now % size)) if size else 3600.0


@dataclass(frozen=True)
class Charge:
    scope: str
    metric: str
    kind: str          # m | h | d | life
    limit: int
    amount: int

    @property
    def is_global(self) -> bool:
        return self.scope == "global"


class _Exceeded(Exception):
    def __init__(self, charge: Charge, retry_after: float) -> None:
        super().__init__(charge.metric)
        self.charge, self.retry_after = charge, retry_after


class _Breaker:
    def __init__(self) -> None:
        self.failures = 0
        self.trips = 0
        self.open_until = 0.0
        self.trial = False
        self.last_category: str | None = None


class CostGuard:
    def __init__(self, sf: sessionmaker[Session], settings: Settings, *, clock: Callable[[], float] = time.time) -> None:
        self.sf, self.settings, self.clock = sf, settings, clock
        self._lock = threading.Lock()
        self._breakers = {p: _Breaker() for p in PROVIDERS}
        self._inflight: dict[str, int] = {}
        self._slots = {
            "gnani": threading.BoundedSemaphore(max(1, settings.gnani_max_concurrent_requests)),
            "azure": threading.BoundedSemaphore(max(1, settings.azure_max_concurrent_requests)),
        }
        self._switch_cache: dict[str, tuple[float, bool, str | None]] = {}
        self._reservations = 0

    # ------------------------------------------------------------------ switches

    def _env_enabled(self, provider: str) -> bool:
        s = self.settings
        return s.ai_services_enabled and (s.gnani_enabled if provider == "gnani" else s.azure_enabled)

    def _db_switch(self, provider: str) -> tuple[bool, str | None]:
        now = self.clock()
        cached = self._switch_cache.get(provider)
        if cached and cached[0] > now:
            return cached[1], cached[2]
        with self.sf() as s:
            rows = {r.provider: r for r in s.scalars(select(ProviderSwitch).where(ProviderSwitch.provider.in_((provider, "all"))))}
        off = next((r for r in (rows.get(provider), rows.get("all")) if r is not None and not r.enabled), None)
        value = (off is None, off.reason if off else None)
        self._switch_cache[provider] = (now + 2.0, value[0], value[1])
        return value

    def assert_enabled(self, provider: str) -> None:
        disabled = ApiError(503, "PROVIDER_DISABLED", "This feature is temporarily unavailable", {"provider": provider},
                            headers={"Retry-After": "300"})
        if not self._env_enabled(provider):
            raise disabled
        try:
            enabled, _reason = self._db_switch(provider)
        except SQLAlchemyError as exc:  # fail closed: if we cannot read the switch we cannot prove the provider is allowed
            LOGGER.error("provider switch unreadable provider=%s error=%s", provider, type(exc).__name__)
            raise ApiError(503, "QUOTA_UNAVAILABLE", "Usage accounting is unavailable, try again shortly",
                           headers={"Retry-After": "10"}) from exc
        if not enabled:
            raise disabled

    def set_switch(self, provider: str, enabled: bool, reason: str | None, actor: str | None) -> dict[str, Any]:
        with self.sf.begin() as s:
            row = s.get(ProviderSwitch, provider)
            if row is None:
                row = ProviderSwitch(provider=provider)
                s.add(row)
            row.enabled, row.reason, row.updated_by, row.updated_at = enabled, (reason or None), actor, utcnow()
        self._switch_cache.clear()
        LOGGER.warning("provider_switch provider=%s enabled=%s actor=%s", provider, enabled, actor)
        return {"provider": provider, "enabled": enabled, "reason": reason}

    # ------------------------------------------------------------------ circuit breaker

    def _breaker_enter(self, provider: str) -> None:
        b, now = self._breakers[provider], self.clock()
        with self._lock:
            if now < b.open_until:
                raise too_many("PROVIDER_UNAVAILABLE", "The voice service is recovering, try again shortly",
                               b.open_until - now, status=503)
            if b.open_until and not b.trial:
                b.trial = True  # half-open: let exactly one trial call through
            elif b.open_until and b.trial:
                raise too_many("PROVIDER_UNAVAILABLE", "The voice service is recovering, try again shortly", 5, status=503)

    def _breaker_ok(self, provider: str) -> None:
        b = self._breakers[provider]
        with self._lock:
            b.failures, b.trips, b.open_until, b.trial, b.last_category = 0, 0, 0.0, False, None

    def _breaker_neutral(self, provider: str) -> None:
        """The call finished without telling us anything about provider health (bad audio, empty transcript, ...)."""
        with self._lock:
            self._breakers[provider].trial = False

    def _breaker_fail(self, provider: str, category: str) -> None:
        s, b, now = self.settings, self._breakers[provider], self.clock()
        with self._lock:
            b.failures += 1
            b.last_category = category
            was_trial, b.trial = b.trial, False
            if category in FATAL_FAILURES:
                b.trips += 1
                b.open_until = now + s.breaker_fatal_cooldown_seconds
            elif was_trial or b.failures >= s.breaker_failure_threshold:
                b.trips += 1
                b.open_until = now + min(s.breaker_cooldown_seconds * (2 ** (b.trips - 1)), s.breaker_fatal_cooldown_seconds)
            else:
                return
        LOGGER.error("circuit_open provider=%s category=%s trips=%s", provider, category, b.trips)

    # ------------------------------------------------------------------ atomic ledger

    def _charges(self, user_id: str, op: str, requests: int, units: dict[str, int]) -> list[Charge]:
        s, u, provider = self.settings, f"user:{user_id}", PROVIDER_OF[op]
        unit = UNIT_OF[op]
        amount = units.get(unit, 0)
        user_rules = {
            "stt": {"requests": [("m", s.user_stt_per_minute), ("h", s.user_stt_per_hour), ("d", s.user_stt_per_day)],
                    unit: [("d", s.user_stt_audio_seconds_per_day)]},
            "tts": {"requests": [("m", s.user_tts_per_minute), ("h", s.user_tts_per_hour), ("d", s.user_tts_per_day)],
                    unit: [("d", s.user_tts_chars_per_day)]},
            "llm": {"requests": [("m", s.user_llm_per_minute), ("h", s.user_llm_per_hour), ("d", s.user_llm_per_day)],
                    unit: [("d", s.user_llm_est_tokens_per_day)]},
        }[op]
        global_rules = {
            "gnani": {"requests": [("m", s.global_gnani_per_minute), ("d", s.gnani_daily_call_budget)],
                      "audio_seconds": [("d", s.global_gnani_audio_seconds_per_day)],
                      "chars": [("d", s.global_gnani_tts_chars_per_day)]},
            "azure": {"requests": [("m", s.global_azure_per_minute), ("d", s.global_azure_requests_per_day)],
                      "est_tokens": [("d", s.global_azure_est_tokens_per_day)]},
        }[provider]
        out: list[Charge] = []
        for metric, rules in user_rules.items():
            n = requests if metric == "requests" else amount
            out += [Charge(u, f"{op}.{metric}", kind, lim, n) for kind, lim in rules if n > 0]
        for metric, rules in global_rules.items():
            n = requests if metric == "requests" else (amount if metric == unit else 0)
            out += [Charge("global", f"{provider}.{metric}", kind, lim, n) for kind, lim in rules if n > 0]
        return out

    @staticmethod
    def _upsert(s: Session):
        name = s.get_bind().dialect.name
        if name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:  # unsupported dialect: refuse rather than guess
            raise RuntimeError(f"atomic quota ledger is not implemented for {name}")
        return insert

    def _bump(self, s: Session, c: Charge, now: float) -> int:
        """Add ``c.amount`` to the counter iff the result stays within ``c.limit``. Returns the new value."""
        if c.limit <= 0 or c.amount > c.limit:
            raise _Exceeded(c, seconds_left(c.kind, now))
        insert = self._upsert(s)
        window, ts = window_key(c.kind, now), utcnow()
        stmt = insert(UsageCounter).values(scope=c.scope, metric=c.metric, window=window, used=c.amount, updated_at=ts)
        stmt = stmt.on_conflict_do_update(
            index_elements=[UsageCounter.scope, UsageCounter.metric, UsageCounter.window],
            set_={"used": UsageCounter.used + c.amount, "updated_at": ts},
            where=(UsageCounter.used + c.amount <= c.limit),
        ).returning(UsageCounter.used)
        used = s.execute(stmt).scalar_one_or_none()
        if used is None:  # the WHERE clause refused the update: the limit would be exceeded
            raise _Exceeded(c, seconds_left(c.kind, now))
        warn_at = int(c.limit * self.settings.budget_warn_fraction)
        if c.is_global and used - c.amount < warn_at <= used:
            LOGGER.warning("budget_warning metric=%s window=%s used=%s limit=%s", c.metric, window, used, c.limit)
        return int(used)

    def _add_unmetered(self, scope: str, metric: str, amount: int) -> None:
        """Record usage that is only monitored (provider-reported tokens). Never raises."""
        try:
            now = self.clock()
            with self.sf.begin() as s:
                insert, ts = self._upsert(s), utcnow()
                stmt = insert(UsageCounter).values(scope=scope, metric=metric, window=window_key("d", now), used=amount,
                                                   updated_at=ts)
                s.execute(stmt.on_conflict_do_update(
                    index_elements=[UsageCounter.scope, UsageCounter.metric, UsageCounter.window],
                    set_={"used": UsageCounter.used + amount, "updated_at": ts}))
        except Exception as exc:  # noqa: BLE001 - monitoring must never break a request
            LOGGER.warning("usage_record_failed metric=%s error=%s", metric, type(exc).__name__)

    def _apply(self, charges: list[Charge]) -> None:
        now = self.clock()
        with self.sf.begin() as s:  # one transaction: any refusal rolls every counter of this reservation back
            for c in charges:
                self._bump(s, c, now)

    def _maybe_cleanup(self) -> None:
        self._reservations += 1
        if self._reservations % 500:
            return
        try:
            with self.sf.begin() as s:
                s.execute(delete(UsageCounter).where(UsageCounter.updated_at < utcnow() - timedelta(days=3)))
        except SQLAlchemyError:
            pass

    def _fail_closed(self, exc: Exception) -> ApiError:
        LOGGER.error("quota_ledger_unavailable error=%s", type(exc).__name__)
        return ApiError(503, "QUOTA_UNAVAILABLE", "Usage accounting is unavailable, try again shortly",
                        headers={"Retry-After": "10"})

    def consume(self, scope: str, metric: str, kind: str, limit: int, amount: int = 1, *,
                code: str = "QUOTA_EXCEEDED", message: str = "Limit reached", status: int = 429) -> None:
        """Atomically spend ``amount`` from a single named counter (sign-ups, per-capture attempts, ...)."""
        try:
            self._apply([Charge(scope, metric, kind, limit, amount)])
        except _Exceeded as exc:
            raise too_many(code, message, exc.retry_after, status=status) from None
        except (SQLAlchemyError, RuntimeError) as exc:
            raise self._fail_closed(exc) from exc

    def reserve(self, user_id: str, op: str, *, requests: int = 1, **units: int) -> None:
        """Check switches and breaker, then atomically reserve user and global quota for ``op`` (stt | tts | llm)."""
        provider = PROVIDER_OF[op]
        self.assert_enabled(provider)
        self._peek_breaker(provider)
        try:
            self._apply(self._charges(user_id, op, requests, units))
        except _Exceeded as exc:
            if exc.charge.is_global:
                LOGGER.warning("provider_budget_exhausted metric=%s", exc.charge.metric)
                raise too_many("PROVIDER_BUDGET_EXCEEDED", "The voice service has reached its capacity for now",
                               exc.retry_after, status=503, details={"provider": provider}) from None
            raise too_many("QUOTA_EXCEEDED", "You have reached your usage limit for this feature. Try again later.",
                           exc.retry_after, details={"limit": exc.charge.metric, "window": exc.charge.kind}) from None
        except (SQLAlchemyError, RuntimeError) as exc:
            raise self._fail_closed(exc) from exc
        self._maybe_cleanup()

    def _peek_breaker(self, provider: str) -> None:
        b, now = self._breakers[provider], self.clock()
        if now < b.open_until:
            raise too_many("PROVIDER_UNAVAILABLE", "The voice service is recovering, try again shortly",
                           b.open_until - now, status=503)

    # ------------------------------------------------------------------ concurrency + execution

    @contextmanager
    def user_slot(self, user_id: str) -> Iterator[None]:
        limit = self.settings.user_max_concurrent_ai
        with self._lock:
            if limit <= 0 or self._inflight.get(user_id, 0) >= limit:
                raise too_many("CONCURRENCY_LIMIT", "Another request is still being processed. Wait for it to finish.", 2)
            self._inflight[user_id] = self._inflight.get(user_id, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                left = self._inflight.get(user_id, 1) - 1
                if left > 0:
                    self._inflight[user_id] = left
                else:
                    self._inflight.pop(user_id, None)

    def call(self, user_id: str, provider: str, fn: Callable[[], T]) -> T:
        """Run one provider call (quota already reserved) behind the switch, breaker and concurrency limit."""
        self.assert_enabled(provider)
        self._breaker_enter(provider)
        slot = self._slots[provider]
        if not slot.acquire(timeout=self.settings.queue_wait_seconds):
            self._breaker_neutral(provider)
            raise too_many("PROVIDER_BUSY", "The voice service is busy, try again shortly", 3, status=503)
        sink: dict[str, int] = {}
        token = USAGE_SINK.set(sink)
        try:
            result = fn()
        except ProviderError as error:
            if error.category in HEALTH_FAILURES:
                self._breaker_fail(provider, error.category)
            else:
                self._breaker_neutral(provider)
            raise
        except Exception:
            self._breaker_fail(provider, "http")
            raise
        else:
            self._breaker_ok(provider)
            return result
        finally:
            USAGE_SINK.reset(token)
            slot.release()
            if sink.get("tokens"):
                self._add_unmetered("global", f"{provider}.actual_tokens", sink["tokens"])
                self._add_unmetered(f"user:{user_id}", f"{provider}.actual_tokens", sink["tokens"])

    def run(self, user_id: str, op: str, fn: Callable[[], T], *, requests: int = 1, **units: int) -> T:
        """Single paid operation: in-flight limit, atomic reservation, then the guarded call."""
        provider = PROVIDER_OF[op]
        with self.user_slot(user_id):
            self.reserve(user_id, op, requests=requests, **units)
            return self.call(user_id, provider, fn)

    # ------------------------------------------------------------------ monitoring

    def snapshot(self) -> dict[str, Any]:
        now = self.clock()
        day = window_key("d", now)
        with self.sf() as s:
            rows = s.execute(select(UsageCounter).where(UsageCounter.window == day)).scalars().all()
            switches = {r.provider: {"enabled": r.enabled, "reason": r.reason} for r in s.scalars(select(ProviderSwitch))}
        glob = {r.metric: r.used for r in rows if r.scope == "global"}
        per_user: dict[str, dict[str, int]] = {}
        for r in rows:
            if r.scope.startswith("user:"):
                per_user.setdefault(r.scope[5:], {})[r.metric] = r.used
        top = sorted(per_user.items(), key=lambda kv: -sum(v for k, v in kv[1].items() if k.endswith(".requests")))[:10]
        s_ = self.settings
        return {
            "day": day[2:],
            "global": glob,
            "ceilings": {"gnani.requests": s_.gnani_daily_call_budget, "gnani.audio_seconds": s_.global_gnani_audio_seconds_per_day,
                         "gnani.chars": s_.global_gnani_tts_chars_per_day, "azure.requests": s_.global_azure_requests_per_day,
                         "azure.est_tokens": s_.global_azure_est_tokens_per_day},
            "env": {"aiServices": s_.ai_services_enabled, "gnani": s_.gnani_enabled, "azure": s_.azure_enabled},
            "switches": switches,
            "breakers": {p: {"open": now < b.open_until, "failures": b.failures, "lastCategory": b.last_category}
                         for p, b in self._breakers.items()},
            "topUsers": [{"userId": uid, "usage": use} for uid, use in top],
            "note": "est_* values are heuristics; actual_tokens is provider-reported; no prices are assumed.",
        }
