"""Payment-promise call agent: a deterministic conversation state machine.

The model only *classifies* what the retailer said (``CallReply``). Everything that matters is decided
here, in code: what the agent says next, which date or amount is accepted, when the call ends, and what
outcome is proposed. Dates are never guessed; amounts are never invented; nothing is committed to
business tables until a human approves the call (see ``services/calls.py``).

Stages: purpose -> (amount) -> (date) -> confirm -> closed, with a callback side branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..schemas_llm import CallReply
from .dates import parse_iso, resolve_date_text

MAX_CUSTOMER_TURNS = 8
MAX_UNCLEAR = 2
MAX_CORRECTIONS = 2

OPEN_STAGES = ("purpose", "amount", "date", "callback", "confirm")


@dataclass
class Step:
    state: dict[str, Any]
    say: str  # script key
    params: dict[str, Any]
    outcome: dict[str, Any] | None  # set when the call ends


def new_state(outstanding_paise: int) -> dict[str, Any]:
    return {"stage": "purpose", "amountPaise": None, "dueDate": None, "amountAssumed": False,
            "unclear": 0, "corrections": 0, "customerTurns": 0, "outstandingPaise": outstanding_paise}


def _fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%d %b")


def _fmt_amount(paise: int) -> str:
    return f"{paise / 100:,.0f}"


def _close(state: dict[str, Any], key: str, outcome: dict[str, Any], **params: Any) -> Step:
    state = {**state, "stage": "closed"}
    return Step(state, key, params, outcome)


def _resolve_date(reply: CallReply, today: date) -> str | None:
    resolved = None
    if reply.date_text:
        resolved = resolve_date_text(reply.date_text, today)
    if resolved is None and reply.date and not reply.date_text:
        resolved = parse_iso(reply.date, today)
    return resolved.isoformat() if resolved else None


def _valid_amount(rupees: float | None, outstanding_paise: int) -> int | None:
    if rupees is None or rupees <= 0:
        return None
    paise = round(rupees * 100)
    return paise if paise <= outstanding_paise else None  # more than owed: ask again rather than accept


def _ask(state: dict[str, Any], params: dict[str, Any]) -> Step:
    """The next question for whatever is still missing, or the confirmation once everything is known."""

    if state["amountPaise"] is None:
        return Step({**state, "stage": "amount"}, "ask_amount", params, None)
    if state["dueDate"] is None:
        return Step({**state, "stage": "date"}, "ask_date", params, None)
    return Step({**state, "stage": "confirm"}, "confirm",
                {**params, "amount": _fmt_amount(state["amountPaise"]), "date": _fmt_date(state["dueDate"])}, None)


def opening_step(state: dict[str, Any]) -> Step:
    return Step(state, "open", {"amount": _fmt_amount(state["outstandingPaise"])}, None)


def advance(state: dict[str, Any], reply: CallReply, today: date) -> Step:
    """Apply one classified retailer reply to the call state."""

    state = {**state, "customerTurns": state["customerTurns"] + 1}
    outstanding = state["outstandingPaise"]
    params: dict[str, Any] = {"amount": _fmt_amount(outstanding)}
    intent, stage = reply.intent, state["stage"]
    when = _resolve_date(reply, today)
    amount = _valid_amount(reply.amount_rupees, outstanding)
    note = (reply.note or "").strip() or None

    # Terminal intents, valid at any open stage.
    if intent == "already_paid":
        return _close(state, "close_paid", {"type": "claims_paid", "note": note})
    if intent == "dispute":
        return _close(state, "close_dispute", {"type": "dispute", "note": note})
    if intent == "refuse":
        return _close(state, "close_refused", {"type": "refused", "note": note})
    if intent == "wrong_person":
        return _close(state, "close_wrong", {"type": "wrong_person", "note": note})
    if intent == "call_later":
        if when:
            return _close(state, "close_callback", {"type": "callback", "dueDate": when, "note": note}, date=_fmt_date(when))
        return Step({**state, "stage": "callback"}, "ask_callback", params, None)

    if state["customerTurns"] >= MAX_CUSTOMER_TURNS:
        return _close(state, "close_unclear", {"type": "unresolved", "note": "Call reached the turn limit"})

    if stage == "callback":
        if when:
            return _close(state, "close_callback", {"type": "callback", "dueDate": when, "note": note}, date=_fmt_date(when))
        return _retry(state, params)

    if stage == "confirm":
        if intent == "yes" and not (when or amount):
            return _close(state, "close_promise",
                          {"type": "promise_to_pay", "amountPaise": state["amountPaise"], "dueDate": state["dueDate"],
                           "amountAssumed": state["amountAssumed"], "note": note},
                          amount=_fmt_amount(state["amountPaise"]), date=_fmt_date(state["dueDate"]))
        state["corrections"] += 1
        if state["corrections"] > MAX_CORRECTIONS:
            return _close(state, "close_unclear", {"type": "unresolved", "note": "Could not agree on a date and amount"})
        if when:
            state["dueDate"] = when
        if amount:
            state["amountPaise"], state["amountAssumed"] = amount, False
        if not (when or amount):  # a plain "no": ask for the date again rather than guess what was wrong
            state["dueDate"] = None
        return _ask(state, params)

    # purpose / amount / date: absorb whatever the reply carries.
    carries = bool(when or amount) or intent in ("will_pay", "partial_pay")
    if not carries:
        return _retry(state, params)
    if when:
        state["dueDate"] = when
    if amount:
        state["amountPaise"], state["amountAssumed"] = amount, False
    elif state["amountPaise"] is None and intent == "will_pay" and reply.amount_rupees is None:
        state["amountPaise"], state["amountAssumed"] = outstanding, True  # "I'll pay" answers the question asked: the full balance
    return _ask(state, params)


def _retry(state: dict[str, Any], params: dict[str, Any]) -> Step:
    state = {**state, "unclear": state["unclear"] + 1}
    if state["unclear"] >= MAX_UNCLEAR:
        return _close(state, "close_unclear", {"type": "unresolved", "note": "The reply could not be understood"})
    key = {"purpose": "ask_date", "amount": "ask_amount", "date": "ask_date", "callback": "ask_callback",
           "confirm": "confirm"}[state["stage"]]
    if key == "confirm":
        params = {**params, "amount": _fmt_amount(state["amountPaise"] or 0), "date": _fmt_date(state["dueDate"]) if state["dueDate"] else ""}
    return Step(state, key, {**params, "repeat": True}, None)


# --------------------------------------------------------------------------- scripts

_SCRIPT: dict[str, dict[str, str]] = {
    "en-IN": {
        "open": "Hello, this is {org} calling for {customer}. Our records show ₹{amount} pending. When can you make the payment?",
        "ask_amount": "How much will you pay?",
        "ask_date": "On which date will you make the payment?",
        "ask_callback": "When should we call you back?",
        "confirm": "So ₹{amount} by {date}. Is that right?",
        "close_promise": "Thank you. I've noted ₹{amount} by {date}. Have a good day.",
        "close_paid": "Thank you for letting us know. Our team will verify and get back to you.",
        "close_dispute": "I understand. I've noted your concern and our team will contact you. Thank you.",
        "close_callback": "Sure, we'll call you around {date}. Thank you.",
        "close_refused": "Understood. Thank you for your time.",
        "close_wrong": "Sorry for the disturbance. Thank you.",
        "close_unclear": "Sorry, I couldn't catch that. Our team will follow up with you. Thank you.",
        "repeat": "Sorry, could you say that again? ",
    },
    "hinglish": {
        "open": "Namaste, main {org} ki taraf se {customer} ke liye bol raha hoon. Hamare record mein ₹{amount} baaki hai. Payment kab tak ho payegi?",
        "ask_amount": "Aap kitna payment karenge?",
        "ask_date": "Kaun si tareekh ko payment kar denge?",
        "ask_callback": "Hum aapko kab dobara call karein?",
        "confirm": "Toh {date} tak ₹{amount}. Sahi hai na?",
        "close_promise": "Dhanyavaad. Maine {date} tak ₹{amount} note kar liya hai. Aapka din shubh ho.",
        "close_paid": "Batane ke liye shukriya. Hamari team check karke aapse sampark karegi.",
        "close_dispute": "Main samajhta hoon. Aapki baat note kar li hai, hamari team aapse baat karegi. Dhanyavaad.",
        "close_callback": "Theek hai, hum {date} ke aaspaas call karenge. Dhanyavaad.",
        "close_refused": "Theek hai. Aapke time ke liye shukriya.",
        "close_wrong": "Disturb karne ke liye maafi. Dhanyavaad.",
        "close_unclear": "Maaf kijiye, mujhe samajh nahi aaya. Hamari team aapse sampark karegi. Dhanyavaad.",
        "repeat": "Maaf kijiye, ek baar phir bolenge? ",
    },
    "hi-IN": {
        "open": "नमस्ते, मैं {org} की तरफ़ से {customer} के लिए बोल रहा हूँ। हमारे रिकॉर्ड में ₹{amount} बाकी है। भुगतान कब तक हो पाएगा?",
        "ask_amount": "आप कितना भुगतान करेंगे?",
        "ask_date": "किस तारीख़ को भुगतान कर देंगे?",
        "ask_callback": "हम आपको कब दोबारा कॉल करें?",
        "confirm": "तो {date} तक ₹{amount}। सही है ना?",
        "close_promise": "धन्यवाद। मैंने {date} तक ₹{amount} नोट कर लिया है। आपका दिन शुभ हो।",
        "close_paid": "बताने के लिए शुक्रिया। हमारी टीम जाँचकर आपसे संपर्क करेगी।",
        "close_dispute": "मैं समझता हूँ। आपकी बात नोट कर ली है, हमारी टीम आपसे बात करेगी। धन्यवाद।",
        "close_callback": "ठीक है, हम {date} के आसपास कॉल करेंगे। धन्यवाद।",
        "close_refused": "ठीक है। आपके समय के लिए शुक्रिया।",
        "close_wrong": "परेशान करने के लिए माफ़ कीजिए। धन्यवाद।",
        "close_unclear": "माफ़ कीजिए, मुझे समझ नहीं आया। हमारी टीम आपसे संपर्क करेगी। धन्यवाद।",
        "repeat": "माफ़ कीजिए, एक बार फिर बोलेंगे? ",
    },
}

CALL_LANGUAGES = tuple(_SCRIPT)


def render(language: str, step: Step, *, org: str, customer: str) -> str:
    table = _SCRIPT.get(language, _SCRIPT["en-IN"])
    params = {"org": org, "customer": customer, **step.params}
    text = table[step.say].format(**params)
    return table["repeat"] + text if step.params.get("repeat") else text
