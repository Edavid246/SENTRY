import type { Me } from "./api";

// Where a user lands after login: the group home, unless their role has no data access.
export function homePath(me: Me): string {
  if (me.permissions.includes("read")) return "/home";
  if (me.permissions.includes("read_audit")) return "/audit";
  return "/chat";
}
