"""Provider interfaces. Live and offline implementations satisfy the same contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from ..domain.languages import LanguageProfile
from ..schemas_llm import Extraction, ManagerQuery, PatchResult


class ProviderError(RuntimeError):
    """A sanitised provider failure. Never carries keys, audio, transcripts or response bodies."""

    def __init__(self, category: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    model: str
    request_id: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class Speech:
    audio: bytes
    content_type: str
    model: str
    voice: str


@dataclass
class ExtractionContext:
    today: date
    weekday: str
    language: str
    customers: list[dict[str, Any]] = field(default_factory=list)  # {name, aliases}
    products: list[dict[str, Any]] = field(default_factory=list)   # {name, aliases}


class SpeechToText(Protocol):
    def transcribe(self, wav: bytes, profile: LanguageProfile) -> Transcript: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, profile: LanguageProfile) -> Speech: ...


class Reasoner(Protocol):
    def extract(self, transcript: str, context: ExtractionContext) -> Extraction: ...

    def patch(self, draft_view: dict[str, Any], utterance: str, context: ExtractionContext) -> PatchResult: ...

    def parse_manager_query(self, text: str) -> ManagerQuery: ...


@dataclass
class Providers:
    stt: SpeechToText
    tts: TextToSpeech
    reasoner: Reasoner
    label: str = "offline"
