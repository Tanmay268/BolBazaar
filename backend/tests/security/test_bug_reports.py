"""Report-a-bug: works for every role, is private to the reporter, is triaged by admins, and cannot be abused."""

from __future__ import annotations

import pytest

REPORT = {"category": "broken", "title": "Confirm button does nothing", "description": "I tapped Confirm twice and nothing happened.",
          "context": {"page": "Log a visit", "appVersion": "0.1.0", "platform": "Android", "language": "hinglish",
                      "lastError": {"code": "PROVIDER_ERROR", "requestId": "abc123", "status": 503, "path": "/v1/captures/cap_1/retry?x=token"}}}


def send(sec, user="asha", body=None, **kw):
    return sec.client.post("/v1/bug-reports", json=body or REPORT, headers=sec.hdr(user), **kw)


def test_every_role_can_report_and_sees_only_their_own(sec):
    ids = {}
    for user in ("asha", "ravi", "meera", "admin"):
        r = send(sec, user)
        assert r.status_code == 201, (user, r.text)
        ids[user] = r.json()["id"]
        assert r.json()["status"] == "open"
    mine = sec.client.get("/v1/bug-reports/mine", headers=sec.hdr("asha")).json()["reports"]
    assert [x["id"] for x in mine] == [ids["asha"]]          # never someone else's report
    assert sec.client.get("/v1/bug-reports/mine").status_code == 401


def test_context_is_whitelisted_and_scrubbed(sec):
    r = send(sec, body={**REPORT, "context": {**REPORT["context"], "page": "x" * 60}})
    assert r.status_code == 201
    ctx = r.json()["context"]
    assert ctx["lastError"]["path"] == "/v1/captures/cap_1/retry"      # query string (could carry a token) is dropped
    assert set(ctx) <= {"page", "appVersion", "platform", "language", "lastError"}
    assert sec.client.post("/v1/bug-reports", headers=sec.hdr("asha"),
                           json={**REPORT, "context": {"token": "secret-jwt", "page": "x"}}).status_code == 422   # unknown keys refused


@pytest.mark.parametrize("patch", [
    {"category": "hacking"}, {"title": "ab"}, {"title": "t" * 121}, {"description": "short"}, {"description": "d" * 2001},
    {"status": "resolved"}, {"userId": "usr_admin"}, {"role": "admin"},
])
def test_report_input_is_validated_and_mass_assignment_refused(sec, patch):
    assert send(sec, body={**REPORT, **patch}).status_code == 422


def test_markup_in_a_report_is_stored_as_inert_text(sec):
    r = send(sec, body={**REPORT, "title": "<img src=x onerror=alert(1)>", "description": "<script>alert(1)</script> broken page"})
    assert r.status_code == 201 and r.headers["content-type"].startswith("application/json")
    assert r.headers["x-content-type-options"] == "nosniff" and r.json()["title"] == "<img src=x onerror=alert(1)>"


def test_reports_are_rate_limited_per_user_and_globally(make_sec):
    sec = make_sec(user_bug_reports_per_day=3)
    assert [send(sec).status_code for _ in range(5)] == [201, 201, 201, 429, 429]
    assert send(sec, user="ravi").status_code == 201                    # another user is not affected


def test_global_daily_cap_on_reports(make_sec):
    glob = make_sec(global_bug_reports_per_day=2)
    assert [send(glob, user=u).status_code for u in ("asha", "ravi", "meera")] == [201, 201, 503]


def test_only_admins_triage(sec):
    bug = send(sec, "asha").json()["id"]
    for user in ("asha", "meera"):
        assert sec.client.get("/v1/admin/bug-reports", headers=sec.hdr(user)).status_code == 403
        assert sec.client.patch(f"/v1/admin/bug-reports/{bug}", json={"status": "resolved"}, headers=sec.hdr(user)).status_code == 403
    assert sec.client.get("/v1/admin/bug-reports").status_code == 401
    rows = sec.client.get("/v1/admin/bug-reports", headers=sec.hdr("admin")).json()["reports"]
    assert rows[0]["id"] == bug and rows[0]["reporter"] == "Asha Verma" and rows[0]["role"] == "rep"
    done = sec.client.patch(f"/v1/admin/bug-reports/{bug}", json={"status": "resolved", "note": "fixed in 0.1.1"}, headers=sec.hdr("admin"))
    assert done.status_code == 200 and done.json()["status"] == "resolved" and done.json()["adminNote"] == "fixed in 0.1.1"
    assert sec.client.get("/v1/admin/bug-reports?status=open", headers=sec.hdr("admin")).json()["reports"] == []
    assert sec.client.get("/v1/bug-reports/mine", headers=sec.hdr("asha")).json()["reports"][0]["status"] == "resolved"
    assert sec.client.patch("/v1/admin/bug-reports/bug_nope", json={"status": "open"}, headers=sec.hdr("admin")).status_code == 404
    assert sec.client.patch(f"/v1/admin/bug-reports/{bug}", json={"status": "deleted"}, headers=sec.hdr("admin")).status_code == 422
