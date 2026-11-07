"""Typed contracts for everything the reasoning model may return.

Every field is required (no defaults) so the derived JSON schema satisfies strict
structured-output mode. The model output is still treated as untrusted.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerX(_Strict):
    spoken_name: Optional[str]
    confidence: float
    evidence: str


class VisitX(_Strict):
    purpose: Optional[str]
    summary: str


class ItemX(_Strict):
    spoken_name: str
    quantity: Optional[int]
    unit: Optional[str]
    confidence: float
    evidence: str


class OrderX(_Strict):
    items: list[ItemX]
    delivery_text: Optional[str]
    delivery_date: Optional[str]


class CollectionX(_Strict):
    kind: Literal["received", "promised"]
    amount_rupees: Optional[float]
    due_text: Optional[str]
    due_date: Optional[str]
    evidence: str


class ComplaintX(_Strict):
    category: Literal["product_quality", "delivery", "pricing", "service", "other"]
    description: str
    product_spoken_name: Optional[str]
    evidence: str


class CompetitorX(_Strict):
    competitor: str
    note: str


class CommitmentX(_Strict):
    action_type: Literal["visit", "call", "payment_followup", "send_material", "stock_followup", "other"]
    description: str
    due_text: Optional[str]
    due_date: Optional[str]
    priority: Literal["low", "normal", "high"]
    evidence: str


class Extraction(_Strict):
    customer: CustomerX
    visit: VisitX
    order: OrderX
    collections: list[CollectionX]
    complaints: list[ComplaintX]
    competitor_notes: list[CompetitorX]
    commitments: list[CommitmentX]


class PatchOp(_Strict):
    op: Literal["set", "remove"]
    path: str
    value: Union[str, float, None]


class PatchResult(_Strict):
    ops: list[PatchOp]
    unsupported: list[str]


MANAGER_INTENTS = (
    "overdue_payments",
    "inactive_retailers",
    "pending_commitments_by_rep",
    "order_conversion_by_rep",
    "declining_products",
    "unsupported",
)


class ManagerQuery(_Strict):
    intent: Literal[
        "overdue_payments", "inactive_retailers", "pending_commitments_by_rep",
        "order_conversion_by_rep", "declining_products", "unsupported",
    ]
    days: Optional[int]


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema accepted by strict structured-output mode (closed objects, all required)."""

    schema = model.model_json_schema()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return schema
