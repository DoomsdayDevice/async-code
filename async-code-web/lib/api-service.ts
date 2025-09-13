import { ChatMessage } from "@/types";
import { API_BASE } from "@/lib/config";

export interface Project {
    id: number;
    user_id: string;
    repo_url: string;
    repo_name: string;
    repo_owner: string;
    name: string;
    description?: string;
    is_active?: boolean;
    settings?: any;
    created_at?: string;
    updated_at?: string;
}

export interface Task {
    id: number;
    user_id: string;
    project_id?: number | null;
    status: string;
    agent: string;
    repo_url?: string;
    target_branch: string;
    pr_branch?: string;
    container_id?: string;
    commit_hash?: string;
    pr_number?: number;
    pr_url?: string;
    git_diff?: string;
    git_patch?: string;
    changed_files?: any[];
    error?: string;
    chat_messages: ChatMessage[];
    execution_metadata?: any;
    created_at?: string;
    updated_at?: string;
    started_at?: string;
    completed_at?: string;
}

export interface ProjectWithStats extends Project {
    task_count?: number;
    completed_tasks?: number;
    active_tasks?: number;
}

// API_BASE определяется в '@/lib/config' и читает из NEXT_PUBLIC_API_BASE

// Helper function to get user ID header
function getUserIdHeader(userId?: string): HeadersInit {
    return userId ? { "X-User-ID": userId } : {};
}

export class ApiService {
    // Auth
    static async register(params: { email: string; password: string; full_name?: string }): Promise<{ user_id: string; user: any }> {
        const response = await fetch(`${API_BASE}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(params),
        });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || "Failed to register");
        }
        return response.json();
    }

    static async login(params: { email: string; password: string }): Promise<{ user_id: string; user: any }> {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(params),
        });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || "Failed to login");
        }
        return response.json();
    }

    // Users
    static async getCurrentUser(userId: string): Promise<any> {
        const response = await fetch(`${API_BASE}/users/me`, {
            headers: getUserIdHeader(userId),
        });
        if (!response.ok) throw new Error("Failed to fetch user");
        const data = await response.json();
        return data.user;
    }

    static async updateUserProfile(userId: string, updates: Record<string, any>): Promise<any> {
        const response = await fetch(`${API_BASE}/users/me`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(updates),
        });
        if (!response.ok) throw new Error("Failed to update user");
        const data = await response.json();
        return data.user;
    }
    // Project operations
    static async getProjects(userId: string): Promise<Project[]> {
        const response = await fetch(`${API_BASE}/projects`, {
            headers: getUserIdHeader(userId),
        });

        if (!response.ok) {
            throw new Error("Failed to fetch projects");
        }

        const data = await response.json();
        return data.projects || [];
    }

    static async createProject(
        userId: string,
        projectData: {
            name: string;
            description?: string;
            repo_url: string;
        }
    ): Promise<Project> {
        const response = await fetch(`${API_BASE}/projects`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(projectData),
        });

        if (!response.ok) {
            throw new Error("Failed to create project");
        }

        const data = await response.json();
        return data.project;
    }

    static async updateProject(userId: string, id: number, updates: Partial<Project>): Promise<Project> {
        const response = await fetch(`${API_BASE}/projects/${id}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(updates),
        });

        if (!response.ok) {
            throw new Error("Failed to update project");
        }

