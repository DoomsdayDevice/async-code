// SQLite-backed API types (frontend)
export interface Project {
    id: number;
    user_id: string;
    repo_url: string;
    repo_name: string;
    repo_owner: string;
    name: string;
    description?: string | null;
    is_active?: boolean | null;
    settings?: any;
    created_at?: string | null;
    updated_at?: string | null;
}

export interface Task {
    id: number;
    user_id: string;
    project_id?: number | null;
    status: string;
    agent: string;
    repo_url?: string | null;
    target_branch: string;
    pr_branch?: string | null;
    container_id?: string | null;
    commit_hash?: string | null;
    pr_number?: number | null;
    pr_url?: string | null;
    git_diff?: string | null;
    git_patch?: string | null;
    changed_files?: any[];
    error?: string | null;
    chat_messages: ChatMessage[];
    execution_metadata?: any;
    created_at?: string | null;
    updated_at?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
}

export interface User {
    id: string;
    email?: string | null;
    full_name?: string | null;
    avatar_url?: string | null;
    github_username?: string | null;
    github_token?: string | null;
    preferences?: any;
    created_at?: string | null;
    updated_at?: string | null;
}

// Chat message interface for tasks
export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
    timestamp: string;
}

// File change interface for merge view
export interface FileChange {
    filename: string;
    before: string;
    after: string;
}

// Frontend-specific interfaces
export interface TaskWithProject extends Task {
    project?: Project;
    file_changes?: FileChange[];
}

export interface ProjectWithStats extends Project {
    task_count?: number;
    completed_tasks?: number;
    active_tasks?: number;
}

// Legacy task interface for backward compatibility
export interface LegacyTask {
    id: string;
    status: string;
    prompt: string;
    repo_url: string;
    branch: string;
    model?: string;
    commit_hash?: string;
    error?: string;
    created_at: number;
}

// API response types
export interface ApiResponse<T = any> {
    status: "success" | "error";
    data?: T;
    error?: string;
    message?: string;
}

export interface TaskListResponse {
    status: "success";
    tasks: Record<
        string,
        {
            id: number;
            status: string;
            created_at: string;
            prompt: string;
            has_patch: boolean;
            project_id?: number;
            repo_url: string;
            agent: string;
        }
    >;
    total_tasks: number;
}

export interface ProjectListResponse {
    status: "success";
    projects: Project[];
}
