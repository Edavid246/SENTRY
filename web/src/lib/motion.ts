"use client";

import { useEffect, useState } from "react";

// Staged entrances are for a view's first appearance after sign-in, not for every return to it.
// The record lives in module scope: it survives client navigation, a full reload starts afresh,
// and signing in clears it.
const played = new Set<string>();

export function resetEntrances(): void {
  played.clear();
}

/** True while this view's entrance has not played since sign-in; marks it played on mount. */
export function useFirstEntrance(key: string): boolean {
  // Read in the initializer, write in the effect: StrictMode calls initializers twice.
  const [first] = useState(() => !played.has(key));
  useEffect(() => {
    played.add(key);
  }, [key]);
  return first;
}

/** Inline delay for the nth item of a staggered entrance. */
export const stagger = (ms: number) => ({ animationDelay: `${ms}ms` });
