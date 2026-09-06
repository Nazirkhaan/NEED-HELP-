"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api, getToken, setToken } from "./api";

export type SessionUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  role_display: string;
  permissions: string[];
  institution_id: string | null;
  institution_name: string | null;
  organization_id: string | null;
  organization_name: string | null;
  consent_given: boolean;
};

type AuthCtx = {
  user: SessionUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<SessionUser>;
  logout: () => void;
  refresh: () => Promise<void>;
  can: (perm: string) => boolean;
};

const Ctx = createContext<AuthCtx>({
  user: null,
  loading: true,
  login: async () => {
    throw new Error("not mounted");
  },
  logout: () => {},
  refresh: async () => {},
  can: () => false,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api<SessionUser>("/auth/me");
      setUser(me);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ access_token: string; user: SessionUser }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) }
    );
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const can = useCallback(
    (perm: string) => {
      if (!user) return false;
      const perms = user.permissions || [];
      return perms.includes("*") || perms.includes(perm);
    },
    [user]
  );

  return (
    <Ctx.Provider value={{ user, loading, login, logout, refresh, can }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  return useContext(Ctx);
}

export const ROLE_HOME: Record<string, string> = {
  student: "/student",
  tpo: "/tpo",
  industry: "/industry",
  admin: "/admin",
};
