"""In-app bug reports: any signed-in user can file one; admins triage them.

Safeguards: per-user and global daily caps (otherwise a report form is an open text sink), length limits, a whitelisted
context (no tokens, no arbitrary client data), and users only ever see their own reports.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..costguard import CostGuard
from ..errors import require
from ..models import BugReport, User
from ..security import Principal

STATUSES = ("open", "in_progress", "resolved", "wontfix")


def _clip(value: Any, n: int) -> str | None:
    return " ".join(str(value).split())[:n] if value not in (None, "") else None


def clean_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only known keys and cap their size; query strings are stripped from paths (they could hold ids or tokens)."""
    raw = raw or {}
    out: dict[str, Any] = {k: _clip(raw.get(k), n) for k, n in (("page", 60), ("appVersion", 20), ("platform", 120), ("language", 16))}
    err = raw.get("lastError") or {}
    last = {"code": _clip(err.get("code"), 60), "requestId": _clip(err.get("requestId"), 100), "status": err.get("status"),
            "path": _clip(str(err.get("path") or "").split("?")[0], 120)}
    out["lastError"] = {k: v for k, v in last.items() if v is not None}
    return {k: v for k, v in out.items() if v not in (None, {}, "")}


def report_dict(r: BugReport, reporter: str | None = None) -> dict[str, Any]:
    out = {"id": r.id, "category": r.category, "title": r.title, "description": r.description, "status": r.status,
           "context": r.context or {}, "adminNote": r.admin_note, "createdAt": r.created_at.isoformat(),
           "updatedAt": r.updated_at.isoformat()}
    if reporter is not None:
        out["reporter"] = reporter
        out["role"] = r.role
    return out


class BugService:
    def __init__(self, sf: sessionmaker[Session], settings: Settings, guard: CostGuard) -> None:
        self.sf, self.settings, self.guard = sf, settings, guard

    def create(self, user: Principal, *, category: str, title: str, description: str, context: dict[str, Any] | None,
               user_agent: str | None) -> dict[str, Any]:
        self.guard.consume(f"user:{user.id}", "bug.reported", "d", self.settings.user_bug_reports_per_day, code="BUG_REPORT_LIMIT",
                           message="You have sent the maximum number of reports for today. Thank you, we have your earlier ones.")
        self.guard.consume("global", "bug.reported", "d", self.settings.global_bug_reports_per_day, code="BUG_REPORT_LIMIT",
                           message="Reports are paused for today. Please try again tomorrow.", status=503)
        with self.sf.begin() as s:
            row = BugReport(org_id=user.org_id, user_id=user.id, role=user.role, category=category, title=" ".join(title.split()),
                            description=description.strip(), context=clean_context(context), user_agent=_clip(user_agent, 200))
            s.add(row)
            s.flush()
            return report_dict(row)

    def mine(self, user: Principal, limit: int = 20) -> list[dict[str, Any]]:
        with self.sf() as s:
            rows = s.scalars(select(BugReport).where(BugReport.user_id == user.id).order_by(BugReport.created_at.desc()).limit(limit))
            return [report_dict(r) for r in rows]

    def admin_list(self, user: Principal, status: str | None, limit: int = 100) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(BugReport, User.name).outerjoin(User, User.id == BugReport.user_id).where(BugReport.org_id == user.org_id)
            if status:
                query = query.where(BugReport.status == status)
            return [report_dict(r, name or "unknown") for r, name in s.execute(query.order_by(BugReport.created_at.desc()).limit(limit))]

    def update(self, user: Principal, bug_id: str, status: str, note: str | None) -> dict[str, Any]:
        require(status in STATUSES, 422, "INVALID_STATUS", "Unknown status")
        with self.sf.begin() as s:
            row = s.get(BugReport, bug_id)
            require(row and row.org_id == user.org_id, 404, "BUG_NOT_FOUND", "Report was not found")
            row.status, row.admin_note = status, _clip(note, 300)
            return report_dict(row)
