// One config map for every clearance / classification colour in the UI.
// Classes are written out in full so Tailwind keeps them.
export interface ClearanceStyle {
  label: string;
  className: string;
}

const MAP: Record<string, ClearanceStyle> = {
  unclassified: { label: "UNCLASSIFIED", className: "border-ok text-ok" },
  restricted: { label: "RESTRICTED", className: "border-amber text-amber" },
  confidential: { label: "CONFIDENTIAL", className: "border-[#e2823a] text-[#e2823a]" },
  secret: { label: "SECRET", className: "border-bad text-bad" },
};

const NONE: ClearanceStyle = { label: "NO CLEARANCE", className: "border-mute text-mute" };

export function clearanceStyle(code: string | null | undefined): ClearanceStyle {
  if (!code) return NONE;
  return MAP[code.toLowerCase()] ?? { label: code.toUpperCase(), className: "border-sage text-sage" };
}
