"""Fixtures for the security suite.

* Providers are mocked and *count every call that would be billed*. Nothing here can reach Gnani or Azure.
* Settings use the REAL default limits (the functional suite relaxes them); tests tighten individual limits explicitly.
* The cost ledger clock is frozen in the middle of a minute/hour/day so fixed-window tests are not flaky at boundaries.
"""

from __future__ import annotations

import io
import math
import struct
import threading
import time
import wave
from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from bolbazaar.config import Settings
from bolbazaar.main import create_app
from bolbazaar.providers.base import ProviderError, Providers
from bolbazaar.providers.offline import OfflineReasoner, OfflineSTT, OfflineTTS

FROZEN_NOW = 1_800_000_000 + 12 * 3600 + 1800 + 30  # 30 s into a minute, 30 min into an hour, mid-day (UTC)
VISIT_TEXT = "Sharma ji ne aaj bees packet Parle-G liya aur paanch hazaar rupaye kal dene ka bola"


def tone_wav(seconds: float = 2.0, rate: int = 16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 300 * n / rate)))
                               for n in range(int(seconds * rate))))
    return out.getvalue()


class Counter:
    """Thread-safe call counter shared by the three mocked providers."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {"stt": 0, "tts": 0, "llm": 0}
        self.fail: dict[str, Exception | None] = {"stt": None, "tts": None, "llm": None}
        self.delay: dict[str, float] = {"stt": 0.0, "tts": 0.0, "llm": 0.0}
        self.inflight: dict[str, int] = {"stt": 0, "tts": 0, "llm": 0}
        self.max_inflight: dict[str, int] = {"stt": 0, "tts": 0, "llm": 0}
        self._lock = threading.Lock()

    def hit(self, kind: str) -> None:
        with self._lock:
            self.calls[kind] += 1
            self.inflight[kind] += 1
            self.max_inflight[kind] = max(self.max_inflight[kind], self.inflight[kind])
        try:
            if self.delay[kind]:
                time.sleep(self.delay[kind])
            if self.fail[kind] is not None:
                raise self.fail[kind]
        finally:
            with self._lock:
                self.inflight[kind] -= 1

    @property
    def total(self) -> int:
        return sum(self.calls.values())


class MockSTT(OfflineSTT):
    def __init__(self, c: Counter) -> None:
        self.c = c

    def transcribe(self, wav, profile):
        self.c.hit("stt")
        return super().transcribe(wav, profile)


class MockTTS(OfflineTTS):
    def __init__(self, c: Counter) -> None:
        self.c = c

    def synthesize(self, text, profile):
        self.c.hit("tts")
        return super().synthesize(text, profile)


class MockReasoner(OfflineReasoner):
    def __init__(self, c: Counter) -> None:
        super().__init__()
        self.c = c

    def extract(self, transcript, context):
        self.c.hit("llm")
        return super().extract(transcript, context)

    def patch(self, draft_view, utterance, context):
        self.c.hit("llm")
        return super().patch(draft_view, utterance, context)

    def parse_manager_query(self, text):
        self.c.hit("llm")
        return super().parse_manager_query(text)

    def parse_catalogue(self, text):
        self.c.hit("llm")
        return super().parse_catalogue(text)


@dataclass
class SecApp:
    client: TestClient
    app: object
    counter: Counter
    settings: Settings
    _tokens: dict[str, str] = field(default_factory=dict)

    @property
    def guard(self):
        return self.app.state.ctx.guard

    def token(self, username: str, password: str = "demo123") -> str:
        if username not in self._tokens:
            r = self.client.post("/v1/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
            self._tokens[username] = r.json()["token"]
        return self._tokens[username]

    def hdr(self, username: str, **extra) -> dict:
        return {"Authorization": f"Bearer {self.token(username)}", **extra}

    def text_capture(self, username: str, key: str, text: str = VISIT_TEXT, **kw):
        return self.client.post("/v1/captures", data={"transcript": text, "language": "hinglish"},
                                headers=self.hdr(username, **{"Idempotency-Key": key}), **kw)

    def audio_capture(self, username: str, key: str, audio: bytes | None = None, name="v.wav", ctype="audio/wav"):
        return self.client.post("/v1/captures", files={"audio": (name, audio if audio is not None else tone_wav(2), ctype)},
                                data={"language": "hinglish"}, headers=self.hdr(username, **{"Idempotency-Key": key}))


def secure_settings(tmp_path, **kw) -> Settings:
    params = dict(database_url=f"sqlite:///{tmp_path / 'sec.db'}", audio_storage_dir=str(tmp_path / "audio"),
                  jwt_secret="test-secret-with-at-least-32-bytes-of-length", provider_mode="offline", _env_file=None,
                  host="127.0.0.1")
    params.update(kw)
    return Settings(**params)


def provider_error(category: str, retryable: bool = False) -> ProviderError:
    return ProviderError(category, f"simulated {category}", retryable=retryable)
