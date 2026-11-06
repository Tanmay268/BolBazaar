const PATHS: Record<string, string> = {
  mic: "M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z",
  home: "M12 3 3 10.5V21h6v-6h6v6h6V10.5L12 3Z",
  list: "M4 5h16v3H4V5Zm0 5.5h16v3H4v-3ZM4 16h16v3H4v-3Z",
  check: "m9.5 16.2-3.7-3.7L4.4 14l5.1 5.1L20 8.6l-1.4-1.4-9.1 9Z",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5h-2v6l5 3 1-1.7-4-2.3V7Z",
  user: "M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-4 0-8 2-8 5v2h16v-2c0-3-4-5-8-5Z",
  send: "M3 20.5 21 12 3 3.5l.01 6.6L15 12 3 13.9l-.01 6.6Z",
  play: "M8 5v14l11-7L8 5Z",
  spark: "m12 2 2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4L12 2Z",
  trend: "m3 17 6-6 4 4 8-8v5h2V3h-9v2h5l-6 6-4-4-8 8 2 2Z",
  alert: "M12 2 1 21h22L12 2Zm1 14h-2v-2h2v2Zm0-4h-2V8h2v4Z",
  wifioff: "M2.8 2.8 1.4 4.2l3.4 3.4A15 15 0 0 0 1 10.5l2 2a12 12 0 0 1 3.6-2.4l2 2A9 9 0 0 0 5 14.5l2 2a6 6 0 0 1 3.4-1.9l9.4 9.4 1.4-1.4L2.8 2.8ZM12 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0-14c3 0 5.8 1.1 8 3l2-2A17 17 0 0 0 12 4c-.8 0-1.6.1-2.3.2l2.1 2.1.2-.3Z",
  receipt: "M6 2h12v20l-3-2-3 2-3-2-3 2V2Zm3 5v2h6V7H9Zm0 4v2h6v-2H9Z",
  rupee: "M7 4h11v2.2h-3.4a4 4 0 0 1 1.1 2H18v2.2h-2.2A5.6 5.6 0 0 1 10.5 14H9.4l6.6 6.2v.1h-3L7 14.8V13h3.5c1.6 0 2.8-.8 3.1-2.6H7V8.2h6.3C13 7 12 6.2 10.5 6.2H7V4Z",
  chevron: "m9 6 6 6-6 6-1.4-1.4L12.2 12 7.6 7.4 9 6Z",
  logout: "M10 3H4v18h6v-2H6V5h4V3Zm7 4-1.4 1.4L18.2 11H9v2h9.2l-2.6 2.6L17 17l5-5-5-5Z",
  bolt: "M13 2 4 14h6l-1 8 9-12h-6l1-8Z",
  keyboard: "M3 6h18v12H3V6Zm2 2v2h2V8H5Zm4 0v2h2V8H9Zm4 0v2h2V8h-2Zm4 0v2h2V8h-2ZM5 12v2h2v-2H5Zm4 4h6v-2H9v2Zm6-4v2h2v-2h-2Zm4 0v2h-2v-2h2Z",
  x: "M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6 6.4 5Z",
};

export function Icon({ name, size = 20 }: { name: keyof typeof PATHS | string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden focusable="false">
      <path d={PATHS[name] ?? PATHS.spark} />
    </svg>
  );
}

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFB020" /><stop offset="1" stopColor="#FF5A4D" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="14" fill="url(#lg)" />
      <g fill="#fff">
        <rect x="9" y="20" width="5" height="8" rx="2.5" />
        <rect x="17" y="12" width="5" height="24" rx="2.5" />
        <rect x="25" y="16" width="5" height="16" rx="2.5" />
        <rect x="33" y="21" width="5" height="6" rx="2.5" />
      </g>
    </svg>
  );
}
