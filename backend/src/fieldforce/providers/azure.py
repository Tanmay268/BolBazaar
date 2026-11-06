"""Azure OpenAI reasoner using strict JSON-schema structured output.

Model output is validated against the typed contracts in ``schemas_llm`` and then again by
domain rules. Prompts never include other tenants' data.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, TypeVar
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..schemas_llm import CallReply, Extraction, MANAGER_INTENTS, ManagerQuery, PatchResult, strict_schema
from .base import CallContext, ExtractionContext, ProviderError

M = TypeVar("M", bound=BaseModel)

EXTRACT_SYSTEM = """You turn a field sales representative's spoken visit report into structured data.
The speech may be Hindi, English, Hinglish, Tamil or Marathi, possibly with transcription errors.
Reference date: {today} ({weekday}). Rules:
- Extract only what was said. Never invent customers, products, quantities, amounts or dates.
- spoken_name is the name as heard; write brand names in Latin script when obvious. The lists of known
  retailers and products are vocabulary hints only; do not force a match.
- Convert spoken number words (bees, paanch hazaar, twenty) to numbers. quantity is null if not stated.
- Money is in rupees. A payment the customer WILL make is kind=promised and ALSO needs a commitment with
  action_type=payment_followup and the same due date. A payment already made is kind=received.
- Put the exact date phrase in due_text. Set due_date (YYYY-MM-DD) only if the reference date lets you
  compute it with certainty; otherwise null. 'kal' means tomorrow for future events. "next week" is null.
- Every distinct product with a quantity is its own order item, even when several share one sentence
  or one delivery date. Never drop an item; never mention an item only in the summary.
- When and how the order will be delivered ("kal bhej dena", "deliver tomorrow") belongs only in
  order.delivery_text/delivery_date. Do NOT also create a commitment for it.
- Every promised payment MUST have a matching payment_followup commitment. Do not skip it.
- Complaints, competitor remarks and follow-ups (visit again, call back, send material, stock check)
  go in their own lists. confidence is 0..1. evidence is the exact phrase you used.
