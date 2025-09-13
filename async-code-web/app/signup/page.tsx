"use client";

import { useAuth } from "@/contexts/auth-context";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function SignUp() {
    const { user, loading, registerWithEmail } = useAuth();
    const router = useRouter();
    const params = useSearchParams();

    const [email, setEmail] = useState("");
    const [fullName, setFullName] = useState("");
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (!loading && user?.id) {
            const redirectTo = params.get("redirect") || "/";
            router.replace(redirectTo);
        }
    }, [user, loading, router, params]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        const trimmedEmail = email.trim();
        const trimmedPass = password.trim();
        const trimmedConfirm = confirm.trim();
        if (!trimmedEmail || !trimmedPass) return;
        if (trimmedPass.length < 6) {
            setError("Пароль должен быть не менее 6 символов");
            return;
        }
        if (trimmedPass !== trimmedConfirm) {
            setError("Пароли не совпадают");
            return;
        }
        setSubmitting(true);
        try {
            await registerWithEmail(trimmedEmail, trimmedPass, fullName.trim());
            const redirectTo = params.get("redirect") || "/";
            router.replace(redirectTo);
        } catch (err: any) {
            const msg = String(err?.message || err);
            if (msg.includes("already") || msg.includes("409")) {
                setError("Email уже зарегистрирован");
            } else if (msg.toLowerCase().includes("invalid email")) {
                setError("Некорректный email");
            } else {
                setError("Не удалось зарегистрироваться");
            }
        } finally {
            setSubmitting(false);
        }
    };

    if (loading || user?.id) return null;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center px-4">
            <Card className="w-full max-w-md shadow-lg">
                <CardHeader>
                    <CardTitle>Sign Up</CardTitle>
                    <CardDescription>Создайте аккаунт, используя email и пароль.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="fullName">Full name</Label>
                            <Input id="fullName" type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Jane Doe" />
                        </div>

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

                        <div className="space-y-2">
                            <Label htmlFor="confirm">Confirm Password</Label>
                            <Input id="confirm" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="••••••••" required />
                        </div>

                        {error ? <div className="text-sm text-red-600">{error}</div> : null}

                        <div className="flex items-center justify-between pt-2">
                            <div className="text-sm text-muted-foreground">
                                Уже есть аккаунт?{" "}
                                <Link className="underline" href="/signin">
                                    Войти
                                </Link>
                            </div>
                            <div className="flex gap-2">
                                <Link href="/">
                                    <Button variant="ghost" type="button">
                                        Отмена
                                    </Button>
                                </Link>
                                <Button type="submit" disabled={submitting || !email.trim() || !password.trim() || !confirm.trim()}>
                                    {submitting ? "Загрузка..." : "Зарегистрироваться"}
                                </Button>
                            </div>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
