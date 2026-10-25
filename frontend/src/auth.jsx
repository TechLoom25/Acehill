import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, clearToken, getToken, setToken, setUnauthorizedHandler } from "./api.js";
import { ACCESS } from "./lib.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState("");
  const [setupInfo, setSetupInfo] = useState({ needsSetup: false, keyRequired: false });

  const boot = useCallback(async () => {
    setBooting(true);
    setBootError("");
    try {
      const s = await api("/auth/setup-status", { auth: false });
      setSetupInfo({ needsSetup: s.needs_setup, keyRequired: s.setup_key_required });
      if (!s.needs_setup && getToken()) {
        try {
          setUser(await api("/auth/me"));
        } catch (ex) {
          if (ex.status === 0) throw ex;
          clearToken(); // stale or revoked token
        }
      }
    } catch (ex) {
      setBootError(ex.message);
    }
    setBooting(false);
  }, []);

  useEffect(() => { boot(); }, [boot]);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);
  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const accept = (res) => {
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const value = useMemo(
    () => ({
      user,
      booting,
      bootError,
      retryBoot: boot,
      needsSetup: setupInfo.needsSetup,
      setupKeyRequired: setupInfo.keyRequired,
      logout,
      login: async (username, password) =>
        accept(await api("/auth/login", { method: "POST", body: { username, password }, auth: false })),
      setup: async (form) => {
        const u = accept(await api("/auth/setup", { method: "POST", body: form, auth: false }));
        setSetupInfo((s) => ({ ...s, needsSetup: false }));
        return u;
      },
      can: (action) => !!user && (user.role === "admin" || (ACCESS[action] ?? []).includes(user.role)),
    }),
    [user, booting, bootError, boot, setupInfo, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
