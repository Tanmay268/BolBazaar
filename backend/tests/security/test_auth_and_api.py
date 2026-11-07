"""Authentication, authorization, input handling, headers, CORS and request-level limits."""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from sqlalchemy import update

from bolbazaar.config import Settings
from bolbazaar.main import create_app
from bolbazaar.models import User
from bolbazaar.storage import AudioStore

from .support import VISIT_TEXT, secure_settings

SECRET = "test-secret-with-at-least-32-bytes-of-length"


def b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def forge(claims_extra=None, secret=SECRET, alg="HS256", **over) -> str:
    now = int(time.time())
    claims = {"sub": "usr_asha", "org": "org_demo", "role": "rep", "ter": "ter_delhi", "name": "x", "iat": now, "exp": now + 600}
    claims.update(claims_extra or {})
    claims.update(over)
    return jwt.encode(claims, secret, algorithm=alg)


# --------------------------------------------------------------------------- unauthenticated access

def test_every_v1_route_requires_authentication_except_the_public_ones(sec):
    import re
    public = {("post", "/v1/auth/login"), ("post", "/v1/auth/register"), ("get", "/v1/auth/territories"), ("get", "/health")}
    checked = 0
    for path, item in sec.app.openapi()["paths"].items():  # the schema lists every route, including forgotten ones
        for method in item:
            if (method, path) in public:
                continue
            url = re.sub(r"\{[^}]+\}", "gnani", path)
            r = sec.client.request(method.upper(), url)
            assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
            checked += 1
    assert checked >= 25
    assert [p for p in sec.app.openapi()["paths"] if not p.startswith("/v1")] == ["/health"]  # no stray dev/test routes


# --------------------------------------------------------------------------- JWT

@pytest.mark.parametrize("token_factory", [
    lambda: forge(secret="a-completely-different-secret-of-32-chars!!"),     # wrong key
    lambda: forge(exp=int(time.time()) - 10),                                 # expired
    lambda: forge(secret="dev-only-secret-change-me"),                        # the old public development secret
    lambda: b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": "usr_admin", "org": "org_demo", "role": "admin",
                                                            "iat": 1, "exp": 9999999999}) + ".",   # alg=none
    lambda: "not.a.jwt",
    lambda: "",
])
def test_forged_or_invalid_tokens_are_rejected(sec, token_factory):
    r = sec.client.get("/v1/me", headers={"Authorization": f"Bearer {token_factory()}"})
    assert r.status_code == 401


def test_tampered_payload_is_rejected(sec):
    header, payload, sig = sec.token("asha").split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "admin"
    evil = f"{header}.{b64(claims)}.{sig}"
    assert sec.client.get("/v1/admin/usage", headers={"Authorization": f"Bearer {evil}"}).status_code == 401


def test_token_missing_required_claims_is_rejected(sec):
    no_exp = jwt.encode({"sub": "usr_asha", "org": "org_demo", "role": "rep", "iat": 1}, SECRET, algorithm="HS256")
    assert sec.client.get("/v1/me", headers={"Authorization": f"Bearer {no_exp}"}).status_code == 401


def test_role_in_token_is_not_trusted_the_database_is(sec):
    # A validly signed token that claims admin for a rep: only possible with the secret, but it must still not escalate.
    token = forge(role="admin")
    r = sec.client.get("/v1/admin/usage", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_deactivated_user_loses_access_immediately(sec):
    headers = sec.hdr("asha")
    assert sec.client.get("/v1/me", headers=headers).status_code == 200
    with sec.app.state.ctx.sf.begin() as s:
        s.execute(update(User).where(User.id == "usr_asha").values(active=False))
    assert sec.client.get("/v1/me", headers=headers).status_code == 401


def test_demoted_user_loses_privileges_immediately(sec):
    headers = sec.hdr("meera")
    assert sec.client.get("/v1/manager/summary", headers=headers).status_code == 200
    with sec.app.state.ctx.sf.begin() as s:
        s.execute(update(User).where(User.id == "usr_meera").values(role="rep"))
    assert sec.client.get("/v1/manager/summary", headers=headers).status_code == 403


def test_jwt_secret_policy():
    assert Settings(_env_file=None, jwt_secret="", app_env="development").jwt_key != "dev-only-secret-change-me"
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, jwt_secret="", app_env="production").jwt_key
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, jwt_secret="short", app_env="production").jwt_key
    assert len(Settings(_env_file=None, jwt_secret="x" * 40, app_env="production").jwt_key) == 40


