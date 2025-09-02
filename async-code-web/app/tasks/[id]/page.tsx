"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import {
    ArrowLeft,
    Github,
    Clock,
    CheckCircle,
    XCircle,
    AlertCircle,
    GitCommit,
    FileText,
    ExternalLink,
    MessageSquare,
    Plus,
    Copy,
    Loader2,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ProtectedRoute } from "@/components/protected-route";
import { useAuth } from "@/contexts/auth-context";
import { ApiService } from "@/lib/api-service";
import { Task, Project, ChatMessage } from "@/types";
import { formatDiff, parseDiffStats } from "@/lib/utils";
import { DiffViewer } from "@/components/diff-viewer";
import { toast } from "sonner";

interface TaskWithProject extends Task {
    project?: Project;
}

export default function TaskDetailPage() {
    const { user } = useAuth();
    const params = useParams();
    const taskId = parseInt(params.id as string);

    const [task, setTask] = useState<TaskWithProject | null>(null);
    const [loading, setLoading] = useState(true);
    const [gitDiff, setGitDiff] = useState("");
    const [diffStats, setDiffStats] = useState({ additions: 0, deletions: 0, files: 0 });
    const [newMessage, setNewMessage] = useState("");
    const [githubToken, setGithubToken] = useState("");
    const [gitlabToken, setGitlabToken] = useState("");
    const [creatingPR, setCreatingPR] = useState(false);

    useEffect(() => {
        if (typeof window !== "undefined") {
            const savedToken = localStorage.getItem("github-token");
            if (savedToken) setGithubToken(savedToken);
            const savedGitlab = localStorage.getItem("gitlab-token");
            if (savedGitlab) setGitlabToken(savedGitlab);
        }
    }, []);

    useEffect(() => {
        if (user?.id && taskId) {
            loadTask();
        }
    }, [user?.id, taskId]);

    // Poll for status updates if task is running
    useEffect(() => {
        if (!user?.id || !task || (task.status !== "running" && task.status !== "pending")) return;

        const interval = setInterval(async () => {
            try {
                const updatedTask = await ApiService.getTaskStatus(user.id, taskId);
                setTask((prev) => ({ ...prev, ...updatedTask }));

                // Fetch git diff if task completed
                if (updatedTask.status === "completed" && !gitDiff) {
                    try {
                        const diff = await ApiService.getGitDiff(user.id, taskId);
                        setGitDiff(diff);
                        const stats = parseDiffStats(diff);
                        setDiffStats(stats);
                    } catch (error) {
                        console.error("Error fetching git diff:", error);
                    }
                }
            } catch (error) {
                console.error("Error polling task status:", error);
            }
        }, 2000);

        return () => clearInterval(interval);
    }, [task, user?.id, taskId, gitDiff]);

    const loadTask = async () => {
        if (!user?.id) return;

        try {
            setLoading(true);
            const taskData = await ApiService.getTask(user.id, taskId);
            setTask(taskData);

            // Load git diff if task is completed
            if (taskData?.status === "completed") {
                try {
                    const diff = await ApiService.getGitDiff(user.id, taskId);
                    setGitDiff(diff);
                    const stats = parseDiffStats(diff);
                    setDiffStats(stats);
                } catch (error) {
                    console.error("Error fetching git diff:", error);
                }
            }
        } catch (error) {
            console.error("Error loading task:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleAddMessage = async () => {
        if (!newMessage.trim() || !user?.id) return;

        try {
            await ApiService.addChatMessage(user.id, taskId, {
                role: "user",
                content: newMessage.trim(),
            });
            setNewMessage("");
            toast.success("Message added successfully");
            loadTask(); // Reload to get updated messages
        } catch (error) {
            console.error("Error adding message:", error);
            toast.error("Failed to add message");
        }
    };

    const handleCreatePR = async () => {
        if (!task || task.status !== "completed" || !user?.id) return;

        setCreatingPR(true);

        try {
            const prompt = (task.chat_messages as unknown as ChatMessage[])?.[0]?.content || "";
            const modelName = task.agent === "codex" ? "Codex" : "Claude Code";

            toast.loading("Creating pull request...");

            const response = await ApiService.createPullRequest(user.id, task.id, {
                title: `${modelName}: ${prompt.substring(0, 50)}...`,
                body: `Automated changes generated by ${modelName}.\n\nPrompt: ${prompt}`,
                github_token: githubToken,
                gitlab_token: gitlabToken,
            });

            toast.dismiss();
            toast.success(`Pull request #${response.pr_number} created successfully!`);

            // Refresh task data to show the new PR info
            await loadTask();

            // Open the PR in a new tab
            window.open(response.pr_url, "_blank");
        } catch (error) {
            toast.dismiss();
            toast.error(`Failed to create PR: ${error}`);
        } finally {
            setCreatingPR(false);
        }
    };

    const getStatusVariant = (status: string) => {
        switch (status) {
            case "pending":
                return "secondary";
            case "running":
                return "default";
            case "completed":
                return "default";
            case "failed":
                return "destructive";
            default:
                return "outline";
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case "pending":
                return <Clock className="w-4 h-4" />;
            case "running":
                return <AlertCircle className="w-4 h-4" />;
            case "completed":
                return <CheckCircle className="w-4 h-4" />;
            case "failed":
                return <XCircle className="w-4 h-4" />;
            default:
                return null;
        }
    };

    if (loading) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
                    <div className="text-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900 mx-auto"></div>
                        <p className="text-slate-600 mt-2">Loading task...</p>
                    </div>
                </div>
            </ProtectedRoute>
        );
    }

    if (!task) {
        return (
            <ProtectedRoute>
                <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center">
                    <div className="text-center">
                        <XCircle className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                        <h3 className="text-xl font-semibold text-slate-900 mb-2">Task Not Found</h3>
                        <p className="text-slate-600 mb-6">The task you're looking for doesn't exist or you don't have access to it.</p>
                        <Link href="/">
                            <Button>Back to Dashboard</Button>
                        </Link>
                    </div>
                </div>
            </ProtectedRoute>
        );
    }

    return (
        <ProtectedRoute>
            <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
                {/* Header */}
                <header className="border-b bg-white/80 backdrop-blur-sm sticky top-0 z-50">
                    <div className="container mx-auto px-6 py-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <Link href="/" className="text-slate-600 hover:text-slate-900 flex items-center gap-2">
                                    <ArrowLeft className="w-4 h-4" />
                                    Back to Dashboard
                                </Link>
                                <div>
                                    <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
                                        Task #{task.id}
                                        <Badge variant={getStatusVariant(task.status || "")} className="gap-1">
                                            {getStatusIcon(task.status || "")}
                                            {task.status}
                                        </Badge>
                                    </h1>
                                    <p className="text-sm text-slate-500">
                                        {task.project ? `${task.project.name} • ` : ""}
                                        {task.agent?.toUpperCase()} •{new Date(task.created_at || "").toLocaleString()}
                                    </p>
                                </div>
                            </div>
                            {task.status === "completed" &&
                                (task.pr_url ? (
                                    <Button asChild variant="outline" className="gap-2">
                                        <a href={task.pr_url} target="_blank" rel="noopener noreferrer">
                                            <ExternalLink className="w-4 h-4" />
                                            {task.repo_url?.includes("gitlab.com") ? "View MR" : "View PR"} #{task.pr_number}
                                        </a>
                                    </Button>
                                ) : (
                                    <Button onClick={handleCreatePR} disabled={creatingPR} className="gap-2">
                                        {creatingPR ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
                                        {creatingPR
                                            ? task.repo_url?.includes("gitlab.com")
                                                ? "Creating MR..."
                                                : "Creating PR..."
                                            : task.repo_url?.includes("gitlab.com")
                                            ? "Create MR"
                                            : "Create PR"}
                                    </Button>
                                ))}
                        </div>
                    </div>
                </header>

                {/* Main Content */}
                <main className="container mx-auto px-6 py-8 max-w-8xl">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                        {/* Left Column - Task Details */}
                        <div className="lg:col-span-2 space-y-6">
                            {/* Task Info */}
                            <Card>
                                <CardHeader>
                                    <CardTitle>Task Information</CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <Label className="text-sm font-medium text-slate-500">Repository</Label>
                                            <p className="text-sm">{task.repo_url}</p>
                                        </div>
                                        <div>
                                            <Label className="text-sm font-medium text-slate-500">Branch</Label>
                                            <p className="text-sm">{task.target_branch}</p>
                                        </div>
                                        <div>
                                            <Label className="text-sm font-medium text-slate-500">AI Model</Label>
                                            <p className="text-sm">{task.agent?.toUpperCase()}</p>
                                        </div>
                                        <div>
                                            <Label className="text-sm font-medium text-slate-500">Created</Label>
                                            <p className="text-sm">{new Date(task.created_at || "").toLocaleString()}</p>
                                        </div>
                                    </div>

                                    {task.commit_hash && (
                                        <div>
                                            <Label className="text-sm font-medium text-slate-500">Commit Hash</Label>
                                            <div className="flex items-center gap-2 mt-1">
                                                <code className="bg-slate-100 px-2 py-1 rounded text-sm">{task.commit_hash.substring(0, 12)}</code>
                                                <Button variant="ghost" size="sm" onClick={() => navigator.clipboard.writeText(task.commit_hash || "")}>
                                                    <Copy className="w-3 h-3" />
                                                </Button>
                                            </div>
                                        </div>
                                    )}

                                    {task.pr_url && (
                                        <div>
                                            <Label className="text-sm font-medium text-slate-500">
                                                {task.repo_url?.includes("gitlab.com") ? "Merge Request" : "Pull Request"}
                                            </Label>
                                            <div className="flex items-center gap-2 mt-1">
                                                <a
                                                    href={task.pr_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-blue-600 hover:underline text-sm"
                                                >
                                                    #{task.pr_number} - View on {task.repo_url?.includes("gitlab.com") ? "GitLab" : "GitHub"}
                                                </a>
                                                <ExternalLink className="w-3 h-3 text-slate-400" />
                                            </div>
                                        </div>
                                    )}

                                    {task.error && (
                                        <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                                            <div className="flex items-center gap-2 text-red-800 mb-2">
                                                <XCircle className="w-4 h-4" />
                                                <span className="font-medium">Error</span>
                                            </div>
                                            <p className="text-sm text-red-700">{task.error}</p>
                                        </div>
                                    )}

                                    {task.status === "running" && (
                                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                            <div className="flex items-center gap-3">
                                                <div className="animate-spin">
                                                    <AlertCircle className="w-5 h-5 text-blue-600" />
                                                </div>
                                                <div>
                                                    <div className="font-medium text-blue-900">AI is working on your code...</div>
                                                    <div className="text-sm text-blue-700 mt-1">
                                                        This may take a few minutes. You can safely close this page.
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="mt-3 bg-blue-100 rounded-full h-2">
                                                <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{ width: "60%" }}></div>
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>

                            {/* Git Diff */}
                            {gitDiff && (
                                <Card>
                                    <CardHeader>
                                        <CardTitle className="flex items-center gap-2">
                                            <CheckCircle className="w-5 h-5 text-green-600" />
                                            Code Changes
                                        </CardTitle>
                                        <CardDescription>Review the changes made by AI</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <DiffViewer diff={gitDiff} fileChanges={(task.execution_metadata as any)?.file_changes} stats={diffStats} />
                                    </CardContent>
                                </Card>
                            )}
                        </div>

                        {/* Right Column - Chat Messages */}
                        <div>
                            <Card className="h-fit">
                                <CardHeader>
                                    <CardTitle className="flex items-center gap-2">
                                        <MessageSquare className="w-5 h-5" />
                                        Task Messages
                                    </CardTitle>
                                    <CardDescription>Conversation history for this task</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    {/* Chat Messages */}
                                    <div className="space-y-3 max-h-96 overflow-y-auto">
                                        {(task.chat_messages as unknown as ChatMessage[])?.map((message, index) => (
                                            <div
                                                key={index}
                                                className={`p-3 rounded-lg ${
                                                    message.role === "user" ? "bg-blue-50 border border-blue-200" : "bg-slate-50 border border-slate-200"
                                                }`}
                                            >
                                                <div className="flex items-center gap-2 mb-2">
                                                    <Badge variant={message.role === "user" ? "default" : "secondary"}>
                                                        {message.role === "user" ? "You" : "Assistant"}
                                                    </Badge>
                                                    <span className="text-xs text-slate-500">{new Date(message.timestamp).toLocaleString()}</span>
                                                </div>
                                                <p className="text-sm text-slate-700 whitespace-pre-wrap">{message.content}</p>
                                            </div>
                                        )) || (
                                            <div className="text-center py-4 text-slate-500">
                                                <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                                <p className="text-sm">No messages yet</p>
                                            </div>
                                        )}
                                    </div>

                                    {/* Add Message Input */}
                                    <Separator />
                                    <div className="space-y-3">
                                        <Label className="text-sm font-medium">Add a note or follow-up instruction</Label>
                                        <div className="flex gap-2">
                                            <Input
                                                value={newMessage}
                                                onChange={(e) => setNewMessage(e.target.value)}
                                                placeholder="Type your message..."
                                                onKeyPress={(e) => e.key === "Enter" && handleAddMessage()}
                                            />
                                            <Button onClick={handleAddMessage} disabled={!newMessage.trim()}>
                                                <Plus className="w-4 h-4" />
                                            </Button>
                                        </div>
                                        <p className="text-xs text-slate-500">
                                            Note: This is for tracking purposes only. New messages won't trigger additional AI processing.
                                        </p>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                </main>
            </div>
        </ProtectedRoute>
    );
}
