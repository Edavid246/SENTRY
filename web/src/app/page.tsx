"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Clock } from "@/components/Clock";
import { Emblem } from "@/components/Emblem";
import { Watermark } from "@/components/Shell";
import { IconArrow, IconEye, IconEyeOff, IconLock, IconUser, IconWarning } from "@/components/Icons";

function Crosshair({ className }: { className: string }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      stroke="#22343b"
      strokeWidth="1.5"
      className={`absolute ${className}`}
      aria-hidden="true"
    >
      <path d="M7 0v14M0 7h14" />
    </svg>
  );
}

export default function LoginPage() {
  const { status, login } = useSession();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "ready") router.replace("/chat");
  }, [status, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      router.replace("/chat");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid credentials"
          : "Sign-in is unavailable. Check that the API is running.",
      );
      setBusy(false);
    }
  }

  return (
    <div className="grid-ground relative flex min-h-screen flex-col">
      <header className="flex items-start justify-between px-9 pt-7">
        <div className="flex items-center gap-4">
          <Emblem size={32} />
          <div className="leading-tight">
            <div className="text-[1rem] tracking-[0.12em]">DEFENCE GATEWAY</div>
            <div className="text-[0.85rem] tracking-[0.12em] text-sage">SECURE ASSISTANT</div>
          </div>
        </div>
        <div className="text-right text-[0.8rem] leading-relaxed text-sage">
          <div>DEMO BUILD</div>
          <div>
            <Clock />
          </div>
        </div>
      </header>

      <main className="relative flex flex-1 items-center justify-center px-6">
        <Crosshair className="left-[14%] top-[22%]" />
        <Crosshair className="right-[14%] top-[22%]" />
        <Crosshair className="bottom-[22%] left-[14%]" />
        <Crosshair className="bottom-[22%] right-[14%]" />

        <div className="w-full max-w-[560px]">
          <div className="mb-3 flex items-center border border-amber/60 bg-amber/10 text-amber">
            <span className="border-r border-amber/60 px-4 py-3">
              <IconWarning size={20} />
            </span>
            <span className="px-4 py-3 text-[0.85rem] tracking-[0.1em]">
              AUTHORIZED PERSONNEL ONLY — DEMONSTRATION SYSTEM
            </span>
          </div>

          <div className="border border-rule bg-surface">
            <div className="flex items-center gap-5 border-b border-rule px-8 py-6">
              <Emblem size={52} />
              <div>
                <h1 className="text-[1.3rem] font-medium tracking-[0.1em]">DEFENCE GATEWAY</h1>
                <p className="text-[0.95rem] tracking-[0.1em] text-sage">SECURE ASSISTANT</p>
              </div>
            </div>

            <form onSubmit={submit} className="flex flex-col gap-5 px-8 py-7" noValidate>
              <div>
                <label htmlFor="username" className="label mb-2 block">
                  Username
                </label>
                <div className="relative">
                  <IconUser size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-sage" />
                  <input
                    id="username"
                    name="username"
                    autoComplete="username"
                    autoFocus
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Enter your username"
                    className="field pl-10"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="password" className="label mb-2 block">
                  Password
                </label>
                <div className="relative">
                  <IconLock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-sage" />
                  <input
                    id="password"
                    name="password"
                    type={reveal ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="field px-10"
                  />
                  <button
                    type="button"
                    onClick={() => setReveal((r) => !r)}
                    aria-label={reveal ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-sage hover:text-ink"
                  >
                    {reveal ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                  </button>
                </div>
              </div>

              {error && (
                <p role="alert" className="border border-bad/60 px-3 py-2 text-[0.9rem] text-bad">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={busy || !username || !password}
                className="btn-amber flex items-center justify-center gap-3"
              >
                {busy ? "Signing in" : "Log in"}
                <IconArrow size={18} />
              </button>
            </form>

            <div className="border-t border-rule px-8 py-4 text-center text-[0.75rem] tracking-[0.14em] text-sage">
              ACCESS-CONTROLLED <span className="mx-3 text-mute">/</span> AUDITABLE{" "}
              <span className="mx-3 text-mute">/</span> DEMO DATA
            </div>
          </div>
        </div>
      </main>

      <div className="px-6 pb-3 text-center text-[0.8rem] text-mute">
        Independent prototype. All data is fictitious.
      </div>
      <Watermark />
    </div>
  );
}
