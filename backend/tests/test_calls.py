from datetime import date

import pytest

from fieldforce.domain import calls as flow
from fieldforce.providers.base import CallContext
from fieldforce.providers.offline import OfflineReasoner
from fieldforce.schemas_llm import CallReply

from conftest import tone_wav

TODAY = date(2026, 11, 4)  # a Wednesday


def reply(intent, amount=None, date_text=None, note=None):
    return CallReply(intent=intent, amount_rupees=amount, date_text=date_text, date=None, note=note)


def ctx(stage="purpose"):
    return CallContext(stage=stage, language="hinglish", today=TODAY, weekday="Wednesday", customer="Khan Mini Mart", outstanding_rupees=8000)


# --------------------------------------------------------------------------- state machine (pure)

def test_will_pay_with_date_assumes_full_balance_then_confirms_and_closes():
    state = flow.new_state(800000)
    step = flow.advance(state, reply("will_pay", date_text="kal"), TODAY)
    assert step.say == "confirm" and step.state["amountPaise"] == 800000 and step.state["amountAssumed"] is True
    assert step.state["dueDate"] == "2026-11-05" and step.outcome is None
    done = flow.advance(step.state, reply("yes"), TODAY)
    assert done.outcome == {"type": "promise_to_pay", "amountPaise": 800000, "dueDate": "2026-11-05", "amountAssumed": True, "note": None}
    assert done.state["stage"] == "closed"


def test_vague_date_is_asked_never_guessed():
    step = flow.advance(flow.new_state(800000), reply("will_pay", date_text="agle hafte"), TODAY)
    assert step.say == "ask_date" and step.state["dueDate"] is None and step.outcome is None


def test_partial_payment_asks_for_the_amount_then_date():
    step = flow.advance(flow.new_state(800000), reply("partial_pay"), TODAY)
    assert step.say == "ask_amount"
    step = flow.advance(step.state, reply("will_pay", amount=3000), TODAY)
    assert step.say == "ask_date" and step.state["amountPaise"] == 300000 and step.state["amountAssumed"] is False


def test_amount_above_the_balance_is_not_accepted_or_assumed():
    step = flow.advance(flow.new_state(800000), reply("will_pay", amount=100000, date_text="kal"), TODAY)
    assert step.say == "ask_amount" and step.state["amountPaise"] is None


def test_no_at_confirm_asks_the_date_again_and_a_new_date_reconfirms():
    confirm = flow.advance(flow.new_state(800000), reply("will_pay", date_text="kal"), TODAY)
    step = flow.advance(confirm.state, reply("no"), TODAY)
    assert step.say == "ask_date" and step.state["dueDate"] is None
    step = flow.advance(step.state, reply("will_pay", date_text="agle Monday"), TODAY)
    assert step.say == "confirm" and step.state["dueDate"] == "2026-11-09"


def test_terminal_intents_close_with_the_right_outcome():
    for intent, kind in [("already_paid", "claims_paid"), ("dispute", "dispute"), ("refuse", "refused"), ("wrong_person", "wrong_person")]:
        step = flow.advance(flow.new_state(800000), reply(intent, note="x"), TODAY)
        assert step.outcome["type"] == kind and step.state["stage"] == "closed"


def test_call_later_needs_a_real_date_else_asks_when():
    step = flow.advance(flow.new_state(800000), reply("call_later"), TODAY)
    assert step.say == "ask_callback" and step.outcome is None
    step = flow.advance(step.state, reply("will_pay", date_text="kal"), TODAY)
    assert step.outcome == {"type": "callback", "dueDate": "2026-11-05", "note": None}


def test_two_unclear_replies_end_the_call_without_an_outcome_to_commit():
    step = flow.advance(flow.new_state(800000), reply("unclear"), TODAY)
    assert step.outcome is None and step.params.get("repeat")
    step = flow.advance(step.state, reply("unclear"), TODAY)
    assert step.outcome["type"] == "unresolved"


def test_turn_limit_ends_the_call():
    state = flow.new_state(800000)
    state["customerTurns"] = flow.MAX_CUSTOMER_TURNS - 1
    assert flow.advance(state, reply("will_pay", date_text="kal"), TODAY).outcome["type"] == "unresolved"


def test_scripts_render_in_every_supported_language():
    step = flow.opening_step(flow.new_state(800000))
    for language in flow.CALL_LANGUAGES:
        text = flow.render(language, step, org="Demo Distributors", customer="Khan Mini Mart")
        assert "8,000" in text and "Khan Mini Mart" in text


@pytest.mark.parametrize("text,stage,intent", [
    ("kal tak de dunga", "purpose", "will_pay"),
    ("haan sahi hai", "confirm", "yes"),
    ("nahi", "confirm", "no"),
    ("paanch hazaar rupaye parso denge", "purpose", "will_pay"),
    ("kuch payment kar dunga", "purpose", "partial_pay"),
    ("maine to pehle hi de diya", "purpose", "already_paid"),
    ("bill galat hai, maal kharab tha", "purpose", "dispute"),
    ("abhi busy hoon baad mein call karo", "purpose", "call_later"),
    ("wrong number", "purpose", "wrong_person"),
    ("hmm kya", "purpose", "unclear"),
])
def test_offline_classifier(text, stage, intent):
    assert OfflineReasoner().interpret_call_reply(text, ctx(stage)).intent == intent


# --------------------------------------------------------------------------- API

KHAN = "cus_khan"  # Delhi, outstanding 8,000 in the demo seed


def start(api, user="asha", customer=KHAN, language="hinglish"):
    return api.client.post("/v1/calls", json={"customerId": customer, "language": language}, headers=api.auth(user))


