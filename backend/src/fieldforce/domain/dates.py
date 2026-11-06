"""Deterministic date resolution for spoken English/Hinglish/Hindi phrases.

Ambiguous phrases ("next week", "after Diwali") resolve to ``None`` so the caller asks the
rep instead of guessing. In a future-oriented business context "kal" means tomorrow.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .normalize import normalize

_WEEKDAYS = {
    "monday": 0, "mon": 0, "somvar": 0, "somwar": 0, "सोमवार": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "mangalvar": 1, "mangalwar": 1, "मंगलवार": 1,
    "wednesday": 2, "wed": 2, "budhvar": 2, "budhwar": 2, "बुधवार": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "guruvar": 3, "guruwar": 3, "brihaspativar": 3,
    "veervar": 3, "गुरुवार": 3,
    "friday": 4, "fri": 4, "shukravar": 4, "shukrawar": 4, "शुक्रवार": 4,
    "saturday": 5, "sat": 5, "shanivar": 5, "shaniwar": 5, "शनिवार": 5,
    "sunday": 6, "sun": 6, "ravivar": 6, "itwar": 6, "raviwar": 6, "रविवार": 6,
}
_TOMORROW = {"tomorrow", "kal", "कल", "நாளை", "उद्या", "udya"}
_TODAY = {"today", "aaj", "आज", "இன்று"}
_DAY_AFTER = {"parso", "parson", "परसों", "परवा"}
_IN_WORDS = {"after", "later", "baad", "बाद", "in", "mein", "me"}

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_N_DAYS = re.compile(r"(\d+)\s*(?:days?|din|दिन)")
_NEXT_WEEK = re.compile(r"next week|agle hafte|agle haphte|अगले हफ्ते|अगले हफ़्ते|this week")

# Used by the offline extractor to cut the date phrase out of a sentence.
_PHRASE = re.compile(
    r"day after tomorrow|next week|agle hafte|(?:in|after)\s+\d+\s+days?|\d+\s+(?:din|days?)\s+(?:baad|later)"
    r"|(?:(?:next|agle)\s+)?(?:" + "|".join(sorted((w for w in _WEEKDAYS if w.isascii() and len(w) > 3), key=len, reverse=True)) + r")"
    r"|tomorrow|today|kal|aaj|parso|parson",
    re.IGNORECASE,
)


def today_in(tz_name: str, now: datetime | None = None) -> date:
    instant = now or datetime.now(timezone.utc)
    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=5, minutes=30)) if tz_name in {"Asia/Kolkata", "Asia/Calcutta"} else timezone.utc
    return instant.astimezone(zone).date()


def day_bounds_utc(tz_name: str, day: date) -> tuple[datetime, datetime]:
    """UTC [start, end) of a calendar day in the organisation's timezone."""

    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=5, minutes=30)) if tz_name in {"Asia/Kolkata", "Asia/Calcutta"} else timezone.utc
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def find_date_phrase(sentence: str) -> str | None:
    match = _PHRASE.search(sentence)
    return match.group(0) if match else None


def _within(target: date, today: date, horizon_days: int) -> date | None:
    offset = (target - today).days
    return target if 0 <= offset <= horizon_days else None


def parse_iso(value: str | None, today: date, horizon_days: int = 180) -> date | None:
    if not value:
        return None
    try:
        return _within(date.fromisoformat(value.strip()[:10]), today, horizon_days)
    except ValueError:
        return None


def resolve_date_text(text: str | None, today: date, horizon_days: int = 180) -> date | None:
    """Return the calendar date a spoken phrase means, or ``None`` if it is not certain."""

    if not text:
        return None
    iso = _ISO.search(text)
    if iso:
        return parse_iso(iso.group(0), today, horizon_days)
    t = normalize(text)
    tokens = set(t.split())
    if _NEXT_WEEK.search(t):
        return None
    if "day after tomorrow" in t or "நாளை மறுநாள்" in t or tokens & _DAY_AFTER:
        return _within(today + timedelta(days=2), today, horizon_days)
    days = _N_DAYS.search(t)
    if days and tokens & _IN_WORDS:
        return _within(today + timedelta(days=int(days.group(1))), today, horizon_days)
    weekday = next((idx for word, idx in _WEEKDAYS.items() if word in tokens), None)
    if weekday is not None:
        delta = (weekday - today.weekday()) % 7 or 7
        return _within(today + timedelta(days=delta), today, horizon_days)
    if tokens & _TOMORROW:
        return _within(today + timedelta(days=1), today, horizon_days)
    if tokens & _TODAY:
        return today
    return None
