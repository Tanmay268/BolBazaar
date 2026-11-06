"""Fuzzy resolution of spoken names against a retailer or product list.

Outcomes are deliberately conservative: a tie or a weak match is *ambiguous* and becomes a
clarification question, never a silent guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .normalize import normalize

RESOLVE_AT = 85
MARGIN = 8
CONSIDER_AT = 55
PARTIAL_CAP = 90  # partial/subset matches never outrank an exact name or alias (100)


@dataclass(frozen=True)
class Entry:
    id: str
    name: str
    names: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    score: int

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "score": self.score}


@dataclass
class Resolution:
    status: str  # resolved | ambiguous | unknown
    best: Candidate | None = None
    candidates: list[Candidate] = field(default_factory=list)


def _score(query: str, entry: Entry) -> int:
    best = 0
    for name in entry.names:
        n = normalize(name)
        if not n:
            continue
        if n == query:
            return 100
        score = min(PARTIAL_CAP, int(max(fuzz.token_set_ratio(query, n), fuzz.ratio(query, n))))
        best = max(best, score)
    return best


def resolve(spoken: str | None, entries: list[Entry]) -> Resolution:
    query = normalize(spoken)
    if not query or not entries:
        return Resolution("unknown", None, [])
    scored = sorted(((_score(query, e), e) for e in entries), key=lambda x: (-x[0], x[1].name))
    top = scored[0][0]
    suggestions = [Candidate(e.id, e.name, s) for s, e in scored[:6]]
    if top < CONSIDER_AT:
        return Resolution("unknown", None, suggestions)
    close = [Candidate(e.id, e.name, s) for s, e in scored if s >= CONSIDER_AT and top - s <= 30][:5]
    second = scored[1][0] if len(scored) > 1 else 0
    if top >= RESOLVE_AT and top - second >= MARGIN:
        return Resolution("resolved", close[0], close)
    return Resolution("ambiguous", None, close)
