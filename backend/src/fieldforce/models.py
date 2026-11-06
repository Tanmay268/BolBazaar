"""SQLAlchemy models. Portable across SQLite (tests/dev) and PostgreSQL (deployment)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


PHONE_CALL = "phone_call"  # Visit.purpose for an approved call; metrics that count field visits exclude it


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store UTC, always return timezone-aware values (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


def _pk(prefix: str) -> Mapped[str]:
    return mapped_column(String(40), primary_key=True, default=lambda: new_id(prefix))


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = _pk("org")
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    default_language: Mapped[str] = mapped_column(String(16), default="hinglish")


class Territory(Base):
    __tablename__ = "territories"
    id: Mapped[str] = _pk("ter")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    manager_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _pk("usr")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16))  # rep | manager | admin
    territory_id: Mapped[Optional[str]] = mapped_column(ForeignKey("territories.id"), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = _pk("cus")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    territory_id: Mapped[str] = mapped_column(ForeignKey("territories.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    outstanding_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    aliases: Mapped[list["CustomerAlias"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class CustomerAlias(Base):
    __tablename__ = "customer_aliases"
    id: Mapped[str] = _pk("cal")
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = _pk("prd")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_unit: Mapped[str] = mapped_column(String(16))
    units_per_pack: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_paise: Mapped[int] = mapped_column(BigInteger)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    aliases: Mapped[list["ProductAlias"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    id: Mapped[str] = _pk("pal")
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    alias: Mapped[str] = mapped_column(String(200))


class Capture(Base):
    __tablename__ = "captures"
    id: Mapped[str] = _pk("cap")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    rep_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(String(24), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(8), default="audio")  # audio | text
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    audio_ext: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    customer_hint_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    error_category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    error_stage: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    client_captured_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    committed_visit_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class CaptureDraft(Base):
    __tablename__ = "capture_drafts"
    capture_id: Mapped[str] = mapped_column(ForeignKey("captures.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    issues: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[str] = _pk("vis")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    capture_id: Mapped[Optional[str]] = mapped_column(ForeignKey("captures.id"), unique=True, nullable=True)
    rep_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    visited_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    purpose: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = _pk("ord")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"), index=True)
    rep_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="CONFIRMED")
    total_paise: Mapped[int] = mapped_column(BigInteger)
    delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[str] = _pk("itm")
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    spoken_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(String(16))
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    line_total_paise: Mapped[int] = mapped_column(BigInteger)


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[str] = _pk("col")
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(10))  # received | promised
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[str] = _pk("cmp")
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[Optional[str]] = mapped_column(ForeignKey("products.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open")


class CompetitorNote(Base):
    __tablename__ = "competitor_notes"
    id: Mapped[str] = _pk("cnt")
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"), index=True)
    competitor: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text)


class Commitment(Base):
    __tablename__ = "commitments"
    id: Mapped[str] = _pk("cmt")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    owner_rep_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | done
    source_phrase: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (Index("ix_commitments_owner_status_due", "owner_rep_id", "status", "due_date"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    scope: Mapped[str] = mapped_column(String(300), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    ref_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = _pk("evt")
    org_id: Mapped[str] = mapped_column(String(40))
    type: Mapped[str] = mapped_column(String(48))
    aggregate_id: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class ReplyAudio(Base):
    __tablename__ = "reply_audio"
    id: Mapped[str] = _pk("rep")
    capture_id: Mapped[str] = mapped_column(ForeignKey("captures.id"), unique=True)
    audio_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16))
    model: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(10))  # READY | FAILED
    error_category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = _pk("aud")
    org_id: Mapped[str] = mapped_column(String(40), index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(48))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(40))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CallSession(Base):
    """One agent-led phone conversation. ``outcome`` is a proposal until a human approves it."""

    __tablename__ = "call_sessions"
    id: Mapped[str] = _pk("cal")
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    started_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    language: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)  # ACTIVE | NEEDS_REVIEW | APPROVED | REJECTED | CANCELLED
    state: Mapped[dict] = mapped_column(JSON)
    outcome: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    visit_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class CallTurn(Base):
    __tablename__ = "call_turns"
    call_id: Mapped[str] = mapped_column(ForeignKey("call_sessions.id"), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(10))  # agent | customer
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # classified intent for customer turns
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
