"""Text normalisation shared by entity matching, dates and the offline extractor."""

from __future__ import annotations

import re
import unicodedata

_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "hundred": 100,
    "ek": 1, "teen": 3, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "barah": 12, "pandrah": 15, "bees": 20, "tees": 30,
    "chalis": 40, "pachas": 50, "sau": 100,
}
_MULTIPLIERS = {"hazaar": 1000, "hazar": 1000, "thousand": 1000, "lakh": 100000}
_TRAILING = ".,;!?"


def normalize(text: str | None) -> str:
    """Case-fold and strip punctuation/symbols while keeping letters and combining marks.

    Combining marks (Devanagari/Tamil vowel signs) must survive, so this avoids ``\\w``.
    """

    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).casefold()
    chars = [" " if unicodedata.category(c)[0] in {"P", "S"} else c for c in folded]
    return " ".join("".join(chars).split())


def replace_number_words(text: str) -> str:
    """Turn simple spoken numbers ("bees", "paanch hazaar", "twenty") into digits.

    Gnani's code-mix output mostly spells numbers as words, so downstream code needs this.
    """

    words = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        core = word.rstrip(_TRAILING)
        trail = word[len(core):]
        key = core.casefold()
        value = int(core) if core.isdigit() else _NUMBER_WORDS.get(key)
        if value is None:
            out.append(word)
            i += 1
            continue
        if i + 1 < len(words):
            nxt = words[i + 1].rstrip(_TRAILING)
            multiplier = _MULTIPLIERS.get(nxt.casefold())
            if multiplier:
                value *= multiplier
                trail = words[i + 1][len(nxt):]
                i += 1
        out.append(f"{value}{trail}")
        i += 1
    return " ".join(out)


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def first_number(text: str) -> float | None:
    match = _NUMBER.search(replace_number_words(text))
    if not match:
        return None
    return float(match.group(0).replace(",", ""))
