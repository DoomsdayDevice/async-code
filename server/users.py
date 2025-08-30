from flask import Blueprint, jsonify, request
import logging
from database import DatabaseOperations

logger = logging.getLogger(__name__)

users_bp = Blueprint('users', __name__)

@users_bp.route('/users/me', methods=['GET'])
def get_me():
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        user = DatabaseOperations.get_user_by_id(user_id)
        return jsonify({'status': 'success', 'user': user})
    except Exception as e:
        logger.error(f"Error fetching current user: {str(e)}")
        return jsonify({'error': str(e)}), 500

@users_bp.route('/users/me', methods=['PUT'])
def update_me():
    try:
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        data = request.get_json() or {}
        # Allow updating profile fields and preferences
        updated = DatabaseOperations.update_user_profile(user_id, data)
        return jsonify({'status': 'success', 'user': updated})
    except Exception as e:
        logger.error(f"Error updating current user: {str(e)}")
        return jsonify({'error': str(e)}), 500


