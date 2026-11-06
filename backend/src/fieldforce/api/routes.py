"""HTTP routes. Thin: validate input, call a service, return plain JSON."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..errors import ApiError, require
from ..models import Organization, User
from ..security import Principal, create_token, verify_password
from .deps import KeyDep, ManagerDep, PrincipalDep, RepDep, StateDep

router = APIRouter(prefix="/v1")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Body):
    username: str
    password: str


class AnswerRequest(_Body):
    revision: int = Field(ge=1)
    answer: Any


class CorrectionRequest(_Body):
    revision: int = Field(ge=1)
    text: str


class ConfirmRequest(_Body):
    revision: int = Field(ge=1)
    speak_reply: bool = Field(True, alias="speakReply")


class CommitmentPatch(_Body):
    status: Literal["open", "done"] | None = None
    due_date: str | None = Field(None, alias="dueDate")


class StartCallRequest(_Body):
    customer_id: str = Field(alias="customerId")
    language: str = "hinglish"


class TurnRequest(_Body):
    text: str = Field(min_length=1, max_length=1000)


class AskRequest(_Body):
    text: str = Field(min_length=3, max_length=400)


# ------------------------------------------------------------------ auth

@router.post("/auth/login", tags=["auth"])
def login(body: LoginRequest, state: StateDep):
    with state.sf() as s:
        user = s.scalar(select(User).where(User.username == body.username.strip().lower(), User.active.is_(True)))
        # Always verify against a hash so unknown users cost the same as wrong passwords.
        valid = verify_password(body.password, user.password_hash if user else "pbkdf2$1$x$00")
        if not user or not valid:
            raise ApiError(401, "INVALID_CREDENTIALS", "Wrong username or password")
        org = s.get(Organization, user.org_id)
        principal = Principal(user.id, user.org_id, user.role, user.territory_id, user.name)
        return {"token": create_token(state.settings, principal),
                "user": {"id": user.id, "name": user.name, "role": user.role, "territoryId": user.territory_id,
                         "organization": org.name, "defaultLanguage": org.default_language}}


@router.get("/me", tags=["auth"])
def me(user: PrincipalDep):
    return {"id": user.id, "name": user.name, "role": user.role, "territoryId": user.territory_id}


# ------------------------------------------------------------------ catalogue

@router.get("/customers", tags=["catalogue"])
def customers(user: PrincipalDep, state: StateDep, q: str = ""):
    return {"customers": state.records.customers(user, q)}


@router.get("/products", tags=["catalogue"])
def products(user: PrincipalDep, state: StateDep, q: str = ""):
    return {"products": state.records.products(user, q)}


# ------------------------------------------------------------------ captures

@router.post("/captures", status_code=202, tags=["captures"])
def create_capture(
    user: RepDep, state: StateDep, key: KeyDep,
    audio: Annotated[UploadFile | None, File()] = None,
    language: Annotated[str, Form()] = "hinglish",
    transcript: Annotated[str | None, Form()] = None,
    customer_id: Annotated[str | None, Form(alias="customerId")] = None,
    captured_at: Annotated[str | None, Form(alias="capturedAt")] = None,
):
    data, content_type, filename = None, None, None
    if audio is not None:
        limit = state.settings.max_audio_bytes
        data = audio.file.read(limit + 1)
        require(len(data) <= limit, 413, "AUDIO_TOO_LARGE", "Recording is too large")
        require(data, 400, "EMPTY_AUDIO", "The recording is empty")
        content_type, filename = audio.content_type, audio.filename
    return state.captures.create_capture(
        user, key, audio=data, content_type=content_type, filename=filename, transcript=transcript,
        language=language, customer_hint_id=customer_id, captured_at=captured_at)


@router.get("/captures", tags=["captures"])
def list_captures(user: PrincipalDep, state: StateDep, limit: int = Query(20, ge=1, le=100)):
    return {"captures": state.captures.list_captures(user, limit)}


@router.get("/captures/{capture_id}", tags=["captures"])
def get_capture(capture_id: str, user: PrincipalDep, state: StateDep):
    return state.captures.get_view(user, capture_id)


@router.post("/captures/{capture_id}/answers", tags=["captures"])
def answer(capture_id: str, body: AnswerRequest, user: RepDep, state: StateDep):
    return state.captures.answer(user, capture_id, body.revision, body.answer)


@router.post("/captures/{capture_id}/corrections", tags=["captures"])
def correct(capture_id: str, body: CorrectionRequest, user: RepDep, state: StateDep):
    return state.captures.correct_text(user, capture_id, body.revision, body.text)


@router.post("/captures/{capture_id}/corrections/audio", tags=["captures"])
def correct_audio(capture_id: str, user: RepDep, state: StateDep,
                  audio: Annotated[UploadFile, File()], revision: Annotated[int, Form(ge=1)]):
    data = audio.file.read(state.settings.max_audio_bytes + 1)
    return state.captures.correct_audio(user, capture_id, revision, data, audio.content_type, audio.filename)


@router.post("/captures/{capture_id}/confirm", tags=["captures"])
def confirm(capture_id: str, body: ConfirmRequest, user: RepDep, state: StateDep, key: KeyDep):
    return state.captures.confirm(user, capture_id, key, body.revision, body.speak_reply)


@router.post("/captures/{capture_id}/cancel", tags=["captures"])
def cancel(capture_id: str, user: RepDep, state: StateDep):
    return state.captures.cancel(user, capture_id)


@router.post("/captures/{capture_id}/retry", tags=["captures"])
def retry(capture_id: str, user: RepDep, state: StateDep):
    return state.captures.retry(user, capture_id)


@router.get("/captures/{capture_id}/reply-audio", tags=["captures"])
def reply_audio(capture_id: str, user: PrincipalDep, state: StateDep):
    data, content_type = state.captures.reply_audio(user, capture_id)
    return Response(data, media_type=content_type)


@router.get("/captures/{capture_id}/question-audio", tags=["captures"])
def question_audio(capture_id: str, user: RepDep, state: StateDep):
    data, content_type = state.captures.question_audio(user, capture_id)
    return Response(data, media_type=content_type)


# ------------------------------------------------------------------ records

@router.get("/visits", tags=["records"])
def visits(user: PrincipalDep, state: StateDep, limit: int = Query(30, ge=1, le=100)):
    return {"visits": state.records.visits(user, limit)}


@router.get("/visits/{visit_id}", tags=["records"])
def visit(visit_id: str, user: PrincipalDep, state: StateDep):
    return state.records.visit(user, visit_id)


@router.get("/orders", tags=["records"])
def orders(user: PrincipalDep, state: StateDep, limit: int = Query(30, ge=1, le=100)):
    return {"orders": state.records.orders(user, limit)}


@router.get("/orders/{order_id}", tags=["records"])
def order(order_id: str, user: PrincipalDep, state: StateDep):
    return state.records.order(user, order_id)


@router.get("/commitments", tags=["records"])
def commitments(user: PrincipalDep, state: StateDep, status: Literal["open", "done", "all"] = "open",
                overdue: bool = False):
    return {"commitments": state.records.commitments(user, status, overdue)}


@router.patch("/commitments/{commitment_id}", tags=["records"])
def patch_commitment(commitment_id: str, body: CommitmentPatch, user: PrincipalDep, state: StateDep):
    require(body.status is not None or body.due_date is not None, 400, "NOTHING_TO_UPDATE", "Provide status or dueDate")
    return state.records.update_commitment(user, commitment_id, status=body.status, due_date=body.due_date)


# ------------------------------------------------------------------ manager

@router.get("/manager/summary", tags=["manager"])
def manager_summary(user: ManagerDep, state: StateDep):
    return state.metrics.summary(user)


@router.get("/manager/overdue-payments", tags=["manager"])
def manager_overdue(user: ManagerDep, state: StateDep):
    return {"rows": state.metrics.overdue_payments(user)}


@router.get("/manager/inactive-retailers", tags=["manager"])
def manager_inactive(user: ManagerDep, state: StateDep, days: int = Query(30, ge=1, le=365)):
    return {"rows": state.metrics.inactive_retailers(user, days)}


@router.get("/manager/pending-commitments", tags=["manager"])
def manager_pending(user: ManagerDep, state: StateDep):
    return {"rows": state.metrics.pending_commitments_by_rep(user)}


@router.get("/manager/conversion", tags=["manager"])
def manager_conversion(user: ManagerDep, state: StateDep, days: int = Query(90, ge=1, le=365)):
    return {"rows": state.metrics.order_conversion_by_rep(user, days)}


@router.get("/manager/declining-products", tags=["manager"])
def manager_declining(user: ManagerDep, state: StateDep, days: int = Query(30, ge=1, le=180)):
    return {"rows": state.metrics.declining_products(user, days)}


@router.post("/manager/ask", tags=["manager"])
def manager_ask(body: AskRequest, user: ManagerDep, state: StateDep):
    return state.metrics.ask(user, body.text)


# ------------------------------------------------------------------ call agent

@router.post("/calls", status_code=201, tags=["calls"])
def start_call(body: StartCallRequest, user: PrincipalDep, state: StateDep):
    return state.calls.start(user, body.customer_id, body.language)


@router.get("/calls", tags=["calls"])
def list_calls(user: PrincipalDep, state: StateDep, limit: int = Query(20, ge=1, le=100)):
    return {"calls": state.calls.list(user, limit)}


@router.get("/calls/{call_id}", tags=["calls"])
def get_call(call_id: str, user: PrincipalDep, state: StateDep):
    return state.calls.get(user, call_id)


@router.post("/calls/{call_id}/turns", tags=["calls"])
def call_turn_audio(call_id: str, user: PrincipalDep, state: StateDep, audio: Annotated[UploadFile, File()]):
    data = audio.file.read(state.settings.max_audio_bytes + 1)
    require(data, 400, "EMPTY_AUDIO", "The recording is empty")
    return state.calls.turn(user, call_id, audio=data, text=None)


@router.post("/calls/{call_id}/turns/text", tags=["calls"])
def call_turn_text(call_id: str, body: TurnRequest, user: PrincipalDep, state: StateDep):
    return state.calls.turn(user, call_id, audio=None, text=body.text)


@router.get("/calls/{call_id}/turns/{idx}/audio", tags=["calls"])
def call_turn_audio_out(call_id: str, idx: int, user: PrincipalDep, state: StateDep):
    data, content_type = state.calls.audio(user, call_id, idx)
    return Response(data, media_type=content_type)


@router.post("/calls/{call_id}/cancel", tags=["calls"])
def cancel_call(call_id: str, user: PrincipalDep, state: StateDep):
    return state.calls.cancel(user, call_id)


@router.post("/calls/{call_id}/approve", tags=["calls"])
def approve_call(call_id: str, user: PrincipalDep, state: StateDep):
    return state.calls.approve(user, call_id)


@router.post("/calls/{call_id}/reject", tags=["calls"])
def reject_call(call_id: str, user: PrincipalDep, state: StateDep):
    return state.calls.reject(user, call_id)
