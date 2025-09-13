import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import threading
import sqlite3
import uuid

logger = logging.getLogger(__name__)

# SQLite-only storage backend
logger.info("Using SQLite backend for persistence")


class _LocalSqliteStore:
    """SQLite-backed store used when Supabase is not configured."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.file_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self._conn.cursor()
        # Базовая схема таблицы пользователей (без уникальности email для совместимости)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT,
                full_name TEXT,
                avatar_url TEXT,
                github_username TEXT,
                github_token TEXT,
                preferences TEXT,
                password_hash TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        # Добавляем недостающие колонки при апгрейде
        try:
            cur.execute("PRAGMA table_info(users)")
            cols = {row[1] for row in cur.fetchall()}
            # Добавляем password_hash, если отсутствует
            if 'password_hash' not in cols:
                cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            # На новых установках email уже есть; пытаемся создать уникальный индекс на email
            # Если в БД есть дубликаты, создание индекса упадёт — проглатываем и логируем.
            try:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users(email)")
            except Exception as e:
                logger.warning(f"Не удалось создать уникальный индекс на users.email (возможны дубликаты): {e}")
        except Exception as e:
            logger.warning(f"Проверка/миграция схемы users завершилась с предупреждением: {e}")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                repo_url TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                repo_owner TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                settings TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(user_id, repo_url)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                project_id INTEGER,
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
                changed_files TEXT,
                error TEXT,
                chat_messages TEXT,
                execution_metadata TEXT,
                created_at TEXT,
                updated_at TEXT,
                started_at TEXT,
                completed_at TEXT
            )
        """)
        self._conn.commit()

    # Helpers
    @staticmethod
    def _json_dump(data: Any) -> str:
        try:
            return json.dumps(data) if data is not None else None  # type: ignore[return-value]
        except Exception:
            return None  # type: ignore[return-value]

    @staticmethod
    def _json_load(data: Optional[str]) -> Any:
        if not data:
            return None
        try:
            return json.loads(data)
        except Exception:
            return None

    # Project operations
    def create_project(self, project: Dict) -> Dict:
        with self._lock:
            now = datetime.utcnow().isoformat()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO projects (user_id, repo_url, repo_name, repo_owner, name, description, is_active, settings, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.get('user_id'),
                    project.get('repo_url'),
                    project.get('repo_name'),
                    project.get('repo_owner'),
                    project.get('name'),
                    project.get('description'),
                    1 if project.get('is_active', True) else 0,
                    self._json_dump(project.get('settings') or {}),
                    now,
                    now,
                ),
            )
            project_id = cur.lastrowid
            self._conn.commit()
            return {**project, 'id': project_id, 'created_at': now, 'updated_at': now}

    def get_user_projects(self, user_id: str) -> List[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY datetime(created_at) DESC",
            (user_id,),
        )
        rows = cur.fetchall()
        result: List[Dict] = []
        for r in rows:
            d = dict(r)
            d['is_active'] = bool(d.get('is_active', 1))
            d['settings'] = self._json_load(d.get('settings')) or {}
            result.append(d)
        return result

    def get_project_by_id(self, project_id: int, user_id: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        )
        r = cur.fetchone()
        if not r:
            return None
        d = dict(r)
        d['is_active'] = bool(d.get('is_active', 1))
        d['settings'] = self._json_load(d.get('settings')) or {}
        return d

    def update_project(self, project_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        allowed = ['name', 'description', 'repo_url', 'repo_name', 'repo_owner', 'settings', 'is_active']
        set_parts = []
        values: List[Any] = []
        for k in allowed:
            if k in updates:
                v = updates[k]
                if k in ['settings']:
                    v = self._json_dump(v)
                if k == 'is_active':
                    v = 1 if bool(v) else 0
                set_parts.append(f"{k} = ?")
                values.append(v)
        values.extend([datetime.utcnow().isoformat(), project_id, user_id])
        if not set_parts:
            return self.get_project_by_id(project_id, user_id)
        sql = f"UPDATE projects SET {', '.join(set_parts)}, updated_at = ? WHERE id = ? AND user_id = ?"
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(values))
            self._conn.commit()
        return self.get_project_by_id(project_id, user_id)

    def delete_project(self, project_id: int, user_id: str) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
            self._conn.commit()
            return cur.rowcount > 0

    # Task operations
    def create_task(self, task: Dict) -> Dict:
        with self._lock:
            now = datetime.utcnow().isoformat()
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO tasks (
                    user_id, project_id, repo_url, target_branch, agent, status,
                    chat_messages, execution_metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.get('user_id'),
                    task.get('project_id'),
                    task.get('repo_url'),
                    task.get('target_branch'),
                    task.get('agent', 'claude'),
                    task.get('status', 'pending'),
                    self._json_dump(task.get('chat_messages') or []),
                    self._json_dump(task.get('execution_metadata') or {}),
                    now,
                    now,
                ),
            )
            task_id = cur.lastrowid
            self._conn.commit()
            return {**task, 'id': task_id, 'created_at': now, 'updated_at': now}

    def get_user_tasks(self, user_id: str, project_id: Optional[int] = None) -> List[Dict]:
        cur = self._conn.cursor()
        if project_id is not None:
            cur.execute(
                "SELECT * FROM tasks WHERE user_id = ? AND project_id = ? ORDER BY datetime(created_at) DESC",
                (user_id, project_id),
            )
        else:
            cur.execute(
                "SELECT * FROM tasks WHERE user_id = ? ORDER BY datetime(created_at) DESC",
                (user_id,),
            )
        rows = cur.fetchall()
        result: List[Dict] = []
        for r in rows:
            d = dict(r)
            d['chat_messages'] = self._json_load(d.get('chat_messages')) or []
            d['execution_metadata'] = self._json_load(d.get('execution_metadata')) or {}
            d['changed_files'] = self._json_load(d.get('changed_files')) or []
            return_fields = d
            result.append(return_fields)
        return result

    def get_task_by_id(self, task_id: int, user_id: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        )
        r = cur.fetchone()
        if not r:
            return None
        d = dict(r)
        d['chat_messages'] = self._json_load(d.get('chat_messages')) or []
        d['execution_metadata'] = self._json_load(d.get('execution_metadata')) or {}
        d['changed_files'] = self._json_load(d.get('changed_files')) or []
        return d

    def update_task(self, task_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        allowed_json = ['chat_messages', 'execution_metadata', 'changed_files']
        set_parts = []
        values: List[Any] = []
        for k, v in updates.items():
            if k in ['status', 'container_id', 'commit_hash', 'git_diff', 'git_patch', 'error', 'pr_branch', 'pr_url', 'pr_number', 'target_branch', 'repo_url', 'agent', 'started_at', 'completed_at'] + allowed_json:
                if k in allowed_json:
                    v = self._json_dump(v)
                set_parts.append(f"{k} = ?")
                values.append(v)
        values.extend([datetime.utcnow().isoformat(), task_id, user_id])
        if not set_parts:
            return self.get_task_by_id(task_id, user_id)
        sql = f"UPDATE tasks SET {', '.join(set_parts)}, updated_at = ? WHERE id = ? AND user_id = ?"
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(values))
            self._conn.commit()
        return self.get_task_by_id(task_id, user_id)

    def get_task_by_legacy_id(self, legacy_id: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM tasks")
        for r in cur.fetchall():
            meta = self._json_load(r['execution_metadata']) or {}
            if isinstance(meta, dict) and meta.get('legacy_id') == legacy_id:
                d = dict(r)
                d['chat_messages'] = self._json_load(d.get('chat_messages')) or []
                d['execution_metadata'] = meta
                d['changed_files'] = self._json_load(d.get('changed_files')) or []
                return d
        return None

    # Users
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        r = cur.fetchone()
        if not r:
            return None
        d = dict(r)
        d['preferences'] = self._json_load(d.get('preferences')) or {}
        return d

    def update_user(self, user_id: str, updates: Dict) -> Optional[Dict]:
        allowed = ['email', 'full_name', 'avatar_url', 'github_username', 'github_token', 'preferences', 'password_hash']
        set_parts = []
        values: List[Any] = []
        for k in allowed:
            if k in updates:
                v = updates[k]
                if k == 'preferences':
                    v = self._json_dump(v)
                set_parts.append(f"{k} = ?")
                values.append(v)
        values.extend([datetime.utcnow().isoformat(), user_id])
        if not set_parts:
            return self.get_user_by_id(user_id)
        sql = f"UPDATE users SET {', '.join(set_parts)}, updated_at = ? WHERE id = ?"
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(values))
            self._conn.commit()
        return self.get_user_by_id(user_id)

    # Новые операции пользователя
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        normalized = (email or '').strip().lower()
        cur.execute("SELECT * FROM users WHERE lower(email) = ?", (normalized,))
        r = cur.fetchone()
        if not r:
            return None
        d = dict(r)
        d['preferences'] = self._json_load(d.get('preferences')) or {}
        return d

    def create_user(self, user: Dict) -> Dict:
        with self._lock:
            now = datetime.utcnow().isoformat()
            cur = self._conn.cursor()
            user_id = user.get('id') or str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO users (id, email, full_name, avatar_url, github_username, github_token, preferences, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    (user.get('email') or '').strip().lower() or None,
                    user.get('full_name'),
                    user.get('avatar_url'),
                    user.get('github_username'),
                    user.get('github_token'),
                    self._json_dump(user.get('preferences') or {}),
                    user.get('password_hash'),
                    now,
                    now,
                ),
            )
            self._conn.commit()
            created = self.get_user_by_id(user_id)
            if not created:
                raise Exception('Failed to create user')
            return created


