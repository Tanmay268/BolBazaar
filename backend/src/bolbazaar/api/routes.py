"""HTTP routes. Thin: validate input, call a service, return plain JSON."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..errors import ApiError, require, too_many
from ..models import AuditLog, Organization, User
from ..security import Principal, create_token, dummy_hash, verify_password
from .deps import AdminDep, KeyDep, ManagerDep, PrincipalDep, RepDep, StateDep

router = APIRouter(prefix="/v1")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Body):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class RegisterRequest(_Body):
    username: str = Field(max_length=80)
    name: str = Field(max_length=120)
    password: str = Field(max_length=200)
    role: Literal["rep", "manager"] = "rep"
    territory_id: str | None = Field(None, alias="territoryId")
    signup_code: str = Field("", alias="signupCode", max_length=200)


class AnswerRequest(_Body):
    revision: int = Field(ge=1)
    answer: Any


class CorrectionRequest(_Body):
    revision: int = Field(ge=1)
    text: str = Field(max_length=500)


class ConfirmRequest(_Body):
    revision: int = Field(ge=1)
    speak_reply: bool = Field(True, alias="speakReply")


class CommitmentPatch(_Body):
    status: Literal["open", "done"] | None = None
    due_date: str | None = Field(None, alias="dueDate")


class AskRequest(_Body):
    text: str = Field(min_length=3, max_length=400)


class ProductCreate(_Body):
    name: str = Field(min_length=2, max_length=120)
    base_unit: str = Field(alias="baseUnit", max_length=16)
    price_rupees: float = Field(alias="priceRupees", gt=0, le=100000)
    units_per_pack: int | None = Field(None, alias="unitsPerPack", ge=2, le=1000)
    aliases: list[Annotated[str, Field(max_length=60)]] = Field(default_factory=list, max_length=10)


class ProductPatch(_Body):
    name: str | None = Field(None, min_length=2, max_length=120)
    base_unit: str | None = Field(None, alias="baseUnit", max_length=16)
    price_rupees: float | None = Field(None, alias="priceRupees", gt=0, le=100000)
    units_per_pack: int | None = Field(None, alias="unitsPerPack", ge=2, le=1000)
    aliases: list[Annotated[str, Field(max_length=60)]] | None = Field(None, max_length=10)
    active: bool | None = None


class BulkProducts(_Body):
    items: list[ProductCreate] = Field(min_length=1, max_length=100)


class BugLastError(_Body):
    code: str | None = Field(None, max_length=60)
    request_id: str | None = Field(None, alias="requestId", max_length=100)
    status: int | None = Field(None, ge=0, le=599)
    path: str | None = Field(None, max_length=200)


class BugContext(_Body):
    page: str | None = Field(None, max_length=60)
    app_version: str | None = Field(None, alias="appVersion", max_length=20)
    platform: str | None = Field(None, max_length=120)
    language: str | None = Field(None, max_length=16)
    last_error: BugLastError | None = Field(None, alias="lastError")


class BugReportIn(_Body):
    category: Literal["broken", "wrong_result", "voice", "suggestion", "other"]
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    context: BugContext | None = None


class BugUpdate(_Body):
    status: Literal["open", "in_progress", "resolved", "wontfix"]
    note: str | None = Field(None, max_length=300)


class SwitchRequest(_Body):
    enabled: bool
    reason: str | None = Field(None, max_length=200)


# ------------------------------------------------------------------ auth

@router.post("/auth/login", tags=["auth"])
def login(body: LoginRequest, request: Request, state: StateDep):
    cfg, lim = state.settings, state.limiter
    username = body.username.strip().lower()
    acct, ip = lim.key("acct:" + username), lim.key("ip:" + getattr(request.state, "client_ip", "unknown"))
    # Throttle before any password work. The account counter is charged up front (atomic, so a burst of parallel guesses
    # cannot slip past the limit) and cleared on success; the IP counter only counts failures.
    wait = max(lim.hit("login_acct", acct, cfg.rl_login_failures_per_account, 900),
               lim.blocked_for("login_fail_ip", ip, cfg.rl_login_failures_per_ip, 900))
    if wait:
        raise too_many("LOGIN_THROTTLED", "Too many sign-in attempts. Try again later.", wait)
    with state.sf() as s:
        user = s.scalar(select(User).where(User.username == username, User.active.is_(True)))
        # Always verify against a real hash of production cost so unknown users take as long as wrong passwords.
        valid = verify_password(body.password, user.password_hash if user else dummy_hash())
        if not user or not valid:
            lim.record("login_fail_ip", ip, 900)
            raise ApiError(401, "INVALID_CREDENTIALS", "Wrong username or password")
        lim.reset("login_acct", acct)
        return _session(state, s, user)


def _session(state: StateDep, s, user: User) -> dict[str, Any]:
    org = s.get(Organization, user.org_id)
    principal = Principal(user.id, user.org_id, user.role, user.territory_id, user.name)
    return {"token": create_token(state.settings, principal),
            "user": {"id": user.id, "name": user.name, "role": user.role, "territoryId": user.territory_id,
                     "organization": org.name, "defaultLanguage": org.default_language}}


@router.post("/auth/register", tags=["auth"], status_code=201)
def register(body: RegisterRequest, state: StateDep):
    user = state.accounts.register(username=body.username, name=body.name, password=body.password, role=body.role,
                                   territory_id=body.territory_id, signup_code=body.signup_code)
    with state.sf() as s:
        return _session(state, s, user)


@router.get("/auth/territories", tags=["auth"])
def signup_territories(state: StateDep):
    return {"territories": state.accounts.territories(), "managerSignup": bool(state.settings.manager_signup_code),
            "signupOpen": state.settings.allow_signup}


@router.get("/me", tags=["auth"])
def me(user: PrincipalDep):
    return {"id": user.id, "name": user.name, "role": user.role, "territoryId": user.territory_id}


# ------------------------------------------------------------------ catalogue

@router.get("/customers", tags=["catalogue"])
def customers(user: PrincipalDep, state: StateDep, q: Annotated[str, Query(max_length=80)] = ""):
    return {"customers": state.records.customers(user, q)}


@router.get("/products", tags=["catalogue"])
def products(user: PrincipalDep, state: StateDep, q: Annotated[str, Query(max_length=80)] = "",
             include_inactive: Annotated[bool, Query(alias="includeInactive")] = False):
    return {"products": state.catalogue.list(user, q, include_inactive)}


@router.post("/products", status_code=201, tags=["catalogue"])
def create_product(body: ProductCreate, user: ManagerDep, state: StateDep):
    """Add an item to the catalogue with its price (manager / admin)."""
    return state.catalogue.create(user, name=body.name, base_unit=body.base_unit, price_rupees=body.price_rupees,
                                  units_per_pack=body.units_per_pack, aliases=body.aliases)


@router.post("/products/draft", tags=["catalogue"])
def draft_products(
    user: ManagerDep, state: StateDep,
    audio: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
    language: Annotated[str, Form(max_length=16)] = "hinglish",
):
    """Speak or type a whole product list; the AI proposes catalogue entries. Nothing is saved (see /products/bulk)."""
    transcript = (text or "").strip()
    if audio is not None:
        limit = state.settings.max_audio_bytes
        data = audio.file.read(limit + 1)
        require(len(data) <= limit, 413, "AUDIO_TOO_LARGE", "Recording is too large")
        transcript = state.captures.transcribe_upload(user, data, audio.content_type, audio.filename, language)
    require(transcript, 400, "INVALID_CAPTURE", "Provide an audio recording or text")
    return state.catalogue.draft_from_text(user, transcript)


@router.post("/products/bulk", status_code=201, tags=["catalogue"])
def bulk_products(body: BulkProducts, user: ManagerDep, state: StateDep):
    """Create the reviewed items. Every item is re-validated; duplicates and invalid items are skipped and reported."""
    return state.catalogue.bulk_create(user, [i.model_dump() for i in body.items])


@router.patch("/products/{product_id}", tags=["catalogue"])
def update_product(product_id: str, body: ProductPatch, user: ManagerDep, state: StateDep):
    """Change name, price, unit, case size, spoken aliases, or retire/restore (manager / admin)."""
    given = body.model_fields_set
    require(given, 400, "NOTHING_TO_UPDATE", "Provide at least one field to change")
    return state.catalogue.update(user, product_id, name=body.name, base_unit=body.base_unit, price_rupees=body.price_rupees,
                                  units_per_pack=body.units_per_pack, units_per_pack_set="units_per_pack" in given,
                                  aliases=body.aliases, active=body.active)


@router.delete("/products/{product_id}", tags=["catalogue"])
def retire_product(product_id: str, user: ManagerDep, state: StateDep):
    """Retire a product. It disappears from new visits; old orders keep it."""
    return state.catalogue.retire(user, product_id)


# ------------------------------------------------------------------ captures

@router.post("/captures", status_code=202, tags=["captures"])
def create_capture(
    user: RepDep, state: StateDep, key: KeyDep,
    audio: Annotated[UploadFile | None, File()] = None,
    language: Annotated[str, Form(max_length=16)] = "hinglish",
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
    limit = state.settings.max_audio_bytes
    data = audio.file.read(limit + 1)
    require(len(data) <= limit, 413, "AUDIO_TOO_LARGE", "Recording is too large")
    require(data, 400, "EMPTY_AUDIO", "The recording is empty")
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



# ------------------------------------------------------------------ admin (cost control)

@router.get("/admin/usage", tags=["admin"])
def admin_usage(user: AdminDep, state: StateDep):
    """Today's provider usage against the configured ceilings, breaker state and kill switches."""
    return state.guard.snapshot()


