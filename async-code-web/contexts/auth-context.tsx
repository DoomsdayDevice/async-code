"use client";

import React, { createContext, useContext, useEffect, useState } from "react";

interface LocalUser {
    id: string;
    email?: string;
}

interface AuthContextType {
    user: LocalUser | null;
    loading: boolean;
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

    useEffect(() => {
        // Use a local storage based user for now
        const storedId = typeof window !== "undefined" ? localStorage.getItem("user-id") : null;
        let localUser: LocalUser | null = null;
        if (storedId) {
            localUser = { id: storedId };
        } else {
            // Generate and persist a simple local user id
            const newId = crypto.randomUUID();
            if (typeof window !== "undefined") {
                localStorage.setItem("user-id", newId);
            }
            localUser = { id: newId };
        }
        setUser(localUser);
        setLoading(false);
    }, []);

    const signOut = async () => {
        if (typeof window !== "undefined") {
            localStorage.removeItem("user-id");
            // Recreate a fresh user id immediately for simplicity
            const newId = crypto.randomUUID();
            localStorage.setItem("user-id", newId);
            setUser({ id: newId });
        }
    };

    const value = {
        user,
        loading,
        signOut,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
