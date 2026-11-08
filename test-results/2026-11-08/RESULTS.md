# BolBazaar Test Results — 2026-11-08

Tester: kaush · Sections completed so far: web speed (signed-out). Everything else is listed under "Not yet tested".

## 1. Web speed — login page, signed out (Lighthouse)

| Item | Value |
|---|---|
| Target | https://bol-bazaar.vercel.app (deployed, not the dev server) |
| Tool | Lighthouse 13.6.0 CLI, `--preset=perf --form-factor=mobile`, throttling method `devtools` (simulated slow mobile network/CPU) |
| Run from | Tester's Windows PC, desktop Chrome, home/office network (not a phone) |
| Sample size | n = 5 runs, same page, back to back |
| Mode | Production build; no speech/LLM calls involved |

| Metric | Median | Min | Max |
|---|---|---|---|
| Performance score | 90 | 88 | 92 |
| First Contentful Paint (ms) | 2664 | 2454 | 2845 |
| Largest Contentful Paint (ms) | 2664 | 2454 | 2845 |
| Speed Index (ms) | 4596 | 4349 | 4668 |
| Total Blocking Time (ms) | 0 | 0 | 0 |
| Cumulative Layout Shift | 0.000 | 0.000 | 0.000 |
| Time to Interactive (ms) | 2664 | 2454 | 2845 |
| Page weight (KiB) | 104 | 104 | 104 |

Reading: no main-thread blocking and no layout shift in any run; spread is small (LCP range ~0.4 s). LCP equals FCP, so the largest element is painted at first paint; with a ~104 KiB page, the ~2.7 s is dominated by the simulated slow network, not by JavaScript. An earlier single run (score 93, LCP 2.4 s) falls inside the range above but was overwritten by a later run and is not counted.

Raw data: `speed.csv` (per-run values) · `evidence/lighthouse/run1-5.json` (full Lighthouse reports).

## 2. API latency — deployed Render API (read endpoints)

| Item | Value |
|---|---|
| Target | https://fieldforce-api-ntd4.onrender.com (Render, Neon Postgres per DEPLOYMENT.md) |
| Tool | `backend/eval/api_latency.py`, httpx, kept-alive connection, 0.6 s pause between requests |
| Run from | Tester's Windows PC (`Tanmay-pc`), 2026-11-08 ~15:45–15:56, so every figure includes the PC-to-Render network path |
| Sample size | n = 30 per endpoint, 450 requests, all HTTP 200 (0 errors) |
| Accounts | rep `asha` (demo data), manager `meera` |
| Not called | `/captures` POST and `/manager/ask` (they spend Gnani/Azure credits) |

Times in ms, payload in KB.

| Endpoint | ok/n | p50 | p95 | max | KB |
|---|---|---|---|---|---|
| /health | 30/30 | 321 | 532 | 740 | 0.0 |
| /v1/auth/territories | 30/30 | 628 | 929 | 1037 | 0.2 |
| /v1/me | 30/30 | 530 | 720 | 731 | 0.1 |
| /v1/products | 30/30 | 838 | 977 | 1071 | 1.8 |
| /v1/customers | 30/30 | 834 | 987 | 1038 | 0.7 |
| /v1/visits | 30/30 | 931 | 1066 | 1176 | 1.6 |
| /v1/orders | 30/30 | 1554 | 1940 | 2019 | 2.4 |
| /v1/commitments | 30/30 | 811 | 954 | 1030 | 0.6 |
| /v1/captures | 30/30 | 763 | 936 | 938 | 0.0 |
| /v1/manager/summary | 30/30 | 1230 | 1443 | 1448 | 0.2 |
| /v1/manager/overdue-payments | 30/30 | 1038 | 1148 | 1652 | 0.5 |
| /v1/manager/inactive-retailers | 30/30 | 935 | 1038 | 1124 | 0.6 |
| /v1/manager/pending-commitments | 30/30 | 874 | 1037 | 1053 | 0.1 |
| /v1/manager/conversion | 30/30 | 867 | 1032 | 1045 | 0.4 |
| /v1/manager/declining-products | 30/30 | 833 | 1040 | 1127 | 0.4 |

Other single measurements: login (`asha`) 1430 ms; first request of the run `/health` 601 ms (the instance was already awake, so this is **not** a cold-start measurement; an earlier aborted run saw 819 ms).

Reading (observations first, then inference):
- Observed: no failures and no outliers beyond ~2 s. Every payload is tiny (≤ 2.4 KB), so response size is not the cause of the times.
- Observed: `/health` (no database work) has p50 321 ms; every data endpoint is slower, from +210 ms (`/me`) to +1230 ms (`/orders`). `/orders` (p50 1554, p95 1940) is the slowest endpoint, then `/manager/summary` (p50 1230).
- Inference, not tested: with `/health` as the network baseline, the extra 200–1200 ms looks like database round trips to the remote Postgres, and `/orders` and `/manager/summary` may issue several queries each. Confirm with server-side timing or query logs before changing anything.
- Against the 500 ms p95 target suggested in the test guide, **none** of the 15 endpoints meet it (best: /health at 532). That target was a suggestion, not a requirement, and the ~320 ms baseline measured from this PC leaves little room under it.

Raw data: `api_latency.csv`.

## Not yet tested
- Signed-in pages (rep thread, products, visits, manager dashboard): need DevTools Lighthouse while logged in.
- Render cold start (needs ≥20 min idle first).
- Capture latency (record end → draft ready) and its STT / LLM / TTS split — spends Gnani/Azure credits.
- Accuracy: WER on recorded clips; held-out extraction cases (current 15 cases were written by the developer who tuned the prompt, so they are optimistic).
- Android APK: cold/warm start, memory, jank, APK size, on a physical phone.

## Limitations
- Web numbers are lab (simulated throttling) results from one machine, not real-user data.
- Login page only; it is the lightest page in the app and is not representative of the signed-in screens.
