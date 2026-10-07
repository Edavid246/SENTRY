"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "@/lib/session";
import { Clock } from "./Clock";
import { ClearanceBadge } from "./ClearanceBadge";
import { Emblem } from "./Emblem";
import { IconChat, IconDashboard, IconLock, IconLog, IconLogout, IconMap, IconOrg, IconShield } from "./Icons";

export function Watermark() {
  return (
    <div className="border-t border-rule bg-ground py-1.5 text-center text-[0.8rem] tracking-[0.3em] text-mute">
      DEMO DATA — NOT CLASSIFIED
    </div>
  );
}

export function Disclaimer() {
  return (
    <footer className="border-t border-rule px-6 py-2 text-center text-[0.8rem] text-mute">
      Independent prototype. All data is fictitious.
    </footer>
  );
}

function Segment({
  icon,
  label,
  children,
}: {
  icon?: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-center gap-1.5 border-l border-rule px-6 py-3">
      <div className="flex items-center gap-2 text-sage">
        {icon}
        <span className="label">{label}</span>
      </div>
      {children}
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { status, me, logout, can } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anon") router.replace("/");
  }, [status, router]);

  if (status !== "ready" || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sage">
        <span className="label">Checking session…</span>
      </div>
    );
  }

  const nav = [
    { href: "/dashboard", label: "Dashboard", icon: <IconDashboard />, show: can("read") },
    { href: "/chat", label: "Assistant", icon: <IconChat />, show: true },
    { href: "/map", label: "Map", icon: <IconMap />, show: can("read") },
    { href: "/audit", label: "Audit log", icon: <IconLog />, show: can("read_audit") },
  ].filter((n) => n.show);

  return (
    <div className="flex h-screen flex-col">
      {/* Identity strip, after the reference: person | unit | clearance | access | session */}
      <header className="flex min-h-[88px] shrink-0 items-stretch border-b border-rule bg-surface">
        <div className="flex items-center gap-4 px-6 py-3">
          <Emblem size={34} />
          <div className="leading-tight">
            <div className="text-[1rem] font-bold tracking-[0.12em]">DEFENCE GATEWAY</div>
            <div className="text-[0.8rem] tracking-[0.12em] text-sage">SECURE ASSISTANT</div>
          </div>
        </div>
        <div className="flex flex-1 items-stretch">
          <div className="flex flex-col justify-center border-l border-rule px-6 py-3">
            <div className="text-[0.8rem] uppercase tracking-[0.12em] text-sage">
              {me.role.replace("_", " ")}
            </div>
            <div data-testid="user-name" className="text-[1.15rem] font-medium tracking-[0.06em]">
              {me.display_name}
            </div>
          </div>
          <Segment icon={<IconOrg size={16} />} label="Unit">
            <div data-testid="unit-breadcrumb" className="flex items-center gap-2 text-[0.95rem]">
              {me.unit_breadcrumb.map((u, i) => (
                <span key={u.path} className="flex items-center gap-2">
                  {i > 0 && <span className="text-mute">›</span>}
                  {u.name}
                </span>
              ))}
            </div>
          </Segment>
          <Segment icon={<IconShield size={16} />} label="Clearance level">
            <div data-testid="clearance-badge">
              <ClearanceBadge code={me.clearance_code} large />
            </div>
          </Segment>
          <Segment icon={<IconLock size={16} />} label="Special access">
            <div data-testid="compartments" className="flex flex-wrap gap-1.5">
              {me.compartments.length ? (
                me.compartments.map((c) => (
                  <span key={c} className="tag">
                    {c}
                  </span>
                ))
              ) : (
                <span className="text-[0.85rem] text-mute">None</span>
              )}
            </div>
          </Segment>
        </div>
        <div className="flex items-center gap-5 border-l border-rule px-6">
          <div className="flex flex-col gap-1 text-[0.85rem]">
            <span className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-ok" />
              <span className="uppercase tracking-[0.12em]">Online</span>
            </span>
            <span className="text-sage">
              <Clock />
            </span>
          </div>
          <button type="button" onClick={logout} className="btn flex items-center gap-2">
            <IconLogout size={16} />
            Log out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <nav className="flex w-52 shrink-0 flex-col border-r border-rule bg-surface py-3">
          {nav.map((n) => {
            const active = pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 border-l-[3px] px-5 py-3 text-[0.9rem] uppercase tracking-[0.12em] ${
                  active
                    ? "border-amber bg-raised text-amber"
                    : "border-transparent text-sage hover:text-ink"
                }`}
              >
                {n.icon}
                {n.label}
              </Link>
            );
          })}
          {["Personnel", "Logistics", "Training"].map((label) => (
            <div
              key={label}
              aria-disabled="true"
              title="Not in demo"
              data-testid="nav-not-in-demo"
              className="flex cursor-not-allowed flex-col items-start border-l-[3px] border-transparent px-5 py-3 text-[0.9rem] uppercase tracking-[0.12em] text-mute opacity-60"
            >
              {label}
              <span className="text-[0.6rem] tracking-[0.08em] whitespace-nowrap">Not in demo</span>
            </div>
          ))}
          <div className="mt-auto px-5 text-[0.75rem] leading-relaxed text-mute">
            Demo build
            <br />
            Dev profile — not sovereign
          </div>
        </nav>
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>

      <Disclaimer />
      <Watermark />
    </div>
  );
}
