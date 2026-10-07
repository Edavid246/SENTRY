import type { Config } from "tailwindcss";

// Palette sampled from the reference screens (inspo-images/): blue-black ground,
// sage-grey type, teal-grey rules, one amber accent. All values live here once.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
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
    },
  },
  plugins: [],
};

export default config;
