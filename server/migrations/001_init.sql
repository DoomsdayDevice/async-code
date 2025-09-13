-- users
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT,
  full_name TEXT,
  avatar_url TEXT,
  github_username TEXT,
  github_token TEXT,
  preferences JSONB DEFAULT '{}'::jsonb,
  password_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
  ON users (lower(email))
  WHERE email IS NOT NULL;

-- projects
CREATE TABLE IF NOT EXISTS projects (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  repo_url TEXT NOT NULL,
  repo_name TEXT NOT NULL,
  repo_owner TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  settings JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, repo_url)
);

-- tasks
CREATE TABLE IF NOT EXISTS tasks (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  project_id BIGINT REFERENCES projects(id) ON DELETE SET NULL,
  status TEXT DEFAULT 'pending',
  agent TEXT DEFAULT 'claude',
  repo_url TEXT,
  target_branch TEXT DEFAULT 'main',
  pr_branch TEXT,
  container_id TEXT,
  commit_hash TEXT,
  pr_number INTEGER,
  pr_url TEXT,
  git_diff TEXT,
  git_patch TEXT,
  changed_files JSONB DEFAULT '[]'::jsonb,
  error TEXT,
  chat_messages JSONB DEFAULT '[]'::jsonb,
  execution_metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

-- indexes
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

