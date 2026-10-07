"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, readToken, storeToken, type Me } from "./api";

type Status = "loading" | "anon" | "ready";

interface Session {
  status: Status;
  me: Me | null;
  login: (username: string, password: string) => Promise<Me>;
  logout: () => void;
  can: (permission: string) => boolean;
}

const Ctx = createContext<Session | null>(null);

// The JWT lives in React state and sessionStorage only. Logout drops it in the
// browser; the token itself stays valid until expiry (docs/PRODUCTION_DEBT.md).
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    const token = readToken();
    if (!token) {
      setStatus("anon");
      return;
    }
    api
      .me(token)
      .then((m) => {
        setMe(m);
        setStatus("ready");
      })
      .catch(() => {
        storeToken(null);
        setStatus("anon");
      });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const { access_token } = await api.login(username, password);
    storeToken(access_token);
    let profile: Me;
    try {
      profile = await api.me(access_token);
    } catch (err) {
      storeToken(null);
      throw err;
    }
    setMe(profile);
    setStatus("ready");
    return profile;
  }, []);

  const logout = useCallback(() => {
    storeToken(null);
    setMe(null);
    setStatus("anon");
  }, []);

  const value = useMemo<Session>(
    () => ({ status, me, login, logout, can: (p) => !!me?.permissions.includes(p) }),
    [status, me, login, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

export { ApiError };
