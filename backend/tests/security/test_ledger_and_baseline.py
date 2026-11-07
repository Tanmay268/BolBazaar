"""Quota ledger semantics (windows, isolation, atomicity, fail-closed) and baseline reproductions.

The baseline tests switch every new protection off by configuration and show the drain that the *original* code allowed
(it had no per-user quota, no Azure budget and no request limits). They prove the harness detects the problem, so the
passing credit tests are not passing by accident.

Set SECTEST_PG_URL (e.g. postgresql+psycopg://user:pw@localhost:55432/db) to run the PostgreSQL atomicity test.
"""

from __future__ import annotations

import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from bolbazaar.costguard import CostGuard, estimate_tokens, window_key
from bolbazaar.db import make_engine, make_session_factory
from bolbazaar.errors import ApiError
from bolbazaar.models import Base, UsageCounter

from .support import FROZEN_NOW, VISIT_TEXT, secure_settings, tone_wav

UNLIMITED = 10 ** 9


def make_guard(tmp_path, clock=lambda: FROZEN_NOW, url=None, **kw) -> CostGuard:
    settings = secure_settings(tmp_path, **kw)
    engine = make_engine(url or settings.database_url)
    Base.metadata.create_all(engine)
    return CostGuard(make_session_factory(engine), settings, clock=clock)


def try_reserve(guard, user="u1", op="llm", **units) -> str:
    try:
        guard.reserve(user, op, **units)
        return "ok"
    except ApiError as e:
        return e.code


# --------------------------------------------------------------------------- ledger semantics

def test_limit_is_exact_then_refuses_with_retry_after(tmp_path):
    guard = make_guard(tmp_path, user_llm_per_minute=3)
    assert [try_reserve(guard, est_tokens=10) for _ in range(5)] == ["ok"] * 3 + ["QUOTA_EXCEEDED"] * 2
    with pytest.raises(ApiError) as caught:
        guard.reserve("u1", "llm", est_tokens=10)
    assert 1 <= int(caught.value.headers["Retry-After"]) <= 60 and caught.value.status == 429


def test_window_rolls_over_but_other_windows_still_bind(tmp_path):
    now = [FROZEN_NOW]
    guard = make_guard(tmp_path, clock=lambda: now[0], user_llm_per_minute=2, user_llm_per_hour=3, user_llm_per_day=100)
    assert [try_reserve(guard, est_tokens=1) for _ in range(3)] == ["ok", "ok", "QUOTA_EXCEEDED"]
    now[0] += 60
    assert try_reserve(guard, est_tokens=1) == "ok"          # new minute, hourly budget now used up (3 of 3)
    assert try_reserve(guard, est_tokens=1) == "QUOTA_EXCEEDED"
    now[0] += 3600
    assert try_reserve(guard, est_tokens=1) == "ok"


def test_users_are_isolated_but_share_the_global_ceiling(tmp_path):
    guard = make_guard(tmp_path, user_llm_per_minute=2, global_azure_requests_per_day=3)
    assert [try_reserve(guard, "a", est_tokens=1) for _ in range(3)] == ["ok", "ok", "QUOTA_EXCEEDED"]
    assert try_reserve(guard, "b", est_tokens=1) == "ok"      # b is not punished for a's exhaustion
    assert try_reserve(guard, "b", est_tokens=1) == "PROVIDER_BUDGET_EXCEEDED"  # but the global ceiling (3) is shared


def test_a_zero_limit_means_blocked_never_unlimited(tmp_path):
    guard = make_guard(tmp_path, user_llm_per_minute=0)
    assert try_reserve(guard, est_tokens=1) == "QUOTA_EXCEEDED"
    assert try_reserve(make_guard(tmp_path / "x", user_max_concurrent_ai=0), est_tokens=1) == "ok"  # reserve alone ignores slots


def test_unit_limits_are_enforced_not_only_request_counts(tmp_path):
    guard = make_guard(tmp_path, user_tts_chars_per_day=100, user_tts_per_minute=50, user_tts_per_hour=50, user_tts_per_day=50)
    assert try_reserve(guard, op="tts", chars=60) == "ok"
    assert try_reserve(guard, op="tts", chars=60) == "QUOTA_EXCEEDED"      # 120 > 100 characters
    assert try_reserve(guard, op="tts", chars=40) == "ok"
    assert try_reserve(guard, op="tts", chars=1) == "QUOTA_EXCEEDED"
    stt = make_guard(tmp_path / "s", user_stt_audio_seconds_per_day=30)
    assert try_reserve(stt, op="stt", requests=1, audio_seconds=31) == "QUOTA_EXCEEDED"


