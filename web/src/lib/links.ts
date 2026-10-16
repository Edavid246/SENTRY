/** The page that opens a ref: findings (FND-…, derived items) have their own page; every other ref is a source record. */
export function recordHref(ref: string): string {
  return `/${ref.startsWith("FND-") ? "findings" : "records"}/${encodeURIComponent(ref)}`;
}
