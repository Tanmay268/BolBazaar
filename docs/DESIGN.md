# Design notes

The interface follows a design board supplied by the project owner: an editorial, ink-and-red look on warm paper, with heavy headlines, hairline rules and square-edged blocks. Mobile comes first; the manager workspace opens into a sidebar layout from 900 px.

## Tokens
| | |
|---|---|
| Primary red | `#D7282F` |
| Ink | `#111111` |
| Paper | `#F5F3ED` (tiles `#ECE9E1`) |
| Neutral | `#9A9A9A` |
| Type | Helvetica Neue / Arial stack (headlines 800 weight, tight tracking), system sans for data; Devanagari falls back to Noto Sans Devanagari |
| Icons | 24 px outline set, 1.8 stroke (`web/src/Icon.tsx`) |
| Shape | square corners (3 px), 1.5–2 px ink rules, uppercase 11 px labels with wide tracking |

Light theme only (the board defines no dark theme).

## Rep app (phone)
1. **Today**: greeting with a line-art kirana storefront, a red "Today's visits" block, Follow-ups and Overdue tiles, a black "Log a Visit" button, waiting drafts and promises due. Bottom bar: Today · Visits · Orders · More.
2. **Log a Visit**: a large red voice orb. Tap to record (with pause and stop, a live waveform from the real microphone level and a running clock) or press and hold to talk and release to send. A "Starting…" state shows while the microphone opens.
3. **Review Visit**: a ruled list (what you said, retailer, order with expandable lines and total, delivery, payments, follow-ups). Rows that need an answer get a red edge; one inline question at a time, also available as audio. **Edit** opens spoken or typed correction. **Confirm** files it.
4. **Visit Saved**: a full red screen with the check, the retailer, order value, follow-ups and an estimated time saved, then the spoken confirmation and "Log Another Visit".
5. **More**: follow-ups, language (English / Hinglish), connection and upload queue, sign out.

## Manager workspace
Black sidebar (Overview, Ask, Visits, Orders, Promises, Retailers, Team) on desktop and an off-canvas drawer on phones. Overview: a red order-value block, three metrics, Overdue Payments, Team Performance and a Visit Activity grid. Ask: a single question box with suggestion chips and an answer block with a red rule. Visits, Orders, Promises, Retailers and Team are table pages over the existing API.

## Where the board is matched and where it is not
Matched: palette, typography, layout and hierarchy of every screen on the board, the voice screen controls, the red Saved screen, the sidebar and the overview grid.

Different on purpose, because the data does not exist:
- **Visit heatmap** → **Visit Activity**, a 28-day calendar grid from real visits. The app does not capture GPS, so there is no map.
- **Trend deltas** (+12%, −6%, +6 pp): only the 30-day visit comparison is shown, computed from real history. Outstanding and conversion have no history, so they show no delta.
- **Visit Completion** → **Order conversion** (visits that ended in an order), which is what the system measures.
- **Zone dropdown and date picker** are shown as plain labels (organisation and today's date); managers are scoped by territory on the server.
- **Reports** is omitted. **Voice input on Ask** is omitted: voice ask is not built.
- **Wordmark**: the board shows another product name. This app keeps its own name, defined once in `web/src/brand.tsx`.

## Originality
All code, copy, the storefront drawing and the layout here were written for this project. A different reference app was studied earlier for general UX principles only.

## Screenshots
Real runs against the live backend are in `docs/screenshots/`: `landing-mobile`, `landing-desktop`, `rep-home`, `rep-record`, `rep-recording`, `rep-review`, `rep-saved`, `rep-orders`, `rep-desktop`, `manager-overview`, `manager-ask`, `manager-team`, `manager-mobile`, `manager-drawer`.
