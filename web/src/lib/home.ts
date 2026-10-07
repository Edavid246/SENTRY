import type { Me } from "./api";

// Where a user lands after login: the dashboard, unless their role has no data access.
export function homePath(me: Me): string {
  if (me.permissions.includes("read")) return "/dashboard";
  if (me.permissions.includes("read_audit")) return "/audit";
  return "/chat";
}
