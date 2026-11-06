"""Per-language Gnani settings. Chosen by the rep's language selection.

Values for ``format`` and the Hinglish TTS option come from docs.gnani.ai (2026-11-04).
They have not yet been exercised against the live API.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ApiError


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    label: str
    stt_language: str
    stt_format: str
    tts_language: str
    tts_model: str
    tts_voice: str


PROFILES: dict[str, LanguageProfile] = {
    "hinglish": LanguageProfile("hinglish", "Hinglish", "hi-IN,en-IN", "codemix", "hi-en", "timbre-v2.5", "Poorvi"),
    "hi-IN": LanguageProfile("hi-IN", "Hindi", "hi-IN", "transcribe", "hi-IN", "timbre-v2.5", "Nalini"),
    "en-IN": LanguageProfile("en-IN", "English", "en-IN", "transcribe", "en-IN", "timbre-v2.5", "Kaveri"),
    "ta-IN": LanguageProfile("ta-IN", "Tamil", "ta-IN", "verbatim", "ta-IN", "timbre-v2.5", "Asmita"),
    "mr-IN": LanguageProfile("mr-IN", "Marathi", "mr-IN", "verbatim", "mr-IN", "timbre-v2.5", "Zahira"),
}


def get_profile(code: str | None) -> LanguageProfile:
    key = (code or "hinglish").strip()
    if key.lower() == "hinglish" or key.lower() == "hi-en":
        return PROFILES["hinglish"]
    profile = PROFILES.get(key) or PROFILES.get(key[:2].lower() + "-IN")
    if profile is None:
        raise ApiError(400, "UNSUPPORTED_LANGUAGE", f"Language '{code}' is not supported",
                       {"supported": sorted(PROFILES)})
    return profile
