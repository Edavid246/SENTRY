/** An ISO timestamp as "YYYY-MM-DD HH:MM:SS" (seconds) or, with `precision` 16, "YYYY-MM-DD HH:MM". */
export function fmtTs(iso: string, precision: 16 | 19 = 19): string {
  return iso.slice(0, precision).replace("T", " ");
}

export interface DisplayOptions {
  /** "json" (default) prints a list as JSON; "comma" joins it with ", ". */
  lists?: "json" | "comma";
  /** "text" (default) prints true/false; "yes-no" prints yes/no. */
  booleans?: "text" | "yes-no";
}

/** Any field value as display text: missing or empty is "—", objects print as JSON. */
export function displayValue(value: unknown, { lists = "json", booleans = "text" }: DisplayOptions = {}): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean" && booleans === "yes-no") return value ? "yes" : "no";
  if (Array.isArray(value) && lists === "comma") return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