def test_dev_server_without_secret_uses_a_secret_nobody_knows(tmp_path):
    app = create_app(secure_settings(tmp_path, jwt_secret=""))
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        token = c.post("/v1/auth/login", json={"username": "asha", "password": "demo123"}).json()["token"]
        assert c.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        old = forge(secret="dev-only-secret-change-me", role="admin", sub="usr_admin")
        assert c.get("/v1/admin/usage", headers={"Authorization": f"Bearer {old}"}).status_code == 401


# --------------------------------------------------------------------------- authorization

def test_rep_cannot_reach_manager_or_admin_endpoints(sec):
    h = sec.hdr("asha")
    for method, path in [("GET", "/v1/manager/summary"), ("GET", "/v1/manager/overdue-payments"),
                         ("POST", "/v1/manager/ask"), ("GET", "/v1/admin/usage"), ("PUT", "/v1/admin/providers/all")]:
        r = sec.client.request(method, path, headers=h, json={"text": "overdue", "enabled": False})
        assert r.status_code == 403, (path, r.status_code)


def test_manager_cannot_use_admin_endpoints_and_manager_cannot_create_captures(sec):
    assert sec.client.get("/v1/admin/usage", headers=sec.hdr("meera")).status_code == 403
    r = sec.client.post("/v1/captures", data={"transcript": VISIT_TEXT}, headers=sec.hdr("meera", **{"Idempotency-Key": "mgr-key-0001"}))
    assert r.status_code == 403 and sec.counter.total == 0


def test_idor_one_rep_cannot_read_or_change_anothers_capture(sec):
    cap = sec.text_capture("asha", "idor-key-0001").json()
    ravi = sec.hdr("ravi")
    for method, path in [("GET", f"/v1/captures/{cap['id']}"), ("GET", f"/v1/captures/{cap['id']}/reply-audio")]:
        assert sec.client.request(method, path, headers=ravi).status_code == 404
    for path, body in [(f"/v1/captures/{cap['id']}/corrections", {"revision": cap["revision"], "text": "twenty"}),
                       (f"/v1/captures/{cap['id']}/cancel", None), (f"/v1/captures/{cap['id']}/retry", None),
                       (f"/v1/captures/{cap['id']}/confirm", {"revision": cap["revision"]})]:
        r = sec.client.post(path, headers={**ravi, "Idempotency-Key": "idor-key-0002"}, json=body)
        assert r.status_code in (403, 404), (path, r.status_code)
    assert sec.client.get(f"/v1/captures/{cap['id']}", headers=sec.hdr("asha")).status_code == 200
    assert cap["id"] not in [c["id"] for c in sec.client.get("/v1/captures", headers=ravi).json()["captures"]]


def test_reps_cannot_read_other_territories_records(sec):
    asha = sec.client.get("/v1/customers", headers=sec.hdr("asha")).json()["customers"]
    ravi = sec.client.get("/v1/customers", headers=sec.hdr("ravi")).json()["customers"]
    assert asha and ravi and not ({c["id"] for c in asha} & {c["id"] for c in ravi})
    visits = sec.client.get("/v1/visits", headers=sec.hdr("ravi")).json()["visits"]
    if visits:
        assert sec.client.get(f"/v1/visits/{visits[0]['id']}", headers=sec.hdr("asha")).status_code == 404


def test_mass_assignment_is_rejected(sec):
    base = {"username": "mallory1", "name": "Mallory", "password": "password123"}
    for extra in ({"role": "admin"}, {"isAdmin": True}, {"org_id": "org_other"}, {"active": True}, {"id": "usr_admin"}):
        r = sec.client.post("/v1/auth/register", json={**base, **extra, "username": "m" + str(abs(hash(str(extra))) % 10**6)})
        assert r.status_code == 422, extra
    cap = sec.text_capture("asha", "mass-key-0001").json()
    r = sec.client.post(f"/v1/captures/{cap['id']}/corrections", headers=sec.hdr("asha"),
                        json={"revision": cap["revision"], "text": "ok", "repId": "usr_ravi"})
    assert r.status_code == 422
    r = sec.client.patch("/v1/commitments/cmt_x", headers=sec.hdr("asha"), json={"status": "done", "ownerRepId": "x"})
    assert r.status_code == 422


