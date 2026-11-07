# BolBazaar — User Guide

How the app works from the user's side, and how to use the catalogue and "add an item by voice" features.

## 1. The idea in one minute

A sales rep visits shops (retailers) all day. Instead of filling forms, the rep **talks**: *"Sharma ji ne aaj bees packet Parle-G liye, paanch hazaar rupaye kal dega, Monday ko dobara aana hai."*
BolBazaar turns that into a **draft**: which retailer, what was ordered (with prices), payments, complaints, follow-ups. The rep checks the draft and taps **Confirm**. Only then is anything saved. Managers see the results on a dashboard.

Two kinds of users:

| Role | Demo login (password `demo123`) | What they see |
|---|---|---|
| **Rep** (field executive) | `asha`, `ravi`, `priya` | Phone-style app: log visits, review, confirm, follow-ups |
| **Manager** | `meera` | Dashboard: overview, visits, orders, **catalogue**, promises, retailers, team, "Ask" |
| **Admin** | `admin` | Everything a manager has, plus the spend/kill-switch endpoints |

Start it locally: `cd backend && uv run bolbazaar-api` and `cd web && npm run dev`, then open http://localhost:5173 and use the demo chips on the sign-in screen.

## 1a. First time you sign in: the guided tour

The first time a user signs in (on a device) a short **welcome tour** opens by itself: 6 cards for reps, 6 for managers, with Back / Next / Skip. It explains logging a visit, reviewing and confirming, fixing by voice, adding a missing item, and where help lives. It is shown in your chosen language (EN / हिं) and never reappears on that device unless you ask for it.

- **Replay it any time:** Rep: **More → Help & manual → Take the tour**. Manager: menu → **Help & manual → Take the tour**.
- **Skip** (or press Esc) closes it for good.

## 1b. The manual ("Help & manual")

A step-by-step manual lives in the app, in the user's language (English or Hinglish):

- **Rep:** bottom bar → **More → Help & manual**. Chapters: Getting started, Log your first visit, What to say, Review/answer/confirm, Correct by voice, An item is not in the catalogue, No internet, Follow-ups, If something goes wrong.
- **Manager:** left menu → **Help & manual**. Chapters: Getting started, Overview/Visits/Orders/Team, Ask, Catalogue and prices, Promises and retailers, Admin tools (admins only), If something goes wrong.

Tap a chapter to open it; each has numbered steps and a tip. The manual has buttons for **Take the tour** and **Report a bug**.

## 1c. Report a bug

Anyone (rep, manager, admin) can report a problem: Rep **More → Report a bug**; manager menu → **Report a bug**.

1. Choose the kind of problem (broken, understood me wrongly, microphone/voice, suggestion, other).
2. Write a short title and describe it: *what you did, what happened, what you expected* (10 to 2000 characters).
3. Leave **Attach technical details** ticked if you can. It adds the screen you were on, the app version, your language and the last error (its code and request ID). It never includes your password, token or data.
4. **Send report**. You get a reference number and can see the status of your own reports (Received, Being looked at, Resolved, Closed) with any note from the team.

Limits: 10 reports per person per day (500 per day overall). You need to be online to send.

