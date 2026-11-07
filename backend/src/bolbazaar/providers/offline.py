"""Deterministic offline providers: no network, no keys.

They exist so tests, demos and judging survive bad Wi-Fi or exhausted credits. They are
NOT the production extractor: the offline reasoner is a rule-based approximation covering
Latin-script English/Hinglish only.
"""

from __future__ import annotations

import io
import math
import re
import struct
import wave
from typing import Any

from rapidfuzz import fuzz

from ..domain.dates import find_date_phrase
from ..domain.languages import LanguageProfile
from ..domain.normalize import first_number, normalize, replace_number_words
from ..schemas_llm import (
    CollectionX, CommitmentX, CompetitorX, ComplaintX, CustomerX, Extraction, ItemX,
    ManagerQuery, OrderX, PatchOp, PatchResult, VisitX,
)
from .base import ExtractionContext, Speech, Transcript

DEMO_TRANSCRIPTS = {
    "hinglish": (
        "Sharma ji ne aaj bees packet Parle-G liye aur das bottle Real juice kal dena hai. "
        "Woh paanch hazaar rupaye kal dega. "
        "Biscuit ke kuch packets damaged the, uski complaint hai. "
        "Agle Monday ko dobara visit karna hai."
    ),
    "en-IN": (
        "Visited Gupta Provision Store today. They ordered 12 packets of Britannia Good Day and "
        "6 bottles of Maaza Mango for tomorrow. He will pay 3000 rupees next Monday. "
        "Please send the price list by tomorrow."
    ),
}


class OfflineSTT:
    """Reads a ``TRANSCRIPT: ...`` text fixture or returns a canned demo transcript."""

    def transcribe(self, wav: bytes, profile: LanguageProfile) -> Transcript:
        head = wav[:4096].decode("utf-8", errors="ignore").strip()
        match = re.fullmatch(r"TRANSCRIPT\s*:\s*(.{8,})", head, flags=re.S | re.I)
        text = match.group(1).strip() if match else DEMO_TRANSCRIPTS.get(profile.code, DEMO_TRANSCRIPTS["hinglish"])
        return Transcript(text=text, language=profile.code, model="offline:stt", request_id="offline-stt")


class OfflineTTS:
    """A short two-tone chirp so the playback path is audible and testable."""

    def synthesize(self, text: str, profile: LanguageProfile) -> Speech:
        rate, buf = 16000, io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            frames = bytearray()
            for freq, seconds in ((660, 0.12), (880, 0.18)):
                for n in range(int(rate * seconds)):
                    envelope = min(1.0, n / 400, (int(rate * seconds) - n) / 400)
                    frames += struct.pack("<h", int(6000 * envelope * math.sin(2 * math.pi * freq * n / rate)))
            out.writeframes(bytes(frames))
        return Speech(audio=buf.getvalue(), content_type="audio/wav", model="offline:tts", voice="offline")


# --------------------------------------------------------------------------- extraction

_UNIT_RX = r"(packets?|pkts?|bottles?|botals?|kgs?|kilos?|cases?|boxes|box|pcs|pieces?|peti)"
_ITEM_RX = re.compile(rf"(?<![\w₹.])(\d+)\s*{_UNIT_RX}?\b", re.I)
_STOP = {"aur", "and", "bhi", "ko", "ke", "ka", "ki", "liye", "for", "chahiye", "diye", "liya", "dena", "do",
         "deliver", "on", "by", "kal", "aaj", "parso", "today", "tomorrow", "please", "hai", "the", "he",
         "she", "they", "will", "wala", "from", "at", "mein", "me", "se", "order", "ordered", "ne", "delivery",
         "next", "agle", "in", "to", "bheje", "bhejna", "need", "needs", "want", "wants", "also", "plus", "is"}
_NOT_ITEM = {"rupees", "rupee", "rupaye", "rs", "din", "days", "day", "baje", "hafte", "week", "tarikh",
             "percent", "ghante", "hours", "minutes", "of"}
_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:rupees?|rupaye|rs\.?|₹|inr)\b|(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)", re.I)
_PROMISE = re.compile(r"\b(will pay|will give|dega|denge|dene wale|promised?|promises)\b", re.I)
_RECEIVED = re.compile(r"\b(paid|received|gave|diya|collected|mila|de diya)\b", re.I)
_COMPLAINT = re.compile(r"complaint|shikayat|shikayat|damaged|kharab|expired|leak|problem|issue|late delivery", re.I)
_COMPETITOR = re.compile(r"competitor|competition|rival", re.I)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def _find_customer(text: str, context: ExtractionContext) -> str | None:
    folded = normalize(text)
    best: tuple[int, str] | None = None
    for customer in context.customers:
        for name in (customer["name"], *customer.get("aliases", [])):
            n = normalize(name)
            if n and re.search(rf"(?<!\S){re.escape(n)}(?!\S)", folded) and (best is None or len(n) > best[0]):
                best = (len(n), name)
    return best[1] if best else None


