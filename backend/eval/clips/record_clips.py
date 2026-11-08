"""Guided recorder: shows each script, records from the microphone, saves recordings/<language>/<id>.wav (16 kHz mono 16-bit).

    uv run python eval/clips/record_clips.py --list-devices
    uv run python eval/clips/record_clips.py --smoke                 # the 10 smoke-test cases
    uv run python eval/clips/record_clips.py --language hinglish
    uv run python eval/clips/record_clips.py --device 2              # pick the mic by index from --list-devices
    uv run python eval/clips/record_clips.py --redo                  # also re-record cases that already have a .wav

Per case: ENTER starts recording, ENTER stops it. Then ENTER keeps the take, r retakes, s skips, q quits.
Cases that already have a .wav are skipped unless --redo is given. Needs: sounddevice (installed in the venv, not in pyproject.toml).
"""
from __future__ import annotations

import argparse
import sys
import threading
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_refs import REC, select  # noqa: E402

RATE = 16000
MAX_SECONDS = 28


def record(sd, device) -> bytes:
    chunks: list[bytes] = []

    def cb(indata, frames, time_info, status):  # noqa: ARG001
        chunks.append(bytes(indata))

    stop = threading.Event()
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", device=device, callback=cb):
        threading.Thread(target=lambda: (input("   ● recording... press ENTER to stop "), stop.set()), daemon=True).start()
        stop.wait(timeout=MAX_SECONDS + 2)
    return b"".join(chunks)


def level(pcm: bytes) -> float:
    s = array("h", pcm[: len(pcm) // 2 * 2])
    return max((abs(x) for x in s), default=0) / 32768


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--device", type=int)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--language", choices=["hinglish", "hi-IN", "en-IN"])
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()

    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("sounddevice is not installed. Run: uv pip install --python .venv/Scripts/python.exe sounddevice")
    if a.list_devices:
        print(sd.query_devices())
        return

    cases = select(a)
    todo = [c for c in cases if a.redo or not (REC / c["language"] / f"{c['id']}.wav").exists()]
    dev = a.device if a.device is not None else sd.default.device[0]
    print(f"Mic: [{dev}] {sd.query_devices(dev)['name']}   |   {len(todo)} to record ({len(cases) - len(todo)} already done)")
    print("Tip: set the mic/noise/speaker shown for each case; log real speaker details in recording_sheet.csv.\n")

    for n, c in enumerate(todo, 1):
        path = REC / c["language"] / f"{c['id']}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            print(f"\n[{n}/{len(todo)}] {c['id']}  ({c['language']}, {c['difficulty']})")
            print(f"   conditions: speaker={c['speaker']}  noise={c['noise']}  mic={c['mic']}")
            print(f"   SAY: {c['say']}")
            if c["notes"]:
                print(f"   note: {c['notes']}")
            cmd = input("   ENTER = start, s = skip, q = quit > ").strip().lower()
            if cmd == "q":
                return
            if cmd == "s":
                break
            pcm = record(sd, a.device)
            secs = len(pcm) / 2 / RATE
            peak = level(pcm)
            flag = []
            if secs < 1: flag.append("too short")
            if secs > MAX_SECONDS: flag.append(f"over {MAX_SECONDS}s")
            if peak < 0.05: flag.append("very quiet, check the mic")
            if peak > 0.98: flag.append("clipping, move back or lower input volume")
            print(f"   {secs:.1f}s  peak {peak:.2f}" + (f"   WARNING: {', '.join(flag)}" if flag else "   looks fine"))
            keep = input("   ENTER = keep, r = retake, s = skip, q = quit > ").strip().lower()
            if keep == "q":
                return
            if keep == "r":
                continue
            if keep != "s":
                with wave.open(str(path), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
                    w.writeframes(pcm)
                print(f"   saved {path.relative_to(path.parents[2])}")
            break
    print("\nDone. Next: build_refs.py --check, then wer_report.py.")


if __name__ == "__main__":
    main()
