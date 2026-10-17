// One config map for every clearance / classification colour in the UI.
// Classes are written out in full so Tailwind keeps them.
export interface ClearanceStyle {
  label: string;
  className: string;
}

const MAP: Record<string, ClearanceStyle> = {
  unclassified: { label: "OPEN", className: "border-ok text-ok" },
  restricted: { label: "INTERNAL", className: "border-gold text-gold" },
  confidential: { label: "CONFIDENTIAL", className: "border-confidential text-confidential" },
  // A solid block, so the highest marking never reads as the red of a button or an error.
  secret: { label: "GOVERNMENT-SENSITIVE", className: "border-ink bg-ink font-bold text-ground" },
};

const NONE: ClearanceStyle = { label: "NO CLEARANCE", className: "border-mute text-mute" };

export function clearanceStyle(code: string | null | undefined): ClearanceStyle {
  if (!code) return NONE;
  return MAP[code.toLowerCase()] ?? { label: code.toUpperCase(), className: "border-soft text-soft" };
}
