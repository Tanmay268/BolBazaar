"""Audio preparation: normalise any upload to WAV and split long recordings.

Gnani STT REST accepts at most 30 s per request, so recordings are cut into segments of
``max_segment_s`` at the quietest moment near each boundary (never mid-word if avoidable).
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import threading
import wave
from array import array

from .providers.base import ProviderError

# Concurrent ffmpeg decodes are CPU- and memory-heavy; callers wait briefly and then fail fast.
FFMPEG_SLOTS = threading.BoundedSemaphore(2)
FFMPEG_WAIT_S = 3.0
FFMPEG_TIMEOUT_S = 30

ACCEPTED_TYPES = {
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/vnd.wave": "wav",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/mp4": "m4a", "audio/x-m4a": "m4a",
    "audio/aac": "aac", "audio/x-aac": "aac", "audio/ogg": "ogg", "audio/opus": "ogg",
    "audio/flac": "flac", "audio/x-flac": "flac", "audio/webm": "webm", "video/webm": "webm",
    "audio/3gpp": "3gp", "audio/amr": "amr",
}
_BLOCK_S = 0.02
_SEARCH_S = 6.0
_MIN_S = 0.1


def extension_for(filename: str | None, content_type: str | None) -> str | None:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in ACCEPTED_TYPES:
        return ACCEPTED_TYPES[mime]
    suffix = (filename or "").rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    return suffix if suffix in set(ACCEPTED_TYPES.values()) else None


def looks_like_audio(data: bytes) -> bool:
    """Cheap container sniff so junk, scripts and archives are rejected before ffmpeg is started or a provider is paid.
    The declared MIME type and file extension are attacker-controlled and are not evidence."""
    h = data[:16]
    return bool(
        (h[:4] == b"RIFF" and h[8:12] == b"WAVE")            # wav
        or h[:3] == b"ID3" or (len(h) > 1 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0)  # mp3 / adts aac
        or h[4:8] == b"ftyp"                                    # m4a / mp4 / 3gp
        or h[:4] == b"OggS" or h[:4] == b"fLaC"                 # ogg/opus, flac
        or h[:4] == bytes.fromhex("1a45dfa3")                   # webm / matroska
        or h[:6] == b"#!AMR" + bytes([10]) or h[:9] == b"#!AMR-WB" + bytes([10])  # amr
    )


def wav_seconds(wav: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError):
        return 0.0


def _read_wav(data: bytes) -> tuple[array, int, int] | None:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            if w.getsampwidth() != 2 or w.getcomptype() != "NONE":
                return None
            samples = array("h")
            samples.frombytes(w.readframes(w.getnframes()))
            if sys.byteorder == "big":
                samples.byteswap()
            return samples, w.getframerate(), w.getnchannels()
    except (wave.Error, EOFError):
        return None


def _write_wav(samples: array, rate: int, channels: int) -> bytes:
    out = io.BytesIO()
    data = array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())
    return out.getvalue()


def _ffmpeg_pcm(data: bytes, max_seconds: float) -> array:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ProviderError("unsupported_audio", "This audio format needs ffmpeg, which is not installed")
    try:
        # -t bounds the decoded output: a small compressed file can otherwise expand to gigabytes of PCM.
        limit = max(1, int(max_seconds) + 2)
        if not FFMPEG_SLOTS.acquire(timeout=FFMPEG_WAIT_S):
            raise ProviderError("busy", "Audio conversion is busy, try again shortly", retryable=True)
        try:
            done = subprocess.run(
                [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-t", str(limit),
                 "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"],
                input=data, capture_output=True, timeout=FFMPEG_TIMEOUT_S, check=True)
        finally:
            FFMPEG_SLOTS.release()
    except (subprocess.SubprocessError, OSError) as exc:
        raise ProviderError("unsupported_audio", "Audio could not be converted") from exc
    samples = array("h")
    samples.frombytes(done.stdout[: len(done.stdout) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _quietest_cut(samples: array, channels: int, rate: int, lo: int, hi: int) -> int:
    block = max(1, int(rate * _BLOCK_S))
    best_pos, best_energy = hi, None
    pos = lo
    while pos + block <= hi:
        base = pos * channels
        energy = sum(abs(samples[base + i * channels]) for i in range(block))
        if best_energy is None or energy < best_energy:
            best_pos, best_energy = pos + block // 2, energy
        pos += block
    return best_pos


def prepare_wav_segments(audio: bytes, *, max_segment_s: float, max_total_s: float) -> list[bytes]:
    """Return one or more WAV byte strings, each at most ``max_segment_s`` long."""

    if not looks_like_audio(audio):
        raise ProviderError("unsupported_audio", "This file is not a supported audio recording")
    decoded = _read_wav(audio)
    original_wav = audio if decoded else None
    if decoded is None:
        samples, rate, channels = _ffmpeg_pcm(audio, max_total_s), 16000, 1
    else:
        samples, rate, channels = decoded
    frames = len(samples) // channels
    seconds = frames / rate if rate else 0
    if seconds < _MIN_S:
        raise ProviderError("unsupported_audio", "Recording is too short")
    if seconds > max_total_s:
        raise ProviderError("unsupported_audio", f"Recording is longer than {int(max_total_s)} seconds")
    max_frames = int(max_segment_s * rate)
    if frames <= max_frames:
        return [original_wav or _write_wav(samples, rate, channels)]
    cuts, pos = [0], 0
    while frames - pos > max_frames:
        hi = pos + max_frames
        lo = max(pos + rate, hi - int(_SEARCH_S * rate))
        cut = _quietest_cut(samples, channels, rate, lo, hi)
        cuts.append(cut)
        pos = cut
    cuts.append(frames)
    return [_write_wav(samples[a * channels: b * channels], rate, channels) for a, b in zip(cuts, cuts[1:])]
