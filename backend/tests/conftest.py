import io
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from bolbazaar.config import Settings
from bolbazaar.main import create_app
from bolbazaar.providers.base import Providers
from bolbazaar.providers.offline import OfflineReasoner, OfflineSTT, OfflineTTS


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(database_url="sqlite://", audio_storage_dir=str(tmp_path / "audio"), jwt_secret="test-secret-with-at-least-32-bytes-of-length",
                    provider_mode="offline", _env_file=None, **kw)


def tone_wav(seconds: float = 2.0, rate: int = 16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 300 * n / rate)))
                               for n in range(int(seconds * rate))))
    return out.getvalue()


class Api:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self._tokens: dict[str, dict] = {}

    def auth(self, username: str) -> dict:
        if username not in self._tokens:
            r = self.client.post("/v1/auth/login", json={"username": username, "password": "demo123"})
            assert r.status_code == 200, r.text
            self._tokens[username] = {"Authorization": f"Bearer {r.json()['token']}"}
        return self._tokens[username]


@pytest.fixture
def make_api(tmp_path):
    clients = []

    def factory(providers: Providers | None = None, **kw) -> Api:
        app = create_app(make_settings(tmp_path, **kw), providers)
        client = TestClient(app)
        clients.append(client)
        api = Api(client)
        api.app = app
        return api

    yield factory
    for c in clients:
        c.close()


@pytest.fixture
def api(make_api) -> Api:
    return make_api()


def offline_providers(**overrides) -> Providers:
    parts = dict(stt=OfflineSTT(), tts=OfflineTTS(), reasoner=OfflineReasoner(), label="test")
    parts.update(overrides)
    return Providers(**parts)
