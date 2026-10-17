// The one source of colour for the UI. tailwind.config.ts turns these into utility classes, CSS
// reads them through theme(), and the map, which cannot use classes, imports them directly.
// Palette sampled from the reference screens (inspo-images/): blue-black ground, sage-grey type,
// teal-grey rules, one amber accent.
export const palette = {
  ground: "#091017",
  surface: "#0d161e",
  raised: "#111d26",
  rule: "#22343b",
  ink: "#cfdcd5",
  sage: "#8fa89d",
  mute: "#5f776f",
  amber: { DEFAULT: "#efa93a", hover: "#f6b955" },
  ok: "#5fae86",
  warn: "#e0a43c",
  bad: "#e0524d",
  // The CONFIDENTIAL marking, between amber (INTERNAL) and bad (GOVERNMENT-SENSITIVE).
  confidential: "#e2823a",
} as const;

// The faint instrument grid behind the login screen: hard 1px lines in an SVG tile, so no
// gradient is involved.
export const gridGround = `url("data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' width='204' height='204'><path d='M0 .5H204M.5 0V204' stroke='${palette.rule}' stroke-opacity='.45' fill='none'/></svg>`,
)}")`;
