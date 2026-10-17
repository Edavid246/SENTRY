"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { homePath } from "@/lib/home";
import { resetEntrances, stagger } from "@/lib/motion";
import { palette } from "@/lib/palette";
import { useSession } from "@/lib/session";
import { Clock } from "@/components/Clock";
import { Emblem } from "@/components/Emblem";
import { IconArrow, IconEye, IconEyeOff, IconLock, IconUser } from "@/components/Icons";

// Icon cross-fade for an infrequent toggle. Under reduced motion only the opacity changes.
const SWAP =
  "[grid-area:1/1] transition-[opacity,filter,transform] duration-300 ease-swap motion-reduce:scale-100 motion-reduce:blur-[0px]";
const SHOWN = "scale-100 opacity-100 blur-[0px]";
const HIDDEN = "scale-[0.25] opacity-0 blur-[4px]";

function Crosshair({ className }: { className: string }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      stroke={palette.mute}
      strokeWidth="1.5"
      className={`absolute ${className}`}
      aria-hidden="true"
    >
      <path d="M7 0v14M0 7h14" />
    </svg>
  );
}

export default function LoginPage() {
  const { status, me, login } = useSession();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [reveal, setReveal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "ready" && me) router.replace(homePath(me));
  }, [status, me, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const signedIn = await login(username.trim(), password);
      resetEntrances();
      router.replace(homePath(signedIn));
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
      <header className="flex items-center justify-between bg-accent px-9 py-5 text-on-accent">
        <div className="flex items-center gap-4">
          <Emblem size={32} className="text-on-accent" />
          <div className="leading-tight">
            <div className="text-[1rem] font-bold tracking-[0.12em]">EIB DEFENCE GATEWAY</div>
            <div className="text-[0.85rem] tracking-[0.12em] text-on-accent/80">SECURE ASSISTANT</div>
          </div>
        </div>
        <div className="text-right text-[0.8rem] leading-relaxed text-on-accent/80">
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
          {/* Sign-in is rare, so it gets the one staged entrance: card and title, form, footer. */}
          <div className="enter border border-rule bg-surface">
            <div className="flex items-center gap-5 border-b border-rule px-8 py-6">
              <Emblem size={52} className="text-accent" />
              <div>
                <h1 className="text-[1.3rem] font-medium tracking-[0.1em]">EIB DEFENCE GATEWAY</h1>
                <p className="text-[0.95rem] tracking-[0.1em] text-soft">SECURE ASSISTANT</p>
              </div>
            </div>

            <form onSubmit={submit} className="enter flex flex-col gap-5 px-8 py-7" style={stagger(100)} noValidate>
              <div>
                <label htmlFor="username" className="label mb-2 block">
                  Username
                </label>
                <div className="relative">
                  <IconUser size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-soft" />
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
                  <IconLock size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-soft" />
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
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-soft hover:text-ink"
                  >
                    {/* Both icons stay mounted in one cell and cross-fade. */}
                    <span className="grid place-items-center">
                      <span className={`${SWAP} ${reveal ? SHOWN : HIDDEN}`}>
                        <IconEyeOff size={18} />
                      </span>
                      <span className={`${SWAP} ${reveal ? HIDDEN : SHOWN}`}>
                        <IconEye size={18} />
                      </span>
                    </span>
                  </button>
                </div>
              </div>

              {error && (
                <p role="alert" className="enter-fade border border-bad/60 px-3 py-2 text-[0.9rem] text-bad">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={busy || !username || !password}
                className="btn-accent flex items-center justify-center gap-3 pe-3.5"
              >
                {busy ? "Signing in" : "Log in"}
                <IconArrow size={18} weight="bold" />
              </button>
            </form>

            <div
              className="enter border-t border-rule px-8 py-4 text-center text-[0.75rem] tracking-[0.14em] text-soft"
              style={stagger(200)}
            >
              ACCESS-CONTROLLED <span className="mx-3 text-mute">/</span> AUDITABLE
            </div>
          </div>
        </div>
      </main>

    </div>
  );
}