        const data = await response.json();
        return data.project;
    }

    static async deleteProject(userId: string, id: number): Promise<void> {
        const response = await fetch(`${API_BASE}/projects/${id}`, {
            method: "DELETE",
            headers: getUserIdHeader(userId),
        });

        if (!response.ok) {
            throw new Error("Failed to delete project");
        }
    }

    static async getProject(userId: string, id: number): Promise<Project | null> {
        const response = await fetch(`${API_BASE}/projects/${id}`, {
            headers: getUserIdHeader(userId),
        });

        if (response.status === 404) {
            return null;
        }

        if (!response.ok) {
            throw new Error("Failed to fetch project");
        }

        const data = await response.json();
        return data.project;
    }

    // Task operations
    static async getTasks(userId: string, projectId?: number): Promise<any[]> {
        const url = projectId ? `${API_BASE}/projects/${projectId}/tasks` : `${API_BASE}/tasks`;

        const response = await fetch(url, {
            headers: getUserIdHeader(userId),
        });

        if (projectId && response.status === 404) {
            // Проект не найден или не принадлежит пользователю — вернём пустой список
            return [];
        }

        if (!response.ok) {
            throw new Error("Failed to fetch tasks");
        }

        const data = await response.json();
        return Object.values(data.tasks || {});
    }

    static async getTask(userId: string, id: number): Promise<Task | null> {
        const response = await fetch(`${API_BASE}/tasks/${id}`, {
            headers: getUserIdHeader(userId),
        });

        if (response.status === 404) {
            return null;
        }

        if (!response.ok) {
            throw new Error("Failed to fetch task");
        }

        const data = await response.json();
        return data.task;
    }

    static async startTask(
        userId: string,
        taskData: {
            prompt: string;
            repo_url: string;
            branch?: string;
            github_token?: string;
            gitlab_token?: string;
            model?: string;
            project_id?: number;
        }
    ): Promise<{ task_id: number }> {
        const response = await fetch(`${API_BASE}/start-task`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(taskData),
        });

        if (!response.ok) {
            throw new Error("Failed to start task");
        }

        const data = await response.json();
        return data;
    }

    static async getTaskStatus(userId: string, taskId: number): Promise<any> {
        const response = await fetch(`${API_BASE}/task-status/${taskId}`, {
            headers: getUserIdHeader(userId),
        });

        if (!response.ok) {
            throw new Error("Failed to fetch task status");
        }

        const data = await response.json();
        return data.task;
    }

    static async addChatMessage(
        userId: string,
        taskId: number,
        message: {
            role: string;
            content: string;
        }
    ): Promise<Task> {
        const response = await fetch(`${API_BASE}/tasks/${taskId}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(message),
        });

        if (!response.ok) {
            throw new Error("Failed to add chat message");
        }

        const data = await response.json();
        return data.task;
    }

    static async createPullRequest(
        userId: string,
        taskId: number,
        prData: {
            title?: string;
            body?: string;
            github_token?: string;
            gitlab_token?: string;
        }
    ): Promise<{ pr_url: string; pr_number: number }> {
        const response = await fetch(`${API_BASE}/create-pr/${taskId}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(prData),
        });

        if (!response.ok) {
            throw new Error("Failed to create pull request");
        }

        const data = await response.json();
        return data;
    }

    static async retryTask(userId: string, taskId: number, tokens: { github_token?: string; gitlab_token?: string } = {}): Promise<{ task_id: number }> {
        const response = await fetch(`${API_BASE}/retry-task/${taskId}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getUserIdHeader(userId),
            },
            body: JSON.stringify(tokens),
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(errText || "Failed to retry task");
        }

        const data = await response.json();
        return data;
    }

    static async validateToken({
        githubToken,
        gitlabToken,
        repoUrl,
    }: {
        githubToken?: string;
        gitlabToken?: string;
        repoUrl?: string;
    }): Promise<{ user: string; repo?: any }> {
        const response = await fetch(`${API_BASE}/validate-token`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                github_token: githubToken,
                gitlab_token: gitlabToken,
                repo_url: repoUrl,
            }),
        });

        if (!response.ok) throw new Error("Token validation failed");

        const data = await response.json();
        return data;
    }

    static async getGitDiff(userId: string, taskId: number): Promise<string> {
        const response = await fetch(`${API_BASE}/git-diff/${taskId}`, {
            headers: getUserIdHeader(userId),
        });

        if (!response.ok) {
            throw new Error("Failed to fetch git diff");
        }

        const data = await response.json();
        return data.git_diff || "";
    }

    // Utility functions
    static parseGitUrl(url: string): { host: string; owner: string; repo: string } {
        const gh = url.match(/github\.com\/([^\/]+)\/([^\/]+?)(?:\.git)?(?:\/|$)/);
        if (gh) return { host: "github.com", owner: gh[1], repo: gh[2] };
        const gl = url.match(/gitlab\.com\/([^\/]+)\/([^\/]+?)(?:\.git)?(?:\/|$)/);
        if (gl) return { host: "gitlab.com", owner: gl[1], repo: gl[2] };
        throw new Error("Invalid Git URL");
    }
}
