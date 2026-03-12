/**
 * Auth context — supports two modes:
 *
 * 1. Supabase mode (production + any env with VITE_SUPABASE_URL set):
 *    - Login/logout via supabase.auth.*
 *    - Session managed by Supabase SDK (auto-refresh, localStorage)
 *    - Token extracted from Supabase session, attached to axios
 *    - /api/auth/me called on session change to hydrate enriched profile
 *
 * 2. Bridge mode (dev without Supabase credentials):
 *    - Login via POST /api/auth/login (local users table, bcrypt)
 *    - Token stored in sessionStorage
 *    - /api/auth/me called on load to restore session
 *
 * The rest of the app is identical in both modes — it reads from `user` and
 * calls `login(email, password)` / `logout()` regardless of which mode is active.
 */

import { createContext, useContext, useState, useEffect, useRef } from "react";
import axios from "axios";
import api from "@/lib/api-client";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";

const AuthContext = createContext(null);

const isAuthEndpoint = (url) => {
  if (!url) return false;
  return url.includes("/auth/login") || url.includes("/auth/register");
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const logoutRef = useRef(null);

  // ── Shared helpers ──────────────────────────────────────────────────────────

  const _setAxiosToken = (token) => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common["Authorization"];
    }
  };

  const _fetchProfile = async () => {
    try {
      const data = await api.auth.me();
      setUser(data);
    } catch {
      logoutRef.current?.();
    }
  };

  // ── 401 interceptor (shared) ────────────────────────────────────────────────

  useEffect(() => {
    logoutRef.current = isSupabaseConfigured ? _supabaseLogout : _bridgeLogout;
  });

  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (res) => res,
      (error) => {
        if (error.response?.status === 401 && !isAuthEndpoint(error.config?.url)) {
          logoutRef.current?.();
        }
        return Promise.reject(error);
      },
    );
    return () => axios.interceptors.response.eject(interceptor);
  }, []);

  // ── Supabase mode ───────────────────────────────────────────────────────────

  const _supabaseLogout = async () => {
    await supabase.auth.signOut();
    _setAxiosToken(null);
    setUser(null);
  };

  useEffect(() => {
    if (!isSupabaseConfigured) return;

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (session?.access_token) {
        _setAxiosToken(session.access_token);
        await _fetchProfile();
      } else {
        _setAxiosToken(null);
        setUser(null);
        setLoading(false);
      }
    });

    // Hydrate on mount from existing session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token) {
        _setAxiosToken(session.access_token);
        _fetchProfile().finally(() => setLoading(false));
      } else {
        setLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const _supabaseLogin = async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    _setAxiosToken(data.session.access_token);
    await _fetchProfile();
    return user;
  };

  const _supabaseRegister = async (email, password, name) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { name } },
    });
    if (error) throw error;
    if (data.session?.access_token) {
      _setAxiosToken(data.session.access_token);
      await _fetchProfile();
    }
    return user;
  };

  // ── Bridge mode (dev, no Supabase) ──────────────────────────────────────────

  const _bridgeLogout = () => {
    sessionStorage.removeItem("token");
    _setAxiosToken(null);
    setUser(null);
  };

  useEffect(() => {
    if (isSupabaseConfigured) return;

    const token = sessionStorage.getItem("token");
    if (token) {
      _setAxiosToken(token);
      _fetchProfile().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const _bridgeLogin = async (email, password) => {
    const { token, user: userData } = await api.auth.login({ email, password });
    sessionStorage.setItem("token", token);
    _setAxiosToken(token);
    setUser(userData);
    return userData;
  };

  const _bridgeRegister = async (email, password, name) => {
    const { token, user: userData } = await api.auth.register({ email, password, name });
    sessionStorage.setItem("token", token);
    _setAxiosToken(token);
    setUser(userData);
    return userData;
  };

  // ── Public API ──────────────────────────────────────────────────────────────

  const login = isSupabaseConfigured ? _supabaseLogin : _bridgeLogin;
  const register = isSupabaseConfigured ? _supabaseRegister : _bridgeRegister;
  const logout = () => {
    if (isSupabaseConfigured) {
      _supabaseLogout();
    } else {
      _bridgeLogout();
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};
