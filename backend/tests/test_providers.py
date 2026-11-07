import io
import json
import math
import struct
import wave

import httpx
import pytest

from bolbazaar.audio import prepare_wav_segments
from bolbazaar.config import Settings
from bolbazaar.domain.languages import get_profile
from bolbazaar.providers.azure import AzureReasoner
from bolbazaar.providers.base import ExtractionContext, ProviderError
from bolbazaar.providers.gnani import GnaniClient, GnaniSTT, GnaniTTS
from bolbazaar.schemas_llm import Extraction, PatchResult, strict_schema

from datetime import date


def settings(**kw):
    base = dict(gnani_api_key="server-secret", gnani_max_retries=2, azure_openai_endpoint="https://az.test",
                azure_openai_api_key="az-secret", azure_openai_deployment="gpt-4.1-mini",
                azure_openai_max_retries=1, _env_file=None)
    base.update(kw)
    return Settings(**base)


def wav(seconds: float, rate: int = 16000, gap_at: float | None = None) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for n in range(int(seconds * rate)):
            t = n / rate
            quiet = gap_at is not None and abs(t - gap_at) < 0.15
            frames += struct.pack("<h", 0 if quiet else int(8000 * math.sin(2 * math.pi * 300 * t)))
        w.writeframes(bytes(frames))
    return out.getvalue()


def duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- audio

def test_short_wav_passes_through_unchanged():
    data = wav(3)
    assert prepare_wav_segments(data, max_segment_s=28, max_total_s=120) == [data]


def test_long_wav_is_cut_at_silence_under_the_limit():
    data = wav(70, gap_at=25.0)
    segments = prepare_wav_segments(data, max_segment_s=28, max_total_s=120)
    assert len(segments) == 3
    assert all(duration(s) <= 28 for s in segments)
    assert abs(sum(duration(s) for s in segments) - 70) < 0.01
    assert abs(duration(segments[0]) - 25.0) < 0.3  # cut landed in the quiet gap


def test_too_short_and_too_long_are_rejected():
    with pytest.raises(ProviderError, match="too short"):
        prepare_wav_segments(wav(0.02), max_segment_s=28, max_total_s=120)
    with pytest.raises(ProviderError, match="longer than"):
        prepare_wav_segments(wav(10), max_segment_s=28, max_total_s=5)


def test_non_wav_is_converted_with_ffmpeg_or_fails_cleanly():
    try:
        out = prepare_wav_segments(b"definitely not audio", max_segment_s=28, max_total_s=120)
    except ProviderError as error:
        assert error.category == "unsupported_audio"
    else:
        pytest.fail(f"garbage accepted: {out}")


# ---------------------------------------------------------------- gnani

def gnani(handler, **kw):
    sleeps = []
    client = GnaniClient(settings(**kw), transport=httpx.MockTransport(handler), sleep=sleeps.append)
    return client, sleeps


def test_stt_request_shape_and_response():
    seen = {}

    def handler(request: httpx.Request):
        seen["headers"], seen["body"], seen["url"] = request.headers, request.read(), str(request.url)
        return httpx.Response(200, json={"success": True, "request_id": "r1", "transcript": " namaste ",
                                         "model": "prisma-v3.0", "detected_language_code": "hi-IN"})

    client, _ = gnani(handler)
    result = GnaniSTT(client).transcribe(b"RIFF", get_profile("hinglish"))
    assert seen["url"].endswith("/stt/v3") and seen["headers"]["x-api-key-id"] == "server-secret"
    body = seen["body"]
    assert b'name="language_code"' in body and b"hi-IN,en-IN" in body
    assert b'name="format"' in body and b"codemix" in body and b"prisma-v3.0" in body
    assert b'name="audio_file"; filename="audio.wav"' in body
    assert result.text == "namaste" and result.request_id == "r1"


def test_tts_request_shape():
    seen = {}

    def handler(request: httpx.Request):
        seen["json"] = json.loads(request.read())
        return httpx.Response(200, content=b"RIFFxxxx", headers={"content-type": "audio/wav"})

    client, _ = gnani(handler)
    speech = GnaniTTS(client).synthesize("Order saved", get_profile("hinglish"))
    body = seen["json"]
    assert body["model"] == "timbre-v2.5" and body["voice"] == "Poorvi" and body["language"] == "hi-en"
    assert body["audio_config"]["container"] == "wav" and 0.85 <= body["speed"] <= 1.15
    assert speech.audio == b"RIFFxxxx"


def test_retries_transient_errors_with_backoff_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429 if len(calls) == 1 else 503, json={"detail": {"error_code": "RATE_LIMITED"}})
        return httpx.Response(200, json={"success": True, "transcript": "ok ok"})

    client, sleeps = gnani(handler)
    assert GnaniSTT(client).transcribe(b"x", get_profile("en-IN")).text == "ok ok"
    assert len(calls) == 3 and sleeps == [0.5, 1.0]


