"""Deterministic interpretation of a short spoken or typed answer to the open question.

Handled here before any model call: it is free, instant and predictable. Anything this
cannot interpret falls through to the reasoning model.
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from ..schemas_llm import PatchOp
from .dates import find_date_phrase, resolve_date_text
from .draft import Catalog
from .normalize import first_number, normalize
from .units import normalize_unit

_FILLER = {"the", "one", "wala", "wali", "vala", "vali", "ka", "ki", "ke", "please", "hai", "ho",
           "it", "is", "a", "an", "wale", "vaale", "वाला", "वाली", "को", "का", "की", "हाँ", "haan", "yes",
           "i", "mean", "meant", "matlab", "woh", "wo", "that", "this", "yeh", "ye"}
_ORDINALS = {"first": 0, "pehla": 0, "pehli": 0, "1": 0, "second": 1, "dusra": 1, "doosra": 1, "2": 1,
             "third": 2, "teesra": 2, "3": 2, "fourth": 3, "4": 3}


def _match_option(utterance: str, options: list[dict[str, str]]) -> str | None:
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
    if kind == "choice":
        value = _match_option(utterance, issue.get("options") or [])
    elif kind == "number":
        value = first_number(utterance)
    elif kind == "date":
        phrase = find_date_phrase(utterance) or utterance
        resolved = resolve_date_text(phrase, cat.today)
        value = resolved.isoformat() if resolved else None
    else:
        value = None
    if value is None:
        return None
    return [PatchOp(op="set", path=path, value=value)]
