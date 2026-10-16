import { ClearanceBadge } from "./ClearanceBadge";

/**
 * A data item's marking: the classification badge, then one tag per compartment. A fragment, so the
 * chips sit in the caller's own flex row. No badge without a classification (a section with no rows).
 */
export function Marking({ code, compartments }: { code: string | null; compartments: readonly string[] }) {
  return (
    <>
      {code && <ClearanceBadge code={code} />}
      {compartments.map((c) => (
        <span key={c} className="tag">
          {c}
        </span>
      ))}
    </>
  );
}
