"use client";

import { useRouter } from "next/navigation";

// Returns to the page the user came from. A page opened directly (new tab, pasted link) has no
// history to return to, so it falls back to `fallback`.
export function BackLink({ fallback }: { fallback: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => (window.history.length > 1 ? router.back() : router.push(fallback))}
      className="label hover:text-ink"
    >
      ← Back
    </button>
  );
}
