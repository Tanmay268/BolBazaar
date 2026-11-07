"""The catalogue AI import is a paid LLM (and optionally STT) call: it must obey the same cost controls."""

from __future__ import annotations

from .support import tone_wav

LIST = "chawal 60 rupaye kilo, besan 45 rupaye kilo"


def post_draft(sec, user="meera", **kw):
    return sec.client.post("/v1/products/draft", data={"text": LIST}, headers=sec.hdr(user), **kw)


def test_draft_is_metered_like_any_llm_call(make_sec):
    sec = make_sec(user_llm_per_minute=3)
    codes = [post_draft(sec).status_code for _ in range(6)]
    assert codes == [200, 200, 200, 429, 429, 429] and sec.counter.calls["llm"] == 3


def test_draft_respects_kill_switches_and_auth(make_sec):
    off = make_sec(azure_enabled=False)
    assert post_draft(off).status_code == 503 and off.counter.total == 0
    sec = make_sec()
    assert post_draft(sec, user="asha").status_code == 403
    assert sec.client.post("/v1/products/draft", data={"text": LIST}).status_code == 401
    assert sec.counter.total == 0


def test_audio_draft_is_checked_before_stt(make_sec):
    sec = make_sec(max_audio_bytes=200_000, max_audio_seconds=5.0)
    h = sec.hdr("meera")
    junk = sec.client.post("/v1/products/draft", files={"audio": ("a.wav", b"not audio" * 50, "audio/wav")}, headers=h)
    long_ = sec.client.post("/v1/products/draft", files={"audio": ("a.wav", tone_wav(9, rate=8000), "audio/wav")}, headers=h)
    huge = sec.client.post("/v1/products/draft", files={"audio": ("a.wav", b"RIFF" + b"\0" * 1_500_000, "audio/wav")}, headers=h)
    assert (junk.status_code, long_.status_code, huge.status_code) == (400, 400, 413)
    assert sec.counter.total == 0
    ok = sec.client.post("/v1/products/draft", files={"audio": ("a.wav", tone_wav(2), "audio/wav")}, headers=h)
    assert ok.status_code in (200, 422) and sec.counter.calls["stt"] == 1


def test_bulk_import_cannot_be_used_to_flood_the_catalogue(make_sec):
    sec = make_sec(user_bulk_products_per_day=5)
    items = lambda n, tag: [{"name": f"{tag} {i}", "baseUnit": "kg", "priceRupees": 1} for i in range(n)]
    h = sec.hdr("meera")
    assert sec.client.post("/v1/products/bulk", json={"items": items(5, "A")}, headers=h).status_code == 201
    r = sec.client.post("/v1/products/bulk", json={"items": items(1, "B")}, headers=h)
    assert r.status_code == 429 and r.headers.get("Retry-After")
    assert sec.client.post("/v1/products/bulk", json={"items": items(1, "C")}, headers=sec.hdr("asha")).status_code == 403
