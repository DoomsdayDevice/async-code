from flask import Blueprint, jsonify, request
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from database import DatabaseOperations

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/auth/register', methods=['POST'])
def register():
    """Регистрация нового пользователя по email и паролю"""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        password = (data.get('password') or '').strip()
        full_name = (data.get('full_name') or '').strip() or None

        if not email or not password:
            return jsonify({'error': 'email and password are required'}), 400

        # Простейшая валидация email
        if '@' not in email or '.' not in email.split('@')[-1]:
            return jsonify({'error': 'invalid email format'}), 400

        # Проверка дубликатов email
        existing = DatabaseOperations.get_user_by_email(email)
        if existing:
            return jsonify({'error': 'email already registered'}), 409

        # Хешируем пароль с помощью Werkzeug (PBKDF2)
        password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

        # Создаём пользователя
        created = DatabaseOperations.create_user(email=email, full_name=full_name, password_hash=password_hash)

        return jsonify({
            'status': 'success',
            'user_id': created['id'],
            'user': {
                'id': created['id'],
                'email': created.get('email'),
                'full_name': created.get('full_name'),
            }
        }), 201
    except Exception as e:
        # Возможен конфликт БД при уникальном индексе email — возвращаем 409
        msg = str(e)
        if 'UNIQUE' in msg or 'unique' in msg:
            return jsonify({'error': 'email already registered'}), 409
        logger.error(f"Registration error: {e}")
        return jsonify({'error': 'registration failed'}), 500


@auth_bp.route('/auth/login', methods=['POST'])
def login():
    """Логин пользователя по email и паролю"""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        password = (data.get('password') or '').strip()

        if not email or not password:
            return jsonify({'error': 'email and password are required'}), 400

        user = DatabaseOperations.get_user_by_email(email)
        if not user or not user.get('password_hash'):
            return jsonify({'error': 'invalid credentials'}), 401

        if not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'invalid credentials'}), 401

        return jsonify({
            'status': 'success',
            'user_id': user['id'],
            'user': {
                'id': user['id'],
                'email': user.get('email'),
                'full_name': user.get('full_name'),
            }
        })
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'login failed'}), 500


