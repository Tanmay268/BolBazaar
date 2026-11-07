"""Product catalogue: list, create, edit and retire products and their prices.

* Managers and admins manage the catalogue. Reps can only *propose* a new item while logging a visit
  (``captures._commit`` creates it on confirm) and cannot edit or retire anything.
* Prices are stored in paise. Orders copy the price at commit time, so changing a price never rewrites history.
* "Deleting" retires a product (active = false): old orders keep pointing at it.
* Guardrails against abuse and cost: duplicate names are refused, the active catalogue is capped (the whole catalogue is
  sent to the language model with every visit), and creations are counted per user per day.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..costguard import CostGuard, estimate_tokens
from ..domain.normalize import normalize
from ..domain.units import BASE_UNITS, MAX_PRICE_PAISE, normalize_unit
from ..errors import ApiError, require
from ..models import AuditLog, Product, ProductAlias
from ..providers.base import ProviderError, Providers
from ..security import Principal


def product_dict(p: Product) -> dict[str, Any]:
    return {"id": p.id, "name": p.name, "baseUnit": p.base_unit, "unitsPerPack": p.units_per_pack,
            "pricePaise": int(p.price_paise), "active": bool(p.active), "aliases": [a.alias for a in p.aliases]}


def clean_aliases(aliases: list[str] | None, name: str) -> list[str]:
    seen, out = {normalize(name)}, []
    for raw in aliases or []:
        alias = " ".join((raw or "").split())[:60]
        key = normalize(alias)
        if len(key) >= 2 and key not in seen:
            seen.add(key)
            out.append(alias)
    return out[:10]


def base_unit_or_error(raw: str) -> str:
    unit = normalize_unit(raw)
    require(unit in BASE_UNITS, 422, "INVALID_UNIT", f"Unit must be one of: {', '.join(BASE_UNITS)}")
    return unit


def paise_or_error(rupees: float) -> int:
    paise = round(float(rupees) * 100)
    require(0 < paise <= MAX_PRICE_PAISE, 422, "INVALID_PRICE",
            f"Price must be more than 0 and at most {MAX_PRICE_PAISE // 100} rupees")
    return paise


class CatalogueService:
    def __init__(self, sf: sessionmaker[Session], settings: Settings, guard: CostGuard, providers: Providers) -> None:
        self.sf, self.settings, self.guard, self.providers = sf, settings, guard, providers

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _taken(s: Session, org_id: str, names: list[str], *, except_id: str | None = None) -> Product | None:
        """An existing product (active or retired) already using one of these names or aliases."""
        wanted = {normalize(n) for n in names if normalize(n)}
        for p in s.scalars(select(Product).where(Product.org_id == org_id)):
            if p.id != except_id and wanted & {normalize(p.name), *(normalize(a.alias) for a in p.aliases)}:
                return p
        return None

    def active_count(self, s: Session, org_id: str) -> int:
        return s.scalar(select(func.count()).select_from(Product).where(Product.org_id == org_id, Product.active.is_(True))) or 0

    def _audit(self, s: Session, user: Principal, action: str, product_id: str, meta: dict[str, Any]) -> None:
        s.add(AuditLog(org_id=user.org_id, actor_id=user.id, action=action, entity="product", entity_id=product_id, meta=meta))

    def _spend_creation(self, user: Principal) -> None:
        self.guard.consume(f"user:{user.id}", "product.created", "d", self.settings.user_products_per_day,
                           code="CATALOGUE_LIMIT", message="You have added the maximum number of products for today.")

    # ------------------------------------------------------------------ read

    def list(self, user: Principal, q: str = "", include_inactive: bool = False, limit: int = 500) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(Product).where(Product.org_id == user.org_id)
            if not (include_inactive and user.role in {"manager", "admin"}):
                query = query.where(Product.active.is_(True))
            if q.strip():
                query = query.where(Product.name.ilike(f"%{q.strip()}%"))
            return [product_dict(p) for p in s.scalars(query.order_by(Product.name).limit(limit))]

    # ------------------------------------------------------------------ write (manager / admin)

    def create(self, user: Principal, *, name: str, base_unit: str, price_rupees: float, units_per_pack: int | None,
               aliases: list[str] | None) -> dict[str, Any]:
        name = " ".join(name.split())
        require(2 <= len(name) <= 120, 422, "INVALID_NAME", "Product name must be 2 to 120 characters")
        unit, paise = base_unit_or_error(base_unit), paise_or_error(price_rupees)
        names = clean_aliases(aliases, name)
        self._spend_creation(user)
        with self.sf.begin() as s:
            clash = self._taken(s, user.org_id, [name, *names])
            if clash:
                raise ApiError(409, "DUPLICATE_PRODUCT", f"\"{clash.name}\" already exists", {"productId": clash.id})
            require(self.active_count(s, user.org_id) < self.settings.max_products, 409, "CATALOGUE_FULL",
                    f"The catalogue is full ({self.settings.max_products} active products). Retire unused ones first.")
            product = Product(org_id=user.org_id, name=name, base_unit=unit, units_per_pack=units_per_pack or None,
                              price_paise=paise, aliases=[ProductAlias(alias=a) for a in names])
            s.add(product)
            s.flush()
            self._audit(s, user, "PRODUCT_CREATED", product.id, {"name": name, "pricePaise": paise})
            return product_dict(product)

    def update(self, user: Principal, product_id: str, *, name: str | None, base_unit: str | None,
               price_rupees: float | None, units_per_pack: int | None, units_per_pack_set: bool,
               aliases: list[str] | None, active: bool | None) -> dict[str, Any]:
        with self.sf.begin() as s:
            p = s.get(Product, product_id)
            require(p and p.org_id == user.org_id, 404, "PRODUCT_NOT_FOUND", "Product was not found")
            changes: dict[str, Any] = {}
            new_name = " ".join(name.split()) if name is not None else p.name
            if name is not None:
                require(2 <= len(new_name) <= 120, 422, "INVALID_NAME", "Product name must be 2 to 120 characters")
            new_aliases = clean_aliases(aliases, new_name) if aliases is not None else [a.alias for a in p.aliases]
            if name is not None or aliases is not None:
                clash = self._taken(s, user.org_id, [new_name, *new_aliases], except_id=p.id)
                if clash:
                    raise ApiError(409, "DUPLICATE_PRODUCT", f"\"{clash.name}\" already exists", {"productId": clash.id})
            if name is not None and new_name != p.name:
                changes["name"], p.name = [p.name, new_name], new_name
            if aliases is not None:
                p.aliases[:] = [ProductAlias(alias=a) for a in new_aliases]
                changes["aliases"] = new_aliases
            if base_unit is not None:
                unit = base_unit_or_error(base_unit)
                if unit != p.base_unit:
                    changes["baseUnit"], p.base_unit = [p.base_unit, unit], unit
            if price_rupees is not None:
                paise = paise_or_error(price_rupees)
                if paise != p.price_paise:
                    changes["pricePaise"], p.price_paise = [int(p.price_paise), paise], paise
            if units_per_pack_set and units_per_pack != p.units_per_pack:
                changes["unitsPerPack"], p.units_per_pack = [p.units_per_pack, units_per_pack], units_per_pack
            if active is not None and active != p.active:
                if active:
                    require(self.active_count(s, user.org_id) < self.settings.max_products, 409, "CATALOGUE_FULL",
                            "The catalogue is full. Retire unused products first.")
                changes["active"], p.active = [p.active, active], active
            if changes:
                self._audit(s, user, "PRODUCT_UPDATED", p.id, changes)
            return product_dict(p)

    def retire(self, user: Principal, product_id: str) -> dict[str, Any]:
        return self.update(user, product_id, name=None, base_unit=None, price_rupees=None, units_per_pack=None,
                           units_per_pack_set=False, aliases=None, active=False)

    # ------------------------------------------------------------------ used by the visit commit (inside its transaction)

    def create_from_visit(self, s: Session, user: Principal, new: dict[str, Any]) -> Product:
        """Create (or reuse) the catalogue item a rep added by voice. Runs in the caller's transaction."""
        unit, paise = new.get("baseUnit"), new.get("pricePaise")
        require(unit in BASE_UNITS and isinstance(paise, int) and 0 < paise <= MAX_PRICE_PAISE, 422, "NEW_PRODUCT_INVALID",
                "The new item needs a unit and a price")
        existing = self._taken(s, user.org_id, [new["name"]])
        if existing is not None:
            if existing.active:
                return existing  # someone added the same item while this draft was open: use theirs, keep their price
            raise ApiError(409, "DUPLICATE_PRODUCT", f"\"{existing.name}\" exists but is retired; ask a manager")
        require(self.active_count(s, user.org_id) < self.settings.max_products, 409, "CATALOGUE_FULL",
                "The catalogue is full. Ask a manager to retire unused products.")
        product = Product(org_id=user.org_id, name=new["name"][:120], base_unit=unit, units_per_pack=None, price_paise=paise)
        s.add(product)
        s.flush()
        self._audit(s, user, "PRODUCT_CREATED", product.id, {"name": product.name, "pricePaise": paise, "via": "visit"})
        return product

    # ------------------------------------------------------------------ whole catalogue from one spoken / typed passage

    @staticmethod
    def _name_index(s: Session, org_id: str) -> dict[str, Product]:
        """Normalised name or alias -> product (active and retired), loaded once per request."""
        index: dict[str, Product] = {}
        for p in s.scalars(select(Product).where(Product.org_id == org_id)):
            for n in (p.name, *(a.alias for a in p.aliases)):
                index.setdefault(normalize(n), p)
        return index

    def draft_from_text(self, user: Principal, text: str) -> dict[str, Any]:
        """Ask the model to propose catalogue entries. Read-only: returns rows for the manager to review."""
        text = text.strip()
        require(len(text) <= self.settings.max_catalogue_text_chars, 413, "TEXT_TOO_LONG",
                f"Too long (maximum {self.settings.max_catalogue_text_chars} characters). Do it in parts.")
        try:
            parsed = self.guard.run(user.id, "llm", lambda: self.providers.reasoner.parse_catalogue(text),
                                    est_tokens=estimate_tokens(text, output=1500))
        except ProviderError as error:
            raise ApiError(503 if error.retryable else 502, "PROVIDER_ERROR", "The assistant could not read the list",
                           {"category": error.category}) from error
        cap = self.settings.max_catalogue_draft_items
        with self.sf() as s:
            index = self._name_index(s, user.org_id)
        rows, seen = [], set()
        for raw in parsed.items[:cap]:
            name = " ".join((raw.name or "").split())[:120]
            issues: list[str] = []
            unit = normalize_unit(raw.unit) if raw.unit else None
            if unit not in BASE_UNITS:
                unit = None
                issues.append("missing_unit")
            price = raw.price_rupees if raw.price_rupees is not None and 0 < round(raw.price_rupees * 100) <= MAX_PRICE_PAISE else None
            if price is None:
                issues.append("missing_price")
            pack = raw.units_per_pack if raw.units_per_pack and 2 <= raw.units_per_pack <= 1000 else None
            aliases = clean_aliases(raw.aliases, name)
            key = normalize(name)
            clash = next((index[normalize(n)] for n in (name, *aliases) if normalize(n) in index), None)
            if len(key) < 2:
                issues.append("missing_name")
            if clash is not None:
                issues.append("duplicate")
            elif key in seen:
                issues.append("repeated")
            seen.add(key)
            rows.append({"name": name, "baseUnit": unit, "priceRupees": price, "unitsPerPack": pack, "aliases": aliases,
                         "evidence": (raw.evidence or "")[:200], "issues": issues,
                         "duplicateOf": clash.name if clash is not None else None, "include": not issues})
        return {"transcript": text, "items": rows, "truncated": len(parsed.items) > cap,
                "note": "Nothing has been saved. Check each row, fix prices, then add the ones you want."}

    def bulk_create(self, user: Principal, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Create reviewed items. Everything is re-validated here; the client's draft is never trusted."""
        skipped: list[dict[str, str]] = []
        ready: list[dict[str, Any]] = []
        with self.sf() as s:
            index = self._name_index(s, user.org_id)
            active = self.active_count(s, user.org_id)
        taken: set[str] = set()
        for it in items:
            name = " ".join(it["name"].split())
            try:
                unit, paise = base_unit_or_error(it["base_unit"]), paise_or_error(it["price_rupees"])
            except ApiError as error:
                skipped.append({"name": name, "reason": str(error)})
                continue
            aliases = clean_aliases(it.get("aliases"), name)
            keys = {normalize(n) for n in (name, *aliases)}
            if keys & index.keys():
                skipped.append({"name": name, "reason": "already in the catalogue"})
            elif keys & taken:
                skipped.append({"name": name, "reason": "listed twice"})
            else:
                taken |= keys
                ready.append({"name": name, "unit": unit, "paise": paise, "pack": it.get("units_per_pack") or None, "aliases": aliases})
        require(active + len(ready) <= self.settings.max_products, 409, "CATALOGUE_FULL",
                f"This would exceed the catalogue limit of {self.settings.max_products} active products.")
        if not ready:
            return {"created": [], "skipped": skipped}
        self.guard.consume(f"user:{user.id}", "product.imported", "d", self.settings.user_bulk_products_per_day, len(ready),
                           code="CATALOGUE_LIMIT", message="That would exceed the number of products you can add today.")
        created: list[Product] = []
        with self.sf.begin() as s:
            index = self._name_index(s, user.org_id)  # re-check inside the transaction: another request may have added some
            for r in ready:
                if {normalize(n) for n in (r["name"], *r["aliases"])} & index.keys():
                    skipped.append({"name": r["name"], "reason": "already in the catalogue"})
                    continue
                p = Product(org_id=user.org_id, name=r["name"], base_unit=r["unit"], units_per_pack=r["pack"], price_paise=r["paise"],
                            aliases=[ProductAlias(alias=a) for a in r["aliases"]])
                s.add(p)
                created.append(p)
                for n in (r["name"], *r["aliases"]):
                    index[normalize(n)] = p
            s.flush()
            self._audit(s, user, "PRODUCTS_IMPORTED", created[0].id if created else "-",
                        {"count": len(created), "names": [p.name for p in created][:50]})
            return {"created": [product_dict(p) for p in created], "skipped": skipped}
