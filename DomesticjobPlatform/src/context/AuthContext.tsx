import React, { createContext, useContext, useState, useEffect } from 'react';
import { Platform } from 'react-native';
import { api, setAuthToken } from '../services/api';

interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'STUDENT' | 'HOUSEHOLD' | 'ADMIN';
  phone_number?: string;
  student_profile?: {
    university_id: string;
    university_name: string;
    verification_status: string;
    availability_status: boolean;
  };
  household_profile?: {
    address: string;
    location_lat?: number;
    location_lng?: number;
    verification_status: string;
  };
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (identifier: string, pass: string) => Promise<void>;
  registerStudent: (data: any) => Promise<void>;
  registerHousehold: (data: any) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Helper for web / native storage
const storage = {
  getItem: async (key: string): Promise<string | null> => {
    try {
      if (Platform.OS === 'web') {
        return localStorage.getItem(key);
      }
      const SecureStore = await import('expo-secure-store');
      return await SecureStore.getItemAsync(key);
    } catch {
      return null;
    }
  },
  setItem: async (key: string, value: string): Promise<void> => {
    try {
      if (Platform.OS === 'web') {
        localStorage.setItem(key, value);
        return;
      }
      const SecureStore = await import('expo-secure-store');
      await SecureStore.setItemAsync(key, value);
    } catch {
      // fallback
    }
  },
  deleteItem: async (key: string): Promise<void> => {
    try {
      if (Platform.OS === 'web') {
        localStorage.removeItem(key);
        return;
      }
      const SecureStore = await import('expo-secure-store');
      await SecureStore.deleteItemAsync(key);
    } catch {
      // fallback
    }
  },
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadSession = async () => {
      try {
        const savedToken = await storage.getItem('auth_token');
        if (savedToken) {
          setAuthToken(savedToken);
          setToken(savedToken);
          const userData = await api.auth.me();
          setUser(userData);
        }
      } catch (err) {
        setAuthToken(null);
        setToken(null);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };
    loadSession();
  }, []);

  const login = async (identifier: string, pass: string) => {
    // Use local loading state in the calling screen — don't flip the global
    // isLoading flag here, which would flash the full-screen spinner on the
    // dashboard every time any button that calls login/register is pressed.
    const res = await api.auth.login(identifier, pass);
    await storage.setItem('auth_token', res.token);
    setAuthToken(res.token);
    setToken(res.token);
    setUser(res.user);
  };

  const registerStudent = async (data: any) => {
    const res = await api.auth.registerStudent(data);
    await storage.setItem('auth_token', res.token);
    setAuthToken(res.token);
    setToken(res.token);
    setUser(res.user);
  };

  const registerHousehold = async (data: any) => {
    const res = await api.auth.registerHousehold(data);
    await storage.setItem('auth_token', res.token);
    setAuthToken(res.token);
    setToken(res.token);
    setUser(res.user);
  };

  const logout = async () => {
    await storage.deleteItem('auth_token');
    setAuthToken(null);
    setToken(null);
    setUser(null);
  };

  const refreshMe = async () => {
    if (token) {
      const userData = await api.auth.me();
      setUser(userData);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        login,
        registerStudent,
        registerHousehold,
        logout,
        refreshMe,
      }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    // Return safe defaults during SSR / before AuthProvider mounts
    return {
      user: null,
      token: null,
      isLoading: true,
      login: async () => {},
      registerStudent: async () => {},
      registerHousehold: async () => {},
      logout: async () => {},
      refreshMe: async () => {},
    } as AuthContextType;
  }
  return context;
};
