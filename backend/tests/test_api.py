from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import offline_providers, tone_wav
from bolbazaar.models import Commitment, Order, Visit
from bolbazaar.providers.base import ProviderError

DEMO = ("Sharma ji ne aaj bees packet Parle-G liye aur das bottle Real juice kal dena hai. "
        "Woh paanch hazaar rupaye kal dega. Biscuit ke kuch packets damaged the, uski complaint hai. "
        "Agle Monday ko dobara visit karna hai.")


def new_capture(api, user="asha", key="cap-key-0001", **form):
    data = {"language": "hinglish", "transcript": DEMO, **form}
    return api.client.post("/v1/captures", data=data, headers={**api.auth(user), "Idempotency-Key": key})


def post(api, path, body, user="asha", key=None):
    headers = api.auth(user) | ({"Idempotency-Key": key} if key else {})
    return api.client.post(f"/v1{path}", json=body, headers=headers)


def get(api, path, user="asha"):
    return api.client.get(f"/v1{path}", headers=api.auth(user))


def resolve_ambiguity(api, cap):
    r = post(api, f"/captures/{cap['id']}/corrections", {"revision": cap["revision"], "text": "the mango one"})
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ the demo scenario

def test_full_demo_scenario_from_speech_to_dashboard(api):
    # 1-3. record, transcribe, extract, detect ambiguity
    r = new_capture(api)
    assert r.status_code == 202, r.text
    cap = r.json()
    assert cap["state"] == "NEEDS_CLARIFICATION" and cap["revision"] == 1
    assert cap["draft"]["customer"]["name"] == "Sharma General Store"
    assert len(cap["draft"]["order"]["items"]) == 2
    # 4. one clarification question, in the rep's language, with catalogue options
    q = cap["clarification"]
    assert q["code"] == "AMBIGUOUS_PRODUCT" and "Real juice" in q["question"] and "kaun sa product" in q["question"]
    labels = {o["label"] for o in q["options"] if o["value"] != "__new__"}
    assert labels == {"Real Mango Juice 1L", "Real Guava Juice 1L", "Real Mixed Fruit Juice 1L"}
    assert any(o["value"] == "__new__" for o in q["options"])  # the rep can also add it as a new catalogue item
    assert get(api, f"/captures/{cap['id']}/question-audio").status_code == 200

    # 5. the rep answers by voice/text; the draft is patched into a new revision
    cap = resolve_ambiguity(api, cap)
    assert cap["state"] == "READY_FOR_REVIEW" and cap["revision"] == 2 and cap["clarification"] is None
    assert cap["patch"][0]["new"] == "Real Mango Juice 1L"
    assert cap["draft"]["totalPaise"] == 20 * 1000 + 10 * 11000

    # ...then corrects a quantity
    r = post(api, f"/captures/{cap['id']}/corrections", {"revision": 2, "text": "make Parle-G 15"})
    cap = r.json()
    assert cap["revision"] == 3 and cap["patch"] == [{"path": "order.items.0.quantity", "old": 20, "new": 15}]

    # 6-8. review, confirm, commit
    before = get(api, "/manager/summary", "meera").json()
    r = post(api, f"/captures/{cap['id']}/confirm", {"revision": 3}, key="confirm-key-0001")
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["orderTotalPaise"] == 15 * 1000 + 10 * 11000
    assert len(done["commitmentIds"]) == 2 and len(done["collectionIds"]) == 1
    # 9. spoken confirmation
    assert done["reply"]["status"] == "READY" and "Sharma General Store" in done["confirmationText"]
    audio = get(api, f"/captures/{cap['id']}/reply-audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"

    # records
    visit = get(api, f"/visits/{done['visitId']}").json()
    assert visit["customer"]["name"] == "Sharma General Store"
    assert [i["quantity"] for i in visit["order"]["items"]] == [15, 10]
    assert visit["complaints"][0]["category"] == "product_quality"
    assert visit["collections"][0]["kind"] == "promised" and visit["collections"][0]["amountPaise"] == 500000
    due = {c["actionType"]: c["dueDate"] for c in visit["commitments"]}
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert due["payment_followup"] == tomorrow

    # 10. manager dashboard reflects the new data
    after = get(api, "/manager/summary", "meera").json()
    assert after["visitsToday"] == before["visitsToday"] + 1
    assert after["ordersToday"] == before["ordersToday"] + 1
    assert after["orderValueTodayPaise"] == before["orderValueTodayPaise"] + done["orderTotalPaise"]
    assert after["openCommitments"] == before["openCommitments"] + 2
    assert after["outstandingPaise"] == before["outstandingPaise"] + done["orderTotalPaise"]


def test_audio_upload_goes_through_stt_and_segmentation(api):
    r = api.client.post("/v1/captures", files={"audio": ("visit.wav", tone_wav(3), "audio/wav")},
                        data={"language": "hinglish"}, headers={**api.auth("asha"), "Idempotency-Key": "audio-key-0001"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["source"] == "audio" and body["transcript"].startswith("Sharma ji ne aaj bees packet")
    assert body["state"] == "NEEDS_CLARIFICATION"


def test_english_scenario_needs_no_question(api):
    text = ("Visited Gupta Provision Store today. They ordered 12 packets of Britannia Good Day and 6 bottles of "
            "Maaza Mango for tomorrow. He will pay 3000 rupees next Monday. Please send the price list by tomorrow.")
    cap = new_capture(api, key="cap-key-0002", language="en-IN", transcript=text).json()
    assert cap["state"] == "READY_FOR_REVIEW", cap["clarification"]
    types = sorted(c["actionType"] for c in cap["draft"]["commitments"])
    assert types == ["payment_followup", "send_material"]
    assert cap["draft"]["totalPaise"] == 12 * 3000 + 6 * 4000


# ------------------------------------------------------------------ idempotency and revisions

def test_capture_creation_is_idempotent_and_detects_conflicts(api):
    a = new_capture(api).json()
    b = new_capture(api).json()
    assert a["id"] == b["id"]
    assert len(get(api, "/captures").json()["captures"]) == 1
    conflict = new_capture(api, transcript="Gupta Provision Store ko 5 packets of Parle-G kal dena hai")
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert new_capture(api, key="short").status_code == 400


def test_confirm_replay_returns_same_result_and_creates_one_visit(api):
    cap = resolve_ambiguity(api, new_capture(api).json())
    first = post(api, f"/captures/{cap['id']}/confirm", {"revision": cap["revision"]}, key="confirm-key-0002").json()
    again = post(api, f"/captures/{cap['id']}/confirm", {"revision": cap["revision"]}, key="confirm-key-0002").json()
    assert again["visitId"] == first["visitId"] and again["commitmentIds"] == first["commitmentIds"]
    other = post(api, f"/captures/{cap['id']}/confirm", {"revision": cap["revision"]}, key="confirm-key-0003")
    assert other.status_code == 409 and other.json()["error"]["code"] == "ALREADY_COMMITTED"
    with api.app.state.ctx.sf() as s:
        assert s.query(Visit).filter(Visit.capture_id == cap["id"]).count() == 1


def test_stale_revision_is_rejected_everywhere(api):
    cap = new_capture(api).json()
    cap = resolve_ambiguity(api, cap)
    stale = post(api, f"/captures/{cap['id']}/corrections", {"revision": 1, "text": "make Parle-G 5"})
    assert stale.status_code == 409 and stale.json()["error"]["details"]["currentRevision"] == 2
    assert post(api, f"/captures/{cap['id']}/confirm", {"revision": 1}, key="confirm-key-0004").status_code == 409


def test_cannot_confirm_with_open_question(api):
    cap = new_capture(api).json()
    r = post(api, f"/captures/{cap['id']}/confirm", {"revision": 1}, key="confirm-key-0005")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATE"
    assert post(api, f"/captures/{cap['id']}/confirm", {"revision": 1}).status_code == 400  # no key


def test_unrecognised_correction_is_reported_not_dropped(api):
    cap = resolve_ambiguity(api, new_capture(api).json())
    r = post(api, f"/captures/{cap['id']}/corrections", {"revision": 2, "text": "sing me a song"}).json()
    assert r["revision"] == 2 and r["patch"] == [] and r["unsupported"] == ["sing me a song"]


def test_answers_endpoint_applies_a_chosen_option(api):
    cap = new_capture(api).json()
    choice = cap["clarification"]["options"][1]["value"]
    r = post(api, f"/captures/{cap['id']}/answers", {"revision": 1, "answer": choice}).json()
    assert r["state"] == "READY_FOR_REVIEW" and r["patch"][0]["path"] == "order.items.1.productId"
    bad = post(api, f"/captures/{cap['id']}/answers", {"revision": 2, "answer": "x"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "NO_OPEN_QUESTION"


def test_ambiguous_date_asks_instead_of_guessing(api):
    text = "Gupta Provision Store ne 3000 rupees dene ka promise kiya hai. Next week dobara visit karna hai."
    cap = new_capture(api, key="cap-key-0003", transcript=text).json()
    assert cap["clarification"]["answerType"] == "date"
    cap = post(api, f"/captures/{cap['id']}/corrections", {"revision": 1, "text": "kal"}).json()
    assert cap["draft"]["collections"][0]["dueDate"] == (date.today() + timedelta(days=1)).isoformat()


# ------------------------------------------------------------------ failures

class FailingSTT:
    def __init__(self, error):
        self.error, self.calls = error, 0

    def transcribe(self, wav, profile):
        self.calls += 1
        if self.calls == 1:
            raise self.error
        return type("T", (), {"text": DEMO})()


def test_stt_failure_keeps_the_capture_and_retry_recovers(make_api):
    stt = FailingSTT(ProviderError("rate_limit", "x", retryable=True))
    api = make_api(offline_providers(stt=stt))
    files = {"audio": ("v.wav", tone_wav(2), "audio/wav")}
    r = api.client.post("/v1/captures", files=files, data={"language": "hinglish"},
                        headers={**api.auth("asha"), "Idempotency-Key": "audio-key-0002"})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "PROVIDER_ERROR" and err["details"]["stage"] == "stt"
    cap_id = err["details"]["captureId"]
    assert get(api, f"/captures/{cap_id}").json()["state"] == "FAILED"
    retried = post(api, f"/captures/{cap_id}/retry", {})
    assert retried.status_code == 200 and retried.json()["state"] == "NEEDS_CLARIFICATION"


def test_no_speech_is_a_clear_error(make_api):
    api = make_api(offline_providers(stt=FailingSTT(ProviderError("empty_transcript", "none"))))
    r = api.client.post("/v1/captures", files={"audio": ("v.wav", tone_wav(2), "audio/wav")},
                        data={"language": "en-IN"}, headers={**api.auth("asha"), "Idempotency-Key": "audio-key-0003"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_SPEECH"


class BrokenTTS:
    def synthesize(self, text, profile):
        raise ProviderError("http", "boom", retryable=True)


def test_tts_failure_never_fails_a_committed_visit(make_api):
    api = make_api(offline_providers(tts=BrokenTTS()))
    cap = resolve_ambiguity(api, new_capture(api).json())
    r = post(api, f"/captures/{cap['id']}/confirm", {"revision": cap["revision"]}, key="confirm-key-0006")
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]["status"] == "FAILED" and body["confirmationText"]
    assert get(api, f"/captures/{cap['id']}/reply-audio").status_code == 404
    assert get(api, f"/visits/{body['visitId']}").status_code == 200


def test_commit_is_atomic(api, monkeypatch):
    cap = resolve_ambiguity(api, new_capture(api).json())
    service = api.app.state.ctx.captures
    original = service._audit

    def exploding(s, org, actor, action, *a, **k):
        if action == "VISIT_COMMITTED":
            raise RuntimeError("disk full")
        return original(s, org, actor, action, *a, **k)

    with service.sf() as s:
        orders_before = s.query(Order).count()
    monkeypatch.setattr(service, "_audit", exploding)
    quiet = TestClient(api.app, raise_server_exceptions=False)
    r = quiet.post(f"/v1/captures/{cap['id']}/confirm", json={"revision": cap["revision"]},
                   headers={**api.auth("asha"), "Idempotency-Key": "confirm-key-0007"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR" and "disk full" not in r.text
    with service.sf() as s:
        assert s.query(Visit).filter(Visit.capture_id == cap["id"]).count() == 0
        assert s.query(Order).count() == orders_before
    assert get(api, f"/captures/{cap['id']}").json()["state"] == "READY_FOR_REVIEW"
    monkeypatch.setattr(service, "_audit", original)
    assert post(api, f"/captures/{cap['id']}/confirm", {"revision": cap["revision"]}, key="confirm-key-0008").status_code == 200


def test_unsupported_language_and_audio_type(api):
    assert new_capture(api, language="fr-FR").json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"
    r = api.client.post("/v1/captures", files={"audio": ("x.txt", b"hello", "text/plain")},
                        headers={**api.auth("asha"), "Idempotency-Key": "audio-key-0004"})
    assert r.json()["error"]["code"] == "UNSUPPORTED_AUDIO"


# ------------------------------------------------------------------ access control

def test_authentication_and_roles(api):
    assert api.client.get("/v1/captures").status_code == 401
    assert api.client.post("/v1/auth/login", json={"username": "asha", "password": "nope"}).status_code == 401
    assert api.client.post("/v1/auth/login", json={"username": "ghost", "password": "demo123"}).status_code == 401
    manager_try = api.client.post("/v1/captures", data={"language": "hinglish", "transcript": DEMO},
                                  headers={**api.auth("meera"), "Idempotency-Key": "cap-key-0009"})
    assert manager_try.status_code == 403
    assert get(api, "/manager/summary", "asha").status_code == 403


def test_reps_cannot_see_each_others_captures_or_customers(api):
    cap = new_capture(api).json()
    assert get(api, f"/captures/{cap['id']}", "ravi").status_code == 404
    assert post(api, f"/captures/{cap['id']}/cancel", {}, "ravi").status_code == 404
    assert get(api, f"/captures/{cap['id']}", "meera").status_code == 200  # manager may read
    assert post(api, f"/captures/{cap['id']}/cancel", {}, "meera").status_code == 403  # but not change
    names = {c["name"] for c in get(api, "/customers", "ravi").json()["customers"]}
    assert "Iyer Stores" in names and "Sharma General Store" not in names
    # a Chennai rep speaking a Delhi retailer's name must not resolve it
    other = new_capture(api, "ravi", key="cap-key-0010", transcript="Sharma ji ko 5 packets Parle-G chahiye").json()
    assert other["draft"]["customer"]["customerId"] is None


def test_manager_scope_and_questions(api):
    summary = get(api, "/manager/summary", "meera").json()
    assert summary["overdueCommitments"] == 2 and summary["outstandingPaise"] == 2_350_000
    inactive = {r["customer"] for r in get(api, "/manager/inactive-retailers?days=30", "meera").json()["rows"]}
    assert {"Khan Mini Mart", "Verma Kirana", "Murugan Provision"} <= inactive and "Iyer Stores" not in inactive
    declining = get(api, "/manager/declining-products?days=30", "meera").json()["rows"]
    by_name = {r["product"]: r for r in declining}
    assert declining[0]["product"] == "Amul Butter 100g" and declining[0]["declinePct"] == 100.0  # sold 20 -> 0
    assert by_name["Britannia Good Day Cookies"]["priorQty"] == 70 and by_name["Britannia Good Day Cookies"]["declinePct"] == 71.4
    assert "Maaza Mango 600ml" not in by_name  # growing, not declining
    answer = post(api, "/manager/ask", {"text": "which retailers haven't ordered in 45 days"}, "meera").json()
    assert answer["intent"] == "inactive_retailers" and answer["parameters"] == {"days": 45}
    assert answer["rows"] and "45 days" in answer["answerText"]
    overdue = post(api, "/manager/ask", {"text": "show overdue payments"}, "meera").json()
    assert overdue["rows"][0]["customer"] == "Khan Mini Mart" and overdue["rows"][0]["overdueFollowUps"] == 1
    unsupported = post(api, "/manager/ask", {"text": "what is the weather"}, "meera").json()
    assert unsupported["intent"] == "unsupported" and unsupported["supportedQuestions"]


def test_commitments_can_be_completed_and_rescheduled(api):
    cap = resolve_ambiguity(api, new_capture(api).json())
    done = post(api, f"/captures/{cap['id']}/confirm", {"revision": cap["revision"]}, key="confirm-key-0009").json()
    items = get(api, "/commitments").json()["commitments"]
    mine = next(c for c in items if c["id"] == done["commitmentIds"][0])
    assert mine["status"] == "open"
    patched = api.client.patch(f"/v1/commitments/{mine['id']}", json={"status": "done"}, headers=api.auth("asha")).json()
    assert patched["status"] == "done"
    new_date = (date.today() + timedelta(days=3)).isoformat()
    moved = api.client.patch(f"/v1/commitments/{done['commitmentIds'][1]}", json={"dueDate": new_date}, headers=api.auth("asha"))
    assert moved.json()["dueDate"] == new_date
    bad = api.client.patch(f"/v1/commitments/{mine['id']}", json={"dueDate": "2001-01-01"}, headers=api.auth("asha"))
    assert bad.status_code == 400
    overdue = get(api, "/commitments?overdue=true").json()["commitments"]
    assert {c["customer"] for c in overdue} == {"Verma Kirana", "Khan Mini Mart"}
    assert api.client.patch(f"/v1/commitments/{mine['id']}", json={"status": "done"}, headers=api.auth("ravi")).status_code == 404


def test_validation_errors_use_the_error_envelope(api):
    r = post(api, "/captures/cap_x/corrections", {"revision": 0, "text": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR" and r.json()["requestId"]
    assert api.client.get("/health").json()["status"] == "ok"
