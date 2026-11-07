"""Evaluation harness for BolBazaar.

    uv run python eval/run_eval.py                 # extraction accuracy + latency on eval/cases.json (Azure only)
    uv run python eval/run_eval.py --clips DIR     # also WER on DIR/*.wav with a DIR/<name>.txt reference (Gnani STT)
    uv run python eval/run_eval.py --offline       # run the rule-based baseline instead of Azure

Extraction is scored on the *application's* draft (after catalogue matching and validation), because that is
what the rep sees. A case passes only when every labelled field is right. Cases marked ``expect_issue`` pass
only if the draft asks about that problem instead of guessing.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

from bolbazaar.config import get_settings
from bolbazaar.domain.draft import build_draft, validate
from bolbazaar.domain.languages import get_profile
from bolbazaar.domain.normalize import normalize
from bolbazaar.providers.base import ExtractionContext, ProviderError
from bolbazaar.providers.offline import OfflineReasoner
from bolbazaar.seed_data import demo_catalog

HERE = Path(__file__).parent
MANUAL_ENTRY_SECONDS = 240  # assumption: typing one visit into a CRM form. Change with --manual-seconds.
REVIEW_SECONDS = 15         # assumption: reading and confirming the draft
WORDS_PER_SECOND = 2.5      # speaking rate used to estimate dictation time


def next_monday(today: date) -> date:
    return today + timedelta(days=(7 - today.weekday()) or 7)


def resolve_date(token: str, today: date) -> str:
    return {"tomorrow": today + timedelta(days=1), "next_monday": next_monday(today), "today": today}[token].isoformat()


def score(case: dict, draft: dict, issues: list[dict], today: date) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    codes = {i["code"] for i in issues}
    if "expect_issue" in case:
        checks["asks_instead_of_guessing"] = case["expect_issue"] in codes
    if case.get("customer") is not None or "expect_issue" not in case:
        checks["customer"] = draft["customer"].get("customerId") == case.get("customer")
    if "items" in case:
        got = sorted((i.get("productId") or "?", i.get("quantity")) for i in draft["order"]["items"])
        want = sorted((p, q) for p, q in case["items"])
        checks["items"] = got == want
    if "collections" in case:
        got = sorted((c["kind"], (c["amountPaise"] or 0) / 100) for c in draft["collections"])
        checks["money"] = got == sorted((k, float(a)) for k, a in case["collections"])
    if "commitments" in case:
        ok = True
        for action, when in case["commitments"]:
            ok &= any(c["actionType"] == action and c.get("dueDate") == resolve_date(when, today) for c in draft["commitments"])
        checks["commitments"] = ok
    if "complaints" in case:
        checks["complaints"] = len(draft["complaints"]) == case["complaints"]
    if "delivery" in case:
        checks["delivery_date"] = draft["order"].get("deliveryDate") == resolve_date(case["delivery"], today)
    if "expect_issue" not in case:
        checks["no_open_questions"] = not issues
    return checks


def run_extraction(offline: bool) -> None:
    today = date.today()
    cat = demo_catalog(today, territory=None)  # all territories: the cases span Delhi, Chennai and Pune retailers
    ctx = ExtractionContext(
        today=today, weekday=today.strftime("%A"), language="hinglish",
        customers=[{"name": c.name, "aliases": list(c.aliases)} for c in cat.customers.values()],
        products=[{"name": p.name, "aliases": list(p.aliases)} for p in cat.products.values()])
    if offline:
        reasoner = OfflineReasoner()
    else:
        from bolbazaar.providers.azure import AzureReasoner
        reasoner = AzureReasoner(get_settings())
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    totals: dict[str, list[bool]] = {}
    latencies: list[float] = []
    passed = 0
    print(f"{'case':22} {'result':6} {'sec':>5}  failed checks")
    for case in cases:
        started = time.perf_counter()
        try:
            extraction = reasoner.extract(case["text"], ctx)
        except ProviderError as error:
            print(f"{case['id']:22} ERROR  {error.category}")
            for name in ("error",):
                totals.setdefault(name, []).append(False)
            continue
        latencies.append(time.perf_counter() - started)
        draft = build_draft(extraction, cat)
        checks = score(case, draft, validate(draft, cat), today)
        for name, ok in checks.items():
            totals.setdefault(name, []).append(ok)
        ok_all = all(checks.values())
        passed += ok_all
        print(f"{case['id']:22} {'PASS' if ok_all else 'FAIL':6} {latencies[-1]:5.1f}  {', '.join(k for k, v in checks.items() if not v)}")
    n = len(cases)
    print(f"\nCases fully correct: {passed}/{n} ({100 * passed / n:.0f}%)")
    for name, results in sorted(totals.items()):
        print(f"  {name:26} {sum(results)}/{len(results)}")
    if latencies:
        lat = sorted(latencies)
        print(f"\nExtraction latency: p50 {statistics.median(lat):.1f}s, p95 {lat[min(len(lat) - 1, int(0.95 * len(lat)))]:.1f}s, n={len(lat)}")
        words = statistics.mean(len(c["text"].split()) for c in cases)
        speak = words / WORDS_PER_SECOND
        ours = speak + statistics.median(lat) + 2.0 + REVIEW_SECONDS  # +2s modelled STT
        print(f"Modelled time per visit: {ours:.0f}s with BolBazaar vs {MANUAL_ENTRY_SECONDS}s manual entry "
              f"(assumptions: speak {words:.0f} words at {WORDS_PER_SECOND}/s, STT ~2s, review {REVIEW_SECONDS}s). Modelled, not measured with users.")


def wer(ref: list[str], hyp: list[str]) -> float:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)] / max(1, len(ref))


def run_clips(directory: Path, language: str) -> None:
    from bolbazaar.providers.gnani import GnaniClient, GnaniSTT
    stt = GnaniSTT(GnaniClient(get_settings()))
    profile = get_profile(language)
    rows = []
    for wav in sorted(directory.glob("*.wav")):
        ref_file = wav.with_suffix(".txt")
        if not ref_file.exists():
            continue
        started = time.perf_counter()
        hyp = stt.transcribe(wav.read_bytes(), profile).text
        elapsed = time.perf_counter() - started
        score_ = wer(normalize(ref_file.read_text(encoding="utf-8")).split(), normalize(hyp).split())
        rows.append((wav.name, score_, elapsed))
        print(f"{wav.name:28} WER {score_:5.2f}  {elapsed:4.1f}s\n   ref: {ref_file.read_text(encoding='utf-8').strip()}\n   hyp: {hyp}")
    if rows:
        print(f"\nMean WER {statistics.mean(r[1] for r in rows):.3f} over {len(rows)} clips; "
              f"STT latency p50 {statistics.median(r[2] for r in rows):.1f}s")
        print("WER is computed after normalisation (case, punctuation) and counts script differences "
              "(Devanagari vs Latin) as errors, so Hinglish references should be written the way the STT format emits them.")
    else:
        print("No <name>.wav + <name>.txt pairs found.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--clips", type=Path)
    ap.add_argument("--language", default="hinglish")
    ap.add_argument("--manual-seconds", type=int)
    args = ap.parse_args()
    if args.manual_seconds:
        MANUAL_ENTRY_SECONDS = args.manual_seconds
    run_extraction(args.offline)
    if args.clips:
        run_clips(args.clips, args.language)
