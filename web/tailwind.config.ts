import type { Config } from "tailwindcss";
import { gridGround, palette } from "./src/lib/palette";

// Colours live in src/lib/palette.ts.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  // hover: styles only where a pointer can hover; on touch a tapped item would stay "hovered".
  future: { hoverOnlyWhenSupported: true },
  theme: {
    extend: {
      colors: palette,
      backgroundImage: { "grid-ground": gridGround },
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
