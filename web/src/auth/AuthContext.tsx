import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { get, post, tokens } from "../api/client";
import type { Me, PublicConfig } from "../api/types";

type Ctx = {
  me: Me | null;
  loading: boolean;
  config: PublicConfig | null;
  refreshMe: () => Promise<void>;
  loginWithTokens: (t: { access: string; refresh: string }) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: string[]) => boolean;
  isStaff: boolean;
};

const AuthCtx = createContext<Ctx>(null as unknown as Ctx);
export const STAFF_ROLES = ["reviewer", "coordinator", "sysadmin", "accountant", "financial_auditor"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  const refreshMe = useCallback(async () => {
    if (!tokens.get()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await get<Me>("/me"));
    } catch {
      // Keep the session when offline; drop it only when the server rejects the token
      if (!tokens.get()) setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe();
    get<PublicConfig>("/config").then(setConfig).catch(() => {});
    return tokens.subscribe(() => {
      if (!tokens.get()) setMe(null);
    });
  }, [refreshMe]);

  const loginWithTokens = async (t: { access: string; refresh: string }) => {
    tokens.set(t);
    await refreshMe();
  };
  const logout = async () => {
    const t = tokens.get();
    try {
      if (t) await post("/auth/logout", { refresh: t.refresh });
    } catch {
      /* offline logout still clears local session */
    }
    tokens.set(null);
    setMe(null);
  };
  const hasRole = (...roles: string[]) => !!me?.roles.some((r) => r.active && roles.includes(r.role));
  return (
    <AuthCtx.Provider value={{ me, loading, config, refreshMe, loginWithTokens, logout, hasRole,
      isStaff: !!me?.roles.some((r) => STAFF_ROLES.includes(r.role)) }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
