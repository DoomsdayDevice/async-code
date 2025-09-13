"use client";

import { useAuth } from "@/contexts/auth-context";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

interface ProtectedRouteProps {
    children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
    const { user, loading } = useAuth();
    const router = useRouter();
    const params = useSearchParams();

    useEffect(() => {
        // Переадресуем на /signin, если пользователь не аутентифицирован
        if (!loading && !user?.id) {
            const current = typeof window !== "undefined" ? window.location.pathname + window.location.search : "";
            const redirect = current && !current.startsWith("/signin") && !current.startsWith("/signup") ? `?redirect=${encodeURIComponent(current)}` : "";
            router.replace(`/signin${redirect}`);
        }
    }, [user, loading, router, params]);

    if (loading) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
            </div>
        );
    }

    if (!user?.id) return null;

    return <>{children}</>;
}
