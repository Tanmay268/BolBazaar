"""Read access to catalogue, customers, visits, orders and commitments, plus commitment updates.

Visibility: reps see their own records, managers see their territories, admins see all.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, sessionmaker

from ..domain.dates import parse_iso, today_in
from ..errors import ApiError, require
from ..models import (
    Collection, Commitment, Complaint, Customer, CustomerAlias, Order, Organization, Product, Territory, Visit,
)
from ..security import Principal


class RecordsService:
    def __init__(self, sf: sessionmaker[Session]) -> None:
        self.sf = sf

    @staticmethod
    def _territories(s: Session, user: Principal) -> list[str] | None:
        if user.role == "admin":
            return None
        if user.role == "rep":
            return [user.territory_id] if user.territory_id else []
        return list(s.scalars(select(Territory.id).where(Territory.org_id == user.org_id, Territory.manager_id == user.id)))

    def _customer_scope(self, s: Session, user: Principal, query: Select) -> Select:
        territories = self._territories(s, user)
        return query if territories is None else query.where(Customer.territory_id.in_(territories))

    # ------------------------------------------------------------ catalogue

    def customers(self, user: Principal, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(Customer).where(Customer.org_id == user.org_id, Customer.active.is_(True))
            query = self._customer_scope(s, user, query)
            needle = q.strip()
            if needle:
                like = f"%{needle}%"
                query = query.outerjoin(CustomerAlias, CustomerAlias.customer_id == Customer.id).where(
                    or_(Customer.name.ilike(like), CustomerAlias.alias.ilike(like))).distinct()
            return [{"id": c.id, "name": c.name, "territoryId": c.territory_id, "outstandingPaise": int(c.outstanding_paise),
                     "aliases": [a.alias for a in c.aliases]} for c in s.scalars(query.order_by(Customer.name).limit(limit))]

    def products(self, user: Principal, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(Product).where(Product.org_id == user.org_id, Product.active.is_(True))
            if q.strip():
                query = query.where(Product.name.ilike(f"%{q.strip()}%"))
            return [{"id": p.id, "name": p.name, "baseUnit": p.base_unit, "unitsPerPack": p.units_per_pack,
                     "pricePaise": int(p.price_paise)} for p in s.scalars(query.order_by(Product.name).limit(limit))]

    # ------------------------------------------------------------ visits and orders

    def _visit_query(self, s: Session, user: Principal) -> Select:
        query = select(Visit, Customer).join(Customer, Visit.customer_id == Customer.id).where(Visit.org_id == user.org_id)
        if user.role == "rep":
            query = query.where(Visit.rep_id == user.id)
        return self._customer_scope(s, user, query) if user.role != "rep" else query

    def visits(self, user: Principal, limit: int = 30) -> list[dict[str, Any]]:
        with self.sf() as s:
            rows = s.execute(self._visit_query(s, user).order_by(Visit.visited_at.desc()).limit(limit)).all()
            orders = {o.visit_id: o for o in s.scalars(select(Order).where(Order.visit_id.in_([v.id for v, _ in rows])))} if rows else {}
            return [{"id": v.id, "customerId": c.id, "customer": c.name, "visitedAt": v.visited_at.isoformat(),
                     "purpose": v.purpose, "summary": v.summary, "hasOrder": v.id in orders,
                     "orderTotalPaise": int(orders[v.id].total_paise) if v.id in orders else 0} for v, c in rows]

    def visit(self, user: Principal, visit_id: str) -> dict[str, Any]:
        with self.sf() as s:
            row = s.execute(self._visit_query(s, user).where(Visit.id == visit_id)).first()
            require(row, 404, "VISIT_NOT_FOUND", "Visit was not found")
            v, c = row
            order = s.scalar(select(Order).where(Order.visit_id == v.id))
            return {
                "id": v.id, "customer": {"id": c.id, "name": c.name}, "visitedAt": v.visited_at.isoformat(),
                "purpose": v.purpose, "summary": v.summary,
                "order": self._order_dict(order, s) if order else None,
                "collections": [{"id": x.id, "kind": x.kind, "amountPaise": int(x.amount_paise),
                                 "dueDate": x.due_date.isoformat() if x.due_date else None}
                                for x in s.scalars(select(Collection).where(Collection.visit_id == v.id))],
                "complaints": [{"id": x.id, "category": x.category, "description": x.description, "status": x.status}
                               for x in s.scalars(select(Complaint).where(Complaint.visit_id == v.id))],
                "commitments": [self._commitment_dict(x) for x in s.scalars(select(Commitment).where(Commitment.visit_id == v.id))],
            }

    @staticmethod
    def _order_dict(order: Order, s: Session) -> dict[str, Any]:
        names = {p.id: p.name for p in s.scalars(select(Product).where(Product.id.in_([i.product_id for i in order.items])))} if order.items else {}
        return {"id": order.id, "status": order.status, "totalPaise": int(order.total_paise),
                "deliveryDate": order.delivery_date.isoformat() if order.delivery_date else None,
                "items": [{"productId": i.product_id, "product": names.get(i.product_id, i.spoken_name), "quantity": i.quantity,
                           "unit": i.unit, "unitPricePaise": int(i.unit_price_paise), "lineTotalPaise": int(i.line_total_paise)}
                          for i in order.items]}

    def orders(self, user: Principal, limit: int = 30) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(Order, Customer).join(Customer, Order.customer_id == Customer.id).where(Order.org_id == user.org_id)
            query = query.where(Order.rep_id == user.id) if user.role == "rep" else self._customer_scope(s, user, query)
            return [{**self._order_dict(o, s), "customer": c.name, "createdAt": o.created_at.isoformat()}
                    for o, c in s.execute(query.order_by(Order.created_at.desc()).limit(limit)).all()]

    def order(self, user: Principal, order_id: str) -> dict[str, Any]:
        with self.sf() as s:
            query = select(Order, Customer).join(Customer, Order.customer_id == Customer.id).where(
                Order.org_id == user.org_id, Order.id == order_id)
            query = query.where(Order.rep_id == user.id) if user.role == "rep" else self._customer_scope(s, user, query)
            row = s.execute(query).first()
            require(row, 404, "ORDER_NOT_FOUND", "Order was not found")
            return {**self._order_dict(row[0], s), "customer": row[1].name, "createdAt": row[0].created_at.isoformat()}

    # ------------------------------------------------------------ commitments

    @staticmethod
    def _commitment_dict(c: Commitment, customer: str | None = None, today: date | None = None) -> dict[str, Any]:
        return {"id": c.id, "customerId": c.customer_id, "customer": customer, "visitId": c.visit_id,
                "actionType": c.action_type, "description": c.description, "dueDate": c.due_date.isoformat(),
                "priority": c.priority, "status": c.status,
                "overdue": bool(today and c.status == "open" and c.due_date < today),
                "sourcePhrase": c.source_phrase}

    def _commitment_query(self, s: Session, user: Principal) -> Select:
        query = select(Commitment, Customer).join(Customer, Commitment.customer_id == Customer.id).where(
            Commitment.org_id == user.org_id)
        return query.where(Commitment.owner_rep_id == user.id) if user.role == "rep" else self._customer_scope(s, user, query)

    def commitments(self, user: Principal, status: str = "open", overdue: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        with self.sf() as s:
            today = today_in(s.get(Organization, user.org_id).timezone)
            query = self._commitment_query(s, user)
            if status in {"open", "done"}:
                query = query.where(Commitment.status == status)
            if overdue:
                query = query.where(Commitment.status == "open", Commitment.due_date < today)
            return [self._commitment_dict(c, cust.name, today)
                    for c, cust in s.execute(query.order_by(Commitment.due_date, Commitment.priority).limit(limit)).all()]

    def update_commitment(self, user: Principal, commitment_id: str, *, status: str | None, due_date: str | None) -> dict[str, Any]:
        with self.sf.begin() as s:
            row = s.execute(self._commitment_query(s, user).where(Commitment.id == commitment_id)).first()
            require(row, 404, "COMMITMENT_NOT_FOUND", "Commitment was not found")
            commitment, customer = row
            require(user.role == "admin" or commitment.owner_rep_id == user.id or user.role == "manager", 403,
                    "FORBIDDEN", "You cannot change this commitment")
            today = today_in(s.get(Organization, user.org_id).timezone)
            if due_date is not None:
                parsed = parse_iso(due_date, today)
                require(parsed, 400, "INVALID_DATE", "Give a date from today to six months ahead (YYYY-MM-DD)")
                commitment.due_date = parsed
            if status is not None:
                commitment.status = status
                commitment.completed_at = datetime.now(timezone.utc) if status == "done" else None
            return self._commitment_dict(commitment, customer.name, today)