Known retailers: {customers}
Known products: {products}"""

PATCH_SYSTEM = """The representative is correcting a draft visit record. Reply with edit operations only.
Allowed paths (N is the index shown in the draft):
customer.name | order.items.N.product | order.items.N.quantity | order.items.N.unit | order.deliveryDate |
collections.N.amountRupees | collections.N.dueDate | collections.N.kind |
commitments.N.dueDate | commitments.N.description | commitments.N.priority | complaints.N.description
Removable: order.items.N, collections.N, commitments.N, complaints.N (op=remove, value=null).
Values: product is the spoken product name; quantity/amount are numbers; dates are YYYY-MM-DD or a
phrase like 'next Monday'. Reference date: {today} ({weekday}). Anything that does not fit goes in
unsupported, verbatim. Never guess an index; if unclear, put the request in unsupported."""

CALL_SYSTEM = """You classify ONE reply from a retailer on a payment-reminder phone call. Do not write the agent's
next line. Reference date: {today} ({weekday}). The retailer {customer} owes about Rs {outstanding}.
The agent is currently at stage "{stage}" (purpose = just asked when they will pay, amount = asked how much,
date = asked which date, confirm = asked "is that right?", callback = asked when to call back).
Speech may be Hindi, English or Hinglish and may contain transcription errors. Classify intent as one of:
will_pay (says they will pay, or just gives a date/amount in answer), partial_pay (will pay only part),
already_paid, dispute (disagrees with the amount, bill or goods), call_later (busy / call back later),
refuse, wrong_person, yes / no (only meaningful at the confirm stage), unclear.
Rules: copy amounts as numbers in rupees only if stated (else null). Put the exact date phrase in date_text
(for example "kal", "agle Monday"); set date (YYYY-MM-DD) only if the reference date lets you compute it with
certainty, else null; "next week" or "month end" is NOT a certain date. note = a short paraphrase of any
complaint or reason, else null. Never invent an amount or a date."""

MANAGER_SYSTEM = (
    "Map the sales manager's question to exactly one intent from: " + ", ".join(MANAGER_INTENTS) +
    ". Use 'unsupported' if none fits. Set days only if the question states a number of days, else null."
)


class AzureReasoner:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        for name in ("azure_openai_endpoint", "azure_openai_api_key", "azure_openai_deployment"):
            if not getattr(settings, name):
                raise ProviderError("configuration", f"{name.upper()} is required for live reasoning")
        self.settings = settings
        self._http = httpx.Client(timeout=settings.azure_openai_timeout_ms / 1000, transport=transport)
        self._sleep = sleep

    def _url_and_extra(self) -> tuple[str, dict[str, Any]]:
        s = self.settings
        endpoint = s.azure_openai_endpoint.rstrip("/")
        if (urlsplit(endpoint).hostname or "").endswith(".services.ai.azure.com"):
            return f"{endpoint}/openai/v1/chat/completions", {"model": s.azure_openai_deployment}
        deployment = quote(s.azure_openai_deployment, safe="")
        return (f"{endpoint}/openai/deployments/{deployment}/chat/completions"
                f"?api-version={quote(s.azure_openai_api_version, safe='')}"), {}

    def _chat(self, system: str, user: str, model: type[M], name: str) -> M:
        url, extra = self._url_and_extra()
        payload = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": name, "strict": True, "schema": strict_schema(model)}},
            **extra,
        }
        headers = {"api-key": self.settings.azure_openai_api_key, "Content-Type": "application/json"}
        last: ProviderError | None = None
        for attempt in range(self.settings.azure_openai_max_retries + 1):
            try:
                response = self._http.post(url, headers=headers, content=json.dumps(payload, ensure_ascii=False))
            except httpx.HTTPError:
                last = ProviderError("network", f"Azure OpenAI {name} request failed", retryable=True)
            else:
                if response.status_code == 200:
                    return self._parse(response, model, name)
                retryable = response.status_code == 429 or response.status_code >= 500
                last = ProviderError("rate_limit" if response.status_code == 429 else "http",
                                     f"Azure OpenAI {name} failed with status {response.status_code}",
                                     retryable=retryable)
            if not last.retryable or attempt >= self.settings.azure_openai_max_retries:
                raise last
            self._sleep(min(0.5 * (2 ** attempt), 4.0))
        raise last or ProviderError("unknown", f"Azure OpenAI {name} failed")

    @staticmethod
    def _parse(response: httpx.Response, model: type[M], name: str) -> M:
        try:
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
            return model.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError("invalid_response", f"Azure OpenAI {name} returned invalid output") from exc

    def extract(self, transcript: str, context: ExtractionContext) -> Extraction:
        system = EXTRACT_SYSTEM.format(
            today=context.today.isoformat(), weekday=context.weekday,
            customers=json.dumps(context.customers, ensure_ascii=False),
            products=json.dumps(context.products, ensure_ascii=False))
        return self._chat(system, transcript, Extraction, "visit_extraction")

    def patch(self, draft_view: dict[str, Any], utterance: str, context: ExtractionContext) -> PatchResult:
        system = PATCH_SYSTEM.format(today=context.today.isoformat(), weekday=context.weekday)
        user = json.dumps({"draft": draft_view, "utterance": utterance}, ensure_ascii=False)
        return self._chat(system, user, PatchResult, "draft_patch")

    def parse_manager_query(self, text: str) -> ManagerQuery:
        return self._chat(MANAGER_SYSTEM, text, ManagerQuery, "manager_query")

    def interpret_call_reply(self, text: str, context: CallContext) -> CallReply:
        system = CALL_SYSTEM.format(today=context.today.isoformat(), weekday=context.weekday, customer=context.customer,
                                    outstanding=f"{context.outstanding_rupees:,.0f}", stage=context.stage)
        return self._chat(system, text, CallReply, "call_reply")
