from flask import Blueprint, jsonify, request
import uuid
import time
import threading
import logging
from models import TaskStatus
from database import DatabaseOperations
from utils import run_ai_code_task_v2  # Updated function name
from github import Github
import gitlab
import base64

logger = logging.getLogger(__name__)

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/start-task', methods=['POST'])
def start_task():
    """Start a new Claude Code automation task"""
    try:
        data = request.get_json()
        user_id = request.headers.get('X-User-ID')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
            
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        prompt = data.get('prompt')
        repo_url = data.get('repo_url')
        branch = data.get('branch', 'main')
        github_token = data.get('github_token')
        gitlab_token = data.get('gitlab_token')
        model = data.get('model', 'claude')  # Default to claude for backward compatibility
        project_id = data.get('project_id')  # Optional project association
        
        if not all([prompt, repo_url]):
            return jsonify({'error': 'prompt and repo_url are required'}), 400
        
        # Determine provider and required token
        is_gitlab = 'gitlab.com' in (repo_url or '')
        if is_gitlab:
            if not gitlab_token and not github_token:
                return jsonify({'error': 'gitlab_token is required for GitLab repositories'}), 400
            effective_token = gitlab_token or github_token
        else:
            if not github_token:
                return jsonify({'error': 'github_token is required for GitHub repositories'}), 400
            effective_token = github_token
        
        # Validate model selection
        if model not in ['claude', 'codex']:
            return jsonify({'error': 'model must be either "claude" or "codex"'}), 400
        
        # Create initial chat message
        chat_messages = [{
            'role': 'user',
            'content': prompt.strip(),
            'timestamp': time.time()
        }]
        
        # Create task in database
        task = DatabaseOperations.create_task(
            user_id=user_id,
            project_id=project_id,
            repo_url=repo_url,
            target_branch=branch,
            agent=model,
            chat_messages=chat_messages
        )
        
        if not task:
            return jsonify({'error': 'Failed to create task'}), 500
        
        # Start task in background thread
        thread = threading.Thread(target=run_ai_code_task_v2, args=(task['id'], user_id, effective_token))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'success',
            'task_id': task['id'],
            'message': 'Task started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting task: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/retry-task/<int:task_id>', methods=['POST'])
