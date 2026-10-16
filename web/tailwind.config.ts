import type { Config } from "tailwindcss";

// Palette sampled from the reference screens (inspo-images/): blue-black ground,
// sage-grey type, teal-grey rules, one amber accent. All values live here once.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  // hover: styles only where a pointer can hover; on touch a tapped item would stay "hovered".
  future: { hoverOnlyWhenSupported: true },
  theme: {
    extend: {
      colors: {
        ground: "#091017",
        surface: "#0d161e",
        raised: "#111d26",
        rule: "#22343b",
        ink: "#cfdcd5",
        sage: "#8fa89d",
        mute: "#5f776f",
        amber: "#efa93a",
        ok: "#5fae86",
        warn: "#e0a43c",
        bad: "#e0524d",
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', "ui-monospace", "Consolas", "monospace"],
      },
      borderRadius: { DEFAULT: "2px", none: "0" },
      // Motion curves, one place: `ease` for hover and colour, a strong ease-out for anything
      // entering or pressed, and a quick-settling curve for icon cross-fades.
      transitionTimingFunction: {
        DEFAULT: "ease",
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        swap: "cubic-bezier(0.2, 0, 0, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