def say(api, call_id, text, user="asha"):
    return api.client.post(f"/v1/calls/{call_id}/turns/text", json={"text": text}, headers=api.auth(user))


def test_full_call_then_approve_creates_the_promise(make_api):
    api = make_api()
    before = api.client.get("/v1/manager/summary", headers=api.auth("meera")).json()
    r = start(api)
    assert r.status_code == 201
    call = r.json()
    assert call["status"] == "ACTIVE" and "8,000" in call["turns"][0]["text"] and call["turns"][0]["role"] == "agent"

    call = say(api, call["id"], "kal tak de dunga").json()
    assert call["stage"] == "confirm" and call["status"] == "ACTIVE"
    call = say(api, call["id"], "haan sahi hai").json()
    assert call["status"] == "NEEDS_REVIEW" and call["outcome"]["type"] == "promise_to_pay" and call["outcome"]["amountPaise"] == 800000

    # Nothing is committed before approval.
    open_before = api.client.get("/v1/commitments?status=open", headers=api.auth("asha")).json()["commitments"]
    approved = api.client.post(f"/v1/calls/{call['id']}/approve", headers=api.auth("asha"))
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert len(body["commitmentIds"]) == 1 and len(body["collectionIds"]) == 1
    open_after = api.client.get("/v1/commitments?status=open", headers=api.auth("asha")).json()["commitments"]
    assert len(open_after) == len(open_before) + 1
    new = next(c for c in open_after if c["id"] == body["commitmentIds"][0])
    assert new["actionType"] == "payment_followup" and new["dueDate"] == call["outcome"]["dueDate"]
    assert api.client.get(f"/v1/calls/{call['id']}", headers=api.auth("asha")).json()["status"] == "APPROVED"
    assert api.client.post(f"/v1/calls/{call['id']}/approve", headers=api.auth("asha")).json()["error"]["code"] == "ALREADY_APPROVED"

    # A call is not a field visit: it must not change visit counts or conversion.
    after = api.client.get("/v1/manager/summary", headers=api.auth("meera")).json()
    assert after["visitsToday"] == before["visitsToday"]


def test_dispute_is_logged_as_complaint_after_approval(make_api):
    api = make_api()
    call = start(api).json()
    call = say(api, call["id"], "bill galat hai, maal kharab tha").json()
    assert call["status"] == "NEEDS_REVIEW" and call["outcome"]["type"] == "dispute"
    body = api.client.post(f"/v1/calls/{call['id']}/approve", headers=api.auth("asha")).json()
    assert len(body["complaintIds"]) == 1 and len(body["commitmentIds"]) == 1 and not body["collectionIds"]


def test_unresolved_call_commits_no_promise(make_api):
    api = make_api()
    call = start(api).json()
    say(api, call["id"], "hmm kya")
    call = say(api, call["id"], "hmm achha").json()
    assert call["outcome"]["type"] == "unresolved"
    body = api.client.post(f"/v1/calls/{call['id']}/approve", headers=api.auth("asha")).json()
    assert not body["commitmentIds"] and not body["collectionIds"]


def test_cannot_approve_before_the_call_finishes_or_after_reject(make_api):
    api = make_api()
    call = start(api).json()
    assert api.client.post(f"/v1/calls/{call['id']}/approve", headers=api.auth("asha")).json()["error"]["code"] == "INVALID_STATE"
    call = say(api, call["id"], "paanch hazaar rupaye kal denge").json()
    call = say(api, call["id"], "haan").json()
    assert api.client.post(f"/v1/calls/{call['id']}/reject", headers=api.auth("asha")).json()["status"] == "REJECTED"
    assert api.client.post(f"/v1/calls/{call['id']}/approve", headers=api.auth("asha")).status_code == 409
    assert say(api, call["id"], "haan").status_code == 409  # call has ended


def test_audio_turn_and_agent_speech(make_api):
    api = make_api()
    call = start(api).json()
    spoken = api.client.get(call["turns"][0]["audioUrl"], headers=api.auth("asha"))
    assert spoken.status_code == 200 and spoken.headers["content-type"] == "audio/wav" and spoken.content[:4] == b"RIFF"
    r = api.client.post(f"/v1/calls/{call['id']}/turns", files={"audio": ("reply.wav", tone_wav(), "audio/wav")}, headers=api.auth("asha"))
    assert r.status_code == 200, r.text
    assert any(t["role"] == "customer" for t in r.json()["turns"])


def test_scoping_and_validation(make_api):
    api = make_api()
    assert start(api, user="ravi").status_code == 404  # Chennai rep, Delhi retailer
    assert start(api, language="ta-IN").status_code == 400
    assert api.client.post("/v1/calls", json={"customerId": "cus_nope", "language": "hinglish"}, headers=api.auth("asha")).status_code == 404
    call = start(api).json()
    assert api.client.get(f"/v1/calls/{call['id']}", headers=api.auth("ravi")).status_code == 404
    assert api.client.get(f"/v1/calls/{call['id']}", headers=api.auth("meera")).status_code == 200  # manager of that territory
    assert [c["id"] for c in api.client.get("/v1/calls", headers=api.auth("asha")).json()["calls"]] == [call["id"]]
    assert api.client.get("/v1/calls", headers=api.auth("ravi")).json()["calls"] == []
    assert api.client.post(f"/v1/calls/{call['id']}/cancel", headers=api.auth("asha")).json()["status"] == "CANCELLED"


def test_retailer_without_a_balance_cannot_be_called(make_api):
    api = make_api()
    rows = api.client.get("/v1/customers", headers=api.auth("asha")).json()["customers"]
    clear = [c for c in rows if c["outstandingPaise"] == 0]
    if clear:
        assert start(api, customer=clear[0]["id"]).json()["error"]["code"] == "NOTHING_DUE"