def retry_task(task_id):
    """Повторный запуск задачи, если она завершилась с ошибкой"""
    try:
        data = request.get_json() or {}
        user_id = request.headers.get('X-User-ID')

        if not user_id:
            return jsonify({'error': 'User ID required'}), 400

        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        if task.get('status') != TaskStatus.FAILED:
            return jsonify({'error': 'Task is not in failed state'}), 400

        # Определяем провайдера и токен
        github_token = data.get('github_token')
        gitlab_token = data.get('gitlab_token')
        repo_url = task.get('repo_url') or ''
        is_gitlab = 'gitlab.com' in repo_url

        if is_gitlab:
            if not gitlab_token and not github_token:
                return jsonify({'error': 'gitlab_token is required for GitLab repositories'}), 400
            effective_token = gitlab_token or github_token
        else:
            if not github_token:
                return jsonify({'error': 'github_token is required for GitHub repositories'}), 400
            effective_token = github_token

        # Сбрасываем поля и переводим задачу в pending
        reset_updates = {
            'status': TaskStatus.PENDING,
            'error': None,
            'commit_hash': None,
            'git_diff': None,
            'git_patch': None,
            'changed_files': [],
            'pr_branch': None,
            'pr_number': None,
            'pr_url': None,
            'container_id': None,
            'started_at': None,
            'completed_at': None,
        }
        DatabaseOperations.update_task(task_id, user_id, reset_updates)

        # Запускаем задачу в фоне
        thread = threading.Thread(target=run_ai_code_task_v2, args=(task_id, user_id, effective_token))
        thread.daemon = True
        thread.start()

        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': 'Task retry started successfully'
        })

    except Exception as e:
        logger.error(f"Error retrying task {task_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/task-status/<int:task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get the status of a specific task"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            logger.warning(f"🔍 Frontend polling for unknown task: {task_id}")
            return jsonify({'error': 'Task not found'}), 404
        
        logger.info(f"📊 Frontend polling task {task_id}: status={task['status']}")
        
        # Get the latest user prompt from chat messages
        prompt = ""
        if task.get('chat_messages'):
            for msg in task['chat_messages']:
                if msg.get('role') == 'user':
                    prompt = msg.get('content', '')
                    break
        
        return jsonify({
            'status': 'success',
            'task': {
                'id': task['id'],
                'status': task['status'],
                'prompt': prompt,
                'repo_url': task['repo_url'],
                'branch': task['target_branch'],
                'model': task.get('agent', 'claude'),
                'commit_hash': task.get('commit_hash'),
                'changed_files': task.get('changed_files', []),
                'error': task.get('error'),
                'created_at': task['created_at'],
                'project_id': task.get('project_id')
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching task status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/tasks', methods=['GET'])
def list_all_tasks():
    """List all tasks for the authenticated user"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        project_id = request.args.get('project_id', type=int)
        tasks = DatabaseOperations.get_user_tasks(user_id, project_id)
        
        # Format tasks for response
        formatted_tasks = {}
        for task in tasks:
            # Get the latest user prompt from chat messages
            prompt = ""
            if task.get('chat_messages'):
                for msg in task['chat_messages']:
                    if msg.get('role') == 'user':
                        prompt = msg.get('content', '')
                        break
            
            formatted_tasks[str(task['id'])] = {
                'id': task['id'],
                'status': task['status'],
                'created_at': task['created_at'],
                'prompt': prompt[:50] + '...' if len(prompt) > 50 else prompt,
                'has_patch': bool(task.get('git_patch')),
                'project_id': task.get('project_id'),
                'repo_url': task.get('repo_url'),
                'agent': task.get('agent', 'claude'),
                'chat_messages': task.get('chat_messages', [])
            }
        
        return jsonify({
            'status': 'success',
            'tasks': formatted_tasks,
            'total_tasks': len(tasks)
        })
        
    except Exception as e:
        logger.error(f"Error listing tasks: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/tasks/<int:task_id>', methods=['GET'])
def get_task_details(task_id):
    """Get detailed information about a specific task"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify({
            'status': 'success',
            'task': task
        })
        
    except Exception as e:
        logger.error(f"Error fetching task details: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/tasks/<int:task_id>/chat', methods=['POST'])
def add_chat_message(task_id):
    """Add a chat message to a task"""
    try:
        data = request.get_json()
        user_id = request.headers.get('X-User-ID')
        
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        content = data.get('content')
        role = data.get('role', 'user')
        
        if not content:
            return jsonify({'error': 'content is required'}), 400
        
        if role not in ['user', 'assistant']:
            return jsonify({'error': 'role must be either "user" or "assistant"'}), 400
        
        task = DatabaseOperations.add_chat_message(task_id, user_id, role, content)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify({
            'status': 'success',
            'task': task
        })
        
    except Exception as e:
        logger.error(f"Error adding chat message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/git-diff/<int:task_id>', methods=['GET'])
def get_git_diff(task_id):
    """Get git diff for a task (legacy endpoint for compatibility)"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify({
            'status': 'success',
            'git_diff': task.get('git_diff', ''),
            'task_id': task_id
        })
        
    except Exception as e:
        logger.error(f"Error fetching git diff: {str(e)}")
        return jsonify({'error': str(e)}), 500

@tasks_bp.route('/validate-token', methods=['POST'])
def validate_github_token():
    """Validate GitHub or GitLab token and check permissions"""
    try:
        data = request.get_json()
        github_token = data.get('github_token')
        gitlab_token = data.get('gitlab_token')
        repo_url = data.get('repo_url', '')

        is_gitlab = 'gitlab.com' in (repo_url or '')

        if is_gitlab:
            token = gitlab_token or github_token
            if not token:
                return jsonify({'error': 'gitlab_token is required for GitLab repositories'}), 400
            # GitLab client
            gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
            gl.auth()
            user = gl.user
            logger.info(f"🔐 GitLab token belongs to user: {user['username']}")

            repo_info = {}
            if repo_url:
                try:
                    project_path = repo_url.replace('https://gitlab.com/', '').replace('.git', '').strip('/')
                    project = gl.projects.get(project_path)

                    permissions = {
                        'read': True,
                        'write': False,
                        'admin': False
                    }

                    # Try reading branches
                    try:
                        branches = project.branches.list(all=True)
                        permissions['read_branches'] = True
                        logger.info(f"✅ GitLab: Can read branches ({len(branches)} found)")
                        test_branch_name = f"test-permissions-{int(time.time())}"
                        try:
                            project.branches.create({'branch': test_branch_name, 'ref': project.default_branch})
                            permissions['create_branches'] = True
                            logger.info("✅ GitLab: Can create branches - test successful")
                            # cleanup
                            project.branches.delete(test_branch_name)
                        except Exception as branch_error:
                            permissions['create_branches'] = False
                            logger.warning(f"❌ GitLab: Cannot create branches: {branch_error}")
                    except Exception as e:
                        permissions['read_branches'] = False
                        permissions['create_branches'] = False
                        logger.warning(f"❌ GitLab: Cannot read branches: {e}")

                    # Infer write/admin from access level if available
                    try:
                        perms = project.attributes.get('permissions') or {}
                        level = 0
                        if perms.get('project_access'):
                            level = max(level, perms['project_access'].get('access_level') or 0)
                        if perms.get('group_access'):
                            level = max(level, perms['group_access'].get('access_level') or 0)
                        permissions['write'] = level >= 30  # developer+
                        permissions['admin'] = level >= 40  # maintainer+
                        logger.info(f"📋 GitLab access level: {level}")
                    except Exception as e:
                        logger.warning(f"⚠️ GitLab: Could not infer access level: {e}")

                    repo_info = {
                        'name': project.attributes.get('path_with_namespace'),
                        'private': not project.attributes.get('visibility') == 'public',
                        'permissions': permissions,
                        'default_branch': project.default_branch
                    }
                except Exception as repo_error:
                    return jsonify({'error': f'Cannot access repository: {str(repo_error)}', 'user': user['username']}), 403

            return jsonify({
                'status': 'success',
                'user': user['username'],
                'repo': repo_info,
                'message': 'Token is valid and has repository access'
            })
        else:
            if not github_token:
                return jsonify({'error': 'github_token is required for GitHub repositories'}), 400

            # Create GitHub client
            g = Github(github_token)
            # Test basic authentication
            user = g.get_user()
            logger.info(f"🔐 Token belongs to user: {user.login}")
            # Test token scopes
            rate_limit = g.get_rate_limit()
            logger.info(f"📊 Rate limit info: {rate_limit.core.remaining}/{rate_limit.core.limit}")
            # If repo URL provided, test repo access
            repo_info = {}
            if repo_url:
                try:
                    repo_parts = repo_url.replace('https://github.com/', '').replace('.git', '')
                    repo = g.get_repo(repo_parts)

                    permissions = {
                        'read': True,
                        'write': False,
                        'admin': False
                    }
                    try:
                        branches = list(repo.get_branches())
                        permissions['read_branches'] = True
                        logger.info(f"✅ Can read branches ({len(branches)} found)")
                        test_branch_name = f"test-permissions-{int(time.time())}"
                        try:
                            main_branch = repo.get_branch(repo.default_branch)
                            test_ref = repo.create_git_ref(f"refs/heads/{test_branch_name}", main_branch.commit.sha)
                            permissions['create_branches'] = True
                            logger.info(f"✅ Can create branches - test successful")
                            test_ref.delete()
                        except Exception as branch_error:
                            permissions['create_branches'] = False
                            logger.warning(f"❌ Cannot create branches: {branch_error}")
                    except Exception as e:
                        permissions['read_branches'] = False
                        permissions['create_branches'] = False
                        logger.warning(f"❌ Cannot read branches: {e}")
                    try:
                        repo_perms = repo.permissions
                        permissions['write'] = repo_perms.push
                        permissions['admin'] = repo_perms.admin
                        logger.info(f"📋 Repo permissions: push={repo_perms.push}, admin={repo_perms.admin}")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not check repo permissions: {e}")
                    repo_info = {
                        'name': repo.full_name,
                        'private': repo.private,
                        'permissions': permissions,
                        'default_branch': repo.default_branch
                    }
                except Exception as repo_error:
                    return jsonify({'error': f'Cannot access repository: {str(repo_error)}', 'user': user.login}), 403

            return jsonify({
                'status': 'success',
                'user': user.login,
                'repo': repo_info,
                'message': 'Token is valid and has repository access'
            })
        
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return jsonify({'error': f'Token validation failed: {str(e)}'}), 401

@tasks_bp.route('/create-pr/<int:task_id>', methods=['POST'])
def create_pull_request(task_id):
    """Create a pull request (GitHub) or merge request (GitLab) by applying the saved patch"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        logger.info(f"🔍 PR creation requested for task: {task_id}")
        
        task = DatabaseOperations.get_task_by_id(task_id, user_id)
        if not task:
            logger.error(f"❌ Task {task_id} not found")
            return jsonify({'error': 'Task not found'}), 404
        
        if task['status'] != 'completed':
            return jsonify({'error': 'Task not completed yet'}), 400
            
        if not task.get('git_patch'):
            return jsonify({'error': 'No patch data available for this task'}), 400
        
        data = request.get_json() or {}
        
        # Get prompt from chat messages
        prompt = ""
        if task.get('chat_messages'):
            for msg in task['chat_messages']:
                if msg.get('role') == 'user':
                    prompt = msg.get('content', '')
                    break
        
        pr_title = data.get('title', f"Claude Code: {prompt[:50]}...")
        pr_body = data.get('body', f"Automated changes generated by Claude Code.\n\nPrompt: {prompt}\n\nChanged files:\n" + '\n'.join(f"- {f}" for f in task.get('changed_files', [])))
        github_token = data.get('github_token')
        gitlab_token = data.get('gitlab_token')

        is_gitlab = 'gitlab.com' in (task.get('repo_url') or '')

        logger.info(f"🚀 Creating PR/MR for task {task_id}")

        if is_gitlab:
            token = gitlab_token or github_token
            if not token:
                return jsonify({'error': 'gitlab_token is required for GitLab repositories'}), 400

            project_path = task['repo_url'].replace('https://gitlab.com/', '').replace('.git', '').strip('/')
            gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
            gl.auth()
            project = gl.projects.get(project_path)

            base_branch = task['target_branch']
            pr_branch = f"claude-code-{task_id}"

            logger.info(f"📋 Creating MR branch '{pr_branch}' from base '{base_branch}' (GitLab)")
            try:
                # Delete if exists
                try:
                    project.branches.delete(pr_branch)
                except Exception:
                    pass
                project.branches.create({'branch': pr_branch, 'ref': base_branch})
            except Exception as branch_error:
                return jsonify({'error': f"Failed to create branch '{pr_branch}': {branch_error}"}), 403

            patch_content = task['git_patch']
            files_to_update = parse_patch_files_for_gitlab(patch_content, project, pr_branch)
            if not files_to_update:
                return jsonify({'error': 'Failed to apply patch - no file changes extracted'}), 500

            # Create a single commit with actions
            actions = []
            for file_path, new_content in files_to_update.items():
                # Determine action: create or update
                action = 'update'
                try:
                    project.files.get(file_path=file_path, ref=pr_branch)
                    action = 'update'
                except Exception:
                    action = 'create'
                actions.append({
                    'action': action,
                    'file_path': file_path,
                    'content': new_content,
                })

            commit_message = pr_title
            project.commits.create({
                'branch': pr_branch,
                'commit_message': commit_message,
                'actions': actions,
            })

            mr = project.mergerequests.create({
                'source_branch': pr_branch,
                'target_branch': base_branch,
                'title': pr_title,
                'description': pr_body,
            })

            DatabaseOperations.update_task(task_id, user_id, {
                'pr_branch': pr_branch,
                'pr_number': mr.attributes.get('iid'),
                'pr_url': mr.web_url,
            })

            logger.info(f"🎉 Created MR !{mr.attributes.get('iid')}: {mr.web_url}")
            return jsonify({
                'status': 'success',
                'pr_url': mr.web_url,
                'pr_number': mr.attributes.get('iid'),
                'branch': pr_branch,
                'files_updated': len(files_to_update)
            })
        else:
            if not github_token:
                return jsonify({'error': 'github_token is required for GitHub repositories'}), 400

            # Extract repo info from URL
            repo_parts = task['repo_url'].replace('https://github.com/', '').replace('.git', '')
            # Create GitHub client
            g = Github(github_token)
            repo = g.get_repo(repo_parts)
            base_branch = task['target_branch']
            pr_branch = f"claude-code-{task_id}"
            logger.info(f"📋 Creating PR branch '{pr_branch}' from base '{base_branch}'")
            base_branch_obj = repo.get_branch(base_branch)
            base_sha = base_branch_obj.commit.sha
            try:
                try:
                    existing_branch = repo.get_branch(pr_branch)
                    logger.warning(f"⚠️ Branch '{pr_branch}' already exists, deleting it first...")
                    repo.get_git_ref(f"heads/{pr_branch}").delete()
                except:
                    pass
                repo.create_git_ref(f"refs/heads/{pr_branch}", base_sha)
            except Exception as branch_error:
                logger.error(f"❌ Failed to create branch '{pr_branch}': {str(branch_error)}")
                error_msg = str(branch_error).lower()
                if "resource not accessible" in error_msg:
                    detailed_error = (
                        f"GitHub token lacks permission to create branches. "
                        f"Please ensure your token has 'repo' scope (not just 'public_repo'). "
                        f"Error: {branch_error}"
                    )
                elif "already exists" in error_msg:
                    detailed_error = f"Branch '{pr_branch}' already exists. Please try again or use a different task."
                else:
                    detailed_error = f"Failed to create branch '{pr_branch}': {branch_error}"
                return jsonify({'error': detailed_error}), 403
            logger.info(f"✅ Created branch '{pr_branch}' from {base_sha[:8]}")
            patch_content = task['git_patch']
            files_updated = apply_patch_to_github_repo(repo, pr_branch, patch_content, task)
            if not files_updated:
                return jsonify({'error': 'Failed to apply patch - no file changes extracted'}), 500
            pr = repo.create_pull(title=pr_title, body=pr_body, head=pr_branch, base=base_branch)
            DatabaseOperations.update_task(task_id, user_id, {'pr_branch': pr_branch, 'pr_number': pr.number, 'pr_url': pr.html_url})
            logger.info(f"🎉 Created PR #{pr.number}: {pr.html_url}")
            return jsonify({'status': 'success', 'pr_url': pr.html_url, 'pr_number': pr.number, 'branch': pr_branch, 'files_updated': len(files_updated)})
        
    except Exception as e:
        logger.error(f"Error creating PR: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Legacy task migration endpoint
@tasks_bp.route('/migrate-legacy-tasks', methods=['POST'])
def migrate_legacy_tasks():
    """Migrate tasks from legacy JSON storage to Supabase"""
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        
        # This would be called manually to migrate existing tasks
        # Load legacy tasks from file if it exists
        import json
        import os
        
        legacy_file = 'tasks_backup.json'
        if not os.path.exists(legacy_file):
            return jsonify({
                'status': 'success',
                'message': 'No legacy tasks file found',
                'migrated': 0
            })
        
        with open(legacy_file, 'r') as f:
            legacy_tasks = json.load(f)
        
        migrated_count = 0
        for task_id, task_data in legacy_tasks.items():
            try:
                # Check if already migrated
                existing = DatabaseOperations.get_task_by_legacy_id(task_id)
                if existing:
                    continue
                
                # Migrate task
                DatabaseOperations.migrate_legacy_task(task_data, user_id)
                migrated_count += 1
            except Exception as e:
                logger.warning(f"Failed to migrate task {task_id}: {e}")
        
        return jsonify({
            'status': 'success',
            'message': f'Migrated {migrated_count} tasks',
            'migrated': migrated_count
        })
        
    except Exception as e:
        logger.error(f"Error migrating legacy tasks: {str(e)}")
        return jsonify({'error': str(e)}), 500


def apply_patch_to_github_repo(repo, branch, patch_content, task):
    """Apply a git patch to a GitHub repository using the GitHub API"""
    try:
        logger.info(f"🔧 Parsing patch content...")
        
        # Parse git patch format to extract file changes
        files_to_update = {}
        current_file = None
        new_content_lines = []
        
        # This is a simplified patch parser - for production you might want a more robust one
        lines = patch_content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Look for file headers in patch format
            if line.startswith('--- a/') or line.startswith('--- /dev/null'):
                # Next line should be +++ b/filename
                if i + 1 < len(lines) and lines[i + 1].startswith('+++ b/'):
                    current_file = lines[i + 1][6:]  # Remove '+++ b/'
                    logger.info(f"📄 Found file change: {current_file}")
                    
                    # Get the original file content if it exists
                    try:
                        file_obj = repo.get_contents(current_file, ref=branch)
                        original_content = file_obj.decoded_content.decode('utf-8')
                        logger.info(f"📥 Got original content for {current_file}")
                    except:
                        original_content = ""  # New file
                        logger.info(f"📝 New file: {current_file}")
                    
                    # For simplicity, we'll reconstruct the file from the diff
                    # Skip to the actual diff content (after @@)
                    j = i + 2
                    while j < len(lines) and not lines[j].startswith('@@'):
                        j += 1
                    
                    if j < len(lines):
                        # Apply the diff changes
                        new_content = apply_diff_to_content(original_content, lines[j:], current_file)
                        if new_content is not None:
                            files_to_update[current_file] = new_content
                            logger.info(f"✅ Prepared update for {current_file}")
                    
                    i = j
            i += 1
        
        # Create a single commit with all file changes using GitHub's Tree API
        if not files_to_update:
            logger.warning("⚠️ No files to update")
            return []
        
        updated_files = []
        commit_message = f"Claude Code: {task.get('prompt', 'Automated changes')[:100]}"
        
        # Get prompt from chat messages if available
        if task.get('chat_messages'):
            for msg in task['chat_messages']:
                if msg.get('role') == 'user':
                    commit_message = f"Claude Code: {msg.get('content', '')[:100]}"
                    break
        
        try:
            # Get the current commit to build upon
            current_commit = repo.get_commit(branch)
            
            # Create tree elements for all changed files
            tree_elements = []
            
            for file_path, new_content in files_to_update.items():
                # Create a blob for the file content
                blob = repo.create_git_blob(new_content, "utf-8")
                
                # Add to tree elements
                tree_elements.append({
                    "path": file_path,
                    "mode": "100644",  # Normal file mode
                    "type": "blob",
                    "sha": blob.sha
                })
                
                logger.info(f"📝 Prepared blob for {file_path}")
                updated_files.append(file_path)
            
            # Create a new tree with all the changes
            new_tree = repo.create_git_tree(tree_elements, base_tree=current_commit.commit.tree)
            
            # Create a single commit with all the changes
            new_commit = repo.create_git_commit(
                message=commit_message,
                tree=new_tree,
                parents=[current_commit.commit]
            )
            
            # Update the branch to point to the new commit
            ref = repo.get_git_ref(f"heads/{branch}")
            ref.edit(new_commit.sha)
            
            logger.info(f"✅ Created single commit {new_commit.sha[:8]} with {len(updated_files)} files")
            
        except Exception as commit_error:
            logger.error(f"❌ Failed to create single commit: {commit_error}")
            # Fallback to individual file updates if tree method fails
            logger.info("🔄 Falling back to individual file updates...")
            
            for file_path, new_content in files_to_update.items():
                try:
                    # Check if file exists
                    try:
                        file_obj = repo.get_contents(file_path, ref=branch)
                        # Update existing file
                        repo.update_file(
                            path=file_path,
                            message=commit_message,
                            content=new_content,
                            sha=file_obj.sha,
                            branch=branch
                        )
                        logger.info(f"📝 Updated existing file: {file_path}")
                    except:
                        # Create new file
                        repo.create_file(
                            path=file_path,
                            message=commit_message,
                            content=new_content,
                            branch=branch
                        )
                        logger.info(f"🆕 Created new file: {file_path}")
                    
                    updated_files.append(file_path)
                    
                except Exception as file_error:
                    logger.error(f"❌ Failed to update {file_path}: {file_error}")
        
        return updated_files
        
    except Exception as e:
        logger.error(f"💥 Error applying patch: {str(e)}")
        return []


def apply_diff_to_content(original_content, diff_lines, filename):
    """Apply diff changes to original content - simplified implementation"""
    try:
        # For now, let's use a simple approach: reconstruct from + lines
        # This is not a complete diff parser, but works for basic cases
        
        result_lines = []
        original_lines = original_content.split('\n') if original_content else []
        
        # Find the actual diff content starting from @@ line
        diff_start = 0
        for i, line in enumerate(diff_lines):
            if line.startswith('@@'):
                diff_start = i + 1
                break
        
        # Simple reconstruction: take context and + lines, skip - lines
        for line in diff_lines[diff_start:]:
            if line.startswith('+++') or line.startswith('---'):
                continue
            elif line.startswith('+') and not line.startswith('+++'):
                result_lines.append(line[1:])  # Remove the +
            elif line.startswith(' '):  # Context line
                result_lines.append(line[1:])  # Remove the space
            elif line.startswith('-'):
                continue  # Skip removed lines
            elif line.strip() == '':
                continue  # Skip empty lines in diff
            else:
                # Check if we've reached the next file
                if line.startswith('diff --git') or line.startswith('--- a/'):
                    break
        
        # If we got content, return it, otherwise fall back to using the git diff directly
        if result_lines:
            return '\n'.join(result_lines)
        else:
            # Fallback: return original content (no changes applied)
            logger.warning(f"⚠️ Could not parse diff for {filename}, keeping original")
            return original_content
            
    except Exception as e:
        logger.error(f"❌ Error applying diff to {filename}: {str(e)}")
        return None


def parse_patch_files_for_gitlab(patch_content: str, project, branch: str):
    """Extract files and new content from a git patch for use with GitLab commit actions"""
    try:
        files_to_update = {}
        lines = patch_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('--- a/') or line.startswith('--- /dev/null'):
                if i + 1 < len(lines) and lines[i + 1].startswith('+++ b/'):
                    current_file = lines[i + 1][6:]
                    # Fetch original content if exists
                    try:
                        f = project.files.get(file_path=current_file, ref=branch)
                        # python-gitlab returns base64 content in f.content
                        if hasattr(f, 'content') and f.content:
                            original_content = base64.b64decode(f.content).decode('utf-8')
                        else:
                            original_content = ""
                    except Exception:
                        original_content = ""
                    # Move to diff hunks
                    j = i + 2
                    while j < len(lines) and not lines[j].startswith('@@'):
                        j += 1
                    if j < len(lines):
                        new_content = apply_diff_to_content(original_content, lines[j:], current_file)
                        if new_content is not None:
                            files_to_update[current_file] = new_content
                    i = j
            i += 1
        return files_to_update
    except Exception as e:
        logger.error(f"💥 Error parsing patch for GitLab: {str(e)}")
        return {}