"use client";

import { useState, useEffect, useCallback } from "react";
import { ApiService } from "@/lib/api-service";
import { useAuth } from "@/contexts/auth-context";

export function useUserProfile() {
    const { user } = useAuth();
    const [profile, setProfile] = useState<any | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<Error | null>(null);

    const fetchProfile = useCallback(async () => {
        try {
            setIsLoading(true);
            if (!user?.id) {
                setProfile(null);
                setError(null);
                setIsLoading(false);
                return;
            }
            const data = await ApiService.getCurrentUser(user.id);
            setProfile(data);
            setError(null);
        } catch (err) {
            setError(err as Error);
            console.error("Failed to fetch user profile:", err);
        } finally {
            setIsLoading(false);
        }
    }, [user?.id]);

    useEffect(() => {
        fetchProfile();
    }, [fetchProfile]);

    const refreshProfile = useCallback(async () => {
        await fetchProfile();
    }, [fetchProfile]);

    return {
        profile,
        isLoading,
        error,
        refreshProfile,
    };
}
