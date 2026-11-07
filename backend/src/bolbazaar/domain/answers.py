"""Deterministic interpretation of a short spoken or typed answer to the open question.

Handled here before any model call: it is free, instant and predictable. Anything this
cannot interpret falls through to the reasoning model.
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from ..schemas_llm import PatchOp
from .dates import find_date_phrase, resolve_date_text
from .draft import NEW_PRODUCT, Catalog
from .normalize import first_number, normalize, replace_number_words
from .units import BASE_UNITS, normalize_unit

_FILLER = {"the", "one", "wala", "wali", "vala", "vali", "ka", "ki", "ke", "please", "hai", "ho",
           "it", "is", "a", "an", "wale", "vaale", "वाला", "वाली", "को", "का", "की", "हाँ", "haan", "yes",
           "i", "mean", "meant", "matlab", "woh", "wo", "that", "this", "yeh", "ye"}
_ORDINALS = {"first": 0, "pehla": 0, "pehli": 0, "1": 0, "second": 1, "dusra": 1, "doosra": 1, "2": 1,
             "third": 2, "teesra": 2, "3": 2, "fourth": 3, "4": 3}


_ADD_WORDS = {"add", "new", "naya", "nayi", "naye", "nai", "jodo", "jod", "jodna", "banao", "bana", "create", "dalo",
              "daalo", "daal", "catalogue", "catalog", "नया", "नई", "नये", "जोड़ो", "जोड़", "जोडो", "बनाओ", "डालो", "कैटलॉग"}
_RUPEE_WORDS = {"rupaye", "rupee", "rupees", "rupya", "rupay", "rs", "inr", "रुपये", "रुपए", "रुपया"}


def _price_in(utterance: str) -> float | None:
    """The number next to a rupee word; else the only number in the sentence; never a guess between several."""
    tokens = replace_number_words(normalize(utterance)).split()
    for i, tok in enumerate(tokens):
        if tok in _RUPEE_WORDS:
            for near in (tokens[i - 1] if i else None, tokens[i + 1] if i + 1 < len(tokens) else None):
                if near and near.replace('.', '', 1).isdigit():
                    return float(near)
    numbers = [t for t in tokens if t.replace('.', '', 1).isdigit()]
    return float(numbers[0]) if len(numbers) == 1 else None


def interpret_new_product(utterance: str, issue: dict[str, Any]) -> list[PatchOp] | None:
    """"add chawal, 60 rupaye kilo" -> mark the line as a new catalogue item, and set its price and unit if said."""
    if not issue.get("canCreate"):
        return None
    tokens = normalize(utterance).split()
    if not any(t in _ADD_WORDS for t in tokens):
        return None
    base = issue["answerPath"].rsplit(".", 1)[0]
    ops = [PatchOp(op="set", path=issue["answerPath"], value=NEW_PRODUCT)]
    unit = next((u for u in (normalize_unit(t) for t in tokens) if u in BASE_UNITS), None)
    if unit:
        ops.append(PatchOp(op="set", path=f"{base}.unit", value=unit))
    price = _price_in(utterance)
    if price:
        ops.append(PatchOp(op="set", path=f"{base}.newProductPrice", value=price))
    return ops


def _match_option(utterance: str, options: list[dict[str, str]]) -> str | None:
    options = [o for o in options if o["value"] != NEW_PRODUCT]  # adding is an explicit act, never a fuzzy match
    tokens = [t for t in normalize(utterance).split() if t not in _FILLER]
    if not tokens or not options:
        return None
    if len(tokens) <= 2:
        for token in tokens:
            if token in _ORDINALS and _ORDINALS[token] < len(options):
                return options[_ORDINALS[token]]["value"]
    scored: list[tuple[float, str]] = []
    for option in options:
        label_tokens = normalize(option["label"]).split()
        hits = 0
        for token in tokens:
            unit = normalize_unit(token)
            if unit and unit == option["value"]:
                hits += 1
            elif any(fuzz.ratio(token, lt) >= 85 for lt in label_tokens):
                hits += 1
        scored.append((hits / len(tokens), option["value"]))
    scored.sort(reverse=True)
    best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if best[0] >= 0.5 and best[0] > runner_up:
        return best[1]
    return None


def interpret_answer(utterance: str, issue: dict[str, Any], cat: Catalog) -> list[PatchOp] | None:
    kind = issue["answerType"]
    path = issue["answerPath"]
    if issue.get("code") in {"UNKNOWN_PRODUCT", "AMBIGUOUS_PRODUCT"}:
        added = interpret_new_product(utterance, issue)
        if added:
            return added
    if kind == "choice":
        value = _match_option(utterance, issue.get("options") or [])
    elif kind == "number":
        value = _price_in(utterance) if issue.get("code") == "NEW_PRODUCT_PRICE" else first_number(utterance)
    elif kind == "date":
        phrase = find_date_phrase(utterance) or utterance
        resolved = resolve_date_text(phrase, cat.today)
        value = resolved.isoformat() if resolved else None
    else:
        value = None
    if value is None:
        return None
    return [PatchOp(op="set", path=path, value=value)]
