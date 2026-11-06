"""Call agent service: start a call, take retailer turns, and commit an approved outcome.

Rules enforced here (same spirit as captures):
* Provider calls (STT, reasoner, TTS) never run inside a database transaction.
* The model only classifies; ``domain.calls.advance`` decides the conversation.
* An outcome stays a proposal (NEEDS_REVIEW) until a rep or manager approves it; only ``approve`` writes
  business rows. A TTS failure never fails a turn.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..audio import prepare_wav_segments
from ..config import Settings
from ..domain import calls as flow
from ..domain.dates import today_in
from ..domain.languages import get_profile
from ..errors import ApiError, require
from ..models import (
    PHONE_CALL, AuditLog, CallSession, CallTurn, Collection, Commitment, Complaint, Customer, Organization, User, Visit,
)
from ..providers.base import CallContext, ProviderError, Providers
from ..security import Principal
from ..services.records import RecordsService
from ..storage import AudioStore

LOGGER = logging.getLogger("fieldforce.calls")


def _provider_error(stage: str, error: ProviderError, call_id: str | None = None) -> ApiError:
    category = error.category
    if category == "empty_transcript":
        return ApiError(422, "NO_SPEECH", "No speech was detected. Please say that again.", {"callId": call_id})
    if category == "unsupported_audio":
        return ApiError(400, "UNSUPPORTED_AUDIO", str(error), {"callId": call_id})
    status = 503 if error.retryable or category in {"credits", "budget", "network", "rate_limit"} else 502
    return ApiError(status, "PROVIDER_ERROR", "The voice service could not process this request",
                    {"stage": stage, "category": category, "callId": call_id, "retryable": True})


class CallService:
    def __init__(self, sf: sessionmaker[Session], providers: Providers, settings: Settings, store: AudioStore,
                 records: RecordsService) -> None:
        self.sf, self.providers, self.settings, self.store, self.records = sf, providers, settings, store, records

    # ------------------------------------------------------------------ helpers

    def _customer(self, s: Session, user: Principal, customer_id: str) -> Customer:
        query = self.records._customer_scope(s, user, select(Customer).where(
            Customer.org_id == user.org_id, Customer.id == customer_id, Customer.active.is_(True)))
        customer = s.scalar(query)
        require(customer, 404, "CUSTOMER_NOT_FOUND", "Retailer was not found")
        return customer

    def _load(self, s: Session, user: Principal, call_id: str) -> tuple[CallSession, Customer]:
        call = s.get(CallSession, call_id)
        if call is None or call.org_id != user.org_id:
            raise ApiError(404, "CALL_NOT_FOUND", "Call was not found")
        if user.role == "rep" and call.started_by != user.id:
            raise ApiError(404, "CALL_NOT_FOUND", "Call was not found")
        customer = s.get(Customer, call.customer_id)
        if user.role != "rep":
            self._customer(s, user, call.customer_id)  # territory scope for managers
        return call, customer

    def _render(self, call: CallSession, step: flow.Step, customer: Customer, org: str) -> str:
        return flow.render(call.language, step, org=org, customer=customer.name)

    @staticmethod
    def _audit(s: Session, org_id: str, actor: str, action: str, call_id: str, meta: dict[str, Any] | None = None) -> None:
        s.add(AuditLog(org_id=org_id, actor_id=actor, action=action, entity="call", entity_id=call_id, meta=meta or {}))

    def _view(self, s: Session, call: CallSession, customer: Customer) -> dict[str, Any]:
        turns = list(s.scalars(select(CallTurn).where(CallTurn.call_id == call.id).order_by(CallTurn.idx)))
        return {
            "id": call.id, "status": call.status, "stage": call.state["stage"], "language": call.language,
            "customer": {"id": customer.id, "name": customer.name},
            "outstandingPaise": call.state["outstandingPaise"],
            "turns": [{"idx": t.idx, "role": t.role, "text": t.text,
                       "audioUrl": f"/v1/calls/{call.id}/turns/{t.idx}/audio" if t.role == "agent" else None,
                       "intent": t.meta.get("intent") if t.role == "customer" else None} for t in turns],
            "outcome": call.outcome, "visitId": call.visit_id, "createdAt": call.created_at.isoformat(),
        }

    # ------------------------------------------------------------------ start / turn

    def start(self, user: Principal, customer_id: str, language: str) -> dict[str, Any]:
        profile = get_profile(language)
        require(profile.code in flow.CALL_LANGUAGES, 400, "UNSUPPORTED_LANGUAGE",
                f"The call agent supports {', '.join(flow.CALL_LANGUAGES)}", {"supported": list(flow.CALL_LANGUAGES)})
        with self.sf.begin() as s:
            customer = self._customer(s, user, customer_id)
            require(customer.outstanding_paise > 0, 422, "NOTHING_DUE", "This retailer has no outstanding balance")
            org = s.get(Organization, user.org_id)
            state = flow.new_state(int(customer.outstanding_paise))
            call = CallSession(org_id=user.org_id, customer_id=customer.id, started_by=user.id, language=profile.code,
                               status="ACTIVE", state=state)
            s.add(call)
            s.flush()
            step = flow.opening_step(state)
            s.add(CallTurn(call_id=call.id, idx=0, role="agent", text=self._render(call, step, customer, org.name)))
            self._audit(s, user.org_id, user.id, "CALL_STARTED", call.id, {"customerId": customer.id})
            s.flush()
            return self._view(s, call, customer)

    def _transcribe(self, audio: bytes, language: str) -> str:
        profile = get_profile(language)
        segments = prepare_wav_segments(audio, max_segment_s=self.settings.gnani_max_segment_seconds,
                                        max_total_s=self.settings.max_audio_seconds)
        return " ".join(self.providers.stt.transcribe(seg, profile).text for seg in segments).strip()

    def turn(self, user: Principal, call_id: str, *, audio: bytes | None, text: str | None) -> dict[str, Any]:
        text = (text or "").strip() or None
        require(audio or text, 400, "INVALID_TURN", "Provide the retailer's audio or text")
        with self.sf() as s:
            call, customer = self._load(s, user, call_id)
            require(call.status == "ACTIVE", 409, "CALL_ENDED", "This call has ended")
            language, state = call.language, dict(call.state)
            org = s.get(Organization, user.org_id)
            tz, org_name, customer_name = org.timezone, org.name, customer.name
            idx = len(list(s.scalars(select(CallTurn.idx).where(CallTurn.call_id == call.id))))
        if audio:
            require(len(audio) <= self.settings.max_audio_bytes, 413, "AUDIO_TOO_LARGE", "Recording is too large")
            try:
                text = self._transcribe(audio, language)
            except ProviderError as error:
                raise _provider_error("stt", error, call_id) from error
        today = today_in(tz)
        context = CallContext(stage=state["stage"], language=language, today=today, weekday=today.strftime("%A"),
                              customer=customer_name, outstanding_rupees=state["outstandingPaise"] / 100)
        try:
            reply = self.providers.reasoner.interpret_call_reply(text, context)
        except ProviderError as error:
            raise _provider_error("llm", error, call_id) from error
        step = flow.advance(state, reply, today)
        closing = step.outcome is not None
        agent_text = flow.render(language, step, org=org_name, customer=customer_name)
        try:
            with self.sf.begin() as s:
                call = s.get(CallSession, call_id)
                require(call.status == "ACTIVE" and len(list(s.scalars(select(CallTurn.idx).where(CallTurn.call_id == call_id)))) == idx,
                        409, "CALL_CHANGED", "The call changed; refresh and retry")
                customer = s.get(Customer, call.customer_id)
                s.add(CallTurn(call_id=call_id, idx=idx, role="customer", text=text,
                               meta={"intent": reply.intent, "amountRupees": reply.amount_rupees,
                                     "dateText": reply.date_text}))
                s.add(CallTurn(call_id=call_id, idx=idx + 1, role="agent", text=agent_text))
                call.state = step.state
                if closing:
                    call.outcome, call.status = step.outcome, "NEEDS_REVIEW"
                self._audit(s, call.org_id, user.id, "CALL_TURN", call_id,
                            {"intent": reply.intent, "stage": step.state["stage"], "closing": closing})
                s.flush()
                return self._view(s, call, customer)
        except IntegrityError as error:
            raise ApiError(409, "CALL_CHANGED", "The call changed; refresh and retry") from error

    # ------------------------------------------------------------------ reads

    def get(self, user: Principal, call_id: str) -> dict[str, Any]:
        with self.sf() as s:
            call, customer = self._load(s, user, call_id)
            return self._view(s, call, customer)

    def list(self, user: Principal, limit: int = 20) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(CallSession, Customer).join(Customer, CallSession.customer_id == Customer.id).where(
                CallSession.org_id == user.org_id)
            query = query.where(CallSession.started_by == user.id) if user.role == "rep" else self.records._customer_scope(s, user, query)
            rows = s.execute(query.order_by(CallSession.created_at.desc()).limit(limit)).all()
            return [{"id": c.id, "status": c.status, "customer": cust.name, "customerId": cust.id,
                     "outcomeType": (c.outcome or {}).get("type"), "amountPaise": (c.outcome or {}).get("amountPaise"),
                     "dueDate": (c.outcome or {}).get("dueDate"), "createdAt": c.created_at.isoformat()} for c, cust in rows]

    def audio(self, user: Principal, call_id: str, idx: int) -> tuple[bytes, str]:
        """Spoken version of an agent line, synthesised on first request and cached (saves credits)."""

        with self.sf() as s:
            call, _customer = self._load(s, user, call_id)
            turn = s.get(CallTurn, (call_id, idx))
            require(turn and turn.role == "agent", 404, "TURN_NOT_FOUND", "That agent line was not found")
            text, language = turn.text, call.language
        key = f"calls/{call_id}/{idx}-{hashlib.sha256(text.encode()).hexdigest()[:10]}.wav"
        data = self.store.load(key)
        if data is None:
            try:
                data = self.providers.tts.synthesize(text, get_profile(language)).audio
            except ProviderError as error:
                raise _provider_error("tts", error, call_id) from error
            self.store.save(key, data)
        return data, "audio/wav"

    # ------------------------------------------------------------------ review

    def cancel(self, user: Principal, call_id: str) -> dict[str, Any]:
        with self.sf.begin() as s:
            call, customer = self._load(s, user, call_id)
            require(call.status == "ACTIVE", 409, "INVALID_STATE", "Only a call in progress can be cancelled")
            call.status = "CANCELLED"
            self._audit(s, user.org_id, user.id, "CALL_CANCELLED", call_id)
            s.flush()
            return self._view(s, call, customer)

    def reject(self, user: Principal, call_id: str) -> dict[str, Any]:
        with self.sf.begin() as s:
            call, customer = self._load(s, user, call_id)
            require(call.status == "NEEDS_REVIEW", 409, "INVALID_STATE", "Only a finished call awaiting review can be rejected")
            call.status = "REJECTED"
            self._audit(s, user.org_id, user.id, "CALL_REJECTED", call_id)
            s.flush()
            return self._view(s, call, customer)

    def approve(self, user: Principal, call_id: str) -> dict[str, Any]:
        """The only place a call changes business tables: one visit log plus whatever the outcome implies."""

        with self.sf.begin() as s:
            call, customer = self._load(s, user, call_id)
            require(call.status != "APPROVED", 409, "ALREADY_APPROVED", "This call was already approved")
            require(call.status == "NEEDS_REVIEW" and call.outcome, 409, "INVALID_STATE", "Only a finished call awaiting review can be approved")
            org = s.get(Organization, user.org_id)
            today = today_in(org.timezone)
            outcome = call.outcome
            kind = outcome["type"]
            owner = user.id if user.role == "rep" else (s.scalar(select(User.id).where(
                User.org_id == user.org_id, User.role == "rep", User.territory_id == customer.territory_id,
                User.active.is_(True))) or user.id)
            summary = self._summary(kind, outcome, customer.name)
            visit = Visit(org_id=user.org_id, rep_id=owner, customer_id=customer.id, visited_at=datetime.now(timezone.utc),
                          purpose=PHONE_CALL, summary=summary)
            s.add(visit)
            s.flush()
            created: dict[str, list[str]] = {"commitmentIds": [], "collectionIds": [], "complaintIds": []}

            def add_commitment(action: str, description: str, due: date, priority: str = "normal") -> None:
                row = Commitment(org_id=user.org_id, visit_id=visit.id, customer_id=customer.id, owner_rep_id=owner,
                                 action_type=action, description=description, due_date=due, priority=priority,
                                 source_phrase=f"Call {call.id}")
                s.add(row)
                s.flush()
                created["commitmentIds"].append(row.id)

            if kind == "promise_to_pay":
                due = date.fromisoformat(outcome["dueDate"])
                col = Collection(visit_id=visit.id, customer_id=customer.id, amount_paise=outcome["amountPaise"], kind="promised", due_date=due)
                s.add(col)
                s.flush()
                created["collectionIds"].append(col.id)
                add_commitment("payment_followup", f"Collect ₹{outcome['amountPaise'] / 100:,.0f} promised on a call", due)
            elif kind == "callback":
                add_commitment("call", "Call back the retailer as agreed on the call", date.fromisoformat(outcome["dueDate"]))
            elif kind == "claims_paid":
                add_commitment("payment_followup", "Verify payment the retailer says is already made", today, "high")
            elif kind == "dispute":
                row = Complaint(visit_id=visit.id, customer_id=customer.id, category="pricing",
                                description=outcome.get("note") or "Retailer disputed the amount on a call")
                s.add(row)
                s.flush()
                created["complaintIds"].append(row.id)
                add_commitment("call", "Resolve the dispute raised on the call", today, "high")
            call.status, call.visit_id = "APPROVED", visit.id
            self._audit(s, user.org_id, user.id, "CALL_APPROVED", call_id, {"visitId": visit.id, "type": kind})
            return {"callId": call_id, "visitId": visit.id, "type": kind, **created}

    @staticmethod
    def _summary(kind: str, outcome: dict[str, Any], customer: str) -> str:
        if kind == "promise_to_pay":
            return f"Call agent: {customer} promised ₹{outcome['amountPaise'] / 100:,.0f} by {outcome['dueDate']}."
        return {"claims_paid": f"Call agent: {customer} says the payment was already made.",
                "dispute": f"Call agent: {customer} disputed the amount. {outcome.get('note') or ''}".strip(),
                "callback": f"Call agent: {customer} asked for a call back on {outcome.get('dueDate')}.",
                "refused": f"Call agent: {customer} declined to commit to a payment.",
                "wrong_person": f"Call agent: wrong person reached for {customer}.",
                "unresolved": f"Call agent: no outcome reached with {customer}."}.get(kind, f"Call agent call with {customer}.")