@router.put("/admin/providers/{provider}", tags=["admin"])
def admin_provider_switch(provider: Literal["gnani", "azure", "all"], body: SwitchRequest, user: AdminDep, state: StateDep):
    """Emergency switch: disable (or re-enable) a paid provider at runtime, without a redeploy."""
    result = state.guard.set_switch(provider, body.enabled, body.reason, user.id)
    with state.sf.begin() as s:
        s.add(AuditLog(org_id=user.org_id, actor_id=user.id, action="PROVIDER_SWITCH", entity="provider",
                       entity_id=provider, meta={"enabled": body.enabled, "reason": body.reason}))
    return result


# ------------------------------------------------------------------ bug reports

@router.post("/bug-reports", status_code=201, tags=["support"])
def report_bug(body: BugReportIn, request: Request, user: PrincipalDep, state: StateDep):
    """Any signed-in user can report a problem. Limited per user and per day."""
    context = body.context.model_dump(by_alias=True, exclude_none=True) if body.context else None
    return state.bugs.create(user, category=body.category, title=body.title, description=body.description, context=context,
                             user_agent=request.headers.get("user-agent"))


@router.get("/bug-reports/mine", tags=["support"])
def my_bug_reports(user: PrincipalDep, state: StateDep):
    return {"reports": state.bugs.mine(user)}


@router.get("/admin/bug-reports", tags=["admin"])
def admin_bug_reports(user: AdminDep, state: StateDep,
                      status: Annotated[Literal["open", "in_progress", "resolved", "wontfix"] | None, Query()] = None):
    return {"reports": state.bugs.admin_list(user, status)}


@router.patch("/admin/bug-reports/{bug_id}", tags=["admin"])
def admin_update_bug(bug_id: str, body: BugUpdate, user: AdminDep, state: StateDep):
    return state.bugs.update(user, bug_id, body.status, body.note)