def test_sign_up_cannot_mint_an_admin_or_manager_without_the_code(sec):
    r = sec.client.post("/v1/auth/register", json={"username": "wannabe", "name": "Wannabe", "password": "password123",
                                                   "role": "manager", "signupCode": "guess"})
    assert r.status_code == 403
    assert sec.client.post("/v1/auth/register", json={"username": "wannabe2", "name": "Wannabe", "password": "password123",
                                                      "role": "admin"}).status_code == 422


# --------------------------------------------------------------------------- brute force / enumeration

def test_login_brute_force_is_throttled_per_account(sec):
    results = [sec.client.post("/v1/auth/login", json={"username": "asha", "password": f"guess{i}"}) for i in range(12)]
    assert [r.status_code for r in results[:8]] == [401] * 8
    assert all(r.status_code == 429 and r.headers.get("Retry-After") for r in results[8:])
    # even the right password is refused while cooled down: the attacker cannot confirm a guess
    assert sec.client.post("/v1/auth/login", json={"username": "asha", "password": "demo123"}).status_code == 429
    # other accounts are unaffected
    assert sec.client.post("/v1/auth/login", json={"username": "ravi", "password": "demo123"}).status_code == 200


def test_login_is_throttled_per_ip_across_many_usernames(make_sec):
    sec = make_sec(rl_login_failures_per_ip=10, rl_login_ip_per_minute=1000)
    results = [sec.client.post("/v1/auth/login", json={"username": f"user{i}", "password": "x"}) for i in range(16)]
    assert [r.status_code for r in results[:10]] == [401] * 10
    assert all(r.status_code == 429 for r in results[10:])


