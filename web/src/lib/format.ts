/** An ISO timestamp as "YYYY-MM-DD HH:MM:SS" (seconds) or, with `precision` 16, "YYYY-MM-DD HH:MM". */
export function fmtTs(iso: string, precision: 16 | 19 = 19): string {
  return iso.slice(0, precision).replace("T", " ");
}
