"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

interface LocalUser {
    id: string;
    email?: string;
}

interface AuthContextType {
    user: LocalUser | null;
    loading: boolean;
    signIn: (id: string, email?: string) => Promise<void>;
    signInWithEmail: (email: string, password: string) => Promise<void>;
    signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}

interface AuthProviderProps {
    children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
    const [user, setUser] = useState<LocalUser | null>(null);
    const [loading, setLoading] = useState(true);

    // Хэширование SHA-256 в hex
    const sha256Hex = async (text: string): Promise<string> => {
        const encoder = new TextEncoder();
        const data = encoder.encode(text);
        const hashBuffer = await crypto.subtle.digest("SHA-256", data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
    };

    useEffect(() => {
        // Инициализация локальной аутентификации: читаем сохранённый ID или используем дефолт из env
        const storedId = typeof window !== "undefined" ? localStorage.getItem("user-id") : null;
        const storedEmail = typeof window !== "undefined" ? localStorage.getItem("user-email") : null;
        const defaultId = process.env.NEXT_PUBLIC_DEFAULT_USER_ID?.trim();

        if (storedId) {
            setUser({ id: storedId, email: storedEmail || undefined });
        } else if (defaultId) {
            if (typeof window !== "undefined") {
                localStorage.setItem("user-id", defaultId);
                if (storedEmail) localStorage.setItem("user-email", storedEmail);
            }
            setUser({ id: defaultId, email: storedEmail || undefined });
        } else {
            // Нет пользователя — пусть защищённые экраны переадресуют на /signin
            setUser(null);
        }
        setLoading(false);
    }, []);

    const signIn = async (id: string, email?: string) => {
        // Простая локальная авторизация: сохраняем ID и опционально email
        if (typeof window !== "undefined") {
            localStorage.setItem("user-id", id);
            if (email && email.trim()) {
                localStorage.setItem("user-email", email.trim());
            } else {
                localStorage.removeItem("user-email");
            }
        }
        setUser({ id, email: email?.trim() || undefined });
    };

    const signInWithEmail = async (email: string, password: string) => {
        // Локальная эмуляция логина: детерминированный userId = sha256(email:password)
        const normalizedEmail = (email || "").trim().toLowerCase();
        const userId = await sha256Hex(`${normalizedEmail}:${password || ""}`);
        await signIn(userId, normalizedEmail);
    };

    const signOut = async () => {
        if (typeof window !== "undefined") {
            localStorage.removeItem("user-id");
            localStorage.removeItem("user-email");
            setUser(null);
        }
    };

    const value = {
        user,
        loading,
        signIn,
        signInWithEmail,
        signOut,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
