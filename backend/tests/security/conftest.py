"""Pytest fixtures for the security suite (helpers live in support.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bolbazaar.main import create_app
from bolbazaar.providers.base import Providers

from .support import FROZEN_NOW, Counter, MockReasoner, MockSTT, MockTTS, SecApp, secure_settings


@pytest.fixture
def make_sec(tmp_path):
    clients: list[TestClient] = []

    def factory(*, providers: Providers | None = None, freeze: bool = True, **kw) -> SecApp:
        counter = Counter()
        providers = providers or Providers(stt=MockSTT(counter), tts=MockTTS(counter), reasoner=MockReasoner(counter), label="mock")
        settings = secure_settings(tmp_path, **kw)
        app = create_app(settings, providers)
        client = TestClient(app)
        clients.append(client)
        sec = SecApp(client=client, app=app, counter=counter, settings=settings)
        if freeze:
            app.state.ctx.guard.clock = lambda: FROZEN_NOW
        return sec

    yield factory
    for c in clients:
        c.close()


@pytest.fixture
def sec(make_sec) -> SecApp:
    return make_sec()
