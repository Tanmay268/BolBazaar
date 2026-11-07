"""Thin Gnani HTTP client (no SDK; the published SDK lags the documented API).

Request shapes follow docs.gnani.ai as read on 2026-11-04. Behaviour against the live API
is not yet verified. Safeguards: a one-request-at-a-time gate (the default account limit),
a daily call budget to protect credits, bounded retries on 429/5xx, and error messages that
never contain keys, bodies or transcripts.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import date
from typing import Any, Callable

import httpx

from ..config import Settings
from ..domain.languages import LanguageProfile
from .base import ProviderError, Speech, Transcript

_RETRY_STATUS = {429, 500, 502, 503, 504}


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit, self._day, self._used, self._lock = limit, date.today(), 0, threading.Lock()

    def consume(self) -> None:
        with self._lock:
            if self._day != date.today():
                self._day, self._used = date.today(), 0
            if self._used >= self.limit:
                raise ProviderError("budget", "Daily Gnani call budget reached")
            self._used += 1

    @property
    def used(self) -> int:
        return self._used


def _error_code(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict) and detail.get("error_code"):
            return str(detail["error_code"])
        error = body.get("error")
        if isinstance(error, dict) and error.get("type"):
            return str(error["type"])
    return None


def _map_status(response: httpx.Response, operation: str) -> ProviderError:
    status = response.status_code
    code = _error_code(response)
    suffix = f" ({code})" if code else ""
    if status == 401:
        return ProviderError("auth", f"Gnani {operation} rejected the API key{suffix}")
    if status == 402:
        return ProviderError("credits", f"Gnani {operation}: insufficient credit")
    if status == 403:
        return ProviderError("auth", f"Gnani {operation}: key lacks permission{suffix}")
    if status in _RETRY_STATUS:
        return ProviderError("rate_limit" if status == 429 else "http",
                             f"Gnani {operation} failed with status {status}", retryable=True)
    return ProviderError("http", f"Gnani {operation} failed with status {status}{suffix}")


class GnaniClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not settings.gnani_api_key:
            raise ProviderError("configuration", "GNANI_API_KEY is required for live speech")
        self.settings = settings
        self._http = httpx.Client(base_url=settings.gnani_base_url.rstrip("/"),
                                  timeout=settings.gnani_timeout_ms / 1000, transport=transport)
        self._gate = threading.Semaphore(max(1, settings.gnani_max_concurrent_requests))
        self._budget = _Budget(settings.gnani_daily_call_budget)
        self._sleep = sleep

    @property
    def calls_used_today(self) -> int:
        return self._budget.used

    def post(self, path: str, operation: str, **kwargs: Any) -> httpx.Response:
        last: ProviderError | None = None
        for attempt in range(self.settings.gnani_max_retries + 1):
            self._budget.consume()
            headers = {"X-API-Key-ID": self.settings.gnani_api_key, "X-API-Request-ID": uuid.uuid4().hex}
            try:
                with self._gate:
                    response = self._http.post(path, headers=headers, **kwargs)
            except httpx.HTTPError:
                last = ProviderError("network", f"Gnani {operation} request failed", retryable=True)
            else:
                if response.status_code == 200:
                    return response
                last = _map_status(response, operation)
            if not last.retryable or attempt >= self.settings.gnani_max_retries:
                raise last
            self._sleep(min(0.5 * (2 ** attempt), 4.0))
        raise last or ProviderError("unknown", f"Gnani {operation} failed")


class GnaniSTT:
    def __init__(self, client: GnaniClient) -> None:
        self.client = client

    def transcribe(self, wav: bytes, profile: LanguageProfile) -> Transcript:
        model = self.client.settings.gnani_stt_model
        response = self.client.post(
            "/stt/v3", "stt",
            files={"audio_file": ("audio.wav", wav, "audio/wav")},
            data={"language_code": profile.stt_language, "model": model, "format": profile.stt_format},
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError("invalid_response", "Gnani STT returned a non-JSON body") from exc
        text = body.get("transcript") if isinstance(body, dict) else None
        if body.get("success") is False or not isinstance(text, str):
            raise ProviderError("invalid_response", "Gnani STT returned no transcript")
        if not text.strip():
            raise ProviderError("empty_transcript", "No speech was detected in the recording")
        return Transcript(text=text.strip(), language=str(body.get("detected_language_code") or profile.code),
                          model=str(body.get("model") or model), request_id=body.get("request_id"),
                          truncated=bool(body.get("truncated")))


class GnaniTTS:
    def __init__(self, client: GnaniClient) -> None:
        self.client = client

    def synthesize(self, text: str, profile: LanguageProfile) -> Speech:
        if not text.strip():
            raise ProviderError("invalid_response", "Nothing to speak")
        s = self.client.settings
        model = s.gnani_tts_model or profile.tts_model
        voice = s.gnani_tts_voice or profile.tts_voice
        body = {
            "text": text, "model": model, "voice": voice, "language": profile.tts_language,
            "speed": s.gnani_tts_speed,
            "audio_config": {"sample_rate": 24000, "encoding": "linear_pcm", "num_channels": 1,
                             "sample_width": 2, "container": "wav"},
        }
        response = self.client.post("/api/v1/tts/inference", "tts", json=body)
        content_type = response.headers.get("content-type", "")
        if not response.content or (content_type and not content_type.startswith(("audio/", "application/octet-stream"))):
            raise ProviderError("invalid_response", "Gnani TTS returned no audio")
        return Speech(audio=response.content, content_type="audio/wav", model=model, voice=voice)
