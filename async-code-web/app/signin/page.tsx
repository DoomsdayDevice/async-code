"use client";

import { useAuth } from "@/contexts/auth-context";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function SignIn() {
    const { user, loading, signInWithEmail } = useAuth();
    const router = useRouter();
    const params = useSearchParams();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        // Если уже залогинен — переадресуем
        if (!loading && user?.id) {
            const redirectTo = params.get("redirect") || "/";
            router.replace(redirectTo);
        }
    }, [user, loading, router, params]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email.trim() || !password.trim()) return;
        setSubmitting(true);
        try {
            await signInWithEmail(email.trim(), password.trim());
            const redirectTo = params.get("redirect") || "/";
            router.replace(redirectTo);
        } finally {
            setSubmitting(false);
        }
    };

    if (loading || user?.id) return null;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center px-4">
            <Card className="w-full max-w-md shadow-lg">
                <CardHeader>
                    <CardTitle>Sign In</CardTitle>
                    <CardDescription>Войдите, используя email и пароль. Данные хранятся локально.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="email">Email</Label>
                            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="password">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                required
                            />
                        </div>

                        <div className="flex items-center justify-between pt-2">
                            <Link href="/">
                                <Button variant="ghost" type="button">
                                    Отмена
                                </Button>
                            </Link>
                            <Button type="submit" disabled={submitting || !email.trim() || !password.trim()}>
                                {submitting ? "Загрузка..." : "Войти"}
                            </Button>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
