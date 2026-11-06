# 60-second demo script

Goal: show the whole loop (speak → verified draft → voice correction → confirm → spoken reply → manager sees it) in one take, in Hinglish.

**Before recording**
- Wake the Render service (`/health`), sign in as `asha` on a phone-sized window and `meera` in a second window.
- Test the mic once. Close other tabs. Reset data by restarting the service if the manager screen is cluttered.
- Have the airplane-mode toggle ready for the offline beat (optional, +10 s).

| Time | On screen | Say / do |
|---|---|---|
| 0:00–0:08 | Rep app, "Bolo, visit ho gayi?" | "Rep ko CRM form nahi bharna. Sirf bolna hai." |
| 0:08–0:20 | Hold the mic bar (live waveform), speak: *"Sharma ji ne aaj bees packet Parle-G liye aur das bottle Real mango kal dena hai. Woh paanch hazaar rupaye kal dega. Biscuit damaged the, complaint hai. Agle Monday dobara visit karna hai."* | Release. The thread shows what was heard, then the draft ledger: retailer, order with ₹ total, promised ₹5,000, complaint, two dated promises. |
| 0:20–0:30 | Point at the totals and dates | "Dates aur prices server nikalta hai, AI nahi." |
| 0:30–0:40 | Hold the correction bar: *"Parle-G pandrah kar do"* | Quantity 20 → 15, total recomputes. "Bina dubara record kiye." |
| 0:40–0:48 | Tap **Confirm & save** | The spoken Hinglish confirmation plays (Gnani TTS). "AI propose karta hai, app commit karta hai." |
| 0:48–0:58 | Switch to the manager window; press "Which retailers have overdue payments?" | Number tiles and the follow-up list already include this visit. "Jawab SQL se aata hai, LLM ke andaaze se nahi." |
| 0:58–1:00 | Logo | "FieldForce AI." |

**Offline beat (optional):** switch to airplane mode, record a short visit; the banner shows "1 recording waiting to upload". Turn the network on; it uploads with the stored Idempotency-Key and appears under "Waiting for you".

**Fallbacks:** if the mic fails, use "Can't talk? Type it" or "Try the sample visit" (typed transcript through the same pipeline). If Gnani is down, set `SPEECH_MODE=offline`.

**Claims to avoid:** do not say transcription works offline (it does not; capture is queued), and do not quote accuracy figures beyond those in TESTING.md.
