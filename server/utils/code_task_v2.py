import json
import os
import logging
import docker
import docker.types
import uuid
import time
import random
from datetime import datetime
from database import DatabaseOperations
import fcntl
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Docker client
docker_client = docker.from_env()

def write_task_logs(task_id: int, model_cli: str, logs_content: str) -> None:
    """Persist container logs for a task under .data/logs.

    Tries these locations in order:
      1) $APP_DATA_DIR/logs (if APP_DATA_DIR is set)
      2) /app/.data/logs (Docker backend container)
      3) <repo>/server/.data/logs (local dev running python main.py)
      4) CWD fallback: ./server/.data/logs

    Logs are appended to allow multiple runs/retries for the same task id.
    """
    try:
        candidates = []
        app_data_env = os.getenv('APP_DATA_DIR')
        if app_data_env:
            candidates.append(os.path.join(app_data_env, 'logs'))
        candidates.append('/app/.data/logs')
        # Resolve repo/server path from this file location
        server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        candidates.append(os.path.join(server_dir, '.data', 'logs'))
        # CWD fallback
        candidates.append(os.path.join(os.getcwd(), 'server', '.data', 'logs'))

        logs_dir = None
        last_err = None
        for candidate in candidates:
            try:
                os.makedirs(candidate, exist_ok=True)
                logs_dir = candidate
                break
            except Exception as e:
                last_err = e
                continue

        if not logs_dir:
            raise last_err or Exception('No writable logs directory found')

        file_path = os.path.join(logs_dir, f"task-{task_id}.log")
        timestamp = datetime.now().isoformat()
        header = f"\n\n===== {timestamp} {model_cli.upper()} CONTAINER LOGS =====\n"
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(header)
            f.write(logs_content or '')
            if not logs_content or not logs_content.endswith('\n'):
                f.write('\n')
    except Exception as e:
        logger.warning(f"⚠️  Failed to write logs for task {task_id}: {e}")

def cleanup_orphaned_containers():
    """Clean up orphaned AI code task containers aggressively"""
    try:
        # Get all containers with our naming pattern
        containers = docker_client.containers.list(all=True, filters={'name': 'ai-code-task-'})
        orphaned_count = 0
        current_time = time.time()
        
        for container in containers:
            try:
                # Get container creation time
                created_at = container.attrs['Created']
                # Parse ISO format timestamp and convert to epoch time
                created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00')).timestamp()
                age_hours = (current_time - created_time) / 3600
                
                # Remove containers that are:
                # 1. Not running (exited, dead, created)
                # 2. OR older than 2 hours (stuck containers)
                # 3. OR in error state
                should_remove = (
                    container.status in ['exited', 'dead', 'created'] or
                    age_hours > 2 or
                    container.status == 'restarting'
                )
                
                if should_remove:
                    logger.info(f"🧹 Removing orphaned container {container.id[:12]} (status: {container.status}, age: {age_hours:.1f}h)")
                    container.remove(force=True)
                    orphaned_count += 1
                
            except Exception as e:
                logger.warning(f"⚠️  Failed to cleanup container {container.id[:12]}: {e}")
                # If we can't inspect it, try to force remove it anyway
                try:
                    container.remove(force=True)
                    orphaned_count += 1
                    logger.info(f"🧹 Force removed problematic container: {container.id[:12]}")
                except Exception as force_error:
                    logger.warning(f"⚠️  Could not force remove container {container.id[:12]}: {force_error}")
        
        if orphaned_count > 0:
            logger.info(f"🧹 Cleaned up {orphaned_count} orphaned containers")
        
    except Exception as e:
        logger.warning(f"⚠️  Failed to cleanup orphaned containers: {e}")

