"""Select live or offline providers from settings."""

from __future__ import annotations

from ..config import Settings
from .azure import AzureReasoner
from .base import Providers
from .gnani import GnaniClient, GnaniSTT, GnaniTTS
from .offline import OfflineReasoner, OfflineSTT, OfflineTTS


def build_providers(settings: Settings) -> Providers:
    if settings.speech == "live":
        client = GnaniClient(settings)
        stt, tts = GnaniSTT(client), GnaniTTS(client)
    else:
        stt, tts = OfflineSTT(), OfflineTTS()
    reasoner = AzureReasoner(settings) if settings.reasoner == "live" else OfflineReasoner()
    label = f"speech={settings.speech if settings.speech == 'live' else 'offline'},reasoner={settings.reasoner if settings.reasoner == 'live' else 'offline'}"
    return Providers(stt=stt, tts=tts, reasoner=reasoner, label=label)
