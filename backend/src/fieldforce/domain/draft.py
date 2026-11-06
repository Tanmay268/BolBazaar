"""The visit-bundle draft: build from an extraction, validate, and patch.

The draft is a plain JSON-serialisable dict so each revision can be stored as-is. Business
rules live here; nothing in this module performs I/O.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..schemas_llm import Extraction, PatchOp
from .dates import parse_iso, resolve_date_text
from .resolution import Entry, Resolution, resolve
from .units import allowed_units, normalize_unit, unit_ok, unit_price


class OpError(ValueError):
    """A requested change that cannot be applied (reported back, never silently dropped)."""


@dataclass(frozen=True)
class CustomerRef:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductRef:
    id: str
    name: str
    aliases: tuple[str, ...]
    base_unit: str
    units_per_pack: int | None
    price_paise: int


class Catalog:
    def __init__(self, customers: list[CustomerRef], products: list[ProductRef], today: date) -> None:
        self.customers = {c.id: c for c in customers}
        self.products = {p.id: p for p in products}
        self.today = today
        self.customer_entries = [Entry(c.id, c.name, (c.name, *c.aliases)) for c in customers]
        self.product_entries = [Entry(p.id, p.name, (p.name, *p.aliases)) for p in products]


# --------------------------------------------------------------------------- build

def _customer_block(spoken: str | None, confidence: float, cat: Catalog, hint_id: str | None) -> dict[str, Any]:
    block: dict[str, Any] = {"spokenName": spoken, "customerId": None, "name": None,
                             "candidates": [], "matchStatus": "unknown", "confidence": confidence}
    res = resolve(spoken, cat.customer_entries) if spoken else Resolution("unknown")
    if res.status == "resolved" and res.best:
        _set_customer(block, cat.customers[res.best.id])
    elif hint_id and hint_id in cat.customers and res.status == "unknown":
        _set_customer(block, cat.customers[hint_id])
    else:
        block["matchStatus"] = res.status
        block["candidates"] = [c.as_dict() for c in res.candidates]
    return block


def _set_customer(block: dict[str, Any], customer: CustomerRef) -> None:
    block.update(customerId=customer.id, name=customer.name, candidates=[], matchStatus="resolved")


def _set_product(item: dict[str, Any], product: ProductRef) -> None:
    unit = item.get("unit")
    if unit is None or unit == "piece":
        unit = product.base_unit
    item.update(productId=product.id, productName=product.name, candidates=[],
                matchStatus="resolved", unit=unit)
    item["unitPricePaise"] = unit_price(product.price_paise, unit, product.base_unit, product.units_per_pack)


def _item_block(raw: Any, cat: Catalog) -> dict[str, Any]:
    item: dict[str, Any] = {
        "spokenName": raw.spoken_name, "spokenUnit": raw.unit, "quantity": raw.quantity,
        "unit": normalize_unit(raw.unit), "productId": None, "productName": None,
        "candidates": [], "matchStatus": "unknown", "unitPricePaise": None,
        "confidence": raw.confidence, "evidence": raw.evidence,
    }
    res = resolve(raw.spoken_name, cat.product_entries)
    if res.status == "resolved" and res.best:
        _set_product(item, cat.products[res.best.id])
    else:
        item["matchStatus"] = res.status
        item["candidates"] = [c.as_dict() for c in res.candidates]
    return item


def _date(text: str | None, iso: str | None, cat: Catalog) -> str | None:
    resolved = resolve_date_text(text, cat.today) if text else None
    if resolved is None and iso:
        resolved = parse_iso(iso, cat.today)
    return resolved.isoformat() if resolved else None


def build_draft(ex: Extraction, cat: Catalog, customer_hint_id: str | None = None) -> dict[str, Any]:
    draft: dict[str, Any] = {
        "customer": _customer_block(ex.customer.spoken_name, ex.customer.confidence, cat, customer_hint_id),
        "visit": {"purpose": ex.visit.purpose, "summary": ex.visit.summary},
        "order": {
            "items": [_item_block(i, cat) for i in ex.order.items],
            "deliveryText": ex.order.delivery_text,
            "deliveryDate": _date(ex.order.delivery_text, ex.order.delivery_date, cat),
        },
        "collections": [{
            "kind": c.kind,
            "amountPaise": round(c.amount_rupees * 100) if c.amount_rupees is not None and c.amount_rupees >= 0 else None,
            "dueText": c.due_text, "dueDate": _date(c.due_text, c.due_date, cat), "evidence": c.evidence,
        } for c in ex.collections],
        "complaints": [_complaint(c, cat) for c in ex.complaints],
        "competitorNotes": [{"competitor": n.competitor, "note": n.note} for n in ex.competitor_notes],
        "commitments": [{
            "actionType": c.action_type, "description": c.description, "dueText": c.due_text,
            "dueDate": _date(c.due_text, c.due_date, cat), "priority": c.priority, "evidence": c.evidence,
        } for c in ex.commitments],
    }
    return finalize(draft)


def _complaint(c: Any, cat: Catalog) -> dict[str, Any]:
    product_id = None
    if c.product_spoken_name:
        res = resolve(c.product_spoken_name, cat.product_entries)
        product_id = res.best.id if res.status == "resolved" and res.best else None
    return {"category": c.category, "description": c.description,
            "productSpokenName": c.product_spoken_name, "productId": product_id, "evidence": c.evidence}


def finalize(draft: dict[str, Any]) -> dict[str, Any]:
    total = 0
    for item in draft["order"]["items"]:
        if isinstance(item.get("quantity"), int) and item.get("unitPricePaise") is not None:
            total += item["quantity"] * item["unitPricePaise"]
    draft["totalPaise"] = total
    return draft


# --------------------------------------------------------------------------- validate

def _issue(code: str, field_path: str, answer_path: str, answer_type: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "fieldPath": field_path, "answerPath": answer_path,
            "answerType": answer_type, "options": [], **extra}


def _options(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"value": c["id"], "label": c["name"]} for c in candidates]


def validate(draft: dict[str, Any], cat: Catalog) -> list[dict[str, Any]]:
    """Return open issues in priority order: customer, items, money, dates."""

    issues: list[dict[str, Any]] = []
    cust = draft["customer"]
    if not cust.get("customerId") or cust["customerId"] not in cat.customers:
        spoken = cust.get("spokenName")
        options = _options(cust.get("candidates") or []) or [
            {"value": c.id, "label": c.name} for c in list(cat.customers.values())[:6]]
        if cust.get("matchStatus") == "ambiguous":
            code = "AMBIGUOUS_CUSTOMER"
        else:
            code = "UNKNOWN_CUSTOMER" if spoken else "MISSING_CUSTOMER"
        issues.append(_issue(code, "customer", "customer.customerId", "choice", spoken=spoken, options=options))

    for i, item in enumerate(draft["order"]["items"]):
        base = f"order.items.{i}"
        label = item.get("productName") or item.get("spokenName")
        if not item.get("productId") or item["productId"] not in cat.products:
            options = _options(item.get("candidates") or []) or [
                {"value": p.id, "label": p.name} for p in list(cat.products.values())[:6]]
            code = "AMBIGUOUS_PRODUCT" if item.get("matchStatus") == "ambiguous" else "UNKNOWN_PRODUCT"
            issues.append(_issue(code, base, f"{base}.productId", "choice",
                                 spoken=item.get("spokenName"), options=options))
            continue
        product = cat.products[item["productId"]]
        quantity = item.get("quantity")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            issues.append(_issue("MISSING_QUANTITY", f"{base}.quantity", f"{base}.quantity", "number", item=label))
        unit = item.get("unit")
        if unit is None or not unit_ok(unit, product.base_unit, product.units_per_pack):
            issues.append(_issue(
                "UNIT_MISMATCH", f"{base}.unit", f"{base}.unit", "choice", item=label,
                options=[{"value": u, "label": u} for u in allowed_units(product.base_unit, product.units_per_pack)]))

    for i, col in enumerate(draft["collections"]):
        if col.get("amountPaise") is None:
            issues.append(_issue("MISSING_AMOUNT", f"collections.{i}.amountPaise",
                                 f"collections.{i}.amountRupees", "number"))
        if col.get("kind") == "promised" and not col.get("dueDate"):
            issues.append(_issue("AMBIGUOUS_DATE", f"collections.{i}.dueDate",
                                 f"collections.{i}.dueDate", "date", what=col.get("dueText") or ""))

    for i, com in enumerate(draft["commitments"]):
        if not com.get("dueDate"):
            issues.append(_issue("AMBIGUOUS_DATE", f"commitments.{i}.dueDate",
                                 f"commitments.{i}.dueDate", "date",
                                 what=com.get("description") or com.get("dueText") or ""))

    order = draft["order"]
    if order.get("deliveryText") and not order.get("deliveryDate") and order["items"]:
        issues.append(_issue("AMBIGUOUS_DATE", "order.deliveryDate", "order.deliveryDate", "date",
                             what=order["deliveryText"]))
    return issues


# --------------------------------------------------------------------------- patch

_PRIORITIES = {"low", "normal", "high"}
_ACTIONS = {"visit", "call", "payment_followup", "send_material", "stock_followup", "other"}
_LISTS = {"order.items": ("order", "items"), "collections": ("collections",),
          "commitments": ("commitments",), "complaints": ("complaints",)}


def _list_ref(draft: dict[str, Any], key: str) -> list[dict[str, Any]]:
    ref: Any = draft
    for part in _LISTS[key]:
        ref = ref[part]
    return ref


def _at(draft: dict[str, Any], key: str, index: str) -> dict[str, Any]:
    items = _list_ref(draft, key)
    i = int(index)
    if not 0 <= i < len(items):
        raise OpError(f"No entry {key}.{index}")
    return items[i]


def _as_int(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise OpError("Value must be a number") from None
    if number != int(number):
        raise OpError("Value must be a whole number")
    return int(number)


def _as_date(value: Any, cat: Catalog) -> str:
    text = str(value or "")
    resolved = parse_iso(text, cat.today) or resolve_date_text(text, cat.today)
    if resolved is None:
        raise OpError("Date could not be determined; give a specific date")
    return resolved.isoformat()


def _apply_set(draft: dict[str, Any], path: str, value: Any, cat: Catalog) -> tuple[Any, Any]:
    """Apply one whitelisted ``set``. Returns (old, new) in display terms."""

    cust = draft["customer"]
    if path == "customer.customerId":
        if value not in cat.customers:
            raise OpError("Unknown customer")
        old = cust.get("name")
        _set_customer(cust, cat.customers[value])
        return old, cust["name"]
    if path == "customer.name":
        res = resolve(str(value), cat.customer_entries)
        old = cust.get("name")
        if res.status == "resolved" and res.best:
            _set_customer(cust, cat.customers[res.best.id])
            return old, cust["name"]
        cust.update(spokenName=str(value), customerId=None, name=None, matchStatus=res.status,
                    candidates=[c.as_dict() for c in res.candidates])
        return old, str(value)
    if path == "order.deliveryDate":
        old = draft["order"].get("deliveryDate")
        draft["order"]["deliveryDate"] = _as_date(value, cat)
        return old, draft["order"]["deliveryDate"]

    m = re.fullmatch(r"order\.items\.(\d+)\.(productId|product|quantity|unit)", path)
    if m:
        item = _at(draft, "order.items", m.group(1))
        field = m.group(2)
        if field in {"productId", "product"}:
            old = item.get("productName") or item.get("spokenName")
            if field == "productId":
                if value not in cat.products:
                    raise OpError("Unknown product")
                _set_product(item, cat.products[value])
            else:
                res = resolve(str(value), cat.product_entries)
                item["spokenName"] = str(value)
                if res.status == "resolved" and res.best:
                    _set_product(item, cat.products[res.best.id])
                else:
                    item.update(productId=None, productName=None, matchStatus=res.status,
                                candidates=[c.as_dict() for c in res.candidates], unitPricePaise=None)
            return old, item.get("productName") or str(value)
        if field == "quantity":
            quantity = _as_int(value)
            if quantity <= 0:
                raise OpError("Quantity must be positive")
            old, item["quantity"] = item.get("quantity"), quantity
            return old, quantity
        unit = normalize_unit(str(value))
        if unit is None:
            raise OpError("Unknown unit")
        old = item.get("unit")
        if item.get("productId"):
            product = cat.products[item["productId"]]
            if unit == "piece":
                unit = product.base_unit
            if not unit_ok(unit, product.base_unit, product.units_per_pack):
                raise OpError(f"{product.name} is not sold by {unit}")
            item["unitPricePaise"] = unit_price(product.price_paise, unit, product.base_unit, product.units_per_pack)
        item["unit"] = unit
        return old, unit

    m = re.fullmatch(r"collections\.(\d+)\.(amountRupees|dueDate|kind)", path)
    if m:
        col = _at(draft, "collections", m.group(1))
        field = m.group(2)
        if field == "amountRupees":
            try:
                rupees = float(value)
            except (TypeError, ValueError):
                raise OpError("Amount must be a number") from None
            if rupees < 0:
                raise OpError("Amount cannot be negative")
            old = None if col.get("amountPaise") is None else col["amountPaise"] / 100
            col["amountPaise"] = round(rupees * 100)
            return old, rupees
        if field == "kind":
            if value not in {"received", "promised"}:
                raise OpError("Kind must be received or promised")
            old, col["kind"] = col["kind"], value
            return old, value
        old, col["dueDate"] = col.get("dueDate"), _as_date(value, cat)
        return old, col["dueDate"]

    m = re.fullmatch(r"commitments\.(\d+)\.(dueDate|description|priority|actionType)", path)
    if m:
        com = _at(draft, "commitments", m.group(1))
        field = m.group(2)
        if field == "dueDate":
            old, com["dueDate"] = com.get("dueDate"), _as_date(value, cat)
            return old, com["dueDate"]
        if field == "priority" and value not in _PRIORITIES:
            raise OpError("Priority must be low, normal or high")
        if field == "actionType" and value not in _ACTIONS:
            raise OpError("Unknown action type")
        if field == "description" and not str(value or "").strip():
            raise OpError("Description cannot be empty")
        old, com[field] = com.get(field), value
        return old, value

    m = re.fullmatch(r"complaints\.(\d+)\.description", path)
    if m:
        complaint = _at(draft, "complaints", m.group(1))
        if not str(value or "").strip():
            raise OpError("Description cannot be empty")
        old, complaint["description"] = complaint["description"], str(value)
        return old, complaint["description"]
    raise OpError("This field cannot be changed by voice")


def _apply_remove(draft: dict[str, Any], path: str) -> Any:
    m = re.fullmatch(r"(order\.items|collections|commitments|complaints)\.(\d+)", path)
    if not m:
        raise OpError("Only list entries can be removed")
    entries = _list_ref(draft, m.group(1))
    _at(draft, m.group(1), m.group(2))
    removed = entries.pop(int(m.group(2)))
    return removed.get("productName") or removed.get("spokenName") or removed.get("description") or "entry"


def normalize_path(path: str) -> str:
    """Accept the spellings a model may use for the same location: ``/order/items/0/quantity``,
    ``order.items[0].quantity``. The whitelist in ``_apply_set`` still decides what is allowed."""

    text = re.sub(r"\[(\d+)\]", r".\1", path.strip())
    return text.replace("/", ".").strip(".")


def apply_ops(draft: dict[str, Any], ops: list[PatchOp], cat: Catalog
              ) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Apply ops to a copy of ``draft``. Returns (new_draft, changes, failures)."""

    working = copy.deepcopy(draft)
    changes: list[dict[str, Any]] = []
    failures: list[str] = []
    for op in ops:
        path = normalize_path(op.path)
        try:
            if op.op == "remove":
                changes.append({"path": path, "old": _apply_remove(working, path), "new": None})
            else:
                old, new = _apply_set(working, path, op.value, cat)
                changes.append({"path": path, "old": old, "new": new})
        except OpError as error:
            failures.append(f"{path}: {error}")
    return finalize(working), changes, failures


def llm_view(draft: dict[str, Any]) -> dict[str, Any]:
    """Compact, indexed view of the draft shown to the model when interpreting a correction."""

    return {
        "customer": draft["customer"].get("name") or draft["customer"].get("spokenName"),
        "items": [{"index": i, "product": it.get("productName") or it.get("spokenName"),
                   "quantity": it.get("quantity"), "unit": it.get("unit")}
                  for i, it in enumerate(draft["order"]["items"])],
        "deliveryDate": draft["order"].get("deliveryDate"),
        "collections": [{"index": i, "kind": c["kind"], "amountRupees": None if c["amountPaise"] is None else c["amountPaise"] / 100,
                         "dueDate": c.get("dueDate")} for i, c in enumerate(draft["collections"])],
        "commitments": [{"index": i, "type": c["actionType"], "description": c["description"], "dueDate": c.get("dueDate")}
                        for i, c in enumerate(draft["commitments"])],
        "complaints": [{"index": i, "description": c["description"]} for i, c in enumerate(draft["complaints"])],
    }
