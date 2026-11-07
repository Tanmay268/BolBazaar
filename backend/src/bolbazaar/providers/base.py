"""Provider interfaces. Live and offline implementations satisfy the same contract."""

from __future__ import annotations

import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from ..domain.languages import LanguageProfile
from ..schemas_llm import CatalogueExtraction, Extraction, ManagerQuery, PatchResult

# Provider-reported usage for the call currently in progress (set by CostGuard.call, filled by the provider client).
USAGE_SINK: ContextVar[dict[str, int] | None] = ContextVar("provider_usage_sink", default=None)


def report_usage(unit: str, amount: int) -> None:
    sink = USAGE_SINK.get()
    if sink is not None and amount > 0:
        sink[unit] = sink.get(unit, 0) + int(amount)


class DailyBudget:
    """Per-process backstop on provider HTTP attempts (retries included). The shared, database-backed ceilings
    live in ``costguard``; this one still protects the account if that layer is bypassed or misconfigured."""

    def __init__(self, limit: int, label: str) -> None:
        self.limit, self.label, self._day, self._used, self._lock = limit, label, date.today(), 0, threading.Lock()

    def consume(self) -> None:
        with self._lock:
            if self._day != date.today():
                self._day, self._used = date.today(), 0
            if self._used >= self.limit:
                raise ProviderError("budget", f"Daily {self.label} call budget reached")
            self._used += 1

    @property
    def used(self) -> int:
        return self._used


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

    def parse_catalogue(self, text: str) -> CatalogueExtraction: ...


@dataclass
class Providers:
    stt: SpeechToText
    tts: TextToSpeech
    reasoner: Reasoner
    label: str = "offline"
