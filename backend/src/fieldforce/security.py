"""Password hashing, JWT issue/verify and the authenticated principal."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt

from .config import Settings
from .errors import ApiError

ITERATIONS = 120_000


@dataclass(frozen=True)
class Principal:
    id: str
    org_id: str
    role: str
    territory_id: str | None
    name: str


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(candidate, digest)


def create_token(settings: Settings, principal: Principal) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": principal.id, "org": principal.org_id, "role": principal.role,
        "ter": principal.territory_id, "name": principal.name,
        "iat": now, "exp": now + settings.jwt_ttl_minutes * 60,
    }
    return jwt.encode(claims, settings.jwt_key, algorithm="HS256")


def decode_token(settings: Settings, token: str) -> Principal:
    try:
        claims = jwt.decode(token, settings.jwt_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ApiError(401, "INVALID_TOKEN", "Sign in again") from exc
    return Principal(claims["sub"], claims["org"], claims["role"], claims.get("ter"), claims.get("name", ""))
