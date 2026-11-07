import { Icon } from "./Icon";

/** The product name lives here only, so renaming the product is a one-line change. */
export const BRAND = { first: "Bol", second: "Bazaar", suffix: "", descriptor: "Field sales operations" };

/** Compact wordmark for app bars and the sidebar. */
export function Wordmark({ light }: { light?: boolean }) {
  return (
    <span className={`wordmark ${light ? "wordmark-light" : ""}`}>
      {BRAND.first}{BRAND.second}{BRAND.suffix && <span className="wordmark-ai">{BRAND.suffix}</span>}
      <i className="wordmark-arrow"><Icon name="upright" size={16} stroke={2.6} /></i>
    </span>
  );
}

/** Big stacked lockup for the landing screen. */
export function Lockup() {
  return (
    <div className="lockup">
      <h1><span>{BRAND.first}</span><span>{BRAND.second}</span></h1>
      <i className="lockup-arrow"><Icon name="upright" size={64} stroke={2.6} /></i>
      <small className="eyebrow">{BRAND.descriptor} platform</small>
    </div>
  );
}

/** Line-art kirana storefront with a red slab, used on the home and landing screens. */
export function Storefront({ className }: { className?: string }) {
  const stripes = Array.from({ length: 8 }, (_, i) => i);
  return (
    <svg className={className} viewBox="0 0 320 260" aria-hidden focusable="false">
      <polygon points="120,0 320,0 320,150 60,150" fill="#D7282F" />
      <g fill="none" stroke="#111" strokeWidth="2.2" strokeLinejoin="round">
        <rect x="50" y="96" width="250" height="150" fill="#F5F3ED" />
        <rect x="70" y="60" width="210" height="34" fill="#F5F3ED" />
        <polygon points="40,150 310,150 322,110 28,110" fill="#F5F3ED" />
        {stripes.map((i) => (
          <polygon key={i} points={`${28 + i * 36.75},110 ${28 + (i + 1) * 36.75},110 ${40 + (i + 1) * 33.75},150 ${40 + i * 33.75},150`}
            fill={i % 2 ? "#F5F3ED" : "#D7282F"} />
        ))}
        <rect x="70" y="170" width="70" height="76" />
        <rect x="160" y="170" width="120" height="76" />
        {[184, 198, 212, 226].map((y) => <line key={y} x1="160" y1={y} x2="280" y2={y} strokeWidth="1.2" />)}
        <rect x="190" y="226" width="34" height="20" fill="#F5F3ED" /><rect x="228" y="214" width="40" height="32" fill="#F5F3ED" />
      </g>
      <text x="175" y="84" textAnchor="middle" fontSize="22" fontWeight="800" fill="#111" fontFamily="Inter, Arial, sans-serif" letterSpacing="-0.5" textLength="150" lengthAdjust="spacingAndGlyphs">BolBazaar</text>
    </svg>
  );
}
