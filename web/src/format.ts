export const rupees = (paise: number | null | undefined) =>
  paise == null ? "—" : `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export function niceDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86_400_000);
  const label = d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  if (iso.length === 10) {
    if (diff === 0) return `Today · ${label}`;
    if (diff === 1) return `Tomorrow · ${label}`;
    if (diff === -1) return `Yesterday · ${label}`;
  }
  return label;
}

export function timeAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const ACTION_LABEL: Record<string, string> = {
  visit: "Visit", call: "Call", payment_followup: "Collect payment",
  send_material: "Send material", stock_followup: "Check stock", other: "Follow up",
};

export const LANGUAGES = [
  { code: "hinglish", label: "Hinglish" },
  { code: "hi-IN", label: "हिन्दी" },
  { code: "en-IN", label: "English" },
] as const;

export const SAMPLE_TRANSCRIPT =
  "Sharma ji ne aaj bees packet Parle-G liye aur das bottle Real juice kal dena hai. " +
  "Woh paanch hazaar rupaye kal dega. Biscuit ke kuch packets damaged the, uski complaint hai. " +
  "Agle Monday ko dobara visit karna hai.";
