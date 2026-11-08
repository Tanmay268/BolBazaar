"""Score recorded clips two ways and break results down by language, noise, mic, speaker, category.

    uv run python eval/clips/wer_report.py --smoke              # speech recognition only (spends Gnani STT calls)
    uv run python eval/clips/wer_report.py --extract            # + does the order/payment/task come out right? (offline extractor, free)
    uv run python eval/clips/wer_report.py --extract --live     # same with the Azure extractor the app really uses (spends Azure calls)
    uv run python eval/clips/wer_report.py --language hi-IN

Two different questions, two metrics:
  1. WER: did the STT write the words we spoke? Only meaningful when the reference and the STT use the same script and
     number style. Gnani writes Hindi words in Devanagari, English words in Latin and numbers as digits or words depending
     on the language profile, while Hinglish references are in Roman script, so most Hinglish clips are flagged
     "not comparable" and excluded from the headline WER (they still appear in the CSV, with both texts to eyeball).
  2. End-to-end (--extract): transcript -> the app's own extraction/catalogue matching -> compared with the labelled
     'expected' order, money, tasks and complaints (same checks as run_eval.py). Script-independent, so this is the
     number that says whether speech really works for a rep.

Transcripts and extractions are cached under recordings/ so re-running never re-bills.
Writes test-results/<date>/accuracy_wer.csv and accuracy_e2e.csv (one row per clip).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from build_refs import REC, select  # noqa: E402
from run_eval import (ExtractionContext, OfflineReasoner, ProviderError, build_draft, demo_catalog,  # noqa: E402
                      get_profile, get_settings, normalize, score, validate, wer)

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
DIGIT = re.compile(r"\d")
DIMENSIONS = ("language", "noise", "mic", "speaker", "category", "difficulty")
SUPPORTED_WHEN = {"tomorrow", "today", "next_monday"}


def load_cache(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(path: Path, cache: dict) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def micro(rs, key="wer", weight="ref_words") -> float:
    return sum(r[key] * r[weight] for r in rs) / sum(r[weight] for r in rs)


def group_print(rows, title, fmt) -> None:
    for dim in DIMENSIONS:
        groups = defaultdict(list)
        for r in rows:
            groups[r[dim]].append(r)
        print(f"\n{title} by {dim}:")
        for k, rs in sorted(groups.items()):
            print(f"  {k:18} n={len(rs):3}  {fmt(rs)}")


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def expected_to_case(exp: dict) -> dict:
    """Same shape as eval/cases.json; drops commitment dates the harness cannot resolve."""
    case = {k: v for k, v in exp.items() if v is not None}
    if "commitments" in case:
        case["commitments"] = [c for c in case["commitments"] if c[1] in SUPPORTED_WHEN]
        if not case["commitments"]:
            del case["commitments"]
    return case


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--language", choices=["hinglish", "hi-IN", "en-IN"])
    ap.add_argument("--extract", action="store_true", help="also score transcript -> extraction against 'expected'")
    ap.add_argument("--live", action="store_true", help="with --extract: use the Azure extractor instead of the offline baseline")
    a = ap.parse_args()
    cases = select(a)

    from bolbazaar.providers.gnani import GnaniClient, GnaniSTT
    stt = GnaniSTT(GnaniClient(get_settings()))
    stt_cache_path = REC / "hyp_cache.json"
    stt_cache = load_cache(stt_cache_path)

    rows, skipped = [], 0
    for c in cases:
        p = REC / c["language"] / f"{c['id']}.wav"
        if not p.exists():
            skipped += 1
            continue
        audio = p.read_bytes()
        key = hashlib.sha1(audio).hexdigest() + "|" + c["language"]
        if key in stt_cache:
            hyp, secs = stt_cache[key]["hyp"], stt_cache[key]["secs"]
        else:
            t0 = time.perf_counter()
            try:
                hyp = stt.transcribe(audio, get_profile(c["language"])).text
            except Exception as e:  # keep going; the failure shows up as an empty transcript
                hyp = ""
                print(f"{c['id']}: STT failed: {e}")
            secs = time.perf_counter() - t0
            stt_cache[key] = {"hyp": hyp, "secs": secs}
            save_cache(stt_cache_path, stt_cache)
        ref_words = normalize(c["say"]).split()
        w = wer(ref_words, normalize(hyp).split())
        same_script = bool(DEVANAGARI.search(c["say"])) == bool(DEVANAGARI.search(hyp))
        same_numfmt = bool(DIGIT.search(c["say"])) == bool(DIGIT.search(hyp))
        rows.append({**{k: c[k] for k in ("id",) + DIMENSIONS}, "wer": round(w, 4), "ref_words": len(ref_words),
                     "comparable": same_script and same_numfmt, "stt_seconds": round(secs, 2), "ref": c["say"], "hyp": hyp,
                     "_case": c})
        flag = "" if rows[-1]["comparable"] else "   [not comparable: script/number style differs]"
        print(f"{c['id']:26} WER {w:5.2f}  {secs:4.1f}s{flag}\n   ref: {c['say']}\n   hyp: {hyp}")

    if not rows:
        print(f"No recordings found under {REC} ({skipped} cases have no .wav).")
        return

    out = Path(__file__).resolve().parents[3] / "test-results" / datetime.now().strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "accuracy_wer.csv", [{k: v for k, v in r.items() if k != "_case"} for r in rows])

    comp = [r for r in rows if r["comparable"]]
    print(f"\n=== 1. SPEECH RECOGNITION (WER) ===  {len(rows)} clips transcribed, {skipped} not recorded")
    print(f"Comparable clips (same script and number style): {len(comp)}/{len(rows)}. "
          f"The other {len(rows) - len(comp)} are excluded from WER, not counted as errors or successes.")
    if comp:
        print(f"Headline WER (comparable only): {micro(comp):.3f} word-weighted, median {statistics.median(r['wer'] for r in comp):.3f}, n={len(comp)} clips")
        group_print(comp, "WER", lambda rs: f"WER {micro(rs):.3f}")
    print(f"STT latency p50 {statistics.median(r['stt_seconds'] for r in rows):.1f}s (n={len(rows)}; cached clips keep their first timing)")

    if a.extract:
        cat = demo_catalog(date.today(), territory=None)
        today = date.today()
        ctx_for = lambda lang: ExtractionContext(  # noqa: E731
            today=today, weekday=today.strftime("%A"), language=lang,
            customers=[{"name": x.name, "aliases": list(x.aliases)} for x in cat.customers.values()],
            products=[{"name": x.name, "aliases": list(x.aliases)} for x in cat.products.values()])
        if a.live:
            from bolbazaar.providers.azure import AzureReasoner
            reasoner, mode = AzureReasoner(get_settings()), "azure-live"
        else:
            reasoner, mode = OfflineReasoner(), "offline-baseline"
        ex_cache_path = REC / "extract_cache.json"
        ex_cache = load_cache(ex_cache_path)
        e2e = []
        print(f"\n=== 2. END-TO-END (transcript -> app extraction -> expected), extractor: {mode} ===")
        for r in rows:
            c = r["_case"]
            case = expected_to_case(c["expected"] or {})
            if not case or not r["hyp"]:
                continue
            ckey = hashlib.sha1((mode + "|" + c["language"] + "|" + r["hyp"]).encode("utf-8")).hexdigest()
            try:
                if ckey not in ex_cache:
                    ex = reasoner.extract(r["hyp"], ctx_for(c["language"]))
                    draft = build_draft(ex, cat)
                    ex_cache[ckey] = {"draft": draft, "issues": validate(draft, cat)}
                    save_cache(ex_cache_path, ex_cache)
                d = ex_cache[ckey]
                checks = score(case, d["draft"], d["issues"], today)
            except ProviderError as err:
                checks = {"error": False}
                print(f"{r['id']}: extraction error {err.category}")
            ok = all(checks.values())
            failed = ", ".join(k for k, v in checks.items() if not v)
            e2e.append({**{k: r[k] for k in ("id",) + DIMENSIONS}, "extractor": mode, "pass": ok, "n_checks": len(checks),
                        "failed_checks": failed, "hyp": r["hyp"], "weight": 1})
            print(f"{r['id']:26} {'PASS' if ok else 'FAIL'}  {failed}")
        if e2e:
            n_ok = sum(x["pass"] for x in e2e)
            print(f"\nEnd-to-end: {n_ok}/{len(e2e)} clips fully correct ({100 * n_ok / len(e2e):.0f}%)  [extractor: {mode}]")
            tot: dict[str, list[bool]] = defaultdict(list)
            for x in e2e:
                for name in (x["failed_checks"].split(", ") if x["failed_checks"] else []):
                    tot[name].append(False)
            if tot:
                print("most common failed checks: " + ", ".join(f"{k} x{len(v)}" for k, v in sorted(tot.items(), key=lambda kv: -len(kv[1]))))
            group_print(e2e, "Pass rate", lambda rs: f"{sum(x['pass'] for x in rs)}/{len(rs)} pass")
            write_csv(out / "accuracy_e2e.csv", e2e)
            print(f"\nraw rows: {out / 'accuracy_e2e.csv'}")
            if not a.live:
                print("NOTE: the offline extractor is a deliberately simple baseline; run with --live for the number that reflects the app.")

    print(f"\nraw rows: {out / 'accuracy_wer.csv'}")
    print("Caveat: groups with n < 10 are anecdotes, not rates; quote n next to every number.")


if __name__ == "__main__":
    main()
