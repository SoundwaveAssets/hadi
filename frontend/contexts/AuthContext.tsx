"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, REMEMBERED_STORAGE_KEY, TOKEN_STORAGE_KEY, USER_STORAGE_KEY } from "@/lib/api";

export type UserRole = "developer" | "admin" | "security_officer" | "direction";

export interface AuthUser {
  username: string;
  role: UserRole;
  email?: string | null;
  must_change_password: boolean;
  created_at?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<AuthUser>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readCachedUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_STORAGE_KEY);
    return raw && window.localStorage.getItem(TOKEN_STORAGE_KEY) ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function persist(user: AuthUser) {
  window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Session restaurée depuis le cache local au premier rendu client (pas
  // d'écran blanc), puis confirmée côté serveur. Le serveur SSR rend sans
  // session : les deux rendus affichent le même spinner, aucun décalage.
  const [user, setUser] = useState<AuthUser | null>(readCachedUser);
  const [isLoading, setIsLoading] = useState<boolean>(() => readCachedUser() !== null);

  useEffect(() => {
    if (!readCachedUser()) return;
    api
      .get<AuthUser>("/api/auth/me")
      .then((res) => {
        setUser(res.data);
        persist(res.data);
      })
      .catch(() => {
        setUser(null);
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        window.localStorage.removeItem(USER_STORAGE_KEY);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string, rememberMe = false) => {
    const response = await api.post("/api/auth/login", { username, password, remember_me: rememberMe });
    const { access_token, username: uname, role, must_change_password, remembered } = response.data;
    let authUser: AuthUser = { username: uname, role, must_change_password };

    window.localStorage.setItem(TOKEN_STORAGE_KEY, access_token);
    // Session longue : le verrouillage par inactivité ne s'y applique pas,
    // c'est tout l'objet de l'option (voir lib/session.ts).
    if (remembered) window.localStorage.setItem(REMEMBERED_STORAGE_KEY, "1");
    else window.localStorage.removeItem(REMEMBERED_STORAGE_KEY);
    persist(authUser);
    setUser(authUser);

    // /login ne renvoie que le strict nécessaire ; /me complète email et date.
    try {
      const me = await api.get<AuthUser>("/api/auth/me");
      authUser = me.data;
      persist(authUser);
      setUser(authUser);
    } catch {
      // Pas bloquant : le sous-ensemble déjà stocké suffit.
    }
    return authUser;
  }, []);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    window.localStorage.removeItem(USER_STORAGE_KEY);
    window.localStorage.removeItem(REMEMBERED_STORAGE_KEY);
    setUser(null);
    window.location.href = "/login";
  }, []);

  const refreshUser = useCallback(async () => {
    const res = await api.get<AuthUser>("/api/auth/me");
    setUser(res.data);
    persist(res.data);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout, refreshUser }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth doit être utilisé à l'intérieur d'un <AuthProvider>.");
  }
  return ctx;
}
