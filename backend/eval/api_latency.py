"""API latency probe: logs in as a rep and a manager, times read endpoints, writes raw CSV + prints p50/p95.

Spends NO speech/LLM credits (does not call /captures or /manager/ask).

    cd backend
    uv run python eval/api_latency.py --base https://fieldforce-api-ntd4.onrender.com -n 30
    BB_PASSWORD=... uv run python eval/api_latency.py --base http://localhost:8000

Paced at ~1.6 req/s per user so the 120 req/min per-user rate limit is never hit (a 429 would corrupt the numbers).
Latency is measured from THIS machine/network over a kept-alive connection, so say where you ran it in the report.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

PUBLIC = ["/health", "/v1/auth/territories"]
REP = ["/v1/me", "/v1/products", "/v1/customers", "/v1/visits", "/v1/orders", "/v1/commitments", "/v1/captures"]
MANAGER = ["/v1/manager/summary", "/v1/manager/overdue-payments", "/v1/manager/inactive-retailers",
           "/v1/manager/pending-commitments", "/v1/manager/conversion", "/v1/manager/declining-products"]
PACE_S = 0.6


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]  # nearest-rank


def login(client: httpx.Client, user: str, password: str) -> str:
    r = client.post("/v1/auth/login", json={"username": user, "password": password})
    r.raise_for_status()
    return r.json()["token"]


def probe(client: httpx.Client, path: str, role: str, n: int, headers: dict, rows: list) -> None:
    for i in range(n):
        t0 = time.perf_counter()
        try:
            r = client.get(path, headers=headers)
            status, size = r.status_code, len(r.content)
        except httpx.HTTPError as e:
            status, size = type(e).__name__, 0
        ms = (time.perf_counter() - t0) * 1000
        rows.append({"role": role, "endpoint": path, "run": i + 1, "status": status, "ms": round(ms, 1), "bytes": size})
        time.sleep(PACE_S)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("-n", type=int, default=30, help="requests per endpoint")
    ap.add_argument("--rep", default="asha")
    ap.add_argument("--manager", default="meera")
    ap.add_argument("--out", default=None, help="output dir (default ../test-results/<date>)")
    a = ap.parse_args()
    password = os.environ.get("BB_PASSWORD", "demo123")
    out = Path(a.out or Path(__file__).resolve().parents[2] / "test-results" / datetime.now().strftime("%Y-%m-%d"))
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with httpx.Client(base_url=a.base.rstrip("/"), timeout=90) as c:
        # Cold start: the very first request, measured on its own. >5 s usually means a sleeping Render instance.
        t0 = time.perf_counter()
        first = c.get("/health")
        cold_ms = (time.perf_counter() - t0) * 1000
        print(f"first request /health: {cold_ms:.0f} ms (status {first.status_code}) <- cold-start indicator")
        print(f"health body: {first.text[:120]}")

        t0 = time.perf_counter()
        rep_h = {"Authorization": "Bearer " + login(c, a.rep, password)}
        login_ms = (time.perf_counter() - t0) * 1000
        mgr_h = {"Authorization": "Bearer " + login(c, a.manager, password)}
        print(f"login ({a.rep}): {login_ms:.0f} ms")

        for p in PUBLIC:
            probe(c, p, "public", a.n, {}, rows)
        for p in REP:
            probe(c, p, a.rep, a.n, rep_h, rows)
        for p in MANAGER:
            probe(c, p, a.manager, a.n, mgr_h, rows)

    csv_path = out / "api_latency.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["role", "endpoint", "run", "status", "ms", "bytes"])
        w.writeheader()
        w.writerows(rows)

    print(f"\nn={a.n}/endpoint | from {platform.node()} | {datetime.now():%Y-%m-%d %H:%M} | base {a.base}")
    print(f"{'endpoint':34}{'ok/n':>7}{'p50':>8}{'p95':>8}{'max':>8}{'KB':>7}")
    summary = []
    for ep in dict.fromkeys(r["endpoint"] for r in rows):
        rs = [r for r in rows if r["endpoint"] == ep]
        ok = [r["ms"] for r in rs if r["status"] == 200]
        if not ok:
            print(f"{ep:34}{'0/' + str(len(rs)):>7}  all failed: {rs[0]['status']}")
            continue
        line = (ep, f"{len(ok)}/{len(rs)}", statistics.median(ok), pct(ok, 95), max(ok), rs[0]["bytes"] / 1024)
        summary.append(line)
        print(f"{line[0]:34}{line[1]:>7}{line[2]:>8.0f}{line[3]:>8.0f}{line[4]:>8.0f}{line[5]:>7.1f}")
    print(f"\nms. raw data: {csv_path}")
    non200 = [r for r in rows if r["status"] != 200]
    if non200:
        print(f"WARNING: {len(non200)} non-200 responses (e.g. {non200[0]['endpoint']} -> {non200[0]['status']}); check the CSV")


if __name__ == "__main__":
    main()
