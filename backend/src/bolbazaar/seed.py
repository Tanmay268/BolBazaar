"""Idempotent demo seeding: organisation, users, retailers, catalogue and order history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .db import make_engine, make_session_factory
from .models import (
    Base, Commitment, Customer, CustomerAlias, Order, OrderItem, Organization, Product, ProductAlias,
    Territory, User, Visit,
)
from .security import hash_password
from .seed_data import CUSTOMERS, DEMO_PASSWORD, PRODUCTS, TERRITORIES, USERS

ORG_ID = "org_demo"
REP_FOR_TERRITORY = {"ter_delhi": "usr_asha", "ter_chennai": "usr_ravi", "ter_pune": "usr_priya"}
PRICE = {pid: (price, pack) for pid, _n, _a, _u, pack, price in PRODUCTS}
CUSTOMER_TERRITORY = {cid: ter for cid, _n, _a, ter in CUSTOMERS}

# customer, days ago, [(product, quantity, unit)]
HISTORY = [
    ("cus_sharma_gen", 10, [("prd_parle_g", 30, "packet"), ("prd_goodday", 20, "packet")]),
    ("cus_sharma_gen", 40, [("prd_parle_g", 40, "packet"), ("prd_goodday", 40, "packet")]),
    ("cus_gupta", 5, [("prd_maaza", 12, "bottle"), ("prd_lays", 20, "packet")]),
    ("cus_gupta", 35, [("prd_goodday", 30, "packet")]),
    ("cus_khan", 50, [("prd_atta", 8, "packet"), ("prd_tata_salt", 10, "packet")]),
    ("cus_sharma_dairy", 45, [("prd_amul_butter", 20, "packet")]),
    ("cus_iyer", 3, [("prd_tata_salt", 15, "packet"), ("prd_atta", 5, "packet")]),
    ("cus_iyer", 33, [("prd_tata_salt", 10, "packet")]),
    ("cus_murugan", 70, [("prd_lays", 30, "packet")]),
    ("cus_patil", 8, [("prd_parle_g", 25, "packet"), ("prd_maaza", 12, "bottle")]),
]
OUTSTANDING = {"cus_sharma_gen": 1_250_000, "cus_khan": 800_000, "cus_gupta": 300_000}


def seed_demo(sf: sessionmaker[Session], now: datetime | None = None, password: str = DEMO_PASSWORD) -> bool:
    """Create demo data once. Returns False if the database already has an organisation."""

    now = now or datetime.now(timezone.utc)
    with sf.begin() as s:
        if s.scalar(select(func.count()).select_from(Organization)):
            return False
        s.add(Organization(id=ORG_ID, name="Sunrise Distributors", timezone="Asia/Kolkata", default_language="hinglish"))
        s.flush()
        for t in TERRITORIES:
            s.add(Territory(id=t["id"], org_id=ORG_ID, name=t["name"], manager_id="usr_meera"))
        s.flush()
        password_hash = hash_password(password)
        for u in USERS:
            s.add(User(org_id=ORG_ID, password_hash=password_hash, **u))
        for pid, name, aliases, unit, pack, price in PRODUCTS:
            s.add(Product(id=pid, org_id=ORG_ID, name=name, base_unit=unit, units_per_pack=pack, price_paise=price,
                          aliases=[ProductAlias(alias=a) for a in aliases]))
        for cid, name, aliases, ter in CUSTOMERS:
            s.add(Customer(id=cid, org_id=ORG_ID, territory_id=ter, name=name,
                           outstanding_paise=OUTSTANDING.get(cid, 0),
                           aliases=[CustomerAlias(alias=a) for a in aliases]))
        s.flush()
        for cid, days, lines in HISTORY:
            when = now - timedelta(days=days)
            rep = REP_FOR_TERRITORY[CUSTOMER_TERRITORY[cid]]
            visit = Visit(org_id=ORG_ID, rep_id=rep, customer_id=cid, visited_at=when, purpose="order",
                          summary="Historical visit (seed)")
            s.add(visit)
            s.flush()
            order = Order(org_id=ORG_ID, visit_id=visit.id, rep_id=rep, customer_id=cid, status="CONFIRMED",
                          total_paise=0, created_at=when)
            total = 0
            for pid, qty, unit in lines:
                price, _pack = PRICE[pid]
                total += qty * price
                order.items.append(OrderItem(product_id=pid, spoken_name=pid, quantity=qty, unit=unit,
                                             unit_price_paise=price, line_total_paise=qty * price))
            order.total_paise = total
            s.add(order)
        # A no-order visit and two overdue open follow-ups, so the dashboard has something to flag.
        visit = Visit(org_id=ORG_ID, rep_id="usr_asha", customer_id="cus_verma", visited_at=now - timedelta(days=20),
                      purpose="visit", summary="Historical visit without an order (seed)")
        s.add(visit)
        s.flush()
        today = now.date()
        s.add(Commitment(org_id=ORG_ID, visit_id=visit.id, customer_id="cus_verma", owner_rep_id="usr_asha",
                         action_type="call", description="Call Verma Kirana about the new scheme",
                         due_date=today - timedelta(days=3), priority="normal"))
        s.add(Commitment(org_id=ORG_ID, visit_id=visit.id, customer_id="cus_khan", owner_rep_id="usr_asha",
                         action_type="payment_followup", description="Collect pending payment from Khan Mini Mart",
                         due_date=today - timedelta(days=5), priority="high"))
    return True


def main() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    created = seed_demo(make_session_factory(engine))
    print("Seeded demo data" if created else "Database already has data; nothing seeded")
