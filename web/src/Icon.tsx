/** Outline icon set (24px grid, 1.8 stroke) to match the editorial, ink-and-red look. */
const PATHS: Record<string, string> = {
  menu: "M3 12h18M3 6h18M3 18h18",
  back: "M19 12H5M12 19l-7-7 7-7",
  arrow: "M5 12h14M12 5l7 7-7 7",
  upright: "M7 17L17 7M7 7h10v10",
  mic: "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8",
  home: "M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10",
  calendar: "M19 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zM16 2v4M8 2v4M3 10h18",
  box: "M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96L12 12.01l8.73-5.05M12 22.08V12",
  users: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  chart: "M12 20V10M18 20V4M6 20v-4",
  flag: "M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7",
  store: "M3 9l1-5h16l1 5M3 9v11h18V9M3 9c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3M9 20v-6h6v6",
  check: "M20 6L9 17l-5-5",
  right: "M9 18l6-6-6-6",
  down: "M6 9l6 6 6-6",
  up: "M18 15l-6-6-6 6",
  pause: "M8 5v14M16 5v14",
  keyboard: "M2 6h20v12H2zM6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10",
  spark: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  x: "M18 6L6 18M6 6l12 12",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  play: "M5 3l14 9-14 9z",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  alert: "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  rupee: "M6 3h12M6 8h12M6 13l8.5 8M6 13h3a4 4 0 0 0 0-8",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  wifioff: "M1 1l22 22M16.7 11.1A11 11 0 0 1 19 12.5M5 12.5a11 11 0 0 1 5.2-2.4M8.5 16.1a6 6 0 0 1 7 0M12 20h.01M1.4 9a16 16 0 0 1 4.7-2.9M22.6 9a16 16 0 0 0-10.6-4",
  trend: "M23 6l-9.5 9.5-5-5L1 18M17 6h6v6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  quote: "M3 21c3 0 7-1 7-8V5H3v8h4c0 3-2 4-4 4zM14 21c3 0 7-1 7-8V5h-7v8h4c0 3-2 4-4 4z",
};

export function Icon({ name, size = 20, stroke = 1.8 }: { name: keyof typeof PATHS | string; size?: number; stroke?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden focusable="false">
      <path d={PATHS[name] ?? PATHS.spark} />
    </svg>
  );
}
