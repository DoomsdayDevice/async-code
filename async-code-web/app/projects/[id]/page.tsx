"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Save, Trash2, Github, FolderGit2 } from "lucide-react";
import { ProtectedRoute } from "@/components/protected-route";
import { useAuth } from "@/contexts/auth-context";
import { ApiService } from "@/lib/api-service";
import { Project } from "@/types";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function ProjectSettingsPage() {
    const params = useParams();
    const projectId = parseInt(params.id as string);
    const { user } = useAuth();

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [project, setProject] = useState<Project | null>(null);
    const [form, setForm] = useState({
        name: "",
        description: "",
        repo_url: "",
    });

    useEffect(() => {
        if (user?.id && projectId) {
            loadProject();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?.id, projectId]);

    const loadProject = async () => {
        if (!user?.id || !projectId) return;
        try {
            setLoading(true);
            const data = await ApiService.getProject(user.id, projectId);
            setProject(data);
            if (data) {
                setForm({
                    name: data.name || "",
                    description: (data.description as string) || "",
                    repo_url: data.repo_url || "",
                });
            }
        } catch (e) {
            console.error("Failed to load project", e);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        if (!user?.id || !projectId) return;
        try {
            setSaving(true);
            const updated = await ApiService.updateProject(user.id, projectId, {
                name: form.name,
                description: form.description,
                repo_url: form.repo_url,
            });
            setProject(updated);
            toast.success("Project updated");
        } catch (e: any) {
            console.error(e);
            toast.error("Failed to update project");
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (!user?.id || !projectId) return;
        if (!confirm("Delete this project and all its tasks?")) return;
        try {
            await ApiService.deleteProject(user.id, projectId);
            toast.success("Project deleted");
            window.location.href = "/projects";
        } catch (e) {
            console.error(e);
            toast.error("Failed to delete project");
        }
    };

    if (loading) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
                    <div className="text-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900 mx-auto"></div>
                        <p className="text-slate-600 mt-2">Loading project...</p>
                    </div>
                </div>
            </ProtectedRoute>
        );
    }

    if (!project) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
                    <div className="text-center">
                        <p className="text-xl font-semibold text-slate-900 mb-2">Project Not Found</p>
                        <Link href="/projects">
                            <Button>Back to Projects</Button>
                        </Link>
                    </div>
                </div>
            </ProtectedRoute>
        );
    }

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
                <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-50">
                    <div className="container mx-auto px-6 py-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <Link href="/projects" className="text-slate-600 hover:text-slate-900 flex items-center gap-2">
                                    <ArrowLeft className="w-4 h-4" />
                                    Back to Projects
                                </Link>
                                <div>
                                    <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
                                        <FolderGit2 className="w-5 h-5" />
                                        {project.name}
                                    </h1>
                                    <p className="text-sm text-slate-500 flex items-center gap-1">
                                        <Github className="w-3 h-3" />
                                        {project.repo_owner}/{project.repo_name}
                                    </p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <Link href={`/projects/${projectId}/tasks`}>
                                    <Button variant="outline">View Tasks</Button>
                                </Link>
                                <Button variant="destructive" onClick={handleDelete} className="gap-2">
                                    <Trash2 className="w-4 h-4" />
                                    Delete
                                </Button>
                                <Button onClick={handleSave} disabled={saving} className="gap-2">
                                    <Save className="w-4 h-4" />
                                    {saving ? "Saving..." : "Save"}
                                </Button>
                            </div>
                        </div>
                    </div>
                </header>

                <main className="container mx-auto px-6 py-8 max-w-3xl">
                    <Card>
                        <CardHeader>
                            <CardTitle>Project Settings</CardTitle>
                            <CardDescription>Update repository and metadata</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="space-y-2">
                                <label className="text-sm font-medium" htmlFor="name">Name</label>
                                <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium" htmlFor="repo_url">Repository URL</label>
                                <Input id="repo_url" value={form.repo_url} onChange={(e) => setForm({ ...form, repo_url: e.target.value })} />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium" htmlFor="description">Description</label>
                                <Textarea id="description" rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                            </div>
                        </CardContent>
                    </Card>
                </main>
            </div>
        </ProtectedRoute>
    );
}


