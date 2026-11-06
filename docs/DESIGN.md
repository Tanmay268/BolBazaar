# Design notes

## Principles
1. **One next action.** The home screen leads with a single hero card and one button ("Log a visit"), then a few facts and whatever is waiting for the user. Nothing competes with the voice action.
2. **The voice moment is the product.** A single large control, driven by the real microphone level (rings and waveform follow the input, not an animation loop), with a status line and a three-step progress read-out while it works (listening → understanding → matching).
3. **Show what was understood, not a form.** The draft appears as cards, one per fact, each with a confidence signal and the phrase that was heard. Items the system is unsure about are highlighted and asked about inline, with the question also available as audio.
4. **State-aware surfaces.** Waiting drafts, overdue promises and offline uploads surface as banners where the user already is, instead of being hidden in menus.
5. **Mobile first, desktop framed.** A phone-sized column with a bottom bar (centre Talk button) is the baseline. On wider screens the rep app stays a framed phone-sized column; the manager dashboard becomes a two-column workspace.
6. **Two voices of the UI.** The interface can be switched between English and Hinglish (header toggle); the language you *speak* in is chosen separately on the Talk screen.
7. **Smoothness.** Skeletons instead of spinners for lists, staggered card entrance, haptic ticks on record/confirm, safe-area padding, 44 px touch targets, `prefers-reduced-motion` respected, light and dark themes.

## Visual language (original)
- Palette: saffron → coral gradient on warm paper (light) or deep indigo-black (dark), with violet for informational states and green/amber/red for status.
- Shapes: 20 px cards, pill chips, a ripple orb for the mic, gradient hero cards, sound-bar logo mark.
- Type: system font stack (works offline and in the Android WebView), tight negative tracking on headings.

## Reference and originality
Early in the project a reference voice-ordering app was analysed read-only for general UX lessons (a phone-first column, a home that surfaces the next action, a single focal voice control, bottom navigation, switchable UI language, drill-down lists, banners for pending work). Only those general ideas informed this design. No code, copy, layout, colours, icons or assets were reused; the palette, orb, screens, navigation structure, data model and flows here are different and were built from scratch for field sales (visits, promises, manager copilot).

## Screens
Screenshots from a real run against the live backend are in `docs/screenshots/`:
`landing-mobile`, `rep-today` (+ `-light`), `rep-listening`, `rep-draft`, `rep-saved`, `rep-desktop`, `manager-mobile`, `manager-ask`, `manager-desktop`.