def test_reservation_is_all_or_nothing(tmp_path):
    """If the global counter refuses, the user counters touched earlier in the same reservation roll back."""
    guard = make_guard(tmp_path, user_llm_per_minute=5, global_azure_requests_per_day=1)
    assert try_reserve(guard, est_tokens=1) == "ok"
    assert try_reserve(guard, est_tokens=1) == "PROVIDER_BUDGET_EXCEEDED"
    with guard.sf() as s:
        used = s.query(UsageCounter).filter_by(scope="user:u1", metric="llm.requests", window=window_key("m", FROZEN_NOW)).one().used
    assert used == 1  # the refused attempt left no trace


def test_failed_provider_calls_are_not_refunded(tmp_path):
    from bolbazaar.providers.base import ProviderError
    guard = make_guard(tmp_path, user_llm_per_minute=2, breaker_failure_threshold=100)

    def boom():
        raise ProviderError("http", "boom", retryable=True)

    for _ in range(2):
        with pytest.raises(ProviderError):
            guard.run("u1", "llm", boom, est_tokens=1)
    assert try_reserve(guard, est_tokens=1) == "QUOTA_EXCEEDED"  # no free retries: a failure still spent the quota


def test_provider_reported_usage_is_recorded_separately(tmp_path):
    from bolbazaar.providers.base import report_usage
    guard = make_guard(tmp_path)
    guard.run("u1", "llm", lambda: report_usage("tokens", 321), est_tokens=estimate_tokens("hello"))
    snap = guard.snapshot()
    assert snap["global"]["azure.actual_tokens"] == 321 and snap["global"]["azure.est_tokens"] == estimate_tokens("hello")
    assert "prices" not in str(snap).replace("no prices are assumed", "")


def test_provider_concurrency_is_bounded_and_waiters_fail_fast(tmp_path):
    guard = make_guard(tmp_path, azure_max_concurrent_requests=1, queue_wait_seconds=0.2, user_max_concurrent_ai=10)
    gate, release = threading.Event(), threading.Event()

    def slow():
        gate.set()
        release.wait(3)

    t = threading.Thread(target=lambda: guard.call("a", "azure", slow))
    t.start()
    gate.wait(2)
    with pytest.raises(ApiError) as caught:
        guard.call("b", "azure", lambda: None)
    assert caught.value.code == "PROVIDER_BUSY" and caught.value.status == 503
    release.set()
    t.join()


def test_cleanup_removes_old_rows_only(tmp_path):
    guard = make_guard(tmp_path)
    try_reserve(guard, est_tokens=1)
    guard._reservations = 499
    try_reserve(guard, est_tokens=1)  # triggers cleanup; rows are fresh so nothing is removed
    with guard.sf() as s:
        assert s.query(UsageCounter).count() > 0


# --------------------------------------------------------------------------- atomicity on real databases

def _race(guard, n=50, limit=5):
    barrier = threading.Barrier(n)

    def attempt(_):
        barrier.wait()
        return try_reserve(guard, est_tokens=1)

    with ThreadPoolExecutor(n) as pool:
        return list(pool.map(attempt, range(n)))


def test_atomic_reservation_sqlite_file(tmp_path):
    results = _race(make_guard(tmp_path, user_llm_per_minute=5))
    assert results.count("ok") == 5, results


