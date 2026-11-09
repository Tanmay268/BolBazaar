/**
 * Scene + narration definition. Narration is Hinglish (Latin script, read by an Indian-English neural voice);
 * `subtitle` is the English subtitle shown on screen. Every claim here maps to something the app really does
 * (see DEMO_SCRIPT.md "Claims to avoid"): no offline transcription claim, no accuracy numbers.
 */
export type SceneId = "intro" | "rep" | "extraction" | "correction" | "confirmation" | "manager" | "outro";

export interface Line { text: string; subtitle: string }
export interface SceneDef {
  id: SceneId;
  title: string;
  /** Narration lines, spoken in order. `voiceCorrection` swaps in the line used when the correction is spoken. */
  lines: Line[];
  minSeconds: number;
  /** Seconds of silence kept after the narration ends. */
  tail: number;
}

export const SCENES: SceneDef[] = [
  { id: "intro", title: "Introduction", minSeconds: 6, tail: 1.2, lines: [
    { text: "Sales reps spend hours filling in CRM forms. What if they could just speak? This is BolBazaar.",
      subtitle: "Sales reps spend hours filling in CRM forms. What if they could just speak? This is BolBazaar." } ] },
  { id: "rep", title: "The rep speaks", minSeconds: 12, tail: 0.6, lines: [
    { text: "At the end of a visit, the rep simply records what happened, in their own words.",
      subtitle: "At the end of a visit, the rep simply records what happened, in their own words." } ] },
  { id: "extraction", title: "Structured visit", minSeconds: 13, tail: 0.6, lines: [
    { text: "BolBazaar turns that one recording into structured data: the retailer, the order, the payment, any complaint, and the next follow-up.",
      subtitle: "BolBazaar turns that one recording into structured data: the retailer, the order, the payment, any complaint, and the next follow-up." },
    { text: "Dates and prices are worked out by the server, not the AI.", subtitle: "Dates and prices are worked out by the server, not the AI." } ] },
  { id: "correction", title: "Correct in one line", minSeconds: 9, tail: 0.6, lines: [
    { text: "If something's wrong, there's no need to start over. Fix it in a single line, and the totals update instantly.",
      subtitle: "If something's wrong, there's no need to start over. Fix it in a single line, and the totals update instantly." } ] },
  { id: "confirmation", title: "Confirm to save", minSeconds: 8, tail: 0.6, lines: [
    { text: "The AI proposes. The rep verifies. And nothing is saved until the rep taps confirm.",
      subtitle: "The AI proposes. The rep verifies. And nothing is saved until the rep taps confirm." } ] },
  { id: "manager", title: "Manager visibility", minSeconds: 15, tail: 0.8, lines: [
    { text: "Meanwhile, managers get live visibility: orders, collections, and pending payments, all in one place.",
      subtitle: "Meanwhile, managers get live visibility: orders, collections, and pending payments, all in one place." },
    { text: "And every answer comes from the database, not from a guess.", subtitle: "And every answer comes from the database, not from a guess." } ] },
  { id: "outro", title: "Outro", minSeconds: 7, tail: 1.5, lines: [
    { text: "Less typing. Better visibility. More productive sales teams. BolBazaar.",
      subtitle: "Less typing. Better visibility. More productive sales teams. BolBazaar." } ] },
];

/** Alternative correction line when the correction really is spoken (live speech-to-text). */
export const SPOKEN_CORRECTION_LINE: Line = {
  text: "Aur agar kuch galat ho, toh manually edit karne ki zarurat nahi. Bas bolkar correct kar do.",
  subtitle: "If something is wrong, no manual editing is needed. Just say the correction.",
};
