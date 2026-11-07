"""Manager analytics. Every number comes from a SQL query; the model only picks which one.

A spoken question is mapped to a named intent from a fixed allow-list, then to a
parameterised query. The model never writes SQL and never produces figures.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..costguard import CostGuard, estimate_tokens
from ..domain.dates import day_bounds_utc, today_in
from ..errors import ApiError
from ..models import Commitment, Complaint, Customer, Order, OrderItem, Organization, Product, Territory, User, Visit
from ..providers.base import ProviderError, Providers
from ..security import Principal

SUPPORTED_QUESTIONS = [
    "Which retailers have overdue payments?",
    "Which retailers haven't ordered in 30 days?",
    "Which representatives have the most pending follow-ups?",
    "Which representative has the best order conversion?",
    "Which products are declining?",
]


def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.0f}"


class MetricsService:
    def __init__(self, sf: sessionmaker[Session], providers: Providers, guard: CostGuard) -> None:
        self.sf, self.providers, self.guard = sf, providers, guard

    # ---------------------------------------------------------------- scope

    @staticmethod
    def _territories(s: Session, user: Principal) -> list[str] | None:
        if user.role == "admin":
            return None
        return list(s.scalars(select(Territory.id).where(Territory.org_id == user.org_id,
                                                         Territory.manager_id == user.id)))

    @staticmethod
    def _scoped(query: Select, territories: list[str] | None) -> Select:
        return query if territories is None else query.where(Customer.territory_id.in_(territories))

    def _ctx(self, s: Session, user: Principal):
        org = s.get(Organization, user.org_id)
        return self._territories(s, user), org.timezone, today_in(org.timezone)

    # ---------------------------------------------------------------- queries

    def summary(self, user: Principal) -> dict[str, Any]:
        with self.sf() as s:
            ter, tz, today = self._ctx(s, user)
            start, end = day_bounds_utc(tz, today)
            visits = s.scalar(self._scoped(select(func.count(Visit.id)).join(Customer, Visit.customer_id == Customer.id)
                              .where(Visit.org_id == user.org_id, Visit.visited_at >= start, Visit.visited_at < end), ter))
            orders = s.execute(self._scoped(select(func.count(Order.id), func.coalesce(func.sum(Order.total_paise), 0))
                               .join(Customer, Order.customer_id == Customer.id)
                               .where(Order.org_id == user.org_id, Order.created_at >= start, Order.created_at < end), ter)).one()
            open_c = s.scalar(self._scoped(select(func.count(Commitment.id)).join(Customer, Commitment.customer_id == Customer.id)
                              .where(Commitment.org_id == user.org_id, Commitment.status == "open"), ter))
            overdue = s.scalar(self._scoped(select(func.count(Commitment.id)).join(Customer, Commitment.customer_id == Customer.id)
                               .where(Commitment.org_id == user.org_id, Commitment.status == "open",
                                      Commitment.due_date < today), ter))
            now = datetime.now(timezone.utc)
            window = lambda a, b: s.scalar(self._scoped(  # noqa: E731 - small local helper
                select(func.count(Visit.id)).join(Customer, Visit.customer_id == Customer.id)
                .where(Visit.org_id == user.org_id, Visit.visited_at >= a, Visit.visited_at < b), ter))
            visits_30d = window(now - timedelta(days=30), now + timedelta(days=1))
            visits_prev_30d = window(now - timedelta(days=60), now - timedelta(days=30))
            outstanding = s.scalar(self._scoped(select(func.coalesce(func.sum(Customer.outstanding_paise), 0))
                                   .where(Customer.org_id == user.org_id), ter))
            complaints = s.scalar(self._scoped(select(func.count(Complaint.id)).join(Customer, Complaint.customer_id == Customer.id)
                                  .where(Complaint.status == "open", Customer.org_id == user.org_id), ter))
            return {"date": today.isoformat(), "visitsToday": visits, "ordersToday": orders[0],
                    "orderValueTodayPaise": int(orders[1]), "openCommitments": open_c,
                    "overdueCommitments": overdue, "outstandingPaise": int(outstanding), "openComplaints": complaints,
                    "visits30d": visits_30d, "visitsPrev30d": visits_prev_30d}

    def overdue_payments(self, user: Principal) -> list[dict[str, Any]]:
        with self.sf() as s:
            ter, _tz, today = self._ctx(s, user)
            followups = {r[0]: (r[1], r[2]) for r in s.execute(
                select(Commitment.customer_id, func.count(), func.min(Commitment.due_date))
                .where(Commitment.org_id == user.org_id, Commitment.action_type == "payment_followup",
                       Commitment.status == "open", Commitment.due_date < today)
                .group_by(Commitment.customer_id))}
            next_due = {r[0]: r[1] for r in s.execute(
                select(Commitment.customer_id, func.min(Commitment.due_date))
                .where(Commitment.org_id == user.org_id, Commitment.action_type == "payment_followup",
                       Commitment.status == "open")
                .group_by(Commitment.customer_id))}
            rows = []
            for c in s.scalars(self._scoped(select(Customer).where(Customer.org_id == user.org_id, Customer.active.is_(True)), ter)):
                count, oldest = followups.get(c.id, (0, None))
                if c.outstanding_paise > 0 or count > 0:
                    rows.append({"customerId": c.id, "customer": c.name, "outstandingPaise": int(c.outstanding_paise),
                                 "overdueFollowUps": count, "oldestDueDate": oldest.isoformat() if oldest else None,
                                 "nextDueDate": next_due[c.id].isoformat() if c.id in next_due else None})
            return sorted(rows, key=lambda r: (-r["overdueFollowUps"], -r["outstandingPaise"]))

    def inactive_retailers(self, user: Principal, days: int = 30) -> list[dict[str, Any]]:
        with self.sf() as s:
            ter, _tz, today = self._ctx(s, user)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            last = select(Order.customer_id.label("cid"), func.max(Order.created_at).label("last")).group_by(Order.customer_id).subquery()
            query = self._scoped(select(Customer, last.c.last).outerjoin(last, last.c.cid == Customer.id)
                                 .where(Customer.org_id == user.org_id, Customer.active.is_(True)), ter)
            rows = []
            for customer, last_order in s.execute(query):
                if last_order is None or last_order < cutoff:
                    rows.append({"customerId": customer.id, "customer": customer.name,
                                 "lastOrderDate": last_order.date().isoformat() if last_order else None,
                                 "daysSinceOrder": (today - last_order.date()).days if last_order else None})
            return sorted(rows, key=lambda r: (r["daysSinceOrder"] is not None, -(r["daysSinceOrder"] or 0)))

    def pending_commitments_by_rep(self, user: Principal) -> list[dict[str, Any]]:
        with self.sf() as s:
            ter, _tz, today = self._ctx(s, user)
            query = self._scoped(
                select(User.id, User.name, func.count(Commitment.id),
                       func.coalesce(func.sum(case((Commitment.due_date < today, 1), else_=0)), 0))
                .join(Commitment, Commitment.owner_rep_id == User.id)
                .join(Customer, Commitment.customer_id == Customer.id)
                .where(Commitment.org_id == user.org_id, Commitment.status == "open").group_by(User.id, User.name), ter)
            rows = [{"repId": r[0], "rep": r[1], "open": r[2], "overdue": int(r[3])} for r in s.execute(query)]
            return sorted(rows, key=lambda r: (-r["open"], r["rep"]))

    def order_conversion_by_rep(self, user: Principal, days: int = 90) -> list[dict[str, Any]]:
        with self.sf() as s:
            ter, _tz, _today = self._ctx(s, user)
            since = datetime.now(timezone.utc) - timedelta(days=days)
            query = self._scoped(
                select(User.id, User.name, func.count(func.distinct(Visit.id)), func.count(func.distinct(Order.visit_id)),
                       func.coalesce(func.sum(Order.total_paise), 0))
                .join(Visit, Visit.rep_id == User.id)
                .join(Customer, Visit.customer_id == Customer.id)
                .outerjoin(Order, Order.visit_id == Visit.id)
                .where(Visit.org_id == user.org_id, Visit.visited_at >= since).group_by(User.id, User.name), ter)
            rows = [{"repId": r[0], "rep": r[1], "visits": r[2], "visitsWithOrder": r[3],
                     "conversionPct": round(100 * r[3] / r[2], 1) if r[2] else 0.0,
                     "orderValuePaise": int(r[4])} for r in s.execute(query)]
            return sorted(rows, key=lambda r: -r["conversionPct"])

    def declining_products(self, user: Principal, days: int = 30) -> list[dict[str, Any]]:
        with self.sf() as s:
            ter, _tz, _today = self._ctx(s, user)
            now = datetime.now(timezone.utc)
            recent_from, prior_from = now - timedelta(days=days), now - timedelta(days=2 * days)
            recent = func.coalesce(func.sum(case((Order.created_at >= recent_from, OrderItem.quantity), else_=0)), 0)
            prior = func.coalesce(func.sum(case((and_(Order.created_at >= prior_from, Order.created_at < recent_from),
                                                 OrderItem.quantity), else_=0)), 0)
            query = self._scoped(
                select(Product.id, Product.name, recent, prior)
                .join(OrderItem, OrderItem.product_id == Product.id).join(Order, OrderItem.order_id == Order.id)
                .join(Customer, Order.customer_id == Customer.id)
                .where(Order.org_id == user.org_id, Order.created_at >= prior_from).group_by(Product.id, Product.name), ter)
            rows = [{"productId": r[0], "product": r[1], "recentQty": int(r[2]), "priorQty": int(r[3]),
                     "declinePct": round(100 * (r[3] - r[2]) / r[3], 1)} for r in s.execute(query) if r[3] > 0 and r[2] < r[3]]
            return sorted(rows, key=lambda r: -r["declinePct"])

    # ---------------------------------------------------------------- ask

    def ask(self, user: Principal, text: str) -> dict[str, Any]:
        try:
            parsed = self.guard.run(user.id, "llm", lambda: self.providers.reasoner.parse_manager_query(text),
                                    est_tokens=estimate_tokens(text))
        except ProviderError as error:
            raise ApiError(503 if error.retryable else 502, "PROVIDER_ERROR", "The assistant could not read the question",
                           {"category": error.category}) from error
        intent, days = parsed.intent, parsed.days
        if intent == "unsupported":
            return {"intent": intent, "parameters": {}, "queryId": None, "rows": [],
                    "answerText": "I can't answer that yet. Try one of the supported questions.",
                    "supportedQuestions": SUPPORTED_QUESTIONS}
        if intent == "overdue_payments":
            rows, params = self.overdue_payments(user), {}
            total = sum(r["outstandingPaise"] for r in rows)
            answer = (f"{len(rows)} retailers have outstanding payments totalling {_rupees(total)}. "
                      f"Largest: {max(rows, key=lambda r: r['outstandingPaise'])['customer']}." if rows
                      else "No retailer has outstanding payments.")
        elif intent == "inactive_retailers":
            params = {"days": days or 30}
            rows = self.inactive_retailers(user, params["days"])
            answer = (f"{len(rows)} retailers have not ordered in {params['days']} days. Longest: {rows[0]['customer']}."
                      if rows else f"All retailers ordered within the last {params['days']} days.")
        elif intent == "pending_commitments_by_rep":
            rows, params = self.pending_commitments_by_rep(user), {}
            answer = (f"{sum(r['open'] for r in rows)} open follow-ups, {sum(r['overdue'] for r in rows)} overdue. "
                      f"Most pending: {rows[0]['rep']} ({rows[0]['open']})." if rows else "There are no open follow-ups.")
        elif intent == "order_conversion_by_rep":
            rows, params = self.order_conversion_by_rep(user), {"days": 90}
            answer = (f"Best conversion: {rows[0]['rep']} at {rows[0]['conversionPct']}% "
                      f"({rows[0]['visitsWithOrder']} of {rows[0]['visits']} visits)." if rows else "No visits recorded yet.")
        else:
            params = {"days": days or 30}
            rows = self.declining_products(user, params["days"])
            answer = (f"{len(rows)} products declined versus the previous {params['days']} days. "
                      f"Biggest drop: {rows[0]['product']} (-{rows[0]['declinePct']}%)." if rows
                      else "No product shows a decline.")
        return {"intent": intent, "parameters": params, "queryId": intent, "rows": rows, "answerText": answer}
