import { createContext, useContext, useState, useEffect, useRef } from "react";
import axios from "axios";
import api from "@/lib/api-client";

const AuthContext = createContext(null);

const isAuthEndpoint = (url) => {
  if (!url) return false;
  return url.includes("/auth/login") || url.includes("/auth/register");
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(sessionStorage.getItem("token"));
  const [loading, setLoading] = useState(true);
  const logoutRef = useRef(null);

  useEffect(() => {
    logoutRef.current = () => {
      sessionStorage.removeItem("token");
      delete axios.defaults.headers.common["Authorization"];
      setToken(null);
      setUser(null);
    };
  }, []);

  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (res) => res,
      (error) => {
        if (
          error.response?.status === 401 &&
          !isAuthEndpoint(error.config?.url)
        ) {
          logoutRef.current?.();
        }
        return Promise.reject(error);
      },
    );
    return () => axios.interceptors.response.eject(interceptor);
  }, []);

  const logout = () => logoutRef.current?.();

  const fetchUser = async () => {
    try {
      const data = await api.auth.me();
      setUser(data);
    } catch {
      logout();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      fetchUser();
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchUser is stable (no deps), token is the only trigger
  }, [token]);

  const login = async (email, password) => {
    const { token: newToken, user: userData } = await api.auth.login({
      email,
      password,
    });
    sessionStorage.setItem("token", newToken);
    axios.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
    setToken(newToken);
    setUser(userData);
    return userData;
  };

  const register = async (email, password, name) => {
    const { token: newToken, user: userData } = await api.auth.register({
      email,
      password,
      name,
    });
    sessionStorage.setItem("token", newToken);
    axios.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
    setToken(newToken);
    setUser(userData);
    return userData;
  };

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, register, logout }}
    >
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