@pytest.mark.skipif(not os.environ.get("SECTEST_PG_URL"), reason="set SECTEST_PG_URL to run against PostgreSQL")
def test_atomic_reservation_postgresql(tmp_path):
    url = os.environ["SECTEST_PG_URL"]
    engine = make_engine(url)
    Base.metadata.drop_all(engine)
    guard = make_guard(tmp_path, url=url, user_llm_per_minute=5)
    for _ in range(3):  # repeat: a race that is only lost sometimes would show up as a count above five
        with guard.sf.begin() as s:
            s.query(UsageCounter).delete()
        results = _race(guard)
        assert results.count("ok") == 5, results
    # also across two independent guards (two "processes") sharing one database
    other = CostGuard(make_session_factory(make_engine(url)), guard.settings, clock=lambda: FROZEN_NOW)
    with guard.sf.begin() as s:
        s.query(UsageCounter).delete()
    barrier = threading.Barrier(40)

    def attempt(i):
        barrier.wait()
        return try_reserve(guard if i % 2 else other, est_tokens=1)

    with ThreadPoolExecutor(40) as pool:
        assert list(pool.map(attempt, range(40))).count("ok") == 5


# --------------------------------------------------------------------------- audio bomb guard (no ffmpeg needed)

def test_ffmpeg_output_is_capped_by_duration_and_junk_never_spawns_it(monkeypatch):
    from bolbazaar import audio
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=b"\0\0" * 16000, stderr=b"")

    monkeypatch.setattr(audio.shutil, "which", lambda name: "ffmpeg")
    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    audio._ffmpeg_pcm(b"OggS-fake", 120.0)
    assert "-t" in seen["cmd"] and seen["cmd"][seen["cmd"].index("-t") + 1] == "122"  # bounded decode (a "zip bomb" guard)
    seen.clear()
    with pytest.raises(Exception):
        audio.prepare_wav_segments(b"MZ\x90\x00" + b"\0" * 5000, max_segment_s=28, max_total_s=120)
    assert "cmd" not in seen


def test_magic_byte_sniffing():
    from bolbazaar.audio import looks_like_audio
    assert looks_like_audio(tone_wav(1))
    assert looks_like_audio(b"ID3\x04" + b"\0" * 20) and looks_like_audio(b"OggS" + b"\0" * 20)
    assert looks_like_audio(b"\0\0\0\x20ftypM4A " + b"\0" * 20) and looks_like_audio(bytes.fromhex("1a45dfa3") + b"\0" * 20)
    for junk in (b"", b"MZ\x90\x00", b"PK\x03\x04", b"#!/bin/sh\n", b"<html>", b"\x7fELF"):
        assert not looks_like_audio(junk)


# --------------------------------------------------------------------------- baseline: what the original code allowed

OFF = dict(user_llm_per_minute=UNLIMITED, user_llm_per_hour=UNLIMITED, user_llm_per_day=UNLIMITED,
           user_llm_est_tokens_per_day=UNLIMITED, global_azure_per_minute=UNLIMITED, global_azure_requests_per_day=UNLIMITED,
           global_azure_est_tokens_per_day=UNLIMITED, user_max_concurrent_ai=UNLIMITED, rl_ip_per_minute=UNLIMITED,
           rl_user_per_minute=UNLIMITED, max_process_attempts_per_capture=UNLIMITED, breaker_failure_threshold=UNLIMITED)


def test_baseline_without_protections_spam_drains_the_provider(make_sec):
    sec = make_sec(**OFF)
    for i in range(100):
        sec.text_capture("asha", f"base-key-{i:04d}", text=f"{VISIT_TEXT} number {i}")
    assert sec.counter.calls["llm"] == 100  # the pre-fix behaviour: every request reached the paid provider


def test_baseline_without_the_claim_concurrent_retries_double_charge(make_sec, monkeypatch):
    from bolbazaar.services.captures import CaptureService
    from .support import provider_error
    sec = make_sec(**OFF)
    sec.token("asha")
    sec.counter.fail["llm"] = provider_error("http", retryable=True)
    first = sec.text_capture("asha", "base-retry-0001").json()
    cap_id = first["error"]["details"]["captureId"]
    sec.counter.fail["llm"], sec.counter.delay["llm"] = None, 0.3
    monkeypatch.setattr(CaptureService, "_claim", lambda self, capture_id, needs_stt: True)  # the original behaviour
    before, barrier = sec.counter.calls["llm"], threading.Barrier(6)

    def fire(_):
        barrier.wait()
        return sec.client.post(f"/v1/captures/{cap_id}/retry", headers=sec.hdr("asha"))

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(fire, range(6)))
    assert sec.counter.calls["llm"] - before > 1  # duplicate paid execution, now prevented by the atomic claim
