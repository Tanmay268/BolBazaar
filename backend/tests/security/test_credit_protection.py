"""The ten credit-drain scenarios from the audit brief. Every provider is a counting mock: the assertions are about how
many billed calls *would* have been made."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import text

from bolbazaar.config import Settings
from bolbazaar.costguard import CostGuard
from bolbazaar.errors import ApiError
from bolbazaar.models import Base
from bolbazaar.providers.azure import AzureReasoner
from bolbazaar.providers.base import ProviderError
from bolbazaar.providers.gnani import GnaniClient, GnaniSTT
from bolbazaar.domain.languages import get_profile

from .support import FROZEN_NOW, VISIT_TEXT, provider_error, secure_settings, tone_wav


def codes(responses) -> list[str]:
    return [((r.json() or {}).get("error") or {}).get("code", "OK") for r in responses]


# --------------------------------------------------------------------------- Test 1: request spam

def test_01_request_spam_cannot_cause_uncontrolled_provider_calls(sec):
    responses = [sec.text_capture("asha", f"spam-key-{i:04d}", text=f"{VISIT_TEXT} number {i}") for i in range(100)]
    ok = [r for r in responses if r.status_code == 202]
    limited = [r for r in responses if r.status_code == 429]
    assert len(ok) + len(limited) == 100
    assert sec.counter.calls["llm"] == len(ok) <= sec.settings.user_llm_per_minute
    assert limited and all(r.headers.get("Retry-After") for r in limited)
    assert set(codes(limited)) == {"QUOTA_EXCEEDED"}


# --------------------------------------------------------------------------- Test 2: concurrent quota bypass

def test_02_concurrent_requests_cannot_exceed_a_quota_of_five(tmp_path):
    settings = secure_settings(tmp_path, user_llm_per_minute=5)
    from bolbazaar.db import make_engine, make_session_factory
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    guard = CostGuard(make_session_factory(engine), settings, clock=lambda: FROZEN_NOW)
    barrier, results = threading.Barrier(50), []

    def attempt(_):
        barrier.wait()  # release all 50 at the same instant
        try:
            guard.reserve("user_x", "llm", est_tokens=100)
            return "reserved"
        except ApiError as error:
            return error.code

    with ThreadPoolExecutor(50) as pool:
        results = list(pool.map(attempt, range(50)))
    assert results.count("reserved") == 5, results
    assert set(results) - {"reserved"} <= {"QUOTA_EXCEEDED", "QUOTA_UNAVAILABLE"}  # unavailable = fail closed, never allowed


def test_02b_concurrent_http_requests_respect_quota(make_sec):
    sec = make_sec(user_llm_per_minute=5, user_max_concurrent_ai=50, rl_user_per_minute=1000, rl_ip_per_minute=1000)
    sec.token("asha")
    barrier = threading.Barrier(50)

    def fire(i):
        barrier.wait()
        return sec.text_capture("asha", f"conc-key-{i:04d}", text=f"{VISIT_TEXT} {i}")

    with ThreadPoolExecutor(50) as pool:
        responses = list(pool.map(fire, range(50)))
    assert sec.counter.calls["llm"] <= 5
    assert sum(r.status_code == 202 for r in responses) == sec.counter.calls["llm"]


def test_02c_per_user_in_flight_limit_rejects_the_burst_without_reserving(make_sec):
    sec = make_sec(user_max_concurrent_ai=2, rl_user_per_minute=1000, rl_ip_per_minute=1000)
    sec.token("asha")
    sec.counter.delay["llm"] = 0.4
    barrier = threading.Barrier(20)

    def fire(i):
        barrier.wait()
        return sec.text_capture("asha", f"inflight-{i:04d}", text=f"{VISIT_TEXT} {i}")

    with ThreadPoolExecutor(20) as pool:
        responses = list(pool.map(fire, range(20)))
    assert "CONCURRENCY_LIMIT" in codes(responses)
    assert sec.counter.max_inflight["llm"] <= 2  # never more than two paid calls running at once for one user
    assert sec.counter.calls["llm"] < 20          # and most of the burst never reached the provider


# --------------------------------------------------------------------------- Test 3: multiple-account abuse

def _register(sec, i, ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return sec.client.post("/v1/auth/register", headers=headers,
                           json={"username": f"farm{i:03d}", "name": f"Farmer {i}", "password": "password123"})


def test_03a_one_ip_cannot_farm_accounts(sec):
    results = [_register(sec, i) for i in range(10)]
    assert [r.status_code for r in results[:5]] == [201] * 5
    assert all(r.status_code == 429 and r.headers.get("Retry-After") for r in results[5:])


def test_03b_global_signup_ceiling_holds_when_every_request_has_a_new_ip(make_sec):
    sec = make_sec(signup_global_per_day=4, trusted_proxy_count=1)
    results = [_register(sec, i, ip=f"198.51.100.{i + 1}") for i in range(8)]
    assert [r.status_code for r in results] == [201] * 4 + [503] * 4
    assert results[-1].json()["error"]["code"] == "SIGNUP_LIMIT"


def test_03c_many_accounts_share_one_global_provider_ceiling(make_sec):
    sec = make_sec(global_azure_requests_per_day=10, trusted_proxy_count=1, user_llm_per_minute=100)
    users = []
    for i in range(6):
        r = _register(sec, i, ip=f"203.0.113.{i + 1}")
        assert r.status_code == 201
        users.append((f"farm{i:03d}", r.json()["token"]))
    for round_ in range(4):
        for name, token in users:
            sec.client.post("/v1/captures", data={"transcript": f"{VISIT_TEXT} {name} {round_}", "language": "hinglish"},
                            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"farm-{name}-{round_}-key"})
    assert sec.counter.calls["llm"] == 10  # 24 attempted, the global ceiling stopped the rest


def test_03d_rep_invite_code_closes_signup_to_strangers(make_sec):
    sec = make_sec(rep_signup_code="s3cret-invite")
    body = {"username": "stranger", "name": "Stranger", "password": "password123"}
    assert sec.client.post("/v1/auth/register", json=body).status_code == 403
    assert sec.client.post("/v1/auth/register", json={**body, "signupCode": "s3cret-invite"}).status_code == 201


# --------------------------------------------------------------------------- Test 4: duplicates

def test_04_identical_request_with_same_idempotency_key_runs_the_provider_once(sec):
    first = sec.text_capture("asha", "dup-key-0001")
    assert first.status_code == 202
    again = [sec.text_capture("asha", "dup-key-0001") for _ in range(10)]
    assert all(r.status_code == 202 and r.json()["id"] == first.json()["id"] for r in again)
    assert sec.counter.calls["llm"] == 1


def test_04b_simultaneous_duplicates_run_the_provider_once(make_sec):
    sec = make_sec(user_max_concurrent_ai=50, rl_user_per_minute=1000, rl_ip_per_minute=1000)
    sec.token("asha")
    sec.counter.delay["llm"] = 0.2
    barrier = threading.Barrier(15)

    def fire(_):
        barrier.wait()
        return sec.text_capture("asha", "dup-key-race-1")

    with ThreadPoolExecutor(15) as pool:
        responses = list(pool.map(fire, range(15)))
    assert all(r.status_code in (202, 409, 503) for r in responses), codes(responses)
    assert sec.counter.calls["llm"] == 1


def test_04c_concurrent_retry_of_a_failed_capture_pays_once(make_sec):
    sec = make_sec(user_max_concurrent_ai=50, rl_user_per_minute=1000, rl_ip_per_minute=1000)
    sec.token("asha")
    sec.counter.fail["llm"] = provider_error("http", retryable=True)
    cap = sec.text_capture("asha", "retry-race-key").json()
    cap_id = ((cap.get("error") or {}).get("details") or {}).get("captureId") or cap.get("id")
    sec.counter.fail["llm"], sec.counter.delay["llm"] = None, 0.3
    before = sec.counter.calls["llm"]
    barrier = threading.Barrier(10)

    def fire(_):
        barrier.wait()
        return sec.client.post(f"/v1/captures/{cap_id}/retry", headers=sec.hdr("asha"))

    with ThreadPoolExecutor(10) as pool:
        list(pool.map(fire, range(10)))
    assert sec.counter.calls["llm"] - before == 1


# --------------------------------------------------------------------------- Test 5: global ceiling + circuit breaker

def test_05a_global_budget_ceiling_stops_further_calls(make_sec):
    sec = make_sec(global_azure_requests_per_day=3, user_llm_per_minute=100)
    results = [sec.text_capture("asha", f"budget-key-{i:04d}", text=f"{VISIT_TEXT} {i}") for i in range(8)]
    assert sec.counter.calls["llm"] == 3
    assert codes(results)[3:] == ["PROVIDER_BUDGET_EXCEEDED"] * 5
    assert all(r.status_code == 503 and r.headers.get("Retry-After") for r in results[3:])


def test_05b_circuit_breaker_opens_after_repeated_failures_and_stops_calling(make_sec):
    sec = make_sec(breaker_failure_threshold=3, user_llm_per_minute=100, user_llm_per_hour=100, user_llm_per_day=100)
    sec.counter.fail["llm"] = provider_error("http", retryable=True)
    results = [sec.text_capture("asha", f"breaker-key-{i:04d}", text=f"{VISIT_TEXT} {i}") for i in range(10)]
    assert sec.counter.calls["llm"] == 3  # the breaker opened on the third consecutive failure
    assert codes(results)[3:] == ["PROVIDER_UNAVAILABLE"] * 7


def test_05c_fatal_credit_error_opens_the_breaker_immediately(make_sec):
    sec = make_sec(user_llm_per_minute=100)
    sec.counter.fail["llm"] = provider_error("credits")
    for i in range(6):
        sec.text_capture("asha", f"credit-key-{i:04d}", text=f"{VISIT_TEXT} {i}")
    assert sec.counter.calls["llm"] == 1


def test_05d_breaker_recovers_through_a_single_trial_call(make_sec):
    clock = [FROZEN_NOW]
    sec = make_sec(breaker_failure_threshold=1, breaker_cooldown_seconds=60, user_llm_per_minute=100)
    sec.guard.clock = lambda: clock[0]
    sec.counter.fail["llm"] = provider_error("http", retryable=True)
    sec.text_capture("asha", "recover-key-0001")
    assert sec.text_capture("asha", "recover-key-0002", text="x " + VISIT_TEXT).status_code == 503
    assert sec.counter.calls["llm"] == 1
    clock[0] += 61
    sec.counter.fail["llm"] = None
    assert sec.text_capture("asha", "recover-key-0003", text="y " + VISIT_TEXT).status_code == 202


# --------------------------------------------------------------------------- Test 6: provider timeout / retry loops

def _settings(**kw) -> Settings:
    return Settings(_env_file=None, gnani_api_key="k" * 10, azure_openai_endpoint="https://x.invalid",
                    azure_openai_api_key="k" * 10, azure_openai_deployment="d", **kw)


def test_06a_gnani_timeouts_are_retried_a_bounded_number_of_times():
    calls, sleeps = [], []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectTimeout("simulated timeout")

    client = GnaniClient(_settings(gnani_max_retries=50), transport=httpx.MockTransport(handler), sleep=sleeps.append)
    with pytest.raises(ProviderError) as caught:
        GnaniSTT(client).transcribe(b"x", get_profile("en-IN"))
    assert caught.value.category == "network"
    assert len(calls) == 4 and len(sleeps) == 3  # hard cap of three retries even if configured for fifty


def test_06b_azure_timeouts_are_bounded_and_budget_counts_every_attempt():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("simulated timeout")

    reasoner = AzureReasoner(_settings(azure_openai_max_retries=99, azure_daily_call_budget=100),
                             transport=httpx.MockTransport(handler), sleep=lambda s: None)
    with pytest.raises(ProviderError):
        reasoner.parse_manager_query("which retailers are overdue")
    assert len(calls) == 4

    tight = AzureReasoner(_settings(azure_openai_max_retries=3, azure_daily_call_budget=2),
                          transport=httpx.MockTransport(handler), sleep=lambda s: None)
    calls.clear()
    with pytest.raises(ProviderError) as caught:
        tight.parse_manager_query("which retailers are overdue")
    assert caught.value.category == "budget" and len(calls) == 2


def test_06c_a_failing_capture_cannot_be_retried_forever(make_sec):
    sec = make_sec(max_process_attempts_per_capture=3, breaker_failure_threshold=1000, user_llm_per_minute=100)
    sec.counter.fail["llm"] = provider_error("network", retryable=True)
    first = sec.text_capture("asha", "loop-key-0001")
    cap_id = first.json()["error"]["details"]["captureId"]
    statuses = [sec.client.post(f"/v1/captures/{cap_id}/retry", headers=sec.hdr("asha")) for _ in range(8)]
    assert sec.counter.calls["llm"] == 3  # first attempt + two retries, then the capture-level cap
    assert "TOO_MANY_ATTEMPTS" in codes(statuses)


def test_06d_provider_error_responses_never_leak_keys_or_bodies(sec):
    sec.counter.fail["llm"] = ProviderError("http", "Azure OpenAI extract failed with status 500", retryable=True)
    r = sec.text_capture("asha", "leak-key-0001")
    assert r.status_code == 503
    blob = r.text.lower()
    assert "api-key" not in blob and "traceback" not in blob and sec.settings.jwt_secret not in r.text


# --------------------------------------------------------------------------- Test 7: oversized / abusive audio

def test_07_bad_audio_is_rejected_before_any_paid_call(make_sec):
    sec = make_sec(max_audio_bytes=200_000, max_audio_seconds=5.0, user_stt_per_minute=100)
    # 1. over the byte limit (declared Content-Length is refused by the middleware before parsing)
    big = sec.audio_capture("asha", "audio-big-0001", audio=b"RIFF" + b"\0" * 1_500_000)
    assert big.status_code == 413
    # 2. within bytes but longer than the duration limit
    long_ = sec.audio_capture("asha", "audio-long-0001", audio=tone_wav(9, rate=8000))
    assert long_.status_code == 400 and long_.json()["error"]["code"] == "UNSUPPORTED_AUDIO"
    # 3. wrong magic bytes with a .wav name, and a script posing as audio
    assert sec.audio_capture("asha", "audio-fake-0001", audio=b"not audio at all" * 50).status_code == 400
    assert sec.audio_capture("asha", "audio-fake-0002", audio=b"#!/bin/sh\nrm -rf /\n", name="a.wav").status_code == 400
    # 4. unsupported MIME and extension
    assert sec.audio_capture("asha", "audio-fake-0003", audio=tone_wav(1), name="a.exe", ctype="application/x-msdownload").status_code == 400
    # 5. empty
    assert sec.audio_capture("asha", "audio-empty-0001", audio=b"").status_code == 400
    assert sec.counter.total == 0


def test_07b_long_text_is_rejected_before_any_paid_call(sec):
    assert sec.text_capture("asha", "long-text-0001", text="a" * (sec.settings.max_transcript_chars + 1)).status_code == 413
    cap = sec.text_capture("asha", "long-text-0002").json()
    before = sec.counter.total
    r = sec.client.post(f"/v1/captures/{cap['id']}/corrections", headers=sec.hdr("asha"),
                        json={"revision": cap["revision"], "text": "x" * 501})
    assert r.status_code == 422 and sec.counter.total == before
    r = sec.client.post("/v1/manager/ask", headers=sec.hdr("meera"), json={"text": "q" * 401})
    assert r.status_code == 422


def test_07c_oversized_json_body_is_refused_by_the_middleware(sec):
    r = sec.client.post("/v1/auth/login", content=b'{"username":"a","password":"' + b"x" * 400_000 + b'"}',
                        headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "REQUEST_TOO_LARGE"


# --------------------------------------------------------------------------- Test 8: disabled providers

def test_08a_gnani_disabled_blocks_speech_but_not_text(make_sec):
    sec = make_sec(gnani_enabled=False)
    assert sec.audio_capture("asha", "gnani-off-0001").status_code == 503
    assert sec.counter.calls["stt"] == 0
    assert sec.text_capture("asha", "gnani-off-0002").status_code == 202  # normal functionality is preserved
    assert sec.counter.calls["llm"] == 1 and sec.counter.calls["stt"] == 0


def test_08b_azure_disabled_blocks_reasoning(make_sec):
    sec = make_sec(azure_enabled=False)
    r = sec.text_capture("asha", "azure-off-0001")
    assert r.status_code == 503 and r.json()["error"]["code"] == "PROVIDER_DISABLED"
    assert sec.client.post("/v1/manager/ask", headers=sec.hdr("meera"), json={"text": "overdue payments"}).status_code == 503
    assert sec.counter.calls["llm"] == 0
    assert sec.client.get("/v1/customers", headers=sec.hdr("asha")).status_code == 200  # the rest of the app still works


def test_08c_master_switch_disables_everything_paid(make_sec):
    sec = make_sec(ai_services_enabled=False)
    assert sec.audio_capture("asha", "all-off-0001").status_code == 503
    assert sec.text_capture("asha", "all-off-0002").status_code == 503
    assert sec.counter.total == 0


def test_08d_runtime_switch_needs_no_restart_and_is_admin_only(sec):
    assert sec.text_capture("asha", "live-sw-0001").status_code == 202
    assert sec.client.put("/v1/admin/providers/azure", headers=sec.hdr("asha"), json={"enabled": False}).status_code == 403
    assert sec.client.put("/v1/admin/providers/azure", headers=sec.hdr("meera"), json={"enabled": False}).status_code == 403
    off = sec.client.put("/v1/admin/providers/azure", headers=sec.hdr("admin"), json={"enabled": False, "reason": "drill"})
    assert off.status_code == 200
    calls = sec.counter.total
    r = sec.text_capture("asha", "live-sw-0002", text="z " + VISIT_TEXT)
    assert r.status_code == 503 and sec.counter.total == calls
    usage = sec.client.get("/v1/admin/usage", headers=sec.hdr("admin")).json()
    assert usage["switches"]["azure"]["enabled"] is False
    sec.client.put("/v1/admin/providers/azure", headers=sec.hdr("admin"), json={"enabled": True})
    sec.guard._switch_cache.clear()
    assert sec.text_capture("asha", "live-sw-0003", text="w " + VISIT_TEXT).status_code == 202


# --------------------------------------------------------------------------- Test 9: missing authentication

@pytest.mark.parametrize("method,path", [
    ("POST", "/v1/captures"), ("POST", "/v1/captures/cap_x/corrections/audio"), ("POST", "/v1/captures/cap_x/corrections"),
    ("POST", "/v1/captures/cap_x/confirm"), ("GET", "/v1/captures/cap_x/question-audio"),
    ("GET", "/v1/captures/cap_x/reply-audio"), ("POST", "/v1/manager/ask"), ("PUT", "/v1/admin/providers/gnani"),
    ("GET", "/v1/admin/usage"),
])
def test_09_expensive_endpoints_reject_anonymous_calls_before_any_provider_work(sec, method, path):
    r = sec.client.request(method, path, data={"transcript": VISIT_TEXT}, headers={"Idempotency-Key": "anon-key-0001"})
    assert r.status_code in (401, 422) and r.status_code != 202
    if r.status_code == 422:  # body validation may run first, but never anything billable
        pass
    assert sec.counter.total == 0


# --------------------------------------------------------------------------- Test 10: ledger failure fails closed

def test_10a_quota_store_failure_fails_closed(sec):
    ctx = sec.app.state.ctx
    sec.token("asha")
    with ctx.sf.kw["bind"].begin() as conn:
        conn.execute(text("DROP TABLE usage_counters"))
    results = [sec.text_capture("asha", f"fail-closed-{i:03d}", text=f"{VISIT_TEXT} {i}") for i in range(5)]
    assert sec.counter.total == 0
    assert set(codes(results)) == {"QUOTA_UNAVAILABLE"} and all(r.status_code == 503 for r in results)


def test_10b_switch_store_failure_fails_closed(sec):
    sec.token("asha")
    with sec.app.state.ctx.sf.kw["bind"].begin() as conn:
        conn.execute(text("DROP TABLE provider_switches"))
    sec.guard._switch_cache.clear()
    r = sec.text_capture("asha", "fail-closed-sw-1")
    assert r.status_code == 503 and sec.counter.total == 0


def test_10c_unsupported_database_dialect_refuses_instead_of_allowing(sec, monkeypatch):
    monkeypatch.setattr(CostGuard, "_upsert", staticmethod(lambda s: (_ for _ in ()).throw(RuntimeError("no upsert"))))
    r = sec.text_capture("asha", "fail-closed-dia-1")
    assert r.status_code == 503 and sec.counter.total == 0