def _items(text: str) -> list[ItemX]:
    items: list[ItemX] = []
    for m in _ITEM_RX.finditer(text):
        before = text[:m.start()].rstrip().casefold()
        if before.endswith(("₹", "rs", "rs.", "inr")):
            continue
        tail = re.match(r"\s+(?:of\s+)?((?:[A-Za-z][A-Za-z\-]*)(?:\s+[A-Za-z][A-Za-z\-]*){0,5})", text[m.end():])
        if not tail:
            continue
        words: list[str] = []
        for word in tail.group(1).split():
            if word.casefold() in _STOP or len(words) == 3:
                break
            words.append(word)
        if not words or words[0].casefold() in _NOT_ITEM:
            continue
        evidence = text[m.start(): m.end() + (tail.end() if tail else 0)].strip()
        items.append(ItemX(spoken_name=" ".join(words), quantity=int(m.group(1)),
                           unit=(m.group(2) or None), confidence=0.8, evidence=evidence))
    return items


def _delivery_text(text: str) -> str | None:
    phrase = r"(day after tomorrow|tomorrow|today|kal|aaj|parso|(?:next\s+|agle\s+)?monday|next week)"
    after = re.search(phrase + r"\s+(?:dena|deliver\w*|bhej\w*)", text, re.I)
    before = re.search(r"(?:deliver\w*|send|bhej\w*|supply)\s+(?:on\s+|by\s+)?" + phrase, text, re.I)
    for_ = re.search(r"\bfor\s+(tomorrow|today)\b", text, re.I)
    found = after or before or for_
    return found.group(1) if found else None


