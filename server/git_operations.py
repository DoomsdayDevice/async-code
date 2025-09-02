from flask import Blueprint, jsonify, request
import logging
from models import TaskStatus
from database import DatabaseOperations

logger = logging.getLogger(__name__)

git_bp = Blueprint('git', __name__)

@git_bp.route('/git-diff/<int:task_id>', methods=['GET'])
def get_git_diff(task_id: int):
    """Возвращает дифф и структуры по изменённым файлам для завершённой задачи"""
    user_id = request.headers.get('X-User-ID')
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400

    task = DatabaseOperations.get_task_by_id(task_id, user_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    logger.info(f"📋 Frontend requesting git diff for task {task_id} (status: {task.get('status')})")

    if task.get('status') != TaskStatus.COMPLETED:
        logger.warning(f"⚠️ Git diff requested for incomplete task {task_id}")
        return jsonify({'error': 'Task not completed yet'}), 400

    git_diff = task.get('git_diff') or ''
    changed_files = task.get('changed_files') or []
    execution_metadata = task.get('execution_metadata') or {}
    file_changes = execution_metadata.get('file_changes') if isinstance(execution_metadata, dict) else []

    logger.info(f"📄 Returning git diff: {len(git_diff)} characters, files: {len(changed_files)}, file_changes: {len(file_changes) if isinstance(file_changes, list) else 0}")

    return jsonify({
        'status': 'success',
        'git_diff': git_diff,
        'changed_files': changed_files,
        'file_changes': file_changes,
        'commit_hash': task.get('commit_hash'),
        'task_id': task_id
    })