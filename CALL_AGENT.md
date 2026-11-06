# Call agent: plan and implementation

Status: **built and tested as a browser-simulated call** (backend + web). It does **not** place real phone calls yet. See "Going live on a phone line".

## 1. What it does
A payment-promise follow-up agent. It "calls" a retailer who owes money, in Hinglish, English or Hindi, and works out one of: a **promise to pay** (amount and date), a **claim that it was already paid**, a **dispute**, a **callback request**, a refusal, or a wrong number. It speaks with Gnani TTS, understands replies with Gnani STT plus the Azure reasoner, and hands a **proposed outcome** to a rep or manager to approve.

Why this use case: it reuses everything already built (STT, TTS, strict-schema reasoner, commitments, manager views), it targets the most painful part of field sales (collections), and it demos well in 60 seconds.

## 2. Principles (same as the rest of the product)
1. **The model classifies; code decides.** The reasoner only labels what the retailer said (`CallReply`: intent, amount, date phrase, note). `domain/calls.py` is a deterministic state machine that chooses the agent's next line, accepts or rejects amounts and dates, and decides when the call ends.
2. **Never guess.** Dates are resolved by the application's date resolver; "next month" or "evening" makes the agent ask again. An amount larger than the balance is not accepted. If the retailer says "I'll pay" without an amount, the full balance is proposed and **flagged as assumed** for the reviewer.
3. **AI proposes, a human commits.** A finished call becomes `NEEDS_REVIEW`. Only `POST /v1/calls/{id}/approve` writes business rows (one visit log of purpose `phone_call`, plus a promised collection, commitment or complaint as the outcome implies). Rejecting writes nothing.
4. **Safe by construction.** Turn limit (8), at most 2 unclear replies, at most 2 corrections at the confirm step, TTS failures never fail a turn, no provider call inside a DB transaction, territory scoping (a rep only sees their own calls and retailers; managers see their territories).

## 2. Conversation flow
```
open ──▶ [purpose] ──will_pay / date / amount──▶ [amount?] ─▶ [date?] ─▶ [confirm] ──yes──▶ close_promise  (NEEDS_REVIEW)
              │                                                   └──no / new date──▶ re-ask (max 2)
              ├─already_paid ─▶ close (claims_paid)      ├─dispute ─▶ close (dispute, note kept)
              ├─refuse ─▶ close    ├─wrong_person ─▶ close   ├─call_later ─▶ [callback date?] ─▶ close (callback)
              └─unclear ×2 ─▶ close (unresolved, nothing to commit)
```

| Outcome | On approval |
|---|---|
| promise_to_pay | promised Collection + `payment_followup` commitment due on the promised date |
| callback | `call` commitment on the agreed date |
| claims_paid | high-priority `payment_followup` "verify payment" due today |
| dispute | Complaint (the retailer's words) + high-priority `call` commitment due today |
| refused / wrong_person / unresolved | only the call log is filed |

A call is stored as a `Visit` with purpose `phone_call` so every promise keeps its provenance. Field-visit metrics (visits today, conversion) **exclude** these.

## 3. API (all `/v1`, JWT)
| Method | Path | Purpose |
|---|---|---|
| POST | `/calls` | `{customerId, language}` start; returns the call with the agent's opening line. Languages: `hinglish`, `en-IN`, `hi-IN`. 422 `NOTHING_DUE` if the retailer owes nothing |
| POST | `/calls/{id}/turns` | multipart `audio` (retailer's reply) → STT → classify → next agent line |
| POST | `/calls/{id}/turns/text` | `{text}` same, without audio (tests, demos, accessibility) |
| GET | `/calls/{id}/turns/{idx}/audio` | the agent line as speech (synthesised on first request, then cached, to save credits) |
| GET | `/calls`, `/calls/{id}` | list / read; `status`, `stage`, `turns[]`, `outcome` |
| POST | `/calls/{id}/approve` · `/reject` · `/cancel` | review (idempotent: a second approve is 409 `ALREADY_APPROVED`) |

Status: `ACTIVE → NEEDS_REVIEW → APPROVED | REJECTED`, or `CANCELLED`.

## 4. Where the code is
`backend/src/fieldforce/domain/calls.py` (state machine, scripts) · `services/calls.py` (lifecycle, approval) · `providers/azure.py` and `offline.py` (`interpret_call_reply`) · `schemas_llm.py` (`CallReply`) · `models.py` (`CallSession`, `CallTurn`) · `web/src/calls/` (call screen, recent calls) · tests in `backend/tests/test_calls.py` (27 tests).

## 5. How it behaves today
- Web "call" screen: the agent's lines are spoken (toggle in the header to save credits); **you play the retailer** by holding the mic bar, typing, or tapping a sample reply.
- Rep: Promises tab → **Call** on a payment follow-up; manager: **Calls** tab → retailers with a balance, and calls awaiting review.
- Live check (Azure): 10 varied Hinglish replies were classified sensibly, including relative dates ("parso"), partial payments, disputes and "wrong number".

## 6. Going live on a phone line (not built)
Gnani's published Vachana docs cover STT and TTS only; I found **no documented telephony or outbound-call API** (Gnani's separate Inya.ai agent platform may offer one; unverified). A real line therefore needs a telephony provider chosen by you (Exotel, Twilio, Knowlarity, an Indian SIP trunk, or Inya.ai). The engine is built so that adapter is small:
1. Provider places the call and, for each caller utterance, sends the recorded audio (or provider-side transcript) to `POST /calls/{id}/turns` (or `/turns/text`).
2. The response's last agent `text` is spoken back, either by fetching `/turns/{idx}/audio` and playing it into the call, or by the provider's own TTS.
3. When `status` becomes `NEEDS_REVIEW`, the provider hangs up and the human review step is unchanged.
Needed first: provider account and number, a webhook auth scheme (the current API uses user JWTs), 8 kHz telephony audio handling (Gnani lists WAV/MP3/OGG/FLAC/AAC/M4A at the documented sample rates; test telephony codecs), and latency work (each turn is STT + LLM + TTS, roughly 4–8 s today, too slow for natural phone speech without streaming).

## 7. Compliance and risk (decide before any real call)
- Outbound calls to real retailers are subject to Indian telecom rules (TRAI/DLT registration, DND, calling hours, recording-consent and AI-disclosure expectations). The agent already identifies itself and the company in the first line; get legal sign-off before dialling anyone.
- Never auto-commit from a call. Keep human approval; consider auto-expiring unreviewed calls.
- Keep call audio retention short (same retention job as other audio, still to be built).
- Only the demo retailers' data is involved; no real phone numbers are stored or used.

## 8. Known limits
- Simulated: no PSTN, no real retailer voice, no barge-in, no streaming.
- The offline classifier is rule-based (Latin-script Hinglish/English only); live quality comes from Azure.
- Hindi/Hinglish scripts are first drafts and need a native-speaker review; Tamil and Marathi are not offered for calls.
- One agent line per TTS call; credits per call are unknown (read app.gnani.ai).
- Classifier output varies slightly between runs, as with extraction.