def test_client_errors_are_not_retried_and_never_leak_secrets():
    def handler(request):
        return httpx.Response(401, json={"detail": {"error_code": "INVALID_API_KEY", "message": "key server-secret bad"}})

    client, sleeps = gnani(handler)
    with pytest.raises(ProviderError) as caught:
        GnaniSTT(client).transcribe(b"x", get_profile("en-IN"))
    assert caught.value.category == "auth" and not caught.value.retryable and sleeps == []
    assert "server-secret" not in str(caught.value)


def test_insufficient_credit_is_its_own_category():
    client, _ = gnani(lambda r: httpx.Response(402, json={"detail": {"message": "Insufficient credit"}}))
    with pytest.raises(ProviderError) as caught:
        GnaniTTS(client).synthesize("hello", get_profile("en-IN"))
    assert caught.value.category == "credits"


def test_daily_budget_is_a_hard_stop():
    client, _ = gnani(lambda r: httpx.Response(200, json={"success": True, "transcript": "fine words"}),
                      gnani_daily_call_budget=2)
    stt = GnaniSTT(client)
    stt.transcribe(b"x", get_profile("en-IN"))
    stt.transcribe(b"x", get_profile("en-IN"))
    with pytest.raises(ProviderError) as caught:
        stt.transcribe(b"x", get_profile("en-IN"))
    assert caught.value.category == "budget"


def test_empty_transcript_means_no_speech():
    client, _ = gnani(lambda r: httpx.Response(200, json={"success": True, "transcript": "  "}))
    with pytest.raises(ProviderError) as caught:
        GnaniSTT(client).transcribe(b"x", get_profile("en-IN"))
    assert caught.value.category == "empty_transcript"


def test_live_mode_requires_a_key():
    with pytest.raises(ProviderError, match="GNANI_API_KEY"):
        GnaniClient(settings(gnani_api_key=""))


# ---------------------------------------------------------------- azure

def _context():
    return ExtractionContext(today=date(2026, 11, 4), weekday="Wednesday", language="hinglish",
                             customers=[{"name": "Sharma General Store", "aliases": []}],
                             products=[{"name": "Parle-G", "aliases": []}])


EMPTY_EXTRACTION = {
    "customer": {"spoken_name": "Sharma", "confidence": 0.9, "evidence": "Sharma ji"},
    "visit": {"purpose": "order", "summary": "s"},
    "order": {"items": [], "delivery_text": None, "delivery_date": None},
    "collections": [], "complaints": [], "competitor_notes": [], "commitments": [],
}


def test_strict_schema_closes_every_object_and_requires_all_fields():
    def check(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert node["additionalProperties"] is False
                assert node["required"] == list(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    for model in (Extraction, PatchResult):
        schema = strict_schema(model)
        check(schema)
        assert "minimum" not in json.dumps(schema)


def test_azure_extract_sends_strict_schema_and_validates_output():
    seen = {}

    def handler(request):
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.read())
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(EMPTY_EXTRACTION)}}]})

    result = AzureReasoner(settings(), transport=httpx.MockTransport(handler)).extract("Sharma ji ne", _context())
    assert result.customer.spoken_name == "Sharma"
    assert seen["url"].startswith("https://az.test/openai/deployments/gpt-4.1-mini/chat/completions?api-version=")
    assert seen["headers"]["api-key"] == "az-secret"
    fmt = seen["body"]["response_format"]["json_schema"]
    assert fmt["strict"] is True and fmt["schema"]["additionalProperties"] is False
    assert "2026-11-04" in seen["body"]["messages"][0]["content"]
    assert "az-secret" not in json.dumps(seen["body"])


def test_azure_rejects_invalid_model_output():
    bad = dict(EMPTY_EXTRACTION, surprise="x")
    handler = lambda r: httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(bad)}}]})
    with pytest.raises(ProviderError) as caught:
        AzureReasoner(settings(), transport=httpx.MockTransport(handler)).extract("t", _context())
    assert caught.value.category == "invalid_response"


def test_azure_retries_rate_limits_then_fails_with_sanitised_error():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, text="secret body az-secret")

    reasoner = AzureReasoner(settings(), transport=httpx.MockTransport(handler), sleep=lambda s: None)
    with pytest.raises(ProviderError) as caught:
        reasoner.extract("t", _context())
    assert len(calls) == 2 and caught.value.category == "rate_limit"
    assert "az-secret" not in str(caught.value)


def test_azure_foundry_endpoint_uses_v1_route():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.read())
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"intent": "unsupported", "days": None})}}]})

    s = settings(azure_openai_endpoint="https://res.services.ai.azure.com")
    AzureReasoner(s, transport=httpx.MockTransport(handler)).parse_manager_query("hi")
    assert seen["url"] == "https://res.services.ai.azure.com/openai/v1/chat/completions"
    assert seen["body"]["model"] == "gpt-4.1-mini"
