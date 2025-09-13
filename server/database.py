import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import uuid
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

# Переключение на Postgres backend для постоянного хранения данных
logger.info("Используется Postgres backend для постоянного хранения данных")


# ... существующий код удалён (sqlite), используем миграции Postgres ниже ...


class _PostgresStore:
    """PostgreSQL-backed store using psycopg with a connection pool."""

    def __init__(self, conninfo: str, min_size: int = 1, max_size: int = 10):
        self.pool = ConnectionPool(conninfo=conninfo, min_size=min_size, max_size=max_size, timeout=30)
        self._init_schema()

    @classmethod
    def from_env(cls) -> "_PostgresStore":
        conninfo = os.getenv("DATABASE_URL")
        if not conninfo:
            host = os.getenv("DB_HOST", "localhost")
            port = int(os.getenv("DB_PORT", "5432"))
            dbname = os.getenv("DB_NAME", "asynccode")
            user = os.getenv("DB_USER", "asynccode")
            password = os.getenv("DB_PASSWORD", "asynccode")
            conninfo = f"host={host} port={port} dbname={dbname} user={user} password={password}"
        return cls(conninfo)

    def _init_schema(self) -> None:
        """Run SQL migrations from migrations directory (idempotent)."""
        migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
        os.makedirs(migrations_dir, exist_ok=True)
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        id BIGSERIAL PRIMARY KEY,
                        filename TEXT UNIQUE NOT NULL,
                        applied_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
                conn.commit()

            # Apply .sql files in lexical order if not yet applied
            filenames = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])
            for name in filenames:
                path = os.path.join(migrations_dir, name)
                with self.pool.connection() as c2:
                    with c2.cursor() as cur2:
                        cur2.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (name,))
                        if cur2.fetchone():
                            continue
                        with open(path, 'r', encoding='utf-8') as f:
                            sql_text = f.read()
                        cur2.execute(sql_text)
                        cur2.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (name,))
                        c2.commit()

    # Project operations
    def create_project(self, project: Dict) -> Dict:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO projects (user_id, repo_url, repo_name, repo_owner, name, description, is_active, settings)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at, updated_at
                    """,
                    (
                        project.get('user_id'),
                        project.get('repo_url'),
                        project.get('repo_name'),
                        project.get('repo_owner'),
                        project.get('name'),
                        project.get('description'),
                        bool(project.get('is_active', True)),
                        project.get('settings') or {}
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return {**project, 'id': row['id'], 'created_at': row['created_at'].isoformat(), 'updated_at': row['updated_at'].isoformat()}

    def get_user_projects(self, user_id: str) -> List[Dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM projects WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,),
                )
                rows = cur.fetchall()
                for d in rows:
                    d['is_active'] = bool(d.get('is_active', True))
                    d['settings'] = d.get('settings') or {}
                return rows

    def get_project_by_id(self, project_id: int, user_id: str) -> Optional[Dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM projects WHERE id = %s AND user_id = %s",
                    (project_id, user_id),
                )
                d = cur.fetchone()
                if not d:
                    return None
                d['is_active'] = bool(d.get('is_active', True))
                d['settings'] = d.get('settings') or {}
                return d

    def update_project(self, project_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        allowed = ['name', 'description', 'repo_url', 'repo_name', 'repo_owner', 'settings', 'is_active']
        set_parts: List[str] = []
        values: List[Any] = []
        for k in allowed:
            if k in updates:
                v = updates[k]
                if k == 'is_active':
                    v = bool(v)
                set_parts.append(f"{k} = %s")
                values.append(v)
        if not set_parts:
            return self.get_project_by_id(project_id, user_id)
        values.extend([project_id, user_id])
        sql = f"UPDATE projects SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s AND user_id = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(values))
                conn.commit()
        return self.get_project_by_id(project_id, user_id)

    def delete_project(self, project_id: int, user_id: str) -> bool:
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, user_id))
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted

    # Task operations
    def create_task(self, task: Dict) -> Dict:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO tasks (
                        user_id, project_id, repo_url, target_branch, agent, status,
                        chat_messages, execution_metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, created_at, updated_at
                    """,
                    (
                        task.get('user_id'),
                        task.get('project_id'),
                        task.get('repo_url'),
                        task.get('target_branch'),
                        task.get('agent', 'claude'),
                        task.get('status', 'pending'),
                        task.get('chat_messages') or [],
                        task.get('execution_metadata') or {}
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return {**task, 'id': row['id'], 'created_at': row['created_at'].isoformat(), 'updated_at': row['updated_at'].isoformat()}

    def get_user_tasks(self, user_id: str, project_id: Optional[int] = None) -> List[Dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if project_id is not None:
                    cur.execute(
                        "SELECT * FROM tasks WHERE user_id = %s AND project_id = %s ORDER BY created_at DESC",
                        (user_id, project_id),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM tasks WHERE user_id = %s ORDER BY created_at DESC",
                        (user_id,),
                    )
                rows = cur.fetchall()
                for d in rows:
                    d['chat_messages'] = d.get('chat_messages') or []
                    d['execution_metadata'] = d.get('execution_metadata') or {}
                    d['changed_files'] = d.get('changed_files') or []
                return rows

    def get_task_by_id(self, task_id: int, user_id: str) -> Optional[Dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM tasks WHERE id = %s AND user_id = %s",
                    (task_id, user_id),
                )
                d = cur.fetchone()
                if not d:
                    return None
                d['chat_messages'] = d.get('chat_messages') or []
                d['execution_metadata'] = d.get('execution_metadata') or {}
                d['changed_files'] = d.get('changed_files') or []
                return d

    def update_task(self, task_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        allowed = [
            'status', 'container_id', 'commit_hash', 'git_diff', 'git_patch', 'error',
            'pr_branch', 'pr_url', 'pr_number', 'target_branch', 'repo_url', 'agent',
            'started_at', 'completed_at', 'chat_messages', 'execution_metadata', 'changed_files'
        ]
        set_parts: List[str] = []
        values: List[Any] = []
        for k, v in updates.items():
            if k in allowed:
                set_parts.append(f"{k} = %s")
                values.append(v)
        if not set_parts:
            return self.get_task_by_id(task_id, user_id)
        values.extend([task_id, user_id])
        sql = f"UPDATE tasks SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s AND user_id = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(values))
                conn.commit()
        return self.get_task_by_id(task_id, user_id)

    def get_task_by_legacy_id(self, legacy_id: str) -> Optional[Dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM tasks WHERE execution_metadata->>'legacy_id' = %s",
                    (legacy_id,)
                )
                d = cur.fetchone()
                if not d:
                    return None
                d['chat_messages'] = d.get('chat_messages') or []
                d['execution_metadata'] = d.get('execution_metadata') or {}
                d['changed_files'] = d.get('changed_files') or []
                return d

    # Users
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                d = cur.fetchone()
                if not d:
                    return None
                d['preferences'] = d.get('preferences') or {}
                return d

    def update_user(self, user_id: str, updates: Dict) -> Optional[Dict]:
        allowed = ['email', 'full_name', 'avatar_url', 'github_username', 'github_token', 'preferences', 'password_hash']
        set_parts: List[str] = []
        values: List[Any] = []
        for k in allowed:
            if k in updates:
                set_parts.append(f"{k} = %s")
                values.append(updates[k])
        if not set_parts:
            return self.get_user_by_id(user_id)
        values.append(user_id)
        sql = f"UPDATE users SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s"
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(values))
                conn.commit()
        return self.get_user_by_id(user_id)

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        normalized = (email or '').strip().lower()
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM users WHERE lower(email) = %s", (normalized,))
                d = cur.fetchone()
                if not d:
                    return None
                d['preferences'] = d.get('preferences') or {}
                return d

    def create_user(self, user: Dict) -> Dict:
        user_id = user.get('id') or str(uuid.uuid4())
        with self.pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO users (id, email, full_name, avatar_url, github_username, github_token, preferences, password_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING created_at, updated_at
                    """,
                    (
                        user_id,
                        (user.get('email') or '').strip().lower() or None,
                        user.get('full_name'),
                        user.get('avatar_url'),
                        user.get('github_username'),
                        user.get('github_token'),
                        user.get('preferences') or {},
                        user.get('password_hash'),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return {**(user or {}), 'id': user_id, 'created_at': row['created_at'].isoformat(), 'updated_at': row['updated_at'].isoformat()}

# SQLite backend устарел; используем Postgres

_db = _PostgresStore.from_env()


class DatabaseOperations:
    
    @staticmethod
    def create_project(user_id: str, name: str, description: str, repo_url: str, 
                      repo_name: str, repo_owner: str, settings: Dict = None) -> Dict:
        """Create a new project"""
        try:
            project_data = {
                'user_id': user_id,
                'name': name,
                'description': description,
                'repo_url': repo_url,
                'repo_name': repo_name,
                'repo_owner': repo_owner,
                'settings': settings or {},
                'is_active': True
            }
            return _db.create_project(project_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            raise
    
    @staticmethod
    def get_user_projects(user_id: str) -> List[Dict]:
        """Get all projects for a user"""
        try:
            return _db.get_user_projects(user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching user projects: {e}")
            raise
    
    @staticmethod
    def get_project_by_id(project_id: int, user_id: str) -> Optional[Dict]:
        """Get a specific project by ID for a user"""
        try:
            return _db.get_project_by_id(project_id, user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching project {project_id}: {e}")
            raise
    
    @staticmethod
    def update_project(project_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        """Update a project"""
        try:
            updates['updated_at'] = datetime.utcnow().isoformat()
            return _db.update_project(project_id, user_id, updates)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error updating project {project_id}: {e}")
            raise
    
    @staticmethod
    def delete_project(project_id: int, user_id: str) -> bool:
        """Delete a project"""
        try:
            return _db.delete_project(project_id, user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error deleting project {project_id}: {e}")
            raise
    
    @staticmethod
    def create_task(user_id: str, project_id: int = None, repo_url: str = None, 
                   target_branch: str = 'main', agent: str = 'claude', 
                   chat_messages: List[Dict] = None) -> Dict:
        """Create a new task"""
        try:
            task_data = {
                'user_id': user_id,
                'project_id': project_id,
                'repo_url': repo_url,
                'target_branch': target_branch,
                'agent': agent,
                'status': 'pending',
                'chat_messages': chat_messages or [],
                'execution_metadata': {}
            }
            return _db.create_task(task_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise
    
    @staticmethod
    def get_user_tasks(user_id: str, project_id: int = None) -> List[Dict]:
        """Get all tasks for a user, optionally filtered by project"""
        try:
            return _db.get_user_tasks(user_id, project_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching user tasks: {e}")
            raise
    
    @staticmethod
    def get_task_by_id(task_id: int, user_id: str) -> Optional[Dict]:
        """Get a specific task by ID for a user"""
        try:
            return _db.get_task_by_id(task_id, user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching task {task_id}: {e}")
            raise
    
    @staticmethod
    def update_task(task_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        """Update a task"""
        try:
            # Handle timestamps
            if 'status' in updates:
                if updates['status'] == 'running' and 'started_at' not in updates:
                    updates['started_at'] = datetime.utcnow().isoformat()
                elif updates['status'] in ['completed', 'failed', 'cancelled'] and 'completed_at' not in updates:
                    updates['completed_at'] = datetime.utcnow().isoformat()
            
            updates['updated_at'] = datetime.utcnow().isoformat()
            return _db.update_task(task_id, user_id, updates)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}")
            raise
    
    @staticmethod
    def add_chat_message(task_id: int, user_id: str, role: str, content: str) -> Optional[Dict]:
        """Add a chat message to a task"""
        try:
            # Get current task
            task = DatabaseOperations.get_task_by_id(task_id, user_id)
            if not task:
                return None
            
            # Add new message
            chat_messages = task.get('chat_messages', [])
            new_message = {
                'role': role,
                'content': content,
                'timestamp': datetime.utcnow().isoformat()
            }
            chat_messages.append(new_message)
            
            # Update task
            return DatabaseOperations.update_task(task_id, user_id, {'chat_messages': chat_messages})
        except Exception as e:
            logger.error(f"Error adding chat message to task {task_id}: {e}")
            raise
    
    @staticmethod
    def get_task_by_legacy_id(legacy_id: str) -> Optional[Dict]:
        """Get a task by its legacy UUID (for migration purposes)"""
        try:
            return _db.get_task_by_legacy_id(legacy_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching task by legacy ID {legacy_id}: {e}")
            raise
    
    @staticmethod
    def migrate_legacy_task(legacy_task: Dict, user_id: str) -> Optional[Dict]:
        """Migrate a legacy task from the JSON storage to SQLite"""
        try:
            # Map legacy task structure to new structure
            task_data = {
                'user_id': user_id,
                'repo_url': legacy_task.get('repo_url'),
                'target_branch': legacy_task.get('branch', 'main'),
                'agent': legacy_task.get('model', 'claude'),
                'status': legacy_task.get('status', 'pending'),
                'container_id': legacy_task.get('container_id'),
                'commit_hash': legacy_task.get('commit_hash'),
                'git_diff': legacy_task.get('git_diff'),
                'git_patch': legacy_task.get('git_patch'),
                'changed_files': legacy_task.get('changed_files', []),
                'error': legacy_task.get('error'),
                'chat_messages': [{
                    'role': 'user',
                    'content': legacy_task.get('prompt', ''),
                    'timestamp': datetime.fromtimestamp(legacy_task.get('created_at', 0)).isoformat()
                }] if legacy_task.get('prompt') else [],
                'execution_metadata': {
                    'legacy_id': legacy_task.get('id'),
                    'migrated_at': datetime.utcnow().isoformat()
                }
            }
            
            # Set timestamps if available
            if legacy_task.get('created_at'):
                task_data['created_at'] = datetime.fromtimestamp(legacy_task['created_at']).isoformat()

            return _db.create_task(task_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error migrating legacy task: {e}")
            raise
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        try:
            return _db.get_user_by_id(user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict]:
        """Get user by email"""
        try:
            return _db.get_user_by_email(email)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return None

    @staticmethod
    def create_user(email: str, full_name: Optional[str], password_hash: str) -> Dict:
        """Create a new user (email unique enforced at app level)."""
        try:
            user_data = {
                'email': (email or '').strip().lower(),
                'full_name': (full_name or '').strip() or None,
                'password_hash': password_hash,
                'preferences': {},
            }
            return _db.create_user(user_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise

    @staticmethod
    def update_user_profile(user_id: str, updates: Dict) -> Optional[Dict]:
        """Update user profile"""
        try:
            return _db.update_user(user_id, updates)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            raise