class OfflineReasoner:
    def extract(self, transcript: str, context: ExtractionContext) -> Extraction:
        text = replace_number_words(transcript)
        customer = _find_customer(text, context)
        items = _items(text)
        collections: list[CollectionX] = []
        complaints: list[ComplaintX] = []
        competitors: list[CompetitorX] = []
        commitments: list[CommitmentX] = []

        for sentence in _sentences(text):
            money = _MONEY.search(sentence)
            if money and not _items(sentence):
                amount = float((money.group(1) or money.group(2)).replace(",", ""))
                promised = bool(_PROMISE.search(sentence)) or (
                    not _RECEIVED.search(sentence) and find_date_phrase(sentence) is not None)
                due = find_date_phrase(sentence) if promised else None
                collections.append(CollectionX(kind="promised" if promised else "received", amount_rupees=amount,
                                               due_text=due, due_date=None, evidence=sentence))
                if promised:
                    commitments.append(CommitmentX(
                        action_type="payment_followup", description=f"Collect ₹{amount:,.0f}",
                        due_text=due, due_date=None, priority="normal", evidence=sentence))
                continue
            if _COMPLAINT.search(sentence):
                lowered = sentence.casefold()
                category = ("delivery" if "late" in lowered else "pricing" if "price" in lowered
                            else "product_quality" if re.search(r"damag|kharab|expired|leak", lowered) else "other")
                complaints.append(ComplaintX(category=category, description=sentence.rstrip("."),
                                             product_spoken_name=None, evidence=sentence))
            if _COMPETITOR.search(sentence):
                competitors.append(CompetitorX(competitor="competitor", note=sentence.rstrip(".")))
            lowered = sentence.casefold()
            action = None
            if re.search(r"visit again|dobara visit|visit karna|come again|dobara aana", lowered):
                action = "visit"
            elif re.search(r"call back|callback|\bcall\b", lowered):
                action = "call"
            elif re.search(r"price list|catalogue|catalog|scheme|sample", lowered) and re.search(r"send|bhej", lowered):
                action = "send_material"
            elif re.search(r"stock", lowered) and re.search(r"check|follow", lowered):
                action = "stock_followup"
            if action:
                commitments.append(CommitmentX(
                    action_type=action, description=sentence.rstrip("."), due_text=find_date_phrase(sentence),
                    due_date=None, priority="high" if re.search(r"urgent|jaldi", lowered) else "normal",
                    evidence=sentence))

        summary = " ".join(transcript.split())[:240]
        return Extraction(
            customer=CustomerX(spoken_name=customer, confidence=0.9 if customer else 0.0, evidence=customer or ""),
            visit=VisitX(purpose="order" if items else "visit", summary=summary),
            order=OrderX(items=items, delivery_text=_delivery_text(text) if items else None, delivery_date=None),
            collections=collections, complaints=complaints, competitor_notes=competitors, commitments=commitments,
        )

    def patch(self, draft_view: dict[str, Any], utterance: str, context: ExtractionContext) -> PatchResult:
        text = replace_number_words(utterance)
        folded = normalize(text)
        items = draft_view.get("items", [])

        def target() -> int | None:
            best: tuple[int, int] | None = None
            for item in items:
                name = normalize(item["product"])
                score = max(int(fuzz.partial_ratio(name, folded)),
                            max((int(fuzz.ratio(t, n)) for t in folded.split() for n in name.split()), default=0))
                if score >= 80 and (best is None or score > best[0]):
                    best = (score, item["index"])
            return best[1] if best else None

        if re.search(r"\b(remove|cancel|hata|delete|drop)\b", folded):
            idx = target()
            if idx is not None:
                return PatchResult(ops=[PatchOp(op="remove", path=f"order.items.{idx}", value=None)], unsupported=[])
        number = first_number(text)
        if number is not None and re.search(r"\b(make|change|set|update|badal|kar do|karo|quantity|qty|instead)\b", folded):
            idx = target()
            if idx is not None:
                return PatchResult(ops=[PatchOp(op="set", path=f"order.items.{idx}.quantity", value=float(number))],
                                   unsupported=[])
        if re.search(r"deliver|delivery|dena", folded):
            phrase = find_date_phrase(text)
            if phrase:
                return PatchResult(ops=[PatchOp(op="set", path="order.deliveryDate", value=phrase)], unsupported=[])
        return PatchResult(ops=[], unsupported=[utterance])

    def parse_catalogue(self, text: str):
        """Rule-based fallback: segments split on commas / 'aur' / newlines; 'chawal 60 rupaye kilo' -> Chawal, kg, 60."""
        from ..domain.units import BASE_UNITS, normalize_unit
        from ..schemas_llm import CatalogueExtraction, CatalogueItemX
        stop = {"add", "karo", "naya", "nayi", "item", "items", "product", "catalogue", "mein", "me", "ka", "ki", "ke", "hai",
                "per", "ek", "one", "price", "rate", "at", "for", "each", "every", "rupaye", "rupees", "rupee", "rs", "inr", "aur", "and"}
        rupee = {"rupaye", "rupees", "rupee", "rs", "inr", "rupya"}
        items = []
        for seg in re.split(r"[,;\n]+|\s+(?:aur|and)\s+", text, flags=re.I):
            words = seg.split()
            if not words:
                continue
            norm = replace_number_words(normalize(seg)).split()
            unit = next((u for u in (normalize_unit(w) for w in norm) if u in BASE_UNITS), None)
            price = None
            for i, tok in enumerate(norm):
                if tok in rupee:
                    near = [norm[j] for j in (i - 1, i + 1) if 0 <= j < len(norm)]
                    price = next((float(n) for n in near if n.replace('.', '', 1).isdigit()), None)
                    if price is not None:
                        break
            if price is None:
                nums = [t for t in norm if t.replace('.', '', 1).isdigit()]
                price = float(nums[0]) if len(nums) == 1 else None
            name_words = []
            for w in words:
                lw = normalize(w)
                if not lw or lw in stop or replace_number_words(lw).replace('.', '', 1).isdigit() or normalize_unit(lw):
                    if name_words and (lw.replace('.', '', 1).isdigit() or normalize_unit(lw) or lw in rupee):
                        break
                    continue
                name_words.append(w.strip(".,;:!?"))
            name = " ".join(name_words).strip()
            if len(name) >= 2:
                items.append(CatalogueItemX(name=name[:1].upper() + name[1:], unit=unit, price_rupees=price,
                                            units_per_pack=None, aliases=[], evidence=seg.strip()))
        return CatalogueExtraction(items=items)

    def parse_manager_query(self, text: str) -> ManagerQuery:
        t = normalize(text)
        days = first_number(t)
        if re.search(r"overdue|payment|baaki|outstanding|collection", t):
            return ManagerQuery(intent="overdue_payments", days=None)
        if re.search(r"not ordered|haven t ordered|havent ordered|inactive|order nahi|no order", t):
            return ManagerQuery(intent="inactive_retailers", days=int(days) if days else 30)
        if re.search(r"follow ?ups?|commitments?|tasks?|pending", t):
            return ManagerQuery(intent="pending_commitments_by_rep", days=None)
        if re.search(r"conversion|convert", t):
            return ManagerQuery(intent="order_conversion_by_rep", days=None)
        if re.search(r"declin|falling|dropping|decrease", t):
            return ManagerQuery(intent="declining_products", days=int(days) if days else 30)
        return ManagerQuery(intent="unsupported", days=None)