def test_login_does_not_reveal_whether_the_account_exists(sec):
    unknown = sec.client.post("/v1/auth/login", json={"username": "nobody-here", "password": "x"})
    wrong = sec.client.post("/v1/auth/login", json={"username": "ravi", "password": "x"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"] == wrong.json()["error"]


def test_unknown_user_costs_about_as_much_as_a_wrong_password(sec):
    def timed(username):
        t = time.perf_counter()
        sec.client.post("/v1/auth/login", json={"username": username, "password": "wrong-password"})
        return time.perf_counter() - t
    timed("ravi"), timed("ghost")  # warm up
    known = sorted(timed("meera") for _ in range(3))[1]
    unknown = sorted(timed(f"ghost{i}") for i in range(3))[1]
    assert unknown > known * 0.5, (known, unknown)  # the old dummy hash (1 iteration) was ~1000x cheaper


# --------------------------------------------------------------------------- request limits

def test_per_ip_rate_limit_returns_429_with_retry_after(make_sec):
    sec = make_sec(rl_ip_per_minute=15)
    results = [sec.client.get("/v1/auth/territories") for _ in range(25)]
    assert [r.status_code for r in results[:15]] == [200] * 15
    assert all(r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 for r in results[15:])
    assert results[-1].json()["error"]["code"] == "RATE_LIMITED"


def test_per_user_rate_limit(make_sec):
    sec = make_sec(rl_user_per_minute=10, rl_ip_per_minute=1000)
    h = sec.hdr("asha")
    results = [sec.client.get("/v1/me", headers=h) for _ in range(15)]
    assert sum(r.status_code == 200 for r in results) == 10 and results[-1].status_code == 429
    assert sec.client.get("/v1/me", headers=sec.hdr("ravi")).status_code == 200  # other users unaffected


def test_forwarded_for_cannot_be_used_to_dodge_ip_limits(make_sec):
    # Default (no trusted proxy): the header is ignored entirely.
    sec = make_sec(rl_ip_per_minute=5)
    results = [sec.client.get("/v1/auth/territories", headers={"X-Forwarded-For": f"10.9.9.{i}"}) for i in range(10)]
    assert sum(r.status_code == 429 for r in results) == 5
    # One trusted proxy: only the entry the proxy appended (rightmost) counts, so a client-chosen prefix is useless.
    sec2 = make_sec(rl_ip_per_minute=5, trusted_proxy_count=1)
    results = [sec2.client.get("/v1/auth/territories", headers={"X-Forwarded-For": f"10.9.9.{i}, 203.0.113.7"}) for i in range(10)]
    assert sum(r.status_code == 429 for r in results) == 5
    other = sec2.client.get("/v1/auth/territories", headers={"X-Forwarded-For": "203.0.113.99"})
    assert other.status_code == 200  # a genuinely different client is not collateral damage


def test_pagination_and_query_caps(sec):
    h = sec.hdr("asha")
    assert sec.client.get("/v1/visits?limit=100000", headers=h).status_code == 422
    assert sec.client.get("/v1/captures?limit=0", headers=h).status_code == 422
    assert sec.client.get("/v1/customers?q=" + "a" * 500, headers=h).status_code == 422
    assert sec.client.get("/v1/manager/inactive-retailers?days=99999", headers=sec.hdr("meera")).status_code == 422


# --------------------------------------------------------------------------- injection / XSS / traversal

@pytest.mark.parametrize("payload", ["' OR '1'='1", "'; DROP TABLE users;--", "%' UNION SELECT password_hash FROM users--",
                                     "\" OR 1=1 --", "%", "_" * 40])
def test_sql_injection_attempts_return_nothing_and_break_nothing(sec, payload):
    h = sec.hdr("asha")
    r = sec.client.get("/v1/customers", params={"q": payload}, headers=h)
    assert r.status_code == 200 and "password" not in r.text.lower()
    assert sec.client.post("/v1/auth/login", json={"username": payload, "password": payload}).status_code in (401, 429)
    assert sec.client.get("/v1/me", headers=h).status_code == 200  # tables still exist


def test_stored_markup_is_returned_as_inert_json_with_nosniff(sec):
    r = sec.text_capture("asha", "xss-key-0001", text="<script>alert(1)</script> " + VISIT_TEXT)
    assert r.status_code == 202
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["x-content-type-options"] == "nosniff"
    got = sec.client.get(f"/v1/captures/{r.json()['id']}", headers=sec.hdr("asha"))
    assert got.headers["content-type"].startswith("application/json")


def test_path_traversal_is_rejected(sec, tmp_path):
    store = AudioStore(tmp_path / "store")
    for key in ("../x", "..\\x", "/etc/passwd", "a/../../x"):
        with pytest.raises(ValueError):
            store.save(key, b"x")
    assert sec.client.get("/v1/captures/..%2F..%2Fetc%2Fpasswd", headers=sec.hdr("asha")).status_code == 404


def test_http_method_tampering(sec):
    h = sec.hdr("asha")
    assert sec.client.delete("/v1/captures", headers=h).status_code == 405
    assert sec.client.put("/v1/me", headers=h).status_code == 405
    assert sec.client.request("TRACE", "/v1/me", headers=h).status_code == 405


# --------------------------------------------------------------------------- headers, CORS, docs, info leaks

def test_security_headers_present(sec):
    r = sec.client.get("/v1/auth/territories")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_hsts_outside_development(make_sec):
    sec = make_sec(app_env="production", jwt_secret=SECRET)
    assert "max-age=" in sec.client.get("/health").headers["strict-transport-security"]


def test_cors_allows_only_configured_origins(sec):
    ok = sec.client.options("/v1/me", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
                                               "Access-Control-Request-Headers": "authorization"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    evil = sec.client.options("/v1/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in evil.headers
    evil_get = sec.client.get("/v1/auth/territories", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil_get.headers
    assert "access-control-allow-credentials" not in ok.headers  # bearer tokens, no ambient cookies


def test_api_docs_and_provider_wiring_are_hidden_in_production(make_sec):
    prod = make_sec(app_env="production", jwt_secret=SECRET)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert prod.client.get(path).status_code == 404
    assert "providers" not in prod.client.get("/health").json()
    dev = make_sec()
    assert dev.client.get("/openapi.json").status_code == 200


def test_errors_do_not_leak_internals(sec):
    r = sec.client.get("/v1/captures/cap_missing", headers=sec.hdr("asha"))
    assert r.status_code == 404 and "Traceback" not in r.text and "sqlalchemy" not in r.text.lower()
    r = sec.client.post("/v1/auth/login", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "Traceback" not in r.text


def test_no_websocket_surface_exists(sec):
    from starlette.websockets import WebSocketDisconnect
    for path in ("/ws", "/v1/ws", "/v1/captures/stream"):
        with pytest.raises(Exception) as caught:
            with sec.client.websocket_connect(path):
                pass
        assert isinstance(caught.value, (WebSocketDisconnect, Exception))


def test_risky_configuration_is_reported():
    risky = Settings(_env_file=None, provider_mode="live", host="0.0.0.0", allow_signup=True, app_env="development")
    text = " ".join(risky.warnings())
    assert "public default password" in text and "sign-up" in text.lower() and "non-loopback" in text
    prod = Settings(_env_file=None, app_env="production", jwt_secret="x" * 40)
    assert any("TRUSTED_PROXY_COUNT" in w for w in prod.warnings())
