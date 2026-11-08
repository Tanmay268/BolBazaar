"""Prepare, guide and check a recording session from test_cases.json.

    uv run python eval/clips/build_refs.py                 # write recordings/<lang>/<id>.txt refs + recording_sheet.csv
    uv run python eval/clips/build_refs.py --list --smoke  # print the 10-case smoke-test scripts to read aloud
    uv run python eval/clips/build_refs.py --list --language hinglish
    uv run python eval/clips/build_refs.py --check         # which .wav files exist, and are they valid (16 kHz mono, <=28 s, not silent)?

Save each recording as  recordings/<language>/<id>.wav  (for example recordings/hinglish/hg01-order.wav).
"""
from __future__ import annotations

import argparse
import csv
import json
import wave
from array import array
from pathlib import Path

HERE = Path(__file__).parent
CASES = json.loads((HERE / "test_cases.json").read_text(encoding="utf-8"))["cases"]
REC = HERE / "recordings"
SMOKE_PER_LANG = {"hinglish": 5, "hi-IN": 2, "en-IN": 3}
ORDER = {"easy": 0, "medium": 1, "hard": 2}


def smoke_ids() -> set[str]:
    out: set[str] = set()
    for lang, n in SMOKE_PER_LANG.items():
        pool = [c for c in CASES if c["language"] == lang and not c["category"].startswith("stress")]
        pool.sort(key=lambda c: ORDER[c["difficulty"]])           # stable: easy first, spread over categories below
        seen, picked = set(), []
        for c in pool:
            if c["category"] not in seen:
                picked.append(c); seen.add(c["category"])
        out |= {c["id"] for c in (picked + pool)[:n]}
    return out


def select(args) -> list[dict]:
    cases = [c for c in CASES if not args.language or c["language"] == args.language]
    if args.smoke:
        keep = smoke_ids()
        cases = [c for c in cases if c["id"] in keep]
    return cases


def write_refs(cases: list[dict]) -> None:
    for c in cases:
        d = REC / c["language"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{c['id']}.txt").write_text(c["say"] + "\n", encoding="utf-8")
    sheet = HERE / "recording_sheet.csv"
    if sheet.exists():
        print(f"kept existing {sheet.name} (it holds your notes; delete it to regenerate)")
    else:
        with open(sheet, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "language", "planned_speaker", "noise", "mic", "recorded(Y/N)", "actual_speaker_name",
                        "speaker_gender_age_accent", "device_model", "retake_count", "problems_notes"])
            for c in CASES:
                w.writerow([c["id"], c["language"], c["speaker"], c["noise"], c["mic"], "", "", "", "", "", ""])
        print(f"wrote {sheet}")
    print(f"wrote {len(cases)} reference .txt files under {REC}")


def show(cases: list[dict]) -> None:
    for i, c in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] {c['id']}   lang={c['language']}  speaker={c['speaker']}  noise={c['noise']}  mic={c['mic']}  ({c['difficulty']})")
        print(f"    SAY: {c['say']}")
        if c["notes"]:
            print(f"    note: {c['notes']}")


def check(cases: list[dict]) -> None:
    ok = bad = missing = 0
    for c in cases:
        p = REC / c["language"] / f"{c['id']}.wav"
        if not p.exists():
            missing += 1
            continue
        problems = []
        try:
            with wave.open(str(p), "rb") as w:
                rate, ch, width, frames = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
                data = w.readframes(frames)
            secs = frames / rate if rate else 0
            if rate != 16000: problems.append(f"rate {rate} (want 16000)")
            if ch != 1: problems.append(f"{ch} channels (want mono)")
            if width != 2: problems.append(f"{8 * width}-bit (want 16)")
            if secs > 28: problems.append(f"{secs:.0f}s (max 28)")
            if secs < 1: problems.append(f"{secs:.1f}s too short")
            samples = array("h", data[: len(data) // 2 * 2]) if width == 2 else array("h")
            peak = max((abs(s) for s in samples), default=0) / 32768
            if peak < 0.02: problems.append("almost silent")
            if peak > 0.99: problems.append("clipping")
        except (wave.Error, EOFError) as e:
            problems.append(f"not a readable WAV ({e})")
        if problems:
            bad += 1
            print(f"PROBLEM  {p.relative_to(HERE)}: {'; '.join(problems)}")
        else:
            ok += 1
    print(f"\n{ok} valid, {bad} with problems, {missing} not recorded yet (of {len(cases)} selected)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="only the 10 smoke-test cases")
    ap.add_argument("--language", choices=["hinglish", "hi-IN", "en-IN"])
    a = ap.parse_args()
    sel = select(a)
    if a.list:
        show(sel)
    elif a.check:
        check(sel)
    else:
        write_refs(sel if a.smoke or a.language else CASES)