# Determine SQLite database file location
# По умолчанию хранить базу в каталоге `.data` рядом с исходниками сервера
default_db_path = os.getenv('LOCAL_DB_FILE')
if not default_db_path:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_db_path = os.path.join(base_dir, '.data', 'local.db')

# Ensure parent directory exists when using a filesystem path
db_dirname = os.path.dirname(default_db_path or '')
if db_dirname:
    try:
        os.makedirs(db_dirname, exist_ok=True)
    except Exception:
        # If directory cannot be created, let sqlite attempt to create file later
        pass

_local_db = _LocalSqliteStore(default_db_path)

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
            return _local_db.create_project(project_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            raise
    
    @staticmethod
    def get_user_projects(user_id: str) -> List[Dict]:
        """Get all projects for a user"""
        try:
            return _local_db.get_user_projects(user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching user projects: {e}")
            raise
    
    @staticmethod
    def get_project_by_id(project_id: int, user_id: str) -> Optional[Dict]:
        """Get a specific project by ID for a user"""
        try:
            return _local_db.get_project_by_id(project_id, user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching project {project_id}: {e}")
            raise
    
    @staticmethod
    def update_project(project_id: int, user_id: str, updates: Dict) -> Optional[Dict]:
        """Update a project"""
        try:
            updates['updated_at'] = datetime.utcnow().isoformat()
            return _local_db.update_project(project_id, user_id, updates)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error updating project {project_id}: {e}")
            raise
    
    @staticmethod
    def delete_project(project_id: int, user_id: str) -> bool:
        """Delete a project"""
        try:
            return _local_db.delete_project(project_id, user_id)  # type: ignore[union-attr]
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
            return _local_db.create_task(task_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            raise
    
    @staticmethod
    def get_user_tasks(user_id: str, project_id: int = None) -> List[Dict]:
        """Get all tasks for a user, optionally filtered by project"""
        try:
            return _local_db.get_user_tasks(user_id, project_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error fetching user tasks: {e}")
            raise
    
    @staticmethod
    def get_task_by_id(task_id: int, user_id: str) -> Optional[Dict]:
        """Get a specific task by ID for a user"""
        try:
            return _local_db.get_task_by_id(task_id, user_id)  # type: ignore[union-attr]
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
            return _local_db.update_task(task_id, user_id, updates)  # type: ignore[union-attr]
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
            return _local_db.get_task_by_legacy_id(legacy_id)  # type: ignore[union-attr]
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

            return _local_db.create_task(task_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error migrating legacy task: {e}")
            raise
    
    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        try:
            return _local_db.get_user_by_id(user_id)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict]:
        """Get user by email"""
        try:
            return _local_db.get_user_by_email(email)  # type: ignore[union-attr]
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
            return _local_db.create_user(user_data)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise

    @staticmethod
    def update_user_profile(user_id: str, updates: Dict) -> Optional[Dict]:
        """Update user profile"""
        try:
            return _local_db.update_user(user_id, updates)  # type: ignore[union-attr]
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            raise