**For admins:** menu → **Bug reports** shows every report (newest first, filter by status). Open one to read the description and technical details, set the status (open, in progress, resolved, won't fix) and leave a note the reporter can see. API: `GET /v1/admin/bug-reports`, `PATCH /v1/admin/bug-reports/{id}`.

## 2. A rep's day, step by step

1. **Log a Visit.** Press and hold (or tap) the red microphone and speak. Can't talk? Choose *Type it*. Want to try? *Try a sample visit*.
2. **Wait a few seconds.** The app listens, understands, and matches names against your retailers and catalogue.
3. **Review.** You see a list: retailer, order (items × quantity, total), delivery date, payment, follow-ups. Tap rows to expand.
4. **Answer at most one question at a time.** If something is unclear (which retailer? which product? what date?) a card says *Check one thing*. Tap an option, type a number, or use **Edit** and speak the answer. *Hear it* plays the question aloud.
5. **Edit by voice if needed.** Tap **Edit**, hold the mic and say e.g. *"Parle-G 15 kar do"* or *"delivery Monday"*. You can also type it.
6. **Confirm.** The visit, order, payments and follow-ups are saved and the app speaks a short confirmation. Prices come from the catalogue on the server, never from what was said.

Nothing is saved until step 6. **Discard draft** throws it away.

## 3. Feature: the catalogue and prices (manager)

*Did it exist before?* No. The app only had read access to a fixed demo catalogue. It is now fully manageable.

**Where:** sign in as a manager (`meera`) → **Catalogue** in the left menu.

**Add an item**
1. Fill **Name** (for example *Basmati Rice*).
2. **Sold by**: kg, packet, bottle or piece.
3. **Price (₹ per unit)** (for example 60 means ₹60 per kg).
4. *Optional* **Units per case** (for example 12) if the item is also sold by the case. A case price is then price × units.
5. *Optional* **Other names reps say**, comma separated (*chawal, rice*). These help the voice matching find the item.
6. Click **Add to catalogue**. Reps can use it immediately.

**Change a price, name or spoken names:** click **Edit** on the row, change, **Save**.
**Remove an item:** click **Retire**. It disappears from new visits but old orders keep it. **Restore** brings it back.

Good to know
- Changing a price affects **new** orders only. Old orders keep the price they were saved with.
- Duplicate names (or an alias that clashes with another item) are refused.
- Price must be above ₹0 and at most ₹1,00,000. The catalogue holds up to 500 active items (the whole list is sent to the AI on every visit, so it is capped). A person can add 60 items a day.
- Only managers and admins can edit the catalogue. Reps cannot change prices.

Using the API instead: `POST /v1/products`, `PATCH /v1/products/{id}`, `DELETE /v1/products/{id}` (retire), `GET /v1/products?includeInactive=true` (managers). See [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

### Build the whole catalogue in one go (voice or text, AI-assisted)

*Did it exist before?* No. It is now on the same **Catalogue** page, in the box **Speak or type your whole list**.

1. **Hold the mic and read your list**, or type/paste it. Say each item with its unit and price, separated by commas or "aur":
   *"chawal 60 rupaye kilo, atta 45 rupaye kilo, Parle-G 10 rupaye packet, Maaza 12 rupaye bottle"*. You can also say a case size ("case mein 24") and other names.
2. The assistant turns it into a table of proposed items. **Nothing is saved yet.** The app shows what it heard so you can spot mistakes.
3. **Review the table.** Fix any name, unit or price, untick rows you do not want, and fill in what is missing. Rows are flagged: *needs unit & price*, *already in catalogue* (unticked by default), *listed twice*.
4. Click **Add N items to catalogue**. The server re-checks every row; duplicates and invalid rows are skipped and reported. Add up to 100 items per list and 300 per day; do longer lists in parts (about 2 minutes of speech per recording).

Notes: with the live AI (Azure) it understands natural Hinglish such as "ek sau bees", "kilo", "botal". Without AI keys the app uses a simpler rule-based reader that handles the pattern "name, price, unit" but can misread complex numbers, so always check the table. Reps cannot use this; it is for managers.

## 4. Feature: item not in the catalogue? Add it by voice (rep)

*Did it exist before?* No. Before, an unknown item (for example *chawal*) only let the rep pick a different existing product. Now the rep can add it on the spot.

**Example.** The rep says: *"Sharma General Store gaya tha, bees kilo chawal order diya, kal bhej dena."*
*Chawal* is not in the catalogue, so the review screen shows the line as **not in catalogue** and asks:

> "chawal" catalogue mein nahi mila. Product chuniye, ya bolo "add karo" aur price, jaise "add karo, 60 rupaye kilo".

You have three ways to answer:

| Way | What to do |
|---|---|
| **One sentence by voice** (fastest) | Tap **Edit**, hold the mic, say *"add karo, 60 rupaye kilo"* (or *"naya add karo, saath rupaye"*, *"add, 60 rupees per kg"*). The item, its unit and price are all set. |
| **Button, then price** | Tap **+ Add "chawal" as a new item**. The app asks *"chawal ka price kitna hai?"* Type the number (60) or say it ("sixty", "pachas rupaye") through **Edit**. |
| **Pick an existing product** | Tap the product that is the same thing. Nothing new is added. |

What happens next
- The line shows **new item, added when you confirm** and the total is calculated with your price.
- If the unit was not said (*"20 chawal"*) the app asks *which unit: kg, packet, bottle or piece?*
- Tap **Confirm**. Only now is *Chawal* created in the catalogue at ₹60 per kg and the order saved. Next visit, *"chawal"* is recognised automatically.
- If you **Discard** the draft, nothing is added.
- If a manager added the same item in the meantime, the manager's version and price are used and no duplicate is created.
- Managers can fix the name, unit, price or spoken names afterwards in **Catalogue**.

Words the app understands for "add": *add, new, naya, nayi, jodo, banao, create, dalo, catalogue* (and Hindi script equivalents). Price is the number next to *rupaye / rupees / rs / ₹*. Units: kg/kilo, packet, bottle, piece.

## 5. Other screens (manager)

- **Overview**: today's order value, 30-day visits, outstanding payments, conversion, overdue payments, team table, activity grid.
- **Ask**: type a question such as *Which retailers have overdue payments?* The answer comes from a fixed database query; the AI only chooses which question it is.
- **Visits / Orders / Promises / Retailers / Team**: lists. In **Promises**, tap **Done** when a follow-up is completed.

## 6. Limits you may hit

The app protects the paid voice/AI services. If you see *"You have reached your usage limit"*, wait for the time shown. Reps get a daily allowance of voice and AI calls. Managers can see usage and switch services off in an emergency through the admin API. Details: [security/SECURITY_IMPLEMENTATION.md](security/SECURITY_IMPLEMENTATION.md).

## 7. Troubleshooting

| Problem | Reason / fix |
|---|---|
| "Needs a retry" after recording | The voice or AI service failed; tap **Try again**. Your recording is kept. |
| "Answer first" on the Confirm button | There is an open question. Answer it, then confirm. |
| Item keeps showing "not in catalogue" | Choose **+ Add ... as a new item**, or ask a manager to add it with its spoken names. |
| Cannot find Catalogue | Only managers/admins see it. |
| Offline | Recordings are queued and sent when you are online again (transcription needs a connection). |
