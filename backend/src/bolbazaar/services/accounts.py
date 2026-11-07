"""Self-service sign-up. New accounts join the organisation; elevated roles need a signup code."""

from __future__ import annotations

import hmac
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..costguard import CostGuard
from ..errors import ApiError, require
from ..models import Organization, Territory, User
from ..security import hash_password

USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MIN_PASSWORD = 8


class AccountService:
    def __init__(self, sf: sessionmaker[Session], settings: Settings, guard: CostGuard) -> None:
        self.sf = sf
        self.settings = settings
        self.guard = guard

    def territories(self) -> list[dict[str, str]]:
        with self.sf() as s:
            org = self._org(s)
            rows = s.scalars(select(Territory).where(Territory.org_id == org.id).order_by(Territory.name)).all() if org else []
            return [{"id": t.id, "name": t.name} for t in rows]

    def register(self, *, username: str, name: str, password: str, role: str, territory_id: str | None,
                 signup_code: str) -> User:
        username = username.strip().lower()
        name = name.strip()
        require(self.settings.allow_signup, 403, "SIGNUP_DISABLED", "Sign-up is closed. Ask your administrator for an account.")
        require(USERNAME.match(username), 422, "INVALID_USERNAME",
                "Username must be 3-32 characters: lowercase letters, digits, dot, dash or underscore.")
        require(2 <= len(name) <= 80, 422, "INVALID_NAME", "Enter your full name.")
        require(MIN_PASSWORD <= len(password) <= 128, 422, "WEAK_PASSWORD", f"Password must be at least {MIN_PASSWORD} characters.")
        require(role in {"rep", "manager"}, 422, "INVALID_ROLE", "Choose field executive or manager.")
        if role == "rep" and self.settings.rep_signup_code:
            require(hmac.compare_digest(signup_code.encode(), self.settings.rep_signup_code.encode()), 403,
                    "BAD_SIGNUP_CODE", "That sign-up code is not valid.")
        if role == "manager":
            expected = self.settings.manager_signup_code
            require(expected, 403, "MANAGER_SIGNUP_CLOSED", "Manager accounts are created by an administrator.")
            require(hmac.compare_digest(signup_code.encode(), expected.encode()), 403, "BAD_SIGNUP_CODE", "That manager code is not valid.")

        # Global daily ceiling on new accounts: bounds account farming even when every request comes from a new IP.
        self.guard.consume("global", "signup.count", "d", self.settings.signup_global_per_day, code="SIGNUP_LIMIT",
                           message="Sign-ups are paused for today. Try again tomorrow.", status=503)
        with self.sf() as s:
            org = self._org(s) or self._create_org(s)
            if s.scalar(select(User.id).where(User.username == username)):
                raise ApiError(409, "USERNAME_TAKEN", "That username is already taken.")
            territory = None
            if role == "rep":
                territory = self._territory(s, org, territory_id)
            # A signed-up manager oversees every territory, which is what the "admin" role scopes to.
            user = User(org_id=org.id, username=username, name=name, role="rep" if role == "rep" else "admin",
                        territory_id=territory.id if territory else None, password_hash=hash_password(password))
            s.add(user)
            try:
                s.commit()
            except IntegrityError as exc:  # concurrent signup with the same username
                s.rollback()
                raise ApiError(409, "USERNAME_TAKEN", "That username is already taken.") from exc
            return user

    @staticmethod
    def _org(s: Session) -> Organization | None:
        return s.scalar(select(Organization).order_by(Organization.id).limit(1))

    def _create_org(self, s: Session) -> Organization:
        org = Organization(name=self.settings.default_org_name)
        s.add(org)
        s.flush()
        s.add(Territory(org_id=org.id, name="Default territory"))
        s.flush()
        return org

    @staticmethod
    def _territory(s: Session, org: Organization, territory_id: str | None) -> Territory:
        if territory_id:
            found = s.get(Territory, territory_id)
            require(found and found.org_id == org.id, 422, "INVALID_TERRITORY", "Choose a valid territory.")
            return found
        first = s.scalar(select(Territory).where(Territory.org_id == org.id).order_by(Territory.name).limit(1))
        if first:
            return first
        first = Territory(org_id=org.id, name="Default territory")
        s.add(first)
        s.flush()
        return first
