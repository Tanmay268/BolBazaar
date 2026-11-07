NEW = {"username": "Kiran.Rao", "name": "Kiran Rao", "password": "s3cret-pass", "role": "rep", "territoryId": "ter_pune"}


def test_register_rep_signs_in_and_sees_own_territory(api):
    r = api.client.post("/v1/auth/register", json=NEW)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "rep" and body["user"]["territoryId"] == "ter_pune"
    headers = {"Authorization": f"Bearer {body['token']}"}
    assert api.client.get("/v1/me", headers=headers).json()["name"] == "Kiran Rao"
    names = {c["name"] for c in api.client.get("/v1/customers", headers=headers).json()["customers"]}
    assert names == {"Patil Kirana", "Deshmukh Stores"}
    again = api.client.post("/v1/auth/login", json={"username": "kiran.rao", "password": NEW["password"]})
    assert again.status_code == 200


def test_register_password_is_hashed(api):
    api.client.post("/v1/auth/register", json=NEW)
    from bolbazaar.models import User
    with api.app.state.ctx.sf() as s:
        user = s.query(User).filter_by(username="kiran.rao").one()
    assert user.password_hash.startswith("pbkdf2$") and NEW["password"] not in user.password_hash


def test_register_rejects_duplicates_and_bad_input(api):
    assert api.client.post("/v1/auth/register", json=NEW).status_code == 201
    dup = api.client.post("/v1/auth/register", json={**NEW, "username": "KIRAN.RAO"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "USERNAME_TAKEN"
    assert api.client.post("/v1/auth/register", json={**NEW, "username": "asha"}).status_code == 409
    assert api.client.post("/v1/auth/register", json={**NEW, "username": "x y"}).json()["error"]["code"] == "INVALID_USERNAME"
    assert api.client.post("/v1/auth/register", json={**NEW, "username": "kiran2", "password": "short"}).json()["error"]["code"] == "WEAK_PASSWORD"
    bad_ter = api.client.post("/v1/auth/register", json={**NEW, "username": "kiran3", "territoryId": "ter_nowhere"})
    assert bad_ter.json()["error"]["code"] == "INVALID_TERRITORY"
    assert api.client.post("/v1/auth/register", json={**NEW, "username": "kiran4", "role": "admin"}).status_code == 422


def test_manager_signup_needs_the_code(make_api):
    api = make_api(manager_signup_code="open-sesame")
    mgr = {**NEW, "username": "boss01", "role": "manager"}
    assert api.client.post("/v1/auth/register", json=mgr).json()["error"]["code"] == "BAD_SIGNUP_CODE"
    ok = api.client.post("/v1/auth/register", json={**mgr, "signupCode": "open-sesame"})
    assert ok.status_code == 201
    headers = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert api.client.get("/v1/manager/summary", headers=headers).status_code == 200


def test_manager_signup_closed_without_configured_code(api):
    r = api.client.post("/v1/auth/register", json={**NEW, "role": "manager", "signupCode": ""})
    assert r.status_code == 403 and r.json()["error"]["code"] == "MANAGER_SIGNUP_CLOSED"


def test_signup_can_be_disabled(make_api):
    api = make_api(allow_signup=False)
    assert api.client.post("/v1/auth/register", json=NEW).json()["error"]["code"] == "SIGNUP_DISABLED"
    assert api.client.get("/v1/auth/territories").json()["signupOpen"] is False


def test_territories_listing_is_public(api):
    data = api.client.get("/v1/auth/territories").json()
    assert {t["id"] for t in data["territories"]} == {"ter_delhi", "ter_chennai", "ter_pune"}


def test_first_signup_creates_org_when_database_is_empty(make_api):
    api = make_api(seed_demo_data=False)
    r = api.client.post("/v1/auth/register", json={**NEW, "territoryId": None})
    assert r.status_code == 201 and r.json()["user"]["organization"] == "BolBazaar Distributors"


def test_database_url_is_normalised_for_psycopg():
    from bolbazaar.config import Settings
    for raw in ("postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d"):
        assert Settings(database_url=raw, _env_file=None).database_url == "postgresql+psycopg://u:p@h:5432/d"
