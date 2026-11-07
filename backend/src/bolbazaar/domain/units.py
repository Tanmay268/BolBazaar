"""Unit vocabulary and product/unit compatibility."""

from __future__ import annotations

from .normalize import normalize

_ALIASES = {
    "packet": "packet", "packets": "packet", "pkt": "packet", "pkts": "packet", "पैकेट": "packet",
    "bottle": "bottle", "bottles": "bottle", "botal": "bottle", "botals": "bottle", "बोतल": "bottle",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "किलो": "kg",
    "piece": "piece", "pieces": "piece", "pc": "piece", "pcs": "piece", "नग": "piece",
    "case": "case", "cases": "case", "peti": "case", "पेटी": "case", "carton": "case",
    "cartons": "case", "box": "case", "boxes": "case", "dabba": "case",
}
KNOWN_UNITS = ("packet", "bottle", "kg", "piece", "case")


def normalize_unit(value: str | None) -> str | None:
    if not value:
        return None
    return _ALIASES.get(normalize(value))


def unit_ok(unit: str, base_unit: str, units_per_pack: int | None) -> bool:
    return unit == base_unit or (unit == "case" and bool(units_per_pack))


def allowed_units(base_unit: str, units_per_pack: int | None) -> list[str]:
    return [base_unit, "case"] if units_per_pack else [base_unit]


def unit_price(price_paise: int, unit: str | None, base_unit: str, units_per_pack: int | None) -> int | None:
    """Price per ordered unit in paise, or ``None`` when the unit does not fit the product."""

    if unit is None or not unit_ok(unit, base_unit, units_per_pack):
        return None
    if unit == "case" and unit != base_unit:
        return price_paise * (units_per_pack or 0)
    return price_paise
