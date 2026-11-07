"""Request-scoped dependencies: application state, authentication and role checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..costguard import CostGuard
from ..errors import ApiError, too_many
from ..guard import SlidingWindowLimiter
from ..models import User
from ..providers.base import Providers
from ..security import Principal, decode_token
from ..services.accounts import AccountService
from ..services.bugs import BugService
from ..services.captures import CaptureService
from ..services.catalogue import CatalogueService
from ..services.metrics import MetricsService
from ..services.records import RecordsService
from ..storage import AudioStore


@dataclass
class AppState:
    settings: Settings
    sf: sessionmaker[Session]
    providers: Providers
    store: AudioStore
    captures: CaptureService
    metrics: MetricsService
    records: RecordsService
    accounts: AccountService
    guard: CostGuard
    limiter: SlidingWindowLimiter
    catalogue: CatalogueService
    bugs: BugService


def get_state(request: Request) -> AppState:
    return request.app.state.ctx


StateDep = Annotated[AppState, Depends(get_state)]


def get_principal(state: StateDep, authorization: Annotated[str | None, Header()] = None) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "AUTH_REQUIRED", "Sign in to continue")
    token = decode_token(state.settings, authorization[7:].strip())
    wait = state.limiter.hit("api_user", token.id, state.settings.rl_user_per_minute, 60)
    if wait:
        raise too_many("RATE_LIMITED", "Too many requests. Slow down and retry shortly.", wait)
    # The database is the source of truth: a deactivated user or a changed role takes effect immediately,
    # instead of staying valid until the token expires.
    with state.sf() as s:
        user = s.get(User, token.id)
    if user is None or not user.active or user.org_id != token.org_id:
        raise ApiError(401, "INVALID_TOKEN", "Sign in again")
    return Principal(user.id, user.org_id, user.role, user.territory_id, user.name)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    def check(user: PrincipalDep) -> Principal:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Your role cannot do this")
        return user

    return check


RepDep = Annotated[Principal, Depends(require_roles("rep"))]
ManagerDep = Annotated[Principal, Depends(require_roles("manager", "admin"))]
AdminDep = Annotated[Principal, Depends(require_roles("admin"))]


def idempotency_key(key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
    return key or ""


KeyDep = Annotated[str, Depends(idempotency_key)]
