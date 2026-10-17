// The one source of colour for the UI. tailwind.config.ts turns these into utility classes, CSS
// reads them through theme(), and the map, which cannot use classes, imports them directly.
// Red and white (docs/DECISIONS.md, 2026-10-17): a red masthead over a white workspace. Inside the
// workspace red marks only brand and action (buttons, active nav, links, focus); rows that need a
// look are gold, and errors a darker crimson that always comes with words.
export const palette = {
  ground: "#ffffff",
  surface: "#faf8f8",
  raised: "#f2eded",
  rule: "#e6dfdf",
  ink: "#1a1414",
  soft: "#4d4545",
  mute: "#6b6161",
  accent: { DEFAULT: "#b0122a", hover: "#94101f" },
  // Text and icons on an accent fill (buttons, the masthead).
  "on-accent": "#ffffff",
  gold: "#8a6100",
  ok: "#1f7a4d",
  bad: "#8e0b1f",
  // The CONFIDENTIAL marking, between gold (INTERNAL) and the solid GOVERNMENT-SENSITIVE block.
  confidential: "#a34a08",
} as const;

// The faint instrument grid behind the login screen: hard 1px lines in an SVG tile, so no
// gradient is involved.
export const gridGround = `url("data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' width='204' height='204'><path d='M0 .5H204M.5 0V204' stroke='${palette.rule}' stroke-opacity='.8' fill='none'/></svg>`,
)}")`;
