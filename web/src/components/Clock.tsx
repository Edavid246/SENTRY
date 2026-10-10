"use client";

import { useEffect, useState } from "react";
import { fmtTs } from "@/lib/format";

// Rendered after mount only, so server and client markup never disagree.
export function Clock() {
  const [now, setNow] = useState<string | null>(null);
  useEffect(() => {
    const tick = () => setNow(fmtTs(new Date().toISOString()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="tabular-nums">{now ? `${now} (UTC)` : "—"}</span>;
}
