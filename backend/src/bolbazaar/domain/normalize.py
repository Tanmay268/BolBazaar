"""Text normalisation shared by entity matching, dates and the offline extractor."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

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


_DEVANAGARI_LETTERS = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "e", "ओ": "o", "औ": "o", "ऑ": "o",
    "ऋ": "ri", "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "e", "ो": "o", "ौ": "o", "ॉ": "o",
    "ृ": "ri", "ं": "n", "ँ": "n", "ः": "h",
    "क": "k", "ख": "kh", "ग": "g", "घ": "g", "ङ": "n", "च": "ch", "छ": "ch", "ज": "j", "झ": "j", "ञ": "n",
    "ट": "t", "ठ": "t", "ड": "d", "ढ": "d", "ण": "n", "त": "t", "थ": "t", "द": "d", "ध": "d", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "b", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
}
_NUKTA_CONSONANTS = {"ज": "z", "फ": "f", "क": "k", "ख": "kh", "ग": "g", "ड": "r", "ढ": "r"}
_CONSONANTS = set("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ")
_VOWEL_SIGNS = set("ािीुूेैोौॉृंँः")
_VIRAMA, _NUKTA = "्", "़"


def romanize(text: str | None) -> str:
    """Rough Devanagari to Latin transliteration, good enough to compare brand names by sound.

    Not a dictionary-grade transliteration: the inherent "a" is dropped at the end of a word and kept inside it.
    Latin text passes through unchanged.
    """

    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _CONSONANTS:
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt == _NUKTA:
                out.append(_NUKTA_CONSONANTS.get(ch, _DEVANAGARI_LETTERS[ch]))
                i += 1
                nxt = text[i + 1] if i + 1 < len(text) else ""
            else:
                out.append(_DEVANAGARI_LETTERS[ch])
            if nxt == _VIRAMA:
                i += 1
            elif nxt not in _VOWEL_SIGNS and "ऀ" <= nxt <= "ॿ":
                out.append("a")
        elif ch in _DEVANAGARI_LETTERS:
            out.append(_DEVANAGARI_LETTERS[ch])
        elif ch not in (_VIRAMA, _NUKTA):
            out.append(ch)
        i += 1
    return "".join(out)


_SOUND_RULES = (("ph", "f"), ("ck", "k"), ("w", "v"), ("q", "k"), ("x", "ks"), ("z", "j"), ("oo", "u"), ("ee", "i"),
                ("ai", "e"), ("ay", "e"), ("ey", "e"), ("ie", "i"), ("y", "i"))


@lru_cache(maxsize=8192)
def phonetic_key(text: str | None) -> str:
    """A coarse "how it sounds" key: Devanagari and Latin spellings of the same brand name map close together.

    Vowels are all treated alike and doubled letters collapse, so "Merry Gold", "Marie Gold" and "मैरी गोल्ड" agree.
    It is deliberately lossy, so callers must only use it to *suggest* matches, never to accept one silently.
    """

    t = re.sub(r"[^a-z0-9 ]", " ", romanize(text).casefold())
    for a, b in _SOUND_RULES:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)
    t = re.sub(r"[aeiou]+", "a", t)
    return " ".join(t.split())


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
