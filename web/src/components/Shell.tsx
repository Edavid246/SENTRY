"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "@/lib/session";
import { Clock } from "./Clock";
import { Emblem } from "./Emblem";
import { IconChat, IconEye, IconLog, IconLogout, IconMap, IconOrg } from "./Icons";

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
    <div className="flex flex-col justify-center gap-1.5 border-t border-on-accent/25 px-4 py-3 md:border-l md:border-t-0 md:px-6">
      <div className="flex items-center gap-2 text-on-accent/80">
        {icon}
        <span className="label text-on-accent/80">{label}</span>
      </div>
      {children}
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { status, me, logout, can } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (status === "anon") router.replace("/");
  }, [status, router]);

  if (status !== "ready" || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center text-soft">
        <span className="label">Checking session…</span>
      </div>
    );
  }

  const nav = [
    { href: "/home", label: "Home", icon: <IconOrg />, show: can("read"), also: ["/d/", "/cases/", "/reports/"] },
    { href: "/findings", label: "Findings", icon: <IconEye />, show: can("read") },
    { href: "/chat", label: "Assistant", icon: <IconChat />, show: true },
    { href: "/map", label: "Map", icon: <IconMap />, show: can("read") },
    { href: "/audit", label: "Audit log", icon: <IconLog />, show: can("read_audit") },
  ].filter((n) => n.show);

  return (
    <div className="flex h-screen flex-col">
      {/* Identity strip, after the reference: person | unit | session */}
      {/* The masthead: the one solid red surface, white type on it. */}
      <header className="flex shrink-0 flex-col bg-accent text-on-accent md:min-h-[88px] [&_:focus-visible]:outline-on-accent md:flex-row md:items-stretch">
        <div className="flex items-center gap-3 px-4 py-3 md:gap-4 md:px-6">
          <Emblem size={34} className="text-on-accent" />
          <div className="leading-tight">
            <div className="text-[0.9rem] font-bold tracking-[0.12em] md:text-[1rem]">DEFENCE GATEWAY</div>
            <div className="text-[0.75rem] tracking-[0.12em] text-on-accent/80 md:text-[0.8rem]">SECURE ASSISTANT</div>
          </div>
          {/* Phone: the identity strip opens on demand. */}
          <div className="ml-auto flex items-center gap-2 md:hidden">
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              aria-expanded={menuOpen}
              aria-controls="identity-strip"
              className="btn px-3"
            >
              {menuOpen ? "Close" : "Menu"}
            </button>
          </div>
        </div>
        <div
          id="identity-strip"
          className={`${menuOpen ? "flex" : "hidden"} min-w-0 flex-col md:flex md:flex-1 md:flex-row md:items-stretch`}
        >
          <div className="flex flex-col justify-center border-t border-on-accent/25 px-4 py-3 md:border-l md:border-t-0 md:px-6">
            <div className="text-[0.8rem] uppercase tracking-[0.12em] text-on-accent/80">
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
                  {i > 0 && <span className="text-on-accent/80">›</span>}
                  {u.name}
                </span>
              ))}
            </div>
          </Segment>
        </div>
        <div
          className={`${menuOpen ? "flex" : "hidden"} items-center justify-between gap-5 border-t border-on-accent/25 px-4 py-3 md:flex md:justify-start md:border-l md:border-t-0 md:px-6 md:py-0`}
        >
          <div className="flex flex-col gap-1 text-[0.85rem]">
            <span className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-on-accent" />
              <span className="uppercase tracking-[0.12em]">Online</span>
            </span>
            <span className="text-on-accent/80">
              <Clock />
            </span>
          </div>
          <button type="button" onClick={logout} className="btn flex items-center gap-2 ps-3.5">
            <IconLogout size={16} />
            Log out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col-reverse md:flex-row">
        <nav
          aria-label="Main"
          className="flex shrink-0 border-t border-rule bg-surface md:w-52 md:flex-col md:border-r md:border-t-0 md:py-3"
        >
          {nav.map((n) => {
            const active = pathname.startsWith(n.href) || (n.also?.some((prefix) => pathname.startsWith(prefix)) ?? false);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-1 border-t-[3px] px-1 py-2 text-[0.7rem] uppercase tracking-[0.08em] md:flex-none md:flex-row md:justify-start md:gap-3 md:border-l-[3px] md:border-t-0 md:px-5 md:py-3 md:text-[0.9rem] md:tracking-[0.12em] ${
                  active
                    ? "border-accent bg-raised text-accent"
                    : "border-transparent text-soft hover:text-ink"
                }`}
              >
                {n.icon}
                {n.label}
              </Link>
            );
          })}
        </nav>
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</main>
      </div>

    </div>
  );
}