def run_ai_code_task_v2(task_id: int, user_id: str, github_token: str):
    """Run AI Code automation (Claude or Codex) in a container - Supabase version"""
    try:
        # Get task from database to check the model type
        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            logger.error(f"Task {task_id} not found in database")
            return
        
        model_cli = task.get('agent', 'claude')
        
        # With comprehensive sandboxing fixes, both Claude and Codex can now run in parallel
        logger.info(f"🚀 Running {model_cli.upper()} task {task_id} directly in parallel mode")
        return _run_ai_code_task_v2_internal(task_id, user_id, github_token)
            
    except Exception as e:
        logger.error(f"💥 Exception in run_ai_code_task_v2: {str(e)}")
        try:
            DatabaseOperations.update_task(task_id, user_id, {
                'status': 'failed',
                'error': str(e)
            })
        except:
            logger.error(f"Failed to update task {task_id} status after exception")

def _run_ai_code_task_v2_internal(task_id: int, user_id: str, github_token: str):
    """Internal implementation of AI Code automation - called directly for Claude or via queue for Codex"""
    try:
        # Clean up any orphaned containers before starting new task
        cleanup_orphaned_containers()
        
        # Get task from database (v2 function)
        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            logger.error(f"Task {task_id} not found in database")
            return
        
        # Update task status to running
        DatabaseOperations.update_task(task_id, user_id, {'status': 'running'})
        
        model_name = task.get('agent', 'claude').upper()
        logger.info(f"🚀 Starting {model_name} Code task {task_id}")
        
        # Get prompt from chat messages
        prompt = ""
        if task.get('chat_messages'):
            for msg in task['chat_messages']:
                if msg.get('role') == 'user':
                    prompt = msg.get('content', '')
                    break
        
        if not prompt:
            error_msg = "No user prompt found in chat messages"
            logger.error(error_msg)
            DatabaseOperations.update_task(task_id, user_id, {
                'status': 'failed',
                'error': error_msg
            })
            return
        
        logger.info(f"📋 Task details: prompt='{prompt[:50]}...', repo={task['repo_url']}, branch={task['target_branch']}, model={model_name}")
        logger.info(f"Starting {model_name} task {task_id}")
        
        # Escape special characters in prompt for shell safety
        escaped_prompt = prompt.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        
        # Create container environment variables
        env_vars = {
            'CI': 'true',  # Indicate we're in CI/non-interactive environment
            'TERM': 'dumb',  # Use dumb terminal to avoid interactive features
            'NO_COLOR': '1',  # Disable colors for cleaner output
            'FORCE_COLOR': '0',  # Disable colors for cleaner output
            'NONINTERACTIVE': '1',  # Common flag for non-interactive mode
            'DEBIAN_FRONTEND': 'noninteractive',  # Non-interactive package installs
        }
        
        # Add model-specific API keys and environment variables
        model_cli = task.get('agent', 'claude')
        
        # Get user preferences for custom environment variables
        user = DatabaseOperations.get_user_by_id(user_id)
        user_preferences = user.get('preferences', {}) if user else {}
        
        if user_preferences:
            logger.info(f"🔧 Found user preferences for {model_cli}: {list(user_preferences.keys())}")
        
        if model_cli == 'claude':
            # Start with default Claude environment
            claude_env = {
                'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY'),
                'ANTHROPIC_NONINTERACTIVE': '1'  # Custom flag for Anthropic tools
            }
            # Merge with user's custom Claude environment variables
            claude_config = user_preferences.get('claudeCode', {})
            if claude_config and claude_config.get('env'):
                claude_env.update(claude_config['env'])
            env_vars.update(claude_env)
        elif model_cli == 'codex':
            # Базовые переменные окружения для полностью неинтерактивного режима Codex
            codex_env = {
                'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
                'OPENAI_NONINTERACTIVE': '1',
                'CODEX_QUIET_MODE': '1',
                'CODEX_UNSAFE_ALLOW_NO_SANDBOX': '1',
                'CODEX_DISABLE_SANDBOX': '1',
                'CODEX_NO_SANDBOX': '1',
                'NODE_NO_READLINE': '1',
                'TERM': 'dumb'  # Принудительно «тупой» терминал без TTY-фич
            }
            # Merge with user's custom Codex environment variables
            codex_config = user_preferences.get('codex', {})
            if codex_config and codex_config.get('env'):
                codex_env.update(codex_config['env'])
            env_vars.update(codex_env)
        
        # Use specialized container images based on model
        if model_cli == 'codex':
            container_image = 'codex-automation:latest'
        else:
            container_image = 'claude-code-automation:latest'
        
        # Add staggered start to prevent race conditions with parallel Codex tasks
        if model_cli == 'codex':
            # Random delay between 0.5-2 seconds for Codex containers to prevent resource conflicts
            stagger_delay = random.uniform(0.5, 2.0)
            logger.info(f"🕐 Adding {stagger_delay:.1f}s staggered start delay for Codex task {task_id}")
            time.sleep(stagger_delay)
            
            # Add file-based locking for Codex to prevent parallel execution conflicts
            lock_file_path = '/tmp/codex_execution_lock'
            try:
                logger.info(f"🔒 Acquiring Codex execution lock for task {task_id}")
                with open(lock_file_path, 'w') as lock_file:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.info(f"✅ Codex execution lock acquired for task {task_id}")
                    # Continue with container creation while holding the lock
            except (IOError, OSError) as e:
                logger.warning(f"⚠️  Could not acquire Codex execution lock for task {task_id}: {e}")
                # Add additional delay if lock fails
                additional_delay = random.uniform(1.0, 3.0)
                logger.info(f"🕐 Adding additional {additional_delay:.1f}s delay due to lock conflict")
                time.sleep(additional_delay)
        
        # Load Claude credentials from user preferences in Supabase
        credentials_content = ""
        escaped_credentials = ""
        if model_cli == 'claude':
            logger.info(f"🔍 Looking for Claude credentials in user preferences for task {task_id}")
            
            # Check if user has Claude credentials in their preferences
            claude_config = user_preferences.get('claudeCode', {})
            credentials_json = claude_config.get('credentials') if claude_config else None
            
            # Check if credentials is meaningful (not empty object, null, undefined, or empty string)
            has_meaningful_credentials = (
                credentials_json is not None and 
                credentials_json != {} and 
                credentials_json != "" and
                (isinstance(credentials_json, dict) and len(credentials_json) > 0)
            )
            
            if has_meaningful_credentials:
                try:
                    # Convert JSON object to string for writing to container
                    credentials_content = json.dumps(credentials_json)
                    logger.info(f"📋 Successfully loaded Claude credentials from user preferences and stringified ({len(credentials_content)} characters) for task {task_id}")
                    # Escape credentials content for shell
                    escaped_credentials = credentials_content.replace("'", "'\"'\"'").replace('\n', '\\n')
                    logger.info(f"📋 Credentials content escaped for shell injection")
                except Exception as e:
                    logger.error(f"❌ Failed to process Claude credentials from user preferences: {e}")
                    credentials_content = ""
                    escaped_credentials = ""
            else:
                logger.info(f"ℹ️  No meaningful Claude credentials found in user preferences for task {task_id} - skipping credentials setup (credentials: {credentials_json})")
        
        # Create the command to run in container by inlining the external script
        script_path = os.path.join(os.path.dirname(__file__), 'container_script.sh')
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                container_script_source = f.read()
        except Exception as e:
            raise Exception(f"Failed to read container script at {script_path}: {e}")

        # Base64-encode dynamic content to avoid quoting/escaping issues
        prompt_b64 = base64.b64encode(prompt.encode('utf-8')).decode('ascii') if prompt else ''
        credentials_b64 = base64.b64encode(credentials_content.encode('utf-8')).decode('ascii') if credentials_content else ''

        # Provide environment variables consumed by the script
        env_vars.update({
            'REPO_URL': task['repo_url'],
            'TARGET_BRANCH': task['target_branch'],
            'GIT_AUTH_TOKEN': github_token,
            'MODEL_CLI': model_cli,
            'PROMPT_B64': prompt_b64,
            'CLAUDE_CREDENTIALS_B64': credentials_b64
        })

        # Create container command that writes the script and executes it
        container_command = f"""
set -e
SCRIPT_PATH=/tmp/container_script.sh
cat > $SCRIPT_PATH <<'SCRIPT_EOF'
{container_script_source}
SCRIPT_EOF
chmod +x $SCRIPT_PATH
bash $SCRIPT_PATH
"""
        
        # Run container with unified AI Code tools (supports both Claude and Codex)
        logger.info(f"🐳 Creating Docker container for task {task_id} using {container_image} (model: {model_name})")
        
        # Configure Docker security options for Codex compatibility
        container_kwargs = {
            'image': container_image,
            'command': ['bash', '-c', container_command],
            'environment': env_vars,
            'detach': True,
            'remove': False,  # Don't auto-remove so we can get logs
            'working_dir': '/workspace',
            'network_mode': 'bridge',  # Ensure proper networking
            'tty': False,  # Default: no TTY (override for Codex)
            'stdin_open': False,  # Default: stdin closed (override for Codex)
            'name': f'ai-code-task-{task_id}-{int(time.time())}-{uuid.uuid4().hex[:8]}',  # Highly unique container name with UUID
            'mem_limit': '2g',  # Limit memory usage to prevent resource conflicts
            'cpu_shares': 1024,  # Standard CPU allocation
            'ulimits': [docker.types.Ulimit(name='nofile', soft=1024, hard=2048)]  # File descriptor limits
        }
        
        # Add essential Docker configuration for Codex compatibility
        if model_cli == 'codex':
            logger.warning(f"⚠️  Running Codex with enhanced Docker privileges to bypass seccomp/landlock restrictions")
            container_kwargs.update({
                # Essential security options for Codex compatibility
                'security_opt': [
                    'seccomp=unconfined',      # Disable seccomp to prevent syscall filtering conflicts
                    'apparmor=unconfined',     # Disable AppArmor MAC controls
                    'no-new-privileges=false'  # Allow privilege escalation needed by Codex
                ],
                'cap_add': ['ALL'],            # Grant all Linux capabilities
                'privileged': True,            # Run in fully privileged mode
                'pid_mode': 'host'            # Share host PID namespace
            })
            # Не выделяем TTY для Codex, чтобы сохранить полностью неинтерактивный режим
            container_kwargs['tty'] = False
            container_kwargs['stdin_open'] = False
        
        # Retry container creation with enhanced conflict handling
        container = None
        max_retries = 5  # Increased retries for better reliability
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Container creation attempt {attempt + 1}/{max_retries}")
                container = docker_client.containers.run(**container_kwargs)
                logger.info(f"✅ Container created successfully: {container.id[:12]} (name: {container_kwargs['name']})")
                break
            except docker.errors.APIError as e:
                error_msg = str(e)
                if "Conflict" in error_msg and "already in use" in error_msg:
                    # Handle container name conflicts by generating a new unique name
                    logger.warning(f"🔄 Container name conflict on attempt {attempt + 1}, generating new name...")
                    new_name = f'ai-code-task-{task_id}-{int(time.time())}-{uuid.uuid4().hex[:8]}'
                    container_kwargs['name'] = new_name
                    logger.info(f"🆔 New container name: {new_name}")
                    # Try to clean up any conflicting containers
                    cleanup_orphaned_containers()
                else:
                    logger.warning(f"⚠️  Docker API error on attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        raise Exception(f"Failed to create container after {max_retries} attempts: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.error(f"❌ Unexpected error creating container on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # Update task with container ID (v2 function)
        DatabaseOperations.update_task(task_id, user_id, {'container_id': container.id})
        
        logger.info(f"⏳ Waiting for container to complete (timeout: 300s)...")
        
        # Wait for container to finish - should exit naturally when script completes
        try:
            logger.info(f"🔄 Waiting for container script to complete naturally...")
            
            # Check initial container state
            container.reload()
            logger.info(f"🔍 Container initial state: {container.status}")
            
            # Use standard wait - container should exit when bash script finishes
            logger.info(f"🔄 Calling container.wait() - container should exit when script completes...")
            result = container.wait(timeout=300)  # 5 minute timeout
            logger.info(f"🎯 Container exited naturally! Exit code: {result['StatusCode']}")
            
            # Verify final container state
            container.reload()
            logger.info(f"🔍 Final container state: {container.status}")
            
            # Get logs before any cleanup operations
            logger.info(f"📜 Retrieving container logs...")
            try:
                logs = container.logs().decode('utf-8')
                logger.info(f"📝 Retrieved {len(logs)} characters of logs")
                logger.info(f"🔍 First 200 chars of logs: {logs[:200]}...")
                # Persist logs for this task
                write_task_logs(task_id, model_cli, logs)
            except Exception as log_error:
                logger.warning(f"❌ Failed to get container logs: {log_error}")
                logs = f"Failed to retrieve logs: {log_error}"
                # Persist at least the error info
                write_task_logs(task_id, model_cli, logs)
            
            # Clean up container after getting logs
            try:
                container.reload()  # Refresh container state
                container.remove()
                logger.info(f"🧹 Successfully removed container {container.id[:12]}")
            except docker.errors.NotFound:
                logger.info(f"🧹 Container {container.id[:12]} already removed")
            except Exception as cleanup_error:
                logger.warning(f"⚠️  Failed to remove container {container.id[:12]}: {cleanup_error}")
                # Try force removal as fallback
                try:
                    container.remove(force=True)
                    logger.info(f"🧹 Force removed container {container.id[:12]}")
                except docker.errors.NotFound:
                    logger.info(f"🧹 Container {container.id[:12]} already removed")
                except Exception as force_cleanup_error:
                    logger.error(f"❌ Failed to force remove container {container.id[:12]}: {force_cleanup_error}")
                
        except Exception as e:
            logger.error(f"⏰ Container timeout or error: {str(e)}")
            logger.error(f"🔄 Updating task status to FAILED due to timeout/error...")
            
            DatabaseOperations.update_task(task_id, user_id, {
                'status': 'failed',
                'error': f"Container execution timeout or error: {str(e)}"
            })
            
            # Try to get logs even on error
            try:
                logs = container.logs().decode('utf-8')
                write_task_logs(task_id, model_cli, logs)
            except Exception as log_error:
                logs = f"Container failed and logs unavailable: {log_error}"
                write_task_logs(task_id, model_cli, logs)
            
            # Try to clean up container on error
            try:
                container.reload()  # Refresh container state
                container.remove(force=True)
                logger.info(f"Cleaned up failed container {container.id}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove failed container {container.id}: {cleanup_error}")
            return
        
        if result['StatusCode'] == 0:
            logger.info(f"✅ Container exited successfully (code 0) - parsing results...")
            # Parse output to extract commit hash, diff, and patch
            lines = logs.split('\n')
            commit_hash = None
            git_diff = []
            git_patch = []
            changed_files = []
            file_changes = []
            capturing_diff = False
            capturing_patch = False
            capturing_files = False
            capturing_file_changes = False
            capturing_before = False
            capturing_after = False
            current_file = None
            current_before = []
            current_after = []
            
            for line in lines:
                if line.startswith('COMMIT_HASH='):
                    commit_hash = line.split('=', 1)[1]
                    logger.info(f"🔑 Found commit hash: {commit_hash}")
                elif line == '=== PATCH START ===':
                    capturing_patch = True
                    logger.info(f"📦 Starting to capture git patch...")
                elif line == '=== PATCH END ===':
                    capturing_patch = False
                    logger.info(f"📦 Finished capturing git patch ({len(git_patch)} lines)")
                elif line == '=== GIT DIFF START ===':
                    capturing_diff = True
                    logger.info(f"📊 Starting to capture git diff...")
                elif line == '=== GIT DIFF END ===':
                    capturing_diff = False
                    logger.info(f"📊 Finished capturing git diff ({len(git_diff)} lines)")
                elif line == '=== CHANGED FILES START ===':
                    capturing_files = True
                    logger.info(f"📁 Starting to capture changed files...")
                elif line == '=== CHANGED FILES END ===':
                    capturing_files = False
                    logger.info(f"📁 Finished capturing changed files ({len(changed_files)} files)")
                elif line == '=== FILE CHANGES START ===':
                    capturing_file_changes = True
                    logger.info(f"🔄 Starting to capture file changes...")
                elif line == '=== FILE CHANGES END ===':
                    capturing_file_changes = False
                    # Add the last file if we were processing one
                    if current_file:
                        file_changes.append({
                            'filename': current_file,
                            'before': '\n'.join(current_before),
                            'after': '\n'.join(current_after)
                        })
                    logger.info(f"🔄 Finished capturing file changes ({len(file_changes)} files)")
                elif capturing_file_changes:
                    if line.startswith('FILE: '):
                        # Save previous file data if exists
                        if current_file:
                            file_changes.append({
                                'filename': current_file,
                                'before': '\n'.join(current_before),
                                'after': '\n'.join(current_after)
                            })
                        # Start new file
                        current_file = line.split('FILE: ', 1)[1]
                        current_before = []
                        current_after = []
                        capturing_before = False
                        capturing_after = False
                    elif line == '=== BEFORE START ===':
                        capturing_before = True
                        capturing_after = False
                    elif line == '=== BEFORE END ===':
                        capturing_before = False
                    elif line == '=== AFTER START ===':
                        capturing_after = True
                        capturing_before = False
                    elif line == '=== AFTER END ===':
                        capturing_after = False
                    elif line == '=== FILE END ===':
                        # File processing complete
                        pass
                    elif capturing_before:
                        current_before.append(line)
                    elif capturing_after:
                        current_after.append(line)
                elif capturing_patch:
                    git_patch.append(line)
                elif capturing_diff:
                    git_diff.append(line)
                elif capturing_files:
                    # Добавляем только непустые строки и игнорируем служебное сообщение скрипта
                    stripped = line.strip()
                    if stripped and stripped != 'No files were changed':
                        changed_files.append(stripped)
            
            # Нормализуем служебное сообщение "No changes were made", чтобы оно не считалось дифом
            git_patch_content = '\n'.join(git_patch).strip()
            git_diff_content = '\n'.join(git_diff).strip()
            if git_patch_content == 'No changes were made':
                git_patch_content = ''
            if git_diff_content == 'No changes were made':
                git_diff_content = ''

            logger.info(f"🔄 Updating task status to COMPLETED...")

            # Update task in database
            DatabaseOperations.update_task(task_id, user_id, {
                'status': 'completed',
                'commit_hash': commit_hash,
                'git_diff': git_diff_content,
                'git_patch': git_patch_content,
                'changed_files': changed_files,
                'execution_metadata': {
                    'file_changes': file_changes,
                    'completed_at': datetime.now().isoformat()
                }
            })
            
            logger.info(f"🎉 {model_name} Task {task_id} completed successfully! Commit: {commit_hash[:8] if commit_hash else 'N/A'}, Diff lines: {len(git_diff_content.splitlines())}")
            
        else:
            logger.error(f"❌ Container exited with error code {result['StatusCode']}")
            DatabaseOperations.update_task(task_id, user_id, {
                'status': 'failed',
                'error': f"Container exited with code {result['StatusCode']}: {logs}"
            })
            logger.error(f"💥 {model_name} Task {task_id} failed: {logs[:200]}...")
            
    except Exception as e:
        model_name = task.get('agent', 'claude').upper() if task else 'UNKNOWN'
        logger.error(f"💥 Unexpected exception in {model_name} task {task_id}: {str(e)}")
        
        try:
            DatabaseOperations.update_task(task_id, user_id, {
                'status': 'failed',
                'error': str(e)
            })
        except:
            logger.error(f"Failed to update task {task_id} status after exception")
        
        logger.error(f"🔄 {model_name} Task {task_id} failed with exception: {str(e)}")
