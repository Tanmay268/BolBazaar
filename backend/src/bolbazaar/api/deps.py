"""Request-scoped dependencies: application state, authentication and role checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..errors import ApiError
from ..providers.base import Providers
from ..security import Principal, decode_token
from ..services.accounts import AccountService
from ..services.captures import CaptureService
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


def get_state(request: Request) -> AppState:
    return request.app.state.ctx


StateDep = Annotated[AppState, Depends(get_state)]


def get_principal(state: StateDep, authorization: Annotated[str | None, Header()] = None) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "AUTH_REQUIRED", "Sign in to continue")
    return decode_token(state.settings, authorization[7:].strip())


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    def check(user: PrincipalDep) -> Principal:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Your role cannot do this")
        return user

    return check


RepDep = Annotated[Principal, Depends(require_roles("rep"))]
ManagerDep = Annotated[Principal, Depends(require_roles("manager", "admin"))]


def idempotency_key(key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
    return key or ""


KeyDep = Annotated[str, Depends(idempotency_key)]
