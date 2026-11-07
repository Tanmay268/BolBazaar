from bolbazaar.models import User
from bolbazaar.seed import ensure_demo_accounts, seed_demo


def test_recruiter_can_view_admin_screens_but_not_change_anything(api):
    h = api.auth("recruiter")
    assert api.client.get("/v1/admin/usage", headers=h).status_code == 200
    r = api.client.put("/v1/admin/providers/all", headers=h, json={"enabled": False, "reason": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "READ_ONLY_DEMO"
    # the view-only rule also covers every other write, e.g. a bug report
    r = api.client.post("/v1/bug-reports", headers=h, json={"category": "other", "title": "t" * 5, "description": "d" * 20})
    assert r.status_code == 403


def test_real_admin_can_still_use_kill_switch(api):
    h = api.auth("admin")
    assert api.client.put("/v1/admin/providers/gnani", headers=h, json={"enabled": True, "reason": "ok"}).status_code == 200


def test_admin_password_is_private_when_configured(make_api):
    api = make_api(admin_password="Str0ng-private-admin-pass")
    ok = api.client.post("/v1/auth/login", json={"username": "admin", "password": "Str0ng-private-admin-pass"})
    bad = api.client.post("/v1/auth/login", json={"username": "admin", "password": "demo123"})
    pub = api.client.post("/v1/auth/login", json={"username": "recruiter", "password": "demo123"})
    assert ok.status_code == 200 and bad.status_code == 401 and pub.status_code == 200


def test_existing_database_gets_recruiter_and_private_admin_password(api):
    sf = api.app.state.ctx.sf
    with sf.begin() as s:
        s.delete(s.get(User, "usr_recruiter"))
    ensure_demo_accounts(sf, "demo123", "Another-private-pass-1")
    login = lambda u, p: api.client.post("/v1/auth/login", json={"username": u, "password": p}).status_code
    assert login("recruiter", "demo123") == 200
    assert login("admin", "Another-private-pass-1") == 200 and login("admin", "demo123") == 